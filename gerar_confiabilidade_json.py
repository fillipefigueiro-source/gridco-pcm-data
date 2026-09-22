# -*- coding: utf-8 -*-
"""Gera confiabilidade.json — MTBF / MTTR / Disponibilidade Inerente por ATIVO
(agrupado por usina), calculado POR TAREFA sobre os tipos de falha definidos.

Reproduz o cálculo do Power BI da Grid Co.:
  MTBF (h)  = Uptime_do_equipamento / nº de tarefas de falha
              onde Uptime = horas(mobilização → agora) − horas de parada (falhas)
  MTTR (h)  = média, por tarefa concluída (Data do evento + Data fim válidos), de
              horas = dias*24 se dias<=1, senão dias*12  (12h/dia p/ eventos multi-dia)
  Disp.     = MTBF / (MTBF + MTTR)

Mobilização vem da AUXILIAR ("Data Mobilização"); sem data válida → DataInicioSistema.
Fonte de dados: API Fracttal via fonte_bd_api (mesmo pipeline dos outros scripts).
"""
import io, sys, os, re, json, unicodedata
from datetime import datetime
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DATA_INICIO = pd.Timestamp(2025, 10, 20)          # DataInicioSistema (DAX)
TIPOS_FALHA = ['Corretiva', 'Corretiva Emergencial', 'Religamento', 'Religamento Remoto']

BASE_DIR = os.environ.get('PCM_PROG_DIR') or os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE_DIR, 'confiabilidade.json')
AUX_PATH = os.environ.get('CONFIAB_AUXILIAR_PATH') or os.path.join(BASE_DIR, 'AUXILIAR - FABRICIO.xlsx')


def _nz(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', s).strip()


def limpa_ativo(a):
    a = re.sub(r'\{[^}]*\}', '', str(a))          # tira código { USINA-EQP }
    a = re.split(r'\s{2,}', a)[0].strip()          # tira marca/endereço após 2+ espaços
    return a or str(a)


def carregar_aux():
    """Retorna (mob_map, cli_map): usina_norm -> Data Mobilização / CLIENTE."""
    mob, cli = {}, {}
    try:
        aux = pd.read_excel(AUX_PATH, sheet_name=0)
    except Exception as e:
        print(f'[AVISO] AUXILIAR não lida ({e}); mobilização usará {DATA_INICIO.date()} p/ todas.')
        return mob, cli
    col_ufv = next((c for c in aux.columns if str(c).strip().upper() == 'UFV'), None)
    col_mob = next((c for c in aux.columns if 'mobiliza' in str(c).lower()), None)
    col_cli = next((c for c in aux.columns if str(c).strip().upper() == 'CLIENTE'), None)
    for _, r in aux.iterrows():
        u = r.get(col_ufv) if col_ufv else None
        if not isinstance(u, str) or not u.strip():
            continue
        un = _nz(u)
        if col_mob is not None:
            dm = r.get(col_mob)
            dt = (pd.to_datetime(dm, errors='coerce', unit='D', origin='1899-12-30')
                  if isinstance(dm, (int, float)) else pd.to_datetime(dm, errors='coerce'))
            if pd.notna(dt):
                mob[un] = dt
        if col_cli is not None and isinstance(r.get(col_cli), str):
            cli[un] = r.get(col_cli).strip()
    print(f'[INFO] AUXILIAR: {len(mob)} datas de mobilização, {len(cli)} clientes.')
    return mob, cli


def _lookup(mp, usina):
    n = _nz(usina)
    if n in mp:
        return mp[n]
    for k, v in mp.items():
        if n.startswith(k) or k.startswith(n):
            return v
    return None


def main():
    _pkl = os.environ.get('CONFIAB_LOCAL_PKL')
    if _pkl and os.path.exists(_pkl):
        print(f'[INFO] Carregando base do cache local: {_pkl}')
        df = pd.read_pickle(_pkl)
    else:
        import fonte_bd_api
        print('[INFO] Carregando base via API Fracttal…')
        df = fonte_bd_api.df_semanal()
    df = df[df['Status'].astype(str) != 'Cancelado'].copy()
    agora = pd.Timestamp(datetime.now())

    mob_map, cli_map = carregar_aux()

    fal = df[df['Tipo de tarefa'].astype(str).str.strip().isin(TIPOS_FALHA)].copy()
    for c in ['Data inicial', 'Data final', 'Data do Incidente']:
        fal[c] = pd.to_datetime(fal[c], errors='coerce')
    fal['usina'] = fal['Ativo Classificação 1'].astype(str)
    fal['ativo'] = fal['Ativo'].astype(str)
    fal = fal[(fal['usina'] != 'nan') & (fal['usina'].str.strip() != '') &
              (~fal['usina'].str.lower().str.contains('teste', na=False))]
    print(f'[INFO] {len(fal)} tarefas de falha em {fal["usina"].nunique()} usinas.')

    def horas(a, b):
        if pd.isna(a) or pd.isna(b):
            return 0.0
        return max(0.0, (b - a).total_seconds() / 3600.0)

    def bloco(sub, mob_eff):
        """Calcula (mtbf, mttr, disp, n) para um conjunto de tarefas de falha."""
        s_dt = sub[sub['Data inicial'] >= mob_eff]
        downtime = sum(horas(r['Data inicial'],
                             r['Data final'] if pd.notna(r['Data final']) else agora)
                       for _, r in s_dt.iterrows())
        horas_desde_mob = max(0.0, (agora - mob_eff).total_seconds() / 3600.0)
        uptime = max(0.0, horas_desde_mob - downtime)
        n = int((sub['Data inicial'] >= DATA_INICIO).sum())
        mtbf = uptime / n if n else None
        conc = sub[sub['Data do Incidente'].notna() & sub['Data final'].notna() &
                   (sub['Data final'] >= sub['Data do Incidente'])]
        if len(conc):
            difd = (conc['Data final'] - conc['Data do Incidente']).dt.total_seconds() / 86400.0
            mttr = float(difd.apply(lambda d: d * 12 if d * 24 > 24 else d * 24).mean())
        else:
            mttr = None
        disp = (mtbf / (mtbf + mttr)) if (mtbf and mttr is not None and (mtbf + mttr) > 0) else None
        return mtbf, mttr, disp, n, uptime

    def mttr_de(sub):
        conc = sub[sub['Data do Incidente'].notna() & sub['Data final'].notna() &
                   (sub['Data final'] >= sub['Data do Incidente'])]
        if not len(conc):
            return None
        difd = (conc['Data final'] - conc['Data do Incidente']).dt.total_seconds() / 86400.0
        return float(difd.apply(lambda d: d * 12 if d * 24 > 24 else d * 24).mean())

    from collections import defaultdict
    cli_acc = defaultdict(lambda: {'uptime': 0.0, 'n': 0, 'usinas': [], '_subs': []})
    for usina, sub_u in fal.groupby('usina'):
        m = _lookup(mob_map, usina)
        mob_eff = max(m, DATA_INICIO) if m is not None else DATA_INICIO
        cliente = _lookup(cli_map, usina) or (usina.split(' - ')[0].strip() if ' - ' in usina else usina)
        ativos = []
        for ativo, s in sub_u.groupby('ativo'):
            mtbf, mttr, disp, n, _ = bloco(s, mob_eff)
            tarefas = []
            for _, r in s.sort_values('Data inicial', ascending=False).iterrows():
                ev, fim = r['Data do Incidente'], r['Data final']
                h = None
                if pd.notna(ev) and pd.notna(fim) and fim >= ev:
                    d = (fim - ev).total_seconds() / 86400.0
                    h = round(d * 12 if d * 24 > 24 else d * 24, 2)
                tarefas.append({'os': str(r.get('OSs ID', '')).split('.')[0],
                                'tarefa': str(r.get('Tarefa') or '').strip(),
                                'tipo': str(r.get('Tipo de tarefa') or '').strip(),
                                'inicio': _iso(r['Data inicial']), 'fim': _iso(r['Data final']),
                                'estado': str(r.get('Estado da Tarefa') or '').strip(), 'horas': h})
            ativos.append({'ativo': limpa_ativo(ativo), 'mtbf': _r(mtbf), 'mttr': _r(mttr, 2),
                           'disp': _r(disp, 4), 'n': n, 'tarefas': tarefas})
        ativos.sort(key=lambda x: -x['n'])
        umtbf, umttr, udisp, un, uupt = bloco(sub_u, mob_eff)
        usina_dict = {'usina': usina, 'cliente': cliente,
                      'mobilizacao': (mob_eff.date().isoformat() if m is not None else None),
                      'mtbf': _r(umtbf), 'mttr': _r(umttr, 2), 'disp': _r(udisp, 4),
                      'n': un, 'ativos': ativos}
        c = cli_acc[cliente]
        c['uptime'] += uupt; c['n'] += un
        c['usinas'].append(usina_dict); c['_subs'].append(sub_u)

    clientes_out = []
    for cliente, c in cli_acc.items():
        cmtbf = c['uptime'] / c['n'] if c['n'] else None
        cmttr = mttr_de(pd.concat(c['_subs'])) if c['_subs'] else None
        cdisp = (cmtbf / (cmtbf + cmttr)) if (cmtbf and cmttr is not None and (cmtbf + cmttr) > 0) else None
        c['usinas'].sort(key=lambda x: x['usina'].lower())
        clientes_out.append({'cliente': cliente, 'mtbf': _r(cmtbf), 'mttr': _r(cmttr, 2),
                             'disp': _r(cdisp, 4), 'n': c['n'], 'usinas': c['usinas']})
    clientes_out.sort(key=lambda x: x['cliente'].lower())

    # ── MTTR por Equipe Cluster (Ativo Classificação 2) ──────────────────────
    # Casing inconsistente no Fracttal ("PA NORTE 01" vs "PA Norte 01") → agrupa
    # case-insensitive e exibe a grafia mais frequente (merge dos dois num só).
    fal['cluster'] = fal['Ativo Classificação 2'].astype(str).str.strip()
    fal['_ck'] = fal['cluster'].str.upper()
    _validc = fal[(fal['cluster'] != '') & (fal['cluster'].str.lower() != 'nan')]
    _canon = {}
    for ck, s in _validc.groupby('_ck'):
        m = s['cluster'].mode()
        _canon[ck] = m.iat[0] if len(m) else s['cluster'].iat[0]
    clusters_out = []
    for ckey, sc in fal.groupby('_ck'):
        cluster = _canon.get(ckey)
        if not cluster:
            continue
        cliente_c = _lookup(cli_map, sc['usina'].iloc[0]) or (
            sc['usina'].iloc[0].split(' - ')[0].strip() if ' - ' in sc['usina'].iloc[0] else '')
        usinas_c = []
        for usina, su in sc.groupby('usina'):
            usinas_c.append({'usina': usina, 'mttr': _r(mttr_de(su), 2), 'n': int(len(su))})
        usinas_c.sort(key=lambda x: -(x['mttr'] or 0))
        clusters_out.append({'cluster': cluster, 'cliente': cliente_c,
                             'mttr': _r(mttr_de(sc), 2), 'n': int(len(sc)), 'usinas': usinas_c})
    clusters_out.sort(key=lambda x: -(x['mttr'] or 0))   # pior (mais lento) primeiro

    out = {'geradoEm': datetime.now().isoformat(timespec='seconds'),
           'tiposFalha': TIPOS_FALHA,
           'dataInicioSistema': DATA_INICIO.date().isoformat(),
           'totalClientes': len(clientes_out),
           'totalUsinas': sum(len(c['usinas']) for c in clientes_out),
           'totalClusters': len(clusters_out),
           'clientes': clientes_out,
           'clusters': clusters_out}
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    print(f'[OK] {OUT} — {len(clientes_out)} clientes, {out["totalUsinas"]} usinas, '
          f'{sum(len(u["ativos"]) for c in clientes_out for u in c["usinas"])} ativos.')


def _r(v, nd=1):
    return round(float(v), nd) if v is not None else None


def _iso(dt):
    return dt.date().isoformat() if pd.notna(dt) else None


if __name__ == '__main__':
    main()
