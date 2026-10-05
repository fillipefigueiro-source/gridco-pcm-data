# -*- coding: utf-8 -*-
"""Analise TOC (Teoria das Restricoes) para o one-page de gargalos do PCM,
Semana 41. Fontes: _nuvem_gestao_pcm.json e _nuvem_banco_dados.json (nuvem,
robos de 15 min). Gera _toc41.json."""
import io, json
import datetime as dt
from collections import defaultdict

HOJE = dt.datetime(2026, 10, 5)
g = json.load(io.open('_nuvem_gestao_pcm.json', encoding='utf-8'))
b = json.load(io.open('_nuvem_banco_dados.json', encoding='utf-8'))
T = [t for t in g['tarefas'] if 'teste' not in str(t.get('usina', '')).lower()]


def d(s):
    try:
        return dt.datetime.strptime(str(s)[:10], '%Y-%m-%d')
    except Exception:
        return None


import re
RX_MPA = re.compile(r'\bMPA\b', re.I)
RX_MPS = re.compile(r'\bMPS\b', re.I)


def grupo(tipo, tarefa=''):
    t = str(tipo).lower()
    tx_ = str(tarefa)
    if 'handover' in t or 'handover' in tx_.lower():
        return 'Handover'
    if RX_MPA.search(tx_) or ('mpa' in t and 'mpas' not in t):
        return 'MPA'
    if RX_MPS.search(tx_) or t.startswith('mps'):
        return 'MPS'
    if 'corretiva' in t or 'emergencial' in t:
        return 'Corretiva'
    if 'mpm' in t or 'preventiva' in t or 'inspe' in t or 'mpt' in t:
        return 'Preventiva (MPM)'
    if 'zeladoria' in t:
        return 'Zeladoria'
    if 'religamento' in t:
        return 'Religamento'
    return 'Outros'


HH = lambda x: float(x.get('dur') or 0)

# ── A. fila aberta por grupo (tarefas e HH) ──────────────────────────
ab = [t for t in T if t.get('aberta')]
fila = defaultdict(lambda: dict(n=0, hh=0.0, atras=0, d30=0, idade_max=0, usinas=set()))
for t in ab:
    e = fila[grupo(t['tipo'], t.get('tarefa',''))]
    e['n'] += 1
    e['hh'] += HH(t)
    if t.get('atrasado'):
        e['atras'] += 1
    dias = t.get('dias') or 0
    if dias and dias > 30:
        e['d30'] += 1
    e['idade_max'] = max(e['idade_max'], dias or 0)
    e['usinas'].add(t['usina'])
for e in fila.values():
    e['usinas'] = len(e['usinas'])
    e['hh'] = round(e['hh'])

# ── B. vazao (throughput) por semana: fechadas x criadas, em HH ─────
def semana_iso(x):
    return x.isocalendar()[1]


vaz = defaultdict(lambda: [0.0, 0.0, 0, 0])  # sem -> [hh_fech, hh_cri, n_fech, n_cri]
for t in T:
    df_ = d(t.get('dataFinal'))
    dc = d(t.get('criacao'))
    if df_ and dt.datetime(2026, 8, 24) <= df_ < dt.datetime(2026, 10, 5):
        v = vaz[semana_iso(df_)]
        v[0] += HH(t); v[2] += 1
    if dc and dt.datetime(2026, 8, 24) <= dc < dt.datetime(2026, 10, 5):
        v = vaz[semana_iso(dc)]
        v[1] += HH(t); v[3] += 1
vazao = {s: dict(hh_fech=round(v[0]), hh_cri=round(v[1]), n_fech=v[2], n_cri=v[3])
         for s, v in sorted(vaz.items())}

# ── C. restricao por equipe: fila HH + W41 HH vs vazao media 4 sem ──
eq = defaultdict(lambda: dict(fila_hh=0.0, fila_n=0, w41_hh=0.0, w41_n=0,
                              vaz_hh=0.0))
for t in ab:
    r = t.get('responsavel') or 'Sem responsável'
    eq[r]['fila_hh'] += HH(t)
    eq[r]['fila_n'] += 1
for t in T:
    df_ = d(t.get('dataFinal'))
    if df_ and dt.datetime(2026, 9, 7) <= df_ < dt.datetime(2026, 10, 5):
        r = t.get('responsavel') or 'Sem responsável'
        eq[r]['vaz_hh'] += HH(t) / 4.0  # media semanal
w41 = next(s for s in b['semanas'] if s['week'] == '2026-W41')
rows41 = [r for r in w41['rows'] if 'teste' not in str(r.get('usina', '')).lower()]
for r in rows41:
    e = eq[r.get('responsavel') or 'Sem responsável']
    e['w41_hh'] += float(r.get('duracao') or 0)
    e['w41_n'] += 1
equipes = []
for nome, e in eq.items():
    if e['fila_n'] < 20 and e['w41_n'] < 20:
        continue
    vaz_ = e['vaz_hh'] or 1.0
    equipes.append(dict(
        nome=nome, fila_hh=round(e['fila_hh']), fila_n=e['fila_n'],
        w41_hh=round(e['w41_hh']), w41_n=e['w41_n'], vaz_hh=round(e['vaz_hh']),
        sem_drenar=round((e['fila_hh']) / vaz_, 1),
        carga_w41=round(e['w41_hh'] / vaz_, 2)))
equipes.sort(key=lambda x: -x['sem_drenar'])

# ── D. handover e MPAS detalhe ───────────────────────────────────────
ho = [t for t in ab if grupo(t['tipo'], t.get('tarefa','')) == 'Handover']
ho_u = defaultdict(lambda: [0, 0.0, 0])
for t in ho:
    v = ho_u[t['usina']]
    v[0] += 1; v[1] += HH(t); v[2] = max(v[2], t.get('dias') or 0)
ho_top = sorted([dict(u=u, n=v[0], hh=round(v[1]), dias=v[2])
                 for u, v in ho_u.items()], key=lambda x: -x['hh'])[:8]
mpas = [t for t in ab if grupo(t['tipo'], t.get('tarefa','')) in ('MPA', 'MPS')]
mpas_u = defaultdict(lambda: [0, 0.0, 0])
for t in mpas:
    v = mpas_u[t['usina']]
    v[0] += 1; v[1] += HH(t); v[2] = max(v[2], t.get('dias') or 0)
mpas_top = sorted([dict(u=u, n=v[0], hh=round(v[1]), dias=v[2])
                   for u, v in mpas_u.items()], key=lambda x: -x['hh'])[:8]

# ── E. W41: composicao e rolagens ────────────────────────────────────
w41_comp = defaultdict(lambda: [0, 0.0])
rolag = 0
for r in rows41:
    gp = grupo(r.get('tipo'), r.get('tarefa',''))
    w41_comp[gp][0] += 1
    w41_comp[gp][1] += float(r.get('duracao') or 0)
    if gp == 'Corretiva' and (r.get('vezes') or 0) >= 3:
        rolag += 1
w41_comp = {k: dict(n=v[0], hh=round(v[1])) for k, v in w41_comp.items()}

out = dict(
    geradoEm=g['geradoEm'],
    fila=dict(fila), vazao=vazao, equipes=equipes,
    handover_top=ho_top, mpas_top=mpas_top,
    w41=dict(total=len(rows41), comp=w41_comp, corr_rolagem3=rolag),
    totais=dict(abertas=len(ab), hh_fila=round(sum(HH(t) for t in ab)),
                atrasadas=sum(1 for t in ab if t.get('atrasado'))))
io.open('_toc41.json', 'w', encoding='utf-8').write(
    json.dumps(out, ensure_ascii=False, indent=1))
print('FILA:', {k: (v['n'], v['hh']) for k, v in fila.items()})
print('VAZAO:', vazao)
print('EQUIPES (fila_hh, vaz_hh/sem, semanas p/ drenar, carga W41):')
for e in equipes[:10]:
    print('  %-22s fila=%5d HH | vaz=%4d HH/sem | drenar=%5.1f sem | W41=%4d HH (%.1fx)'
          % (e['nome'][:22], e['fila_hh'], e['vaz_hh'], e['sem_drenar'],
             e['w41_hh'], e['carga_w41']))
print('TOTAIS:', out['totais'])
