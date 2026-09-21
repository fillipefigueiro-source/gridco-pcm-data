# -*- coding: utf-8 -*-
"""Cruza usinas com MPA/MPS abertas (_semana39_dados.json) com a aba MPAS da
Gerencial - PCM_2026_R00 (Criticidade + Observacao). Gera _s39_mpas_obs.json."""
import io, json, re, unicodedata
import pandas as pd

P = (r'C:\Users\Fabricio Barreto\OneDrive - GRID CO\Shortcuts'
     r'\GRID CO_ - 4. O&M\11.Pré-Operação\1. Gerencial'
     r'\4. Gerencial - MPAS e Zeladoria\Gerencial - PCM_2026_R00.xlsx')

FECHADOS = {'finalizado', 'cancelado'}


def norm(u):
    s = unicodedata.normalize('NFKD', str(u)).encode('ascii', 'ignore').decode()
    s = s.lower().strip()
    s = re.sub(r'\s*-\s*[a-z]{2}$', '', s)          # tira UF do nome do Fracttal
    s = re.sub(r'\b([1-9])00\b', r'\1', s)           # 100->1, 200->2...
    s = re.sub(r'[^a-z0-9]+', ' ', s).strip()
    s = s.replace('utragaz', 'ultragaz').replace('ultraltragaz', 'ultragaz')
    return s


def candidatos(n):
    """Variantes do nome do Fracttal para casar com a grafia da planilha."""
    c = [n]
    c.append(re.sub(r'\s+e\s+\d$', '', n))           # 'tupi paulista 1 e 2' -> '... 1'
    c.append(re.sub(r'\s+\d$', '', n))               # 'indaiatuba 1' -> 'indaiatuba'
    c.append(re.sub(r'\s+1$', ' ia', n))             # 'aracoiaba ... 1' -> '... ia'
    c.append(re.sub(r'\s+2$', ' ib', n))             # 'aracoiaba ... 2' -> '... ib'
    sem_e = re.sub(r'\s+e\s+\d$', '', n)
    c.append(re.sub(r'\s+\d$', '', sem_e))
    vistos, out = set(), []
    for x in c:
        if x and x not in vistos:
            vistos.add(x)
            out.append(x)
    return out


PRIO = {'em execução': 0, 'refazer pendências': 1, 'pendente envio relatório': 2,
        'programado': 3, 'programar': 4}
df = pd.read_excel(P, sheet_name='MPAS', header=3)
mapa = {}
for r in df.to_dict('records'):
    tipo = str(r.get('Tipo de manutenção') or '').strip().upper()
    if tipo not in ('MPA', 'MPS'):
        continue
    status = str(r.get('Status') or '').strip()
    if status.lower() in FECHADOS or status.lower() == 'nan':
        continue
    obs = str(r.get('Observação') or '').strip()
    crit = str(r.get('Criticidade') or '').strip()
    novo = dict(crit=('' if crit.lower() == 'nan' else crit),
                obs=('' if obs.lower() == 'nan' else obs), status=status)
    key = (norm(r.get('Usina')), tipo)
    velho = mapa.get(key)
    if velho:  # prefere a linha com observacao; empate decide pelo status
        if (bool(velho['obs']), -PRIO.get(velho['status'].lower(), 9)) >= \
           (bool(novo['obs']), -PRIO.get(novo['status'].lower(), 9)):
            continue
    mapa[key] = novo

D = json.load(io.open('_semana39_dados.json', encoding='utf-8'))
out, miss = {}, []
for c in D['clientes']:
    ent = []
    for tipo, usinas in (('MPA', c['mpa_usinas']), ('MPS', c['mps_usinas'])):
        for u in usinas:
            m = None
            for cand in candidatos(norm(u)):
                m = mapa.get((cand, tipo))
                if m:
                    break
            if m:
                ent.append(dict(u=u, tipo=tipo, **m))
            else:
                miss.append('%s [%s] -> %s' % (u, tipo, norm(u)))
    if ent:
        out[c['cli']] = ent
io.open('_s39_mpas_obs.json', 'w', encoding='utf-8').write(
    json.dumps(out, ensure_ascii=False, indent=1))
print('clientes com match:', {k: len(v) for k, v in out.items()})
print('SEM MATCH (%d):' % len(miss))
for m in miss:
    print('  ', m)
