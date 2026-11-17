# -*- coding: utf-8 -*-
"""Gera o documento semanal do PCM (estilo one-page R09 da Semana 41),
100%% a partir das fontes da nuvem (gestao_pcm.json + banco_dados.json).

Modos:
  python semana_doc.py --modo abertura     (sabado 00h: semana que comeca)
  python semana_doc.py --modo fechamento   (sexta 12h: corte da semana corrente)

Saida: PDF em "...\\1. Inicio e Fechamento da Semana\\OnePages\\" +
copia local. Regras: so OS vivas (osStatus != Finalizados); sem dado = "sem
leitura"; sem travessao nos textos.
"""
import argparse, datetime as dt, io, json, os, re, subprocess, sys, time
import urllib.request
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
URL = 'https://fillipefigueiro-source.github.io/gridco-pcm-data/'
DEST_DIR = (r'C:\Users\Fabricio Barreto\OneDrive - GRID CO\Shortcuts'
            r'\GRID CO_ - 4. O&M\11.Pré-Operação\9. Reuniões\0. Grid Interno'
            r'\1. Inicio e Fechamento da Semana\OnePages')
EDGE = next(p for p in (
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe') if os.path.exists(p))

VIVA = lambda t: str(t.get('osStatus', '')).strip().lower() not in ('finalizados', 'finalizado')


def baixar(nome):
    dst = os.path.join(BASE, '_auto_' + nome)
    urllib.request.urlretrieve(URL + nome, dst)
    return json.load(io.open(dst, encoding='utf-8'))


def usina_curta(u):
    m = re.match(r'^[^-]+?\s*-\s*(.+?)\s*-\s*[A-Za-z]{2}\s*$', ' '.join(str(u).split()))
    return (m.group(1) if m else str(u)).strip()


def cliente(u):
    return str(u).split(' - ')[0].strip().replace('Utragaz', 'Ultragaz')


def regiao(cluster):
    m = re.match(r'^([A-Z]{2})\b', str(cluster).strip())
    return m.group(1) if m else 'Outros'


def trunc(s_, n):
    s_ = ' '.join(str(s_).split())
    return s_ if len(s_) <= n else s_[:n].rsplit(' ', 1)[0].rstrip(' ,;·-') + '…'


def fmt(n):
    return ('%d' % n) if n < 1000 else ('%d.%03d' % (n // 1000, n % 1000))


def dcor(d):
    return 'red' if d > 60 else ('amber' if d > 35 else '')


# ── argumentos e datas ───────────────────────────────────────────────
ap = argparse.ArgumentParser()
ap.add_argument('--modo', choices=['abertura', 'fechamento'], required=True)
ap.add_argument('--data', help='AAAA-MM-DD simulada (testes)')
A = ap.parse_args()
hoje = dt.datetime.strptime(A.data, '%Y-%m-%d') if A.data else dt.datetime.now()
if A.modo == 'abertura':
    # alvo = semana ISO de (hoje + 2 dias): sabado/domingo -> semana seguinte;
    # segunda a quarta -> a propria semana corrente
    base = hoje + dt.timedelta(days=2)
    ref = base - dt.timedelta(days=base.weekday())
else:
    ref = hoje - dt.timedelta(days=hoje.weekday())  # segunda da semana corrente
seg = ref
sex = seg + dt.timedelta(days=4)
ano, ww, _ = seg.isocalendar()
WTAG = '%d-W%02d' % (ano, ww)
TITULO = ('Abertura da Semana %d' % ww) if A.modo == 'abertura' else ('Fechamento da Semana %d' % ww)
PERIODO = '%s a %s' % (seg.strftime('%d/%m'), sex.strftime('%d/%m'))
AGORA = dt.datetime.now().strftime('%d/%m, %Hh%M')
if A.data:
    # semana passada gerada depois: os dados são os de agora, não uma foto daquela data
    AGORA += ' (gerado depois, retroativo)'

g = baixar('gestao_pcm.json')
b = baixar('banco_dados.json')
import filtro_campo
filtro_campo.aplicar(g, b)
T = [t for t in g['tarefas'] if 'teste' not in str(t.get('usina', '')).lower()]
AB = [t for t in T if t.get('aberta') and VIVA(t)]
sem = next((s for s in b.get('semanas', []) if s.get('week') == WTAG), None)
# só o PLANO: linhas "fora do plano" (corretivas, religamentos etc. executados sem estar
# na planilha) não são planejadas. Preventivas já chegam como plano (16/11/2026).
rows = [r for r in (sem or {}).get('rows', [])
        if 'teste' not in str(r.get('usina', '')).lower() and not r.get('foraDoPlano')]

# ── metricas de fila (vivas) ─────────────────────────────────────────
rxMPA = re.compile(r'\bMPA\b', re.I)
rxMPS = re.compile(r'\bMPS\b', re.I)
is_ho = lambda t: 'handover' in (str(t.get('tipo', '')) + str(t.get('tarefa', ''))).lower()
is_corr = lambda t: 'corretiva' in str(t.get('tipo', '')).lower()
is_mpas = lambda t: bool(rxMPA.search(str(t.get('tarefa', '')) + str(t.get('tipo', '')))
                         or rxMPS.search(str(t.get('tarefa', '')) + str(t.get('tipo', ''))))
is_rel = lambda t: 'religamento' in str(t.get('tipo', '')).lower()

corr_os = len({t['os'] for t in AB if is_corr(t)})
atr35 = [t for t in AB if (t.get('dias') or 0) > 35]
atr35_os = len({t['os'] for t in atr35})
mpas_atr = [t for t in AB if is_mpas(t) and (t.get('dias') or 0) > 0]
mpas_us = len({t['usina'] for t in mpas_atr})
rel_viv = [t for t in AB if is_rel(t)]
rel_os = len({t['os'] for t in rel_viv})
rel_35 = len({t['os'] for t in rel_viv if (t.get('dias') or 0) > 35})
ho_viv = [t for t in AB if is_ho(t)]

# ── bloco: ranking usinas ────────────────────────────────────────────
UR = defaultdict(lambda: dict(n=0, corr=set(), dias=0))
for t in AB:
    e = UR[t['usina']]
    e['n'] += 1
    e['dias'] = max(e['dias'], t.get('dias') or 0)
    if is_corr(t):
        e['corr'].add(t['os'])
rank = sorted(UR.items(), key=lambda kv: -kv[1]['n'])
rank10 = rank[:10]
resto_n = sum(e['n'] for _, e in rank[10:])

# ── bloco: rolagens (semana de referencia ou ultima disponivel) ─────
rsem = rows or ([r for r in b['semanas'][0].get('rows', [])
                 if 'teste' not in str(r.get('usina', '')).lower()] if b.get('semanas') else [])
porv = {}
for r in rsem:
    o = str(r.get('os_id'))
    v = int(r.get('vezes') or 1)
    cur = porv.get(o)
    if cur is None or v > cur['v']:
        porv[o] = dict(v=v, u=r.get('usina', ''), t=r.get('tarefa', ''),
                       tp=str(r.get('tipo', '')), st=str(r.get('status', '')))
rol10 = sorted(porv.items(), key=lambda kv: -kv[1]['v'])[:10]

# ── bloco: atrasadas +35d por OS ─────────────────────────────────────
OS35 = defaultdict(lambda: dict(n=0, dias=0, u='', ts=[], obs='', etq=''))
tot_por_os = defaultdict(int)
for t in T:
    tot_por_os[t['os']] += 1
for t in atr35:
    e = OS35[t['os']]
    e['n'] += 1
    d = t.get('dias') or 0
    if d >= e['dias']:
        e['dias'] = d
        e['obs'] = str(t.get('obs') or '')
        e['etq'] = ', '.join(t.get('etiquetas') or [])
    e['u'] = t['usina']
    e['ts'].append(str(t.get('tarefa', '')))
os35 = sorted(OS35.items(), key=lambda kv: -kv[1]['dias'])[:8]

# ── bloco: religamentos vivos ────────────────────────────────────────
RL = defaultdict(lambda: dict(n=0, dias=0, u='', tp=''))
for t in rel_viv:
    e = RL[t['os']]
    e['n'] += 1
    e['dias'] = max(e['dias'], t.get('dias') or 0)
    e['u'] = t['usina']
    e['tp'] = str(t.get('tipo', ''))
rl10 = sorted(RL.items(), key=lambda kv: -kv[1]['dias'])[:10]

# ── bloco: MPAS por usina ────────────────────────────────────────────
MU = defaultdict(lambda: dict(n=0, dias=0, oss=set(), tipos=set()))
for t in mpas_atr:
    e = MU[t['usina']]
    e['n'] += 1
    e['dias'] = max(e['dias'], t.get('dias') or 0)
    e['oss'].add(t['os'])
    txt = str(t.get('tarefa', '')) + str(t.get('tipo', ''))
    e['tipos'].add('MPS' if rxMPS.search(txt) else 'MPA')
mu12 = sorted(MU.items(), key=lambda kv: -kv[1]['dias'])[:12]

# ── bloco: handovers ─────────────────────────────────────────────────
HU = defaultdict(lambda: dict(n=0, atr=0, dias=0, oss=set()))
for t in ho_viv:
    e = HU[t['usina']]
    e['n'] += 1
    if t.get('atrasado'):
        e['atr'] += 1
    e['dias'] = max(e['dias'], t.get('dias') or 0)
    e['oss'].add(t['os'])
hu = sorted(HU.items(), key=lambda kv: -kv[1]['dias'])

# ── bloco: plano/execucao da semana (banco) ──────────────────────────
def grupo_b(r):
    t = (str(r.get('tipo', '')) + ' ' + str(r.get('tarefa', ''))).lower()
    if 'handover' in t:
        return 'Handover'
    if re.search(r'\bmpa\b', t):
        return 'MPA'
    if re.search(r'\bmps\b', t):
        return 'MPS'
    if 'corretiva' in t:
        return 'Corretivas'
    if 'zeladoria' in t:
        return 'Zeladoria'
    if 'religamento' in t:
        return 'Religamentos'
    if 'administrativa' in t:
        return 'Administrativas'
    return 'Preventivas (MPM e inspeções)'


PL = defaultdict(lambda: [0, 0])
SUPD = defaultdict(lambda: defaultdict(int))
DIAS_SEM = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira']
for r in rows:
    gp = grupo_b(r)
    PL[gp][0] += 1
    fin = str(r.get('status', '')).strip().lower().startswith('finaliz')
    if fin:
        PL[gp][1] += 1
    resp = r.get('responsavel') or 'Sem resp.'
    SUPD[resp][r.get('dia')] += 1
    SUPD[resp]['__tot'] += 1
    if fin:
        SUPD[resp]['__fin'] += 1
pl_ord = sorted(PL.items(), key=lambda kv: -kv[1][0])
sup_ord = sorted(SUPD.items(), key=lambda kv: -kv[1]['__tot'])

# ══ HTML ═════════════════════════════════════════════════════════════
CSS = '''
  @page { size: 470mm 275mm; margin: 0; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: "Segoe UI", Calibri, sans-serif; color: #23203A; background: #fff; width: 1740px; padding: 30px 42px 16px; }
  .kicker { font-size: 13px; font-weight: 700; letter-spacing: 3px; color: #7a9a2e; }
  h1 { font-size: 32px; font-weight: 800; margin: 5px 0 4px; }
  .sub { font-size: 14px; color: #6B6880; }
  .head { display: flex; justify-content: space-between; align-items: flex-start; }
  .chips { display: flex; gap: 8px; margin-top: 6px; }
  .chip { font-size: 12.5px; font-weight: 700; padding: 5px 14px; border-radius: 14px; white-space: nowrap; }
  .chip.dark { background: #1C1F3B; color: #fff; } .chip.line { border: 1.5px solid #A2CA40; color: #4a6b10; }
  .chip.soft { border: 1.5px solid #d8d8e0; color: #6B6880; }
  .meta { font-size: 12px; color: #9a97a8; margin-top: 8px; text-align: right; }
  .kpis { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-top: 14px; }
  .kpi { border: 1px solid #E3E3EA; border-radius: 10px; padding: 10px 14px 8px; }
  .kpi .v { font-size: 28px; font-weight: 800; line-height: 1.05; }
  .kpi .l { font-size: 11.6px; color: #6B6880; margin-top: 3px; line-height: 1.25; }
  .v.amber { color: #B9770E; } .v.red { color: #B3261E; } .v.navy { color: #1C1F3B; } .v.green { color: #2E7D32; }
  .row { display: grid; gap: 12px; margin-top: 12px; }
  .r2 { grid-template-columns: 1fr 1.18fr; } .r3 { grid-template-columns: 1.52fr 1fr; } .r1 { grid-template-columns: 1fr; }
  .card { border: 1px solid #E3E3EA; border-radius: 10px; padding: 11px 14px; break-inside: avoid; }
  .card h2 { font-size: 14.5px; font-weight: 800; }
  .card .tag { font-size: 10.5px; font-weight: 800; letter-spacing: 1.6px; color: #9a97a8; }
  .card .nota { font-size: 10.8px; color: #9a97a8; margin-top: 5px; line-height: 1.3; }
  table { width: 100%; border-collapse: collapse; font-size: 11.8px; margin-top: 6px; }
  th { text-align: left; font-size: 10px; letter-spacing: .5px; color: #9a97a8; font-weight: 800; border-bottom: 1.5px solid #E3E3EA; padding: 3px 5px 4px; }
  td { padding: 3.6px 5px; border-bottom: 1px solid #F0F0F4; vertical-align: top; }
  td.n, th.n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .red { color: #B3261E; font-weight: 800; } .amber { color: #B9770E; font-weight: 700; }
  .green { color: #2E7D32; font-weight: 700; } .navy { color: #1C1F3B; font-weight: 700; }
  .etq { display: inline-block; font-size: 9.5px; font-weight: 800; border: 1px solid #c9cbd6; border-radius: 8px; padding: 1px 7px; color: #6B6880; }
  .obs { color: #55526a; font-size: 11.2px; line-height: 1.3; }
  .foot { display: flex; justify-content: space-between; gap: 30px; margin-top: 12px; font-size: 11px; color: #9a97a8; }
  .page2 { break-before: page; padding-top: 6px; }
  .minihead { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px; }
  .minihead .t { font-size: 17px; font-weight: 800; }
  .umbloco { width: 1420px; margin: 10px auto 0; }
  .reghead { background: #1C1F3B; color: #fff; font-size: 13.5px; font-weight: 800; border-radius: 8px; padding: 7px 13px; margin: 14px 0 8px; }
  .clblk { border: 1px solid #E3E3EA; border-radius: 8px; padding: 8px 12px 6px; margin-bottom: 8px; break-inside: avoid; }
  .clhead { display: flex; justify-content: space-between; font-size: 12.5px; font-weight: 800; color: #1C1F3B; border-bottom: 1.5px solid #E3E3EA; padding-bottom: 4px; }
  .clhead span:last-child { font-weight: 700; color: #7a9a2e; font-size: 11px; }
  .usina { display: flex; justify-content: space-between; margin-top: 7px; background: #F7F7FA; border-radius: 6px; padding: 4px 9px; }
  .unome { font-size: 12.3px; font-weight: 800; } .ustats { font-size: 11px; color: #55526a; }
  .ustats b.red { color: #B3261E; } .ustats b.amber { color: #B9770E; }
  .cli { color: #9a97a8; font-size: 10px; font-weight: 700; }
  table.mini { font-size: 11px; } table.mini td { padding: 2.4px 6px; }
  table.mini td.osn { width: 72px; font-weight: 800; color: #1C1F3B; }
  table.mini td.tp { width: 150px; color: #7a9a2e; font-weight: 700; }
  .xmul { color: #B9770E; font-weight: 800; } .mais { color: #9a97a8; font-style: italic; }
'''

H = []
chip2 = ('Plano da semana' if A.modo == 'abertura' else 'Corte de sexta 12h')
H.append('<div class="head"><div>')
H.append('<div class="kicker">GRID CO. · OPERAÇÃO DE ATIVOS · PCM</div>')
H.append('<h1>%s: %s</h1>' % (TITULO, 'o plano e a fila' if A.modo == 'abertura' else 'o que rodou e o que ficou'))
H.append('<div class="sub">Documento gerado automaticamente das fontes da nuvem. Informativo para o time; prioridades e decisões com a coordenação.</div>')
H.append('</div><div><div class="chips"><span class="chip dark">Semana %d · %s</span>'
         '<span class="chip line">%s</span><span class="chip soft">Gerado em %s</span></div>'
         % (ww, PERIODO, chip2, AGORA))
H.append('<div class="meta">Fontes: Gestão PCM e Programação Semanal (nuvem, robôs de 15 min) · gestão de %s</div></div></div>'
         % str(g.get('geradoEm', ''))[:16].replace('T', ' '))

# KPIs
if A.modo == 'abertura':
    k1v, k1l = (fmt(len(rows)), 'tarefas na programação da semana') if rows else ('sem leitura', 'plano da semana ainda não publicado')
else:
    fins = sum(v[1] for v in PL.values())
    plan = len(rows)
    k1v, k1l = (('%d%%' % round(100.0 * fins / plan)) if plan else 'sem leitura',
                'execução da semana (%s de %s tarefas)' % (fmt(fins), fmt(plan)) if plan else 'plano da semana não encontrado')
H.append('<div class="kpis">')
H.append('<div class="kpi"><div class="v navy">%s</div><div class="l">%s</div></div>' % (k1v, k1l))
H.append('<div class="kpi"><div class="v red">%d</div><div class="l">corretivas abertas (OS vivas, emergenciais incluídas)</div></div>' % corr_os)
H.append('<div class="kpi"><div class="v red">%s</div><div class="l">tarefas atrasadas há mais de 35 dias, em %d OS</div></div>' % (fmt(len(atr35)), atr35_os))
H.append('<div class="kpi"><div class="v red">%s</div><div class="l">tarefas de MPA/MPS atrasadas, em %d usinas</div></div>' % (fmt(len(mpas_atr)), mpas_us))
cor_rel = 'green' if rel_35 == 0 else 'amber'
H.append('<div class="kpi"><div class="v %s">%d</div><div class="l">religamentos em aberto (%d OS); %d acima de 35 dias</div></div>' % (cor_rel, len(rel_viv), rel_os, rel_35))
H.append('</div>')

# bloco plano/execucao
H.append('<div class="row r2">')
H.append('<div class="card"><div class="tag">1 · %s</div><h2>%s</h2><table>' % (
    ('O PLANO DA SEMANA' if A.modo == 'abertura' else 'PLANEJADO × EXECUTADO'),
    ('Composição por tipo de tarefa' if A.modo == 'abertura' else 'Por tipo de tarefa (até o corte)')))
if rows:
    if A.modo == 'abertura':
        H.append('<tr><th>Tipo</th><th class="n">Tarefas</th></tr>')
        for gp, (n, _) in pl_ord:
            H.append('<tr><td>%s</td><td class="n">%d</td></tr>' % (gp, n))
        H.append('<tr><td class="navy">Total</td><td class="n navy">%s</td></tr>' % fmt(len(rows)))
    else:
        H.append('<tr><th>Tipo</th><th class="n">Planejadas</th><th class="n">Executadas</th><th class="n">%</th></tr>')
        for gp, (n, f) in pl_ord:
            pc = round(100.0 * f / n) if n else 0
            cor = 'green' if pc >= 80 else ('amber' if pc >= 40 else 'red')
            H.append('<tr><td>%s</td><td class="n">%d</td><td class="n">%d</td><td class="n %s">%d%%</td></tr>' % (gp, n, f, cor, pc))
else:
    H.append('<tr><td class="red">sem leitura: o plano desta semana ainda não está na nuvem</td></tr>')
H.append('</table><div class="nota">Espelho da planilha da Programação (religamentos remotos fora do cálculo de aderência).</div></div>')

H.append('<div class="card"><div class="tag">2 · QUEM FAZ O QUÊ</div><h2>Tarefas por supervisor e dia%s</h2><table>'
         % ('' if A.modo == 'abertura' else ' · executadas/total'))
H.append('<tr><th>Supervisor</th>' + ''.join('<th class="n">%s</th>' % d[:3] for d in DIAS_SEM)
         + '<th class="n">Total</th>%s</tr>' % ('' if A.modo == 'abertura' else '<th class="n">Exec.</th>'))
for resp, dd in sup_ord[:8]:
    extra = '' if A.modo == 'abertura' else '<td class="n green">%d</td>' % dd.get('__fin', 0)
    H.append('<tr><td class="navy">%s</td>%s<td class="n navy">%d</td>%s</tr>'
             % (trunc(resp, 20), ''.join('<td class="n">%d</td>' % dd.get(d, 0) for d in DIAS_SEM),
                dd['__tot'], extra))
if not sup_ord:
    H.append('<tr><td class="red">sem leitura</td></tr>')
H.append('</table></div></div>')

# ranking + rolagens
H.append('<div class="row r2">')
H.append('<div class="card"><div class="tag">3 · USINAS QUE PEDEM ATENÇÃO</div><h2>Ordenado por tarefas em aberto (OS vivas)</h2>'
         '<table><tr><th>#</th><th>Usina</th><th class="n">Em aberto</th><th class="n">Corr.+Emerg.</th><th class="n">Mais antiga</th></tr>')
for i, (u, e) in enumerate(rank10, 1):
    H.append('<tr><td>%d</td><td class="navy">%s (%s)</td><td class="n">%d</td><td class="n">%s</td><td class="n %s">%d d</td></tr>'
             % (i, usina_curta(u), cliente(u), e['n'], len(e['corr']) or '—', dcor(e['dias']), e['dias']))
H.append('</table><div class="nota">As demais %d usinas somam %s tarefas em aberto.</div></div>' % (len(rank) - 10, fmt(resto_n)))

H.append('<div class="card"><div class="tag">4 · TOP 10 · TAREFAS QUE MAIS ROLARAM</div><h2>Nº de semanas em que a OS entrou na programação</h2>'
         '<table><tr><th>OS</th><th>Usina</th><th>Tarefa</th><th>Tipo</th><th class="n">Rolagens</th></tr>')
for o, e in rol10:
    cor = 'red' if e['v'] >= 10 else 'amber'
    H.append('<tr><td class="navy">%s</td><td>%s</td><td>%s</td><td>%s</td><td class="n %s">%d×</td></tr>'
             % (o, usina_curta(e['u']), trunc(e['t'], 52), trunc(e['tp'], 14), cor, e['v']))
if not rol10:
    H.append('<tr><td class="red">sem leitura</td></tr>')
H.append('</table><div class="nota">Rolagem = a OS voltou para a programação em outra semana sem ser concluída.</div></div></div>')

# atrasadas por OS + religamentos
H.append('<div class="row r3">')
H.append('<div class="card"><div class="tag">5 · ATRASADAS HÁ MAIS DE 35 DIAS · AGRUPADAS POR OS</div><h2>As 8 OS mais antigas (de %d)</h2>'
         '<table><tr><th class="n">Dias</th><th>OS</th><th>Cliente · usina</th><th>Tarefa(s)</th><th class="n">Faltam</th><th>Observação da OS</th></tr>' % atr35_os)
for o, e in os35:
    ts = sorted({trunc(x, 28) for x in e['ts']})
    tt = trunc(', '.join(ts), 56) + (' <span class="xmul">· %d tarefas</span>' % e['n'] if e['n'] > 1 else '')
    etq = (' <span class="etq">%s</span>' % trunc(e['etq'].upper(), 24)) if e['etq'] else ''
    obs = trunc(e['obs'], 110) if e['obs'] else 'sem observação registrada na OS'
    H.append('<tr><td class="n red">%d d</td><td class="navy">%s</td><td>%s · %s</td><td>%s%s</td>'
             '<td class="n navy">%d/%d</td><td class="obs">%s</td></tr>'
             % (e['dias'], o, cliente(e['u']), usina_curta(e['u']), tt, etq, e['n'], tot_por_os[o], obs))
H.append('</table><div class="nota">Faltam = tarefas abertas ÷ total da OS. Só OS vivas.</div></div>')

H.append('<div class="card"><div class="tag">6 · RELIGAMENTOS EM ABERTO</div><h2>%s</h2>'
         '<table><tr><th class="n">Dias</th><th>OS</th><th>Usina</th><th>Tipo</th></tr>'
         % ('Em dia: %d OS vivas, nenhuma acima de 35 dias' % rel_os if rel_35 == 0
            else '%d OS vivas, %d acima de 35 dias' % (rel_os, rel_35)))
for o, e in rl10:
    H.append('<tr><td class="n %s">%d d</td><td class="navy">%s</td><td>%s (%s)</td><td>%s</td></tr>'
             % (dcor(e['dias']) or ('amber' if e['dias'] > 20 else ''), e['dias'], o,
                usina_curta(e['u']), cliente(e['u']), trunc(e['tp'], 20)))
H.append('</table><div class="nota">Religamentos de OS já finalizada (erro de sistema) não contam.</div></div></div>')
H.append('<div class="foot"><span>Grid Co. · PCM · %s · página 1</span><span>continua: MPAS, handovers e backlog por região</span></div>' % TITULO)

# pagina 2: MPAS + handovers
H.append('<div class="page2"><div class="minihead"><div>'
         '<div class="kicker">GRID CO. · OPERAÇÃO DE ATIVOS · PCM · %s · CONTINUAÇÃO</div>'
         '<div class="t">MPAS atrasadas e handovers em andamento</div></div>'
         '<div class="meta">foto de %s</div></div>' % (TITULO.upper(), AGORA))
H.append('<div class="row r1"><div class="card"><div class="tag">7 · MPAS ATRASADAS · UMA LINHA POR USINA</div>'
         '<h2>Anuais e semestrais atrasadas: 12 usinas mais antigas (de %d)</h2>'
         '<table><tr><th>Usina</th><th>Tipo</th><th>OS</th><th class="n">Tarefas abertas</th><th class="n">Mais antiga</th></tr>' % len(MU))
for u, e in mu12:
    H.append('<tr><td class="navy">%s (%s)</td><td>%s</td><td>%s</td><td class="n">%d</td><td class="n %s">%d d</td></tr>'
             % (usina_curta(u), cliente(u), '/'.join(sorted(e['tipos'])), ', '.join(sorted(e['oss'])[:3]),
                e['n'], dcor(e['dias']), e['dias']))
H.append('</table><div class="nota">Carteira toda: %s tarefas de MPA/MPS atrasadas em %d usinas.</div></div></div>' % (fmt(len(mpas_atr)), len(MU)))

H.append('<div class="row r1"><div class="card"><div class="tag">8 · HANDOVERS EM ANDAMENTO</div>'
         '<h2>Entrada de usinas: %s tarefas vivas em %d usinas</h2>'
         '<table><tr><th>Usina</th><th>OS</th><th class="n">Tarefas</th><th class="n">Atrasadas</th><th class="n">Mais antiga</th></tr>' % (fmt(len(ho_viv)), len(HU)))
for u, e in hu[:16]:
    H.append('<tr><td class="navy">%s (%s)</td><td class="navy">OS %s</td><td class="n">%d</td><td class="n">%d</td><td class="n %s">%d d</td></tr>'
             % (usina_curta(u), cliente(u), ' / '.join(sorted(e['oss'])), e['n'], e['atr'], dcor(e['dias']), e['dias']))
H.append('</table><div class="nota">Só OS vivas.</div></div></div>')
H.append('<div class="foot"><span>Grid Co. · PCM · %s · página 2</span><span>Painel: pcm.gridco.com.br · Relatório Executivo: github.io/gridco-pcm-data</span></div></div>' % TITULO)

# pagina 3+: backlog por regiao (compacto: 4 OS/usina)
US2 = {}
for t in AB:
    if not t.get('atrasado'):
        continue
    u = t['usina']
    e = US2.setdefault(u, dict(atr=0, dias=0, cluster='', oss={}))
    e['atr'] += 1
    e['dias'] = max(e['dias'], t.get('dias') or 0)
    e['cluster'] = str(t.get('cluster') or 'Sem cluster').strip() or 'Sem cluster'
    o = e['oss'].setdefault(t['os'], dict(n=0, dias=0, tipo='', tit=''))
    o['n'] += 1
    d = t.get('dias') or 0
    if d >= o['dias']:
        o['dias'], o['tipo'], o['tit'] = d, str(t.get('tipo', '')), str(t.get('tarefa', ''))
CL2 = defaultdict(list)
for u, e in US2.items():
    CL2[e['cluster']].append(u)


def cstat(c):
    us = CL2[c]
    return (sum(US2[u]['atr'] for u in us), max(US2[u]['dias'] for u in us))


ordem_u = sorted(US2, key=lambda u: (-US2[u]['atr'], -US2[u]['dias']))
feitas, seqr = set(), []
for u in ordem_u:
    reg = regiao(US2[u]['cluster'])
    if reg in feitas:
        continue
    cl0 = US2[u]['cluster']
    cls = [cl0] + sorted([c for c in CL2 if regiao(c) == reg and c != cl0],
                         key=lambda c: (-cstat(c)[0], -cstat(c)[1]))
    seqr.append((reg, cls))
    feitas.add(reg)

H.append('<div class="page2"><div class="minihead"><div>'
         '<div class="kicker">GRID CO. · OPERAÇÃO DE ATIVOS · PCM · %s · CONTINUAÇÃO</div>'
         '<div class="t">9 · Backlog atrasado por região, cluster e usina</div></div>'
         '<div class="meta">só tarefas atrasadas de OS vivas · até 4 OS por usina · foto de %s</div></div>'
         '<div class="umbloco">' % (TITULO.upper(), AGORA))
for reg, cls in seqr:
    tot_r = sum(cstat(c)[0] for c in cls)
    H.append('<div class="reghead">%s · %d tarefas atrasadas · %d cluster(s)</div>' % (reg, tot_r, len(cls)))
    for c in cls:
        atr_c, dmax_c = cstat(c)
        H.append('<div class="clblk"><div class="clhead"><span>%s</span><span>%d atrasadas · mais antiga %dd</span></div>' % (c, atr_c, dmax_c))
        for u in sorted(CL2[c], key=lambda x: (-US2[x]['atr'], -US2[x]['dias'])):
            e = US2[u]
            H.append('<div class="usina"><span class="unome">%s <span class="cli">(%s)</span></span>'
                     '<span class="ustats">%d atrasadas · mais antiga <b class="%s">%dd</b></span></div>'
                     % (usina_curta(u), cliente(u), e['atr'], dcor(e['dias']), e['dias']))
            oss = sorted(e['oss'].items(), key=lambda kv: -kv[1]['dias'])
            H.append('<table class="mini">')
            for o, oe in oss[:4]:
                extra = ' <span class="xmul">· %d tarefas</span>' % oe['n'] if oe['n'] > 1 else ''
                H.append('<tr><td class="n %s">%dd</td><td class="osn">OS %s</td><td class="tp">%s</td><td>%s%s</td></tr>'
                         % (dcor(oe['dias']), oe['dias'], o, trunc(oe['tipo'], 20), trunc(oe['tit'], 64), extra))
            if len(oss) > 4:
                H.append('<tr><td></td><td colspan="3" class="mais">+ %d OS atrasadas nesta usina</td></tr>' % (len(oss) - 4))
            H.append('</table>')
        H.append('</div>')
H.append('</div><div class="foot"><span>Grid Co. · PCM · %s · backlog por região</span>'
         '<span>tarefas de OS já finalizada (erro de sistema) não contam · gerado automaticamente</span></div></div>' % TITULO)

HTML = ('<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><title>%s</title>'
        '<style>%s</style></head><body>%s</body></html>' % (TITULO, CSS, '\n'.join(H)))
nome = '%s_Semana%02d_PCM_GridCo' % ('Abertura' if A.modo == 'abertura' else 'Fechamento', ww)
html_path = os.path.join(BASE, '_auto_%s.html' % nome)
io.open(html_path, 'w', encoding='utf-8').write(HTML)

pdf_local = os.path.join(BASE, '_auto_%s.pdf' % nome)
if os.path.exists(pdf_local):
    os.remove(pdf_local)
try:
    subprocess.run([EDGE, '--headless=new', '--disable-gpu',
                    '--print-to-pdf=%s' % pdf_local, '--no-pdf-header-footer',
                    'file:///' + html_path.replace('\\', '/').replace(' ', '%20')],
                   check=False, timeout=180)
except subprocess.TimeoutExpired:
    # o Edge headless às vezes grava o PDF e não encerra; o run() já matou o processo
    print('AVISO: Edge não encerrou em 180 s; conferindo se o PDF foi gravado')
time.sleep(2)
if not os.path.exists(pdf_local) or os.path.getsize(pdf_local) == 0:
    sys.exit('ERRO: PDF nao gerado')
os.makedirs(DEST_DIR, exist_ok=True)
dest = os.path.join(DEST_DIR, nome + '.pdf')
try:
    import shutil
    shutil.copy2(pdf_local, dest)
    print('ok -> %s' % dest)
except PermissionError:
    print('AVISO: destino bloqueado; PDF local em %s' % pdf_local)
