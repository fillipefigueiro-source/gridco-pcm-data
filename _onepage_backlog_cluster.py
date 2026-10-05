# -*- coding: utf-8 -*-
"""Gera a secao 'Backlog por cluster e usina' (pagina 3+) e injeta no one-page
R04, salvando como _onepage_semana41_r05.html. Agrupa por REGIAO (sigla UF no
nome do cluster), regiao e cluster do maior backlog para o menor; usinas em
ordem de tarefas abertas."""
import io, json, re
from collections import defaultdict

g = json.load(io.open('_nuvem_gestao_pcm.json', encoding='utf-8'))
AB = [t for t in g['tarefas'] if t.get('aberta')
      and 'teste' not in str(t.get('usina', '')).lower()
      and str(t.get('osStatus', '')).strip().lower() not in ('finalizados', 'finalizado')]


def usina_curta(u):
    m = re.match(r'^[^-]+?\s*-\s*(.+?)\s*-\s*[A-Za-z]{2}\s*$', ' '.join(str(u).split()))
    return m.group(1).strip() if m else u


def cliente(u):
    return str(u).split(' - ')[0].strip()


def regiao(cluster):
    m = re.match(r'^([A-Z]{2})\b', str(cluster).strip())
    return m.group(1) if m else 'Outros'


# usina -> dados
US = defaultdict(lambda: dict(n=0, atr=0, dias=0, cluster='', cli=''))
for t in AB:
    u = t['usina']
    e = US[u]
    e['n'] += 1
    if t.get('atrasado'):
        e['atr'] += 1
    e['dias'] = max(e['dias'], t.get('dias') or 0)
    e['cluster'] = str(t.get('cluster') or 'Sem cluster').strip() or 'Sem cluster'
    e['cli'] = cliente(u)

# cluster -> usinas
CL = defaultdict(list)
for u, e in US.items():
    CL[e['cluster']].append((u, e))
clusters = []
for c, us in CL.items():
    tot = sum(e['n'] for _, e in us)
    atr = sum(e['atr'] for _, e in us)
    dmax = max(e['dias'] for _, e in us)
    us.sort(key=lambda ue: (-ue[1]['n'], -ue[1]['dias']))
    clusters.append(dict(c=c, reg=regiao(c), tot=tot, atr=atr, dmax=dmax, us=us))

# regiao -> clusters (regiao por backlog desc; cluster por backlog desc)
RG = defaultdict(list)
for cl in clusters:
    RG[cl['reg']].append(cl)
regioes = sorted(RG.items(), key=lambda kv: -sum(c['tot'] for c in kv[1]))
for _, cls in regioes:
    cls.sort(key=lambda c: (-c['tot'], -c['dmax']))


def dcor(d):
    if d > 60:
        return 'red'
    if d > 35:
        return 'amber'
    return ''


html = ['<div class="page2">',
        '<div class="minihead"><div>',
        '<div class="kicker">GRID CO. · OPERAÇÃO DE ATIVOS · PCM · SEMANA 41 · CONTINUAÇÃO</div>',
        '<div class="t">7 · Backlog por cluster e usina, agrupado por região</div>',
        '</div><div class="meta">Região = UF do cluster · regiões e clusters do maior backlog para o menor · tarefas abertas hoje · foto de 05/10, 11h42</div></div>',
        '<div class="cols">']
for reg, cls in regioes:
    tot_r = sum(c['tot'] for c in cls)
    html.append('<div class="regblk"><div class="reghead">%s · %d tarefas em aberto · %d clusters</div>'
                % (reg, tot_r, len(cls)))
    for cl in cls:
        html.append('<div class="clblk">')
        html.append('<div class="clhead"><span>%s</span><span>%d abertas · %d atrasadas · mais antiga %dd</span></div>'
                    % (cl['c'], cl['tot'], cl['atr'], cl['dmax']))
        html.append('<table class="mini">')
        for u, e in cl['us']:
            html.append('<tr><td>%s <span class="cli">(%s)</span></td>'
                        '<td class="n">%d</td><td class="n">%d</td>'
                        '<td class="n %s">%dd</td></tr>'
                        % (usina_curta(u), e['cli'], e['n'], e['atr'],
                           dcor(e['dias']), e['dias']))
        html.append('</table></div>')
    html.append('</div>')
html.append('</div>')
html.append('<div class="foot"><span>Grid Co. · PCM · Semana 41 · Backlog por cluster '
            '· colunas: abertas · atrasadas · idade da mais antiga</span>'
            '<span>Fonte: Gestão PCM (nuvem) · tarefas abertas dentro de OS já finalizada (erro de sistema) não contam · usinas sem tarefa aberta não aparecem</span></div>')
html.append('</div>')
SEC = '\n'.join(html)

CSS_EXTRA = '''
  .cols { column-count: 3; column-gap: 14px; margin-top: 10px; }
  .regblk { break-inside: avoid-column; margin-bottom: 12px; }
  .reghead { background: #1C1F3B; color: #fff; font-size: 12.5px; font-weight: 800;
             letter-spacing: .8px; border-radius: 8px; padding: 6px 11px; margin-bottom: 6px; }
  .clblk { border: 1px solid #E3E3EA; border-radius: 8px; padding: 7px 9px 4px;
           margin-bottom: 7px; break-inside: avoid; }
  .clhead { display: flex; justify-content: space-between; font-size: 11.3px;
            font-weight: 800; color: #1C1F3B; }
  .clhead span:last-child { font-weight: 700; color: #7a9a2e; font-size: 10.3px; }
  table.mini { font-size: 10.8px; margin-top: 3px; }
  table.mini td { padding: 2.2px 4px; border-bottom: 1px solid #F4F4F7; }
  .cli { color: #9a97a8; font-size: 9.8px; }
'''

base = io.open('_onepage_semana41_r04.html', encoding='utf-8').read()
base = base.replace('Emitido em 05/10 · R04', 'Emitido em 05/10 · R06')
base = base.replace('</style>', CSS_EXTRA + '</style>')
base = base.replace('</body>', SEC + '\n</body>')
io.open('_onepage_semana41_r06.html', 'w', encoding='utf-8').write(base)
print('ok: regioes=%d clusters=%d usinas=%d tarefas=%d'
      % (len(regioes), len(clusters), len(US), sum(e['n'] for e in US.values())))
print('ordem regioes:', [(r, sum(c['tot'] for c in cls)) for r, cls in regioes])
