# -*- coding: utf-8 -*-
"""Dados para a apresentacao Inicio Semana 39 (21 a 25/09/2026).
Visao por CLIENTE: corretivas abertas, backlog +30d, MPA/MPS abertas e
vencidas, MPM de setembro, oleo — tudo direto da API Fracttal."""
import io, json, re
import datetime as dt
from collections import defaultdict
import pandas as pd
import fonte_bd_api as F

HOJE = dt.datetime(2026, 9, 21)
SET_INI = dt.datetime(2026, 9, 1)
OUT_INI = dt.datetime(2026, 10, 1)
S37_INI = dt.datetime(2026, 9, 14)


def _d(v):
    x = pd.to_datetime(v, errors='coerce', dayfirst=True)
    return None if pd.isna(x) else x.to_pydatetime()


df = F.df_semanal()
regs = []
for r in df.to_dict('records'):
    if str(r.get('Status') or '').strip() == 'Cancelado':
        continue
    ufv = str(r.get('Ativo Classificação 1') or '').strip()
    if not ufv or ' - ' not in ufv:
        continue
    cli = ufv.split(' - ')[0].strip()
    regs.append(dict(
        os=str(r.get('OSs ID') or ''),
        cli=cli, ufv=ufv,
        cluster=str(r.get('Ativo Classificação 2') or '').strip(),
        tarefa=str(r.get('Tarefa') or ''),
        tipo=str(r.get('Tipo de tarefa') or ''),
        estado=str(r.get('Estado da Tarefa') or '').strip(),
        status=str(r.get('Status') or '').strip(),
        dprog=_d(r.get('Data Programada')) or _d(r.get('Data Calculada')),
        dfim=_d(r.get('Data final')),
        dcria=_d(r.get('Data de Criação da OS')),
    ))

SUP = json.load(io.open('supervisores.json', encoding='utf-8')).get('porCluster', {})
aberta = lambda x: x['estado'] != 'Finalizados' and x['status'] != 'Finalizados'
rx_mpa = re.compile(r'\bMPA\b', re.I)
rx_mps = re.compile(r'\bMPS\b', re.I)
rx_mpm = re.compile(r'\bMPM\b', re.I)
rx_oleo = re.compile(r'[óo]leo', re.I)
corr = lambda x: 'corretiv' in x['tipo'].lower()

CLI = defaultdict(lambda: dict(
    corr_ab_os=set(), corr_30d_os=set(), corr_usinas=set(),
    mpa_ab=set(), mpa_venc=set(), mps_ab=set(), mps_venc=set(),
    mpa_usinas=set(), mps_usinas=set(), mpa_antiga=None, mps_antiga=None,
    ho_ab=set(), ho_usinas=set(), ho_antiga=None,
    mpm_tot=0, mpm_fei=0, mpm_pend_usinas=set(),
    antiga=None, usinas_corr=defaultdict(set)))


def _mais_antiga(atual, x):
    if not x['dprog']:
        return atual
    dias = (HOJE - x['dprog']).days
    if atual is None or dias > atual['dias']:
        return dict(os=x['os'], u=x['ufv'], t=x['tarefa'][:60],
                    d=x['dprog'].strftime('%d/%m'), dias=dias)
    return atual

backlog_os = {}
for x in regs:
    c = CLI[x['cli']]
    ab = aberta(x)
    # corretivas abertas
    if corr(x) and ab:
        c['corr_ab_os'].add(x['os'])
        c['corr_usinas'].add(x['ufv'])
        c['usinas_corr'][x['ufv']].add(x['os'])
        if x['dprog'] and (HOJE - x['dprog']).days > 30:
            c['corr_30d_os'].add(x['os'])
    # MPA / MPS abertas e vencidas
    if ab and rx_mpa.search(x['tarefa']):
        c['mpa_ab'].add(x['os'])
        c['mpa_usinas'].add(x['ufv'])
        c['mpa_antiga'] = _mais_antiga(c['mpa_antiga'], x)
        if x['dprog'] and x['dprog'] < HOJE:
            c['mpa_venc'].add(x['os'])
    if ab and rx_mps.search(x['tarefa']):
        c['mps_ab'].add(x['os'])
        c['mps_usinas'].add(x['ufv'])
        c['mps_antiga'] = _mais_antiga(c['mps_antiga'], x)
        if x['dprog'] and x['dprog'] < HOJE:
            c['mps_venc'].add(x['os'])
    # Handover
    if ab and x['tipo'] == 'Handover':
        c['ho_ab'].add(x['os'])
        c['ho_usinas'].add(x['ufv'])
        c['ho_antiga'] = _mais_antiga(c['ho_antiga'], x)
    # MPM de setembro
    if rx_mpm.search(x['tarefa']) and x['dprog'] and SET_INI <= x['dprog'] < OUT_INI \
            and 'spare' not in x['tarefa'].lower():
        c['mpm_tot'] += 1
        if not ab:
            c['mpm_fei'] += 1
        else:
            c['mpm_pend_usinas'].add(x['ufv'])
    # OS aberta mais antiga do cliente (ignora handover)
    if ab and x['dprog'] and x['dprog'] < HOJE and x['tipo'] not in ('Handover',):
        dias = (HOJE - x['dprog']).days
        if c['antiga'] is None or dias > c['antiga']['dias']:
            c['antiga'] = dict(os=x['os'], u=x['ufv'], t=x['tarefa'][:60],
                               d=x['dprog'].strftime('%d/%m'), dias=dias)
        if dias > 30:
            e = backlog_os.setdefault(x['os'], dict(
                os=x['os'], u=x['ufv'], cli=x['cli'], dias=dias, tarefas=0,
                sup=SUP.get(x['cluster'], 'Sem cluster')))
            e['tarefas'] += 1
            e['dias'] = max(e['dias'], dias)

# ── consolida por cliente ────────────────────────────────────────────
clientes = []
for cli, c in CLI.items():
    if not (c['corr_ab_os'] or c['mpa_ab'] or c['mps_ab'] or c['mpm_tot']
            or c['ho_ab']):
        continue
    top_u = sorted(c['usinas_corr'].items(), key=lambda kv: -len(kv[1]))[:3]
    clientes.append(dict(
        cli=cli,
        corr_ab=len(c['corr_ab_os']), corr_30d=len(c['corr_30d_os']),
        usinas_corr=len(c['corr_usinas']),
        mpa_ab=len(c['mpa_ab']), mpa_venc=len(c['mpa_venc']),
        mps_ab=len(c['mps_ab']), mps_venc=len(c['mps_venc']),
        mpm_tot=c['mpm_tot'], mpm_fei=c['mpm_fei'],
        mpm_pct=round(100.0 * c['mpm_fei'] / c['mpm_tot']) if c['mpm_tot'] else None,
        mpm_pend_usinas=sorted(c['mpm_pend_usinas']),
        mpa_usinas=sorted(c['mpa_usinas']), mps_usinas=sorted(c['mps_usinas']),
        mpa_antiga=c['mpa_antiga'], mps_antiga=c['mps_antiga'],
        ho_ab=len(c['ho_ab']), ho_usinas=sorted(c['ho_usinas']),
        ho_antiga=c['ho_antiga'],
        antiga=c['antiga'],
        top_usinas=[dict(u=u, n=len(oss)) for u, oss in top_u]))
clientes.sort(key=lambda e: -(e['corr_ab'] + e['mpa_ab'] + e['mps_ab']))

# ── handover por usina (todas as OS abertas de tipo Handover) ───────
ho_u = {}
for x in regs:
    if aberta(x) and x['tipo'] == 'Handover':
        e = ho_u.setdefault(x['ufv'], dict(u=x['ufv'], cli=x['cli'], oss=set(),
                                           tarefas=0, antiga=None))
        e['oss'].add(x['os'])
        e['tarefas'] += 1
        e['antiga'] = _mais_antiga(e['antiga'], x)
handover = sorted(ho_u.values(),
                  key=lambda e: -(e['antiga']['dias'] if e['antiga'] else 0))
for e in handover:
    e['oss'] = sorted(e['oss'])

# ── globais ──────────────────────────────────────────────────────────
oleo_ab = [x for x in regs if rx_oleo.search(x['tarefa']) and aberta(x)]
mpm_tot = sum(e['mpm_tot'] for e in clientes)
mpm_fei = sum(e['mpm_fei'] for e in clientes)
bl = sorted(backlog_os.values(), key=lambda e: -e['dias'])
corr_criadas_s37 = len({x['os'] for x in regs if corr(x) and x['dcria']
                        and S37_INI <= x['dcria'] < HOJE})
fin_s37 = len({x['os'] for x in regs if x['dfim']
               and S37_INI <= x['dfim'] < HOJE})

out = dict(
    clientes=clientes,
    geral=dict(
        corr_ab=sum(e['corr_ab'] for e in clientes),
        corr_30d=sum(e['corr_30d'] for e in clientes),
        mpa_ab=sum(e['mpa_ab'] for e in clientes),
        mpa_venc=sum(e['mpa_venc'] for e in clientes),
        mps_ab=sum(e['mps_ab'] for e in clientes),
        mps_venc=sum(e['mps_venc'] for e in clientes),
        mpm_tot=mpm_tot, mpm_fei=mpm_fei,
        mpm_pct=round(100.0 * mpm_fei / mpm_tot) if mpm_tot else 0,
        backlog_os=len(bl), backlog_tarefas=sum(e['tarefas'] for e in bl),
        oleo_ab=len({x['os'] for x in oleo_ab}),
        ho_ab=sum(len(CLI[c['cli']]['ho_ab']) for c in clientes),
        corr_criadas_s37=corr_criadas_s37, fin_s37=fin_s37),
    backlog=bl,
    handover=handover,
    oleo=[dict(os=x['os'], u=x['ufv'], t=x['tarefa'][:60], estado=x['estado'])
          for x in oleo_ab][:10],
)
io.open('_semana39_dados.json', 'w', encoding='utf-8').write(
    json.dumps(out, ensure_ascii=False, indent=1, default=str))
g = out['geral']
print('clientes=%d | corr ab=%d (+30d %d) | MPA ab=%d venc=%d | MPS ab=%d venc=%d | '
      'MPM set %d/%d (%d%%) | backlog=%d OS | oleo=%d | s37: criadas=%d fin=%d'
      % (len(clientes), g['corr_ab'], g['corr_30d'], g['mpa_ab'], g['mpa_venc'],
         g['mps_ab'], g['mps_venc'], g['mpm_fei'], g['mpm_tot'], g['mpm_pct'],
         g['backlog_os'], g['oleo_ab'], g['corr_criadas_s37'], g['fin_s37']))
