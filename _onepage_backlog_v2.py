# -*- coding: utf-8 -*-
"""Secao 7 v2: backlog focado nas ATRASADAS, bloco unico centralizado.
Ordem: usina com mais pendencias/mais antiga puxa o cluster dela; depois os
demais clusters da mesma regiao (UF); depois a proxima usina campea de outra
regiao, e assim por diante. Por usina: OS atrasadas com numero, tipo e titulo
(OS com varias tarefas viram uma linha so). So OS vivas. Gera R07."""
import io, json, re
from collections import defaultdict
import fonte_bd_api as F
_dfr = F.df_semanal(ttl_min=2880)[['OSs ID', 'Responsável']].dropna()
RESP = {}
for _r in _dfr.to_dict('records'):
    RESP.setdefault(str(_r['OSs ID']), ' '.join(str(_r['Responsável']).split()))

g = json.load(io.open('_nuvem_gestao_pcm.json', encoding='utf-8'))
AB = [t for t in g['tarefas'] if t.get('aberta')
      and 'teste' not in str(t.get('usina', '')).lower()
      and str(t.get('osStatus', '')).strip().lower() not in ('finalizados', 'finalizado')]


def usina_curta(u):
    m = re.match(r'^[^-]+?\s*-\s*(.+?)\s*-\s*[A-Za-z]{2}\s*$', ' '.join(str(u).split()))
    return m.group(1).strip() if m else u


def cliente(u):
    return str(u).split(' - ')[0].strip().replace('Utragaz', 'Ultragaz')


def regiao(cluster):
    m = re.match(r'^([A-Z]{2})\b', str(cluster).strip())
    return m.group(1) if m else 'Outros'


# ── estrutura usina -> OS ────────────────────────────────────────────
US = {}
for t in AB:
    u = t['usina']
    e = US.setdefault(u, dict(n=0, atr=0, dias=0, cluster='', sup='', oss={}))
    e['n'] += 1
    if t.get('atrasado'):
        e['atr'] += 1
    e['dias'] = max(e['dias'], t.get('dias') or 0)
    e['cluster'] = str(t.get('cluster') or 'Sem cluster').strip() or 'Sem cluster'
    e['sup'] = str(t.get('responsavel') or '')
    if t.get('atrasado'):
        o = e['oss'].setdefault(t['os'], dict(n=0, dias=0, tipo='', tit=''))
        o['n'] += 1
        d = t.get('dias') or 0
        if d >= o['dias']:
            o['dias'] = d
            o['tipo'] = str(t.get('tipo', ''))
            o['tit'] = str(t.get('tarefa', ''))

CL = defaultdict(list)
for u, e in US.items():
    CL[e['cluster']].append(u)


def cluster_stats(c):
    us = CL[c]
    return (sum(US[u]['atr'] for u in us), max(US[u]['dias'] for u in us),
            sum(US[u]['n'] for u in us))


# ── ordem: campea -> cluster dela -> regiao dela -> proxima campea ──
ordem_usinas = sorted(US, key=lambda u: (-US[u]['atr'], -US[u]['dias'], -US[u]['n']))
emitidas = set()
sequencia = []  # lista de (regiao, [clusters em ordem])
regioes_feitas = set()
for u in ordem_usinas:
    if u in emitidas:
        continue
    cl0 = US[u]['cluster']
    reg = regiao(cl0)
    if reg in regioes_feitas:
        continue
    cls_reg = [c for c in CL if regiao(c) == reg]
    resto = sorted([c for c in cls_reg if c != cl0],
                   key=lambda c: (-cluster_stats(c)[0], -cluster_stats(c)[1]))
    ordem_cls = [cl0] + resto
    sequencia.append((reg, ordem_cls))
    regioes_feitas.add(reg)
    for c in ordem_cls:
        emitidas.update(CL[c])


def trunc(s_, n):
    s_ = str(s_).strip()
    if len(s_) <= n:
        return s_
    return s_[:n].rsplit(' ', 1)[0].rstrip(' ,;·-') + '…'


def dcor(d):
    return 'red' if d > 60 else ('amber' if d > 35 else '')


html = ['<div class="page2">',
        '<div class="minihead"><div>',
        '<div class="kicker">GRID CO. · OPERAÇÃO DE ATIVOS · PCM · SEMANA 41 · CONTINUAÇÃO</div>',
        '<div class="t">7 · Backlog atrasado por região, cluster e usina</div>',
        '</div><div class="meta">Só tarefas atrasadas, de OS vivas · a usina mais pendente puxa o cluster e a região · OS com várias tarefas viram uma linha · colunas finais: responsável da OS e supervisor · foto de 05/10, 11h42</div></div>',
        '<div class="umbloco">']
for reg, cls in sequencia:
    tot_atr = sum(cluster_stats(c)[0] for c in cls)
    if tot_atr == 0:
        continue
    html.append('<div class="reghead">%s · %d tarefas atrasadas · %d cluster(s)</div>'
                % (reg, tot_atr, len(cls)))
    for c in cls:
        atr_c, dmax_c, n_c = cluster_stats(c)
        if atr_c == 0:
            continue
        html.append('<div class="clblk"><div class="clhead"><span>%s</span>'
                    '<span>%d atrasadas · %d abertas · mais antiga %dd</span></div>' % (c, atr_c, n_c, dmax_c))
        us = sorted(CL[c], key=lambda u: (-US[u]['atr'], -US[u]['dias']))
        for u in us:
            e = US[u]
            if e['atr'] == 0:
                continue
            html.append('<div class="usina"><span class="unome">%s <span class="cli">(%s)</span></span>'
                        '<span class="ustats">%d atrasadas de %d abertas · mais antiga <b class="%s">%dd</b></span></div>'
                        % (usina_curta(u), cliente(u), e['atr'], e['n'], dcor(e['dias']), e['dias']))
            oss = sorted(e['oss'].items(), key=lambda kv: -kv[1]['dias'])
            html.append('<table class="mini">')
            for os_, o in oss[:6]:
                extra = ' <span class="xmul">· %d tarefas</span>' % o['n'] if o['n'] > 1 else ''
                html.append('<tr><td class="n %s">%dd</td><td class="osn">OS %s</td>'
                            '<td class="tp">%s</td><td>%s%s</td>'
                            '<td class="resp">%s</td><td class="supv">%s</td></tr>'
                            % (dcor(o['dias']), o['dias'], os_, trunc(o['tipo'], 20),
                               trunc(o['tit'], 54), extra,
                               trunc(RESP.get(os_, '-'), 20), trunc(e['sup'], 18)))
            if len(oss) > 6:
                html.append('<tr><td></td><td colspan="5" class="mais">+ %d OS atrasadas nesta usina</td></tr>'
                            % (len(oss) - 6))
            html.append('</table>')
        html.append('</div>')
html.append('</div>')
html.append('<div class="foot"><span>Grid Co. · PCM · Semana 41 · Backlog atrasado por região</span>'
            '<span>Fonte: Gestão PCM (nuvem) · tarefas de OS já finalizada (erro de sistema) não contam</span></div>')
html.append('</div>')
SEC = '\n'.join(html)

CSS_EXTRA = '''
  .umbloco { width: 1420px; margin: 10px auto 0; }
  table.mini td.resp { width: 150px; font-weight: 700; color: #1C1F3B; }
  table.mini td.supv { width: 130px; color: #9a97a8; }
  .reghead { background: #1C1F3B; color: #fff; font-size: 13.5px; font-weight: 800;
             letter-spacing: .8px; border-radius: 8px; padding: 7px 13px; margin: 14px 0 8px; }
  .clblk { border: 1px solid #E3E3EA; border-radius: 8px; padding: 8px 12px 6px;
           margin-bottom: 8px; break-inside: avoid; }
  .clhead { display: flex; justify-content: space-between; font-size: 12.5px;
            font-weight: 800; color: #1C1F3B; border-bottom: 1.5px solid #E3E3EA; padding-bottom: 4px; }
  .clhead span:last-child { font-weight: 700; color: #7a9a2e; font-size: 11px; }
  .usina { display: flex; justify-content: space-between; margin-top: 7px;
           background: #F7F7FA; border-radius: 6px; padding: 4px 9px; }
  .unome { font-size: 12.3px; font-weight: 800; }
  .ustats { font-size: 11px; color: #55526a; }
  .ustats b.red { color: #B3261E; } .ustats b.amber { color: #B9770E; }
  .cli { color: #9a97a8; font-size: 10px; font-weight: 700; }
  table.mini { font-size: 11px; margin: 2px 0 4px; }
  table.mini td { padding: 2.4px 6px; border-bottom: 1px solid #F4F4F7; }
  table.mini td.n { width: 44px; text-align: right; font-weight: 800; }
  table.mini td.osn { width: 72px; font-weight: 800; color: #1C1F3B; }
  table.mini td.tp { width: 150px; color: #7a9a2e; font-weight: 700; }
  .xmul { color: #B9770E; font-weight: 800; }
  .mais { color: #9a97a8; font-style: italic; }
'''

base = io.open('_onepage_semana41_r04.html', encoding='utf-8').read()
base = base.replace('Emitido em 05/10 · R04', 'Emitido em 05/10 · R08')
base = base.replace('</style>', CSS_EXTRA + '</style>')
base = base.replace('</body>', SEC + '\n</body>')
io.open('_onepage_semana41_r08.html', 'w', encoding='utf-8').write(base)
print('ordem das regioes:', [r for r, _ in sequencia])
print('primeiras usinas:', [usina_curta(u) for u in ordem_usinas[:5]])
