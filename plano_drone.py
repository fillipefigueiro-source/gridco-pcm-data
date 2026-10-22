# -*- coding: utf-8 -*-
"""Plano de Acao Drone - termografia aerea pos-MPA (aba do Controle Semanal).

Chamado por controle_semanal.py, que passa o gestao_pcm.json ja baixado. As demais
fontes sao lidas em tempo de execucao, por caminho exato (nada e copiado para o git):
  - AUXILIAR - FABRICIO.xlsx (Operacoes_1): cliente, cluster, cidade/UF, coordenadas, STATUS
  - Gerencial - PCM_2026_R00.xlsx: "ENG - Acompanhamento Manutencao" (termografia) e
    "Zeladoria e MPAS" (status da MPA)
  - PCM 52 Semanas - R04.xlsx: data planejada da MPA (frequencia anual)

Rotas: Drone Grid A = ordem fixa definida pelo PCM (ROTA_A); Terceiro = os
BLOCOS_TERCEIRO blocos geograficos com a divida de MPA mais antiga; Drone Grid B = o
resto, em blocos regionais. Dentro do bloco, vizinho mais proximo a partir da maior
divida. Usina cuja termografia passa a constar (ENG ou Fracttal) sai sozinha do plano.

A coluna "Observacoes do time" e preservada pela chave K(usina) (nome normalizado),
independente de rota e ordem.
"""
import collections, datetime as dt, math, re, unicodedata

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

NOME = 'Plano de Ação Drone'
_RAIZ = r'C:\Users\Fabricio Barreto\OneDrive - GRID CO\Shortcuts\GRID CO_ - 4. O&M\11.Pré-Operação'
CAM_AUX = _RAIZ + r'\6. PCM\09. Programação Semanal\AUXILIAR - FABRICIO.xlsx'
CAM_GER = _RAIZ + r'\1. Gerencial\4. Gerencial - MPAS e Zeladoria\Gerencial - PCM_2026_R00.xlsx'
CAM_P52 = _RAIZ + r'\Modelo pasta - PCM\00_PCM 52 Semanas\PCM 52 Semanas - R04.xlsx'

CICLO = dt.date(2026, 6, 1)      # inicio do ciclo de MPA considerado
JANELA_LIMP = 90                 # limpeza mais antiga que isso -> recomendar limpeza
JANELA_TERMO = 120               # termografia ate N dias antes da MPA vale para o ciclo
RAIO_BLOCO = 350                 # km: bloco = usinas a ate RAIO_BLOCO (Terceiro: do semente)
BLOCOS_TERCEIRO = 2
PERTO_A = 30                     # km: avisa encaixe na Rota A
NAVY, CINZA, AMAR = '1C1F3B', '6B6880', 'FFF2CC'
COR = {'Drone Grid A': 'DDEBF7', 'Terceiro': 'FCE4D6', 'Drone Grid B': 'E2EFDA'}

# Drone Grid A: ordem fixa do PCM (chave normalizada, observacao, limpeza informada pelo PCM)
ROTA_A = [
    ('marialva', 'Lista do Fabrício: termografia em andamento', None),
    ('mandaguacu', 'Lista do Fabrício: limpeza 29/07', dt.date(2026, 7, 29)),
    ('elias fausto', 'Lista do Fabrício: limpeza 05/08', dt.date(2026, 8, 5)),
    ('indaiatuba', 'Lista do Fabrício: limpeza 10/08', dt.date(2026, 8, 10)),
    ('aparecida 3', 'Lista do Fabrício: limpeza 17/08', dt.date(2026, 8, 17)),
    ('matao 2', 'Lista do Fabrício: limpeza 01/08', dt.date(2026, 8, 1)),
    ('nova xavantina', 'Lista do Fabrício: limpeza 08/08', dt.date(2026, 8, 8)),
    ('nova xavantina 2', 'Lista do Fabrício: limpeza 15/08', dt.date(2026, 8, 15)),
    ('nobres', 'Lista do Fabrício: limpeza iniciada 20/08', dt.date(2026, 8, 20)),
    ('colider', 'Lista do Fabrício: limpeza início 31/08', dt.date(2026, 8, 31)),
    ('colider 2', 'Lista do Fabrício: limpeza início 07/09', dt.date(2026, 9, 7)),
]
MARIALVA = 'marialva'

ALIAS = {'topazio matao 2': 'matao 2', 'topazio': 'matao 2', 'santo inacio 12': 'santo inacio 1 e 2',
         'aracoiaba da serra ia': 'aracoiaba da serra', 'aracoiaba da serra ib': 'aracoiaba da serra 2',
         'campos dos goytacazes': 'goytacazes', 'tupi paulista 1 e 2': 'tupi paulista'}
_CLIENTES = (r'thopen|athon|axis|renogrid|greenyellow|gy|ultragaz|utragaz|2c|semp|gd energy|'
             r'sal energia|alves lima|elis energia|e1')

CAB = ['Rota', 'Ordem', 'Usina', 'Cliente', 'Cluster', 'Cidade/UF', 'Lat', 'Long',
       'Dist. do ponto anterior (km)', 'OS MPA', 'Data MPA (prog/exec)', 'Status termografia',
       'Dias em atraso', 'Última limpeza de módulos (Fracttal)', 'Dias desde a limpeza', 'Prioridade',
       'Observação (automática)', 'Ponto de entrega do drone']
LARG = [14, 7, 34, 12, 13, 24, 11, 11, 12, 18, 40, 46, 10, 15, 10, 16, 90, 22]
I_OBS = CAB.index('Observação (automática)')


def K(n):
    """chave estavel da usina (sem cliente, UF, acento; com apelidos)."""
    s = unicodedata.normalize('NFKD', str(n or '')).encode('ascii', 'ignore').decode().lower().strip()
    s = re.sub(r'^(%s)\s*-\s*' % _CLIENTES, '', s)
    s = re.sub(r'\s*-\s*[a-z]{2}\s*$', '', s)
    s = re.sub(r'[^a-z0-9 ]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'\b(\d)00\b', r'\1', s)
    s = ALIAS.get(s, s)
    s = re.sub(r' 1$', '', s)
    return ALIAS.get(s, s)


def D(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if not v:
        return None
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def num(v):
    if v is None or v == '':
        return None
    try:
        return float(str(v).replace('°', '').replace(',', '.').strip())
    except ValueError:
        return None


def hav(a, b):
    if not a or not b:
        return None
    la1, lo1 = map(math.radians, a)
    la2, lo2 = map(math.radians, b)
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def f(d):
    return d.strftime('%d/%m/%y') if d else '—'


# ── leitura das planilhas locais ─────────────────────────────────────
def ler_aux(cam=CAM_AUX):
    wb = openpyxl.load_workbook(cam, read_only=True, data_only=True)
    try:
        rows = wb['Operacoes_1'].iter_rows(values_only=True)
        hdr = None
        for r in rows:
            up = [str(c).strip().upper() if c is not None else '' for c in r]
            if 'UFV' in up and 'LATITUDE' in up:
                hdr = up
                break
        if not hdr:
            raise ValueError('cabecalho UFV/LATITUDE nao achado em Operacoes_1')
        want = ['UFV', 'CLIENTE', 'CLUSTER', 'CIDADE', 'UF', 'LATITUDE', 'LONGITUDE', 'STATUS']
        idx = {w: hdr.index(w) for w in want if w in hdr}
        out = []
        for r in rows:
            d = {w: (r[j] if j < len(r) else None) for w, j in idx.items()}
            if d.get('UFV'):
                out.append(d)
        return out
    finally:
        wb.close()


def ler_gerencial(cam=CAM_GER):
    wb = openpyxl.load_workbook(cam, read_only=True, data_only=True)
    try:
        zel = []
        for r in wb['Zeladoria e MPAS'].iter_rows(min_row=5, values_only=True):
            if len(r) > 10 and r[8] and 'MPA' in str(r[8]).upper():
                zel.append(dict(usina=r[3], status=r[10]))
        eng = []
        for r in wb['ENG - Acompanhamento Manutenção'].iter_rows(min_row=5, values_only=True):
            if len(r) > 20 and r[2]:
                eng.append(dict(usina=r[2], ativ=r[4], os=r[7], ini=D(r[9]), fin=D(r[14]), termo=r[20]))
        return zel, eng
    finally:
        wb.close()


def ler_p52(cam=CAM_P52):
    wb = openpyxl.load_workbook(cam, read_only=True, data_only=True)
    try:
        nome = next(n for n in wb.sheetnames if n.strip() == 'PCM 52 Semanas')
        mpa = {}
        for r in wb[nome].iter_rows(min_row=2, values_only=True):
            if len(r) > 8 and r[4] and str(r[8] or '').strip().lower() == 'anual' and D(r[2]):
                k = K(r[4])
                mpa[k] = min(mpa.get(k, D(r[2])), D(r[2]))
        return mpa
    finally:
        wb.close()


# ── calculo ──────────────────────────────────────────────────────────
def calcular(gestao, hoje=None, aux_rows=None, ger=None, p52=None):
    hoje = hoje or dt.date.today()
    corte_limp = hoje - dt.timedelta(days=JANELA_LIMP)
    aux_rows = ler_aux() if aux_rows is None else aux_rows
    zel_rows, eng_rows = ler_gerencial() if ger is None else ger
    p52 = ler_p52() if p52 is None else p52

    aux, auxfin = {}, set()
    for a in aux_rows:
        k = K(a['UFV'])
        if str(a.get('STATUS')).upper() == 'FINALIZADO':
            auxfin.add(k)
            continue
        aux.setdefault(k, a)
    U = collections.defaultdict(lambda: dict(mpa=collections.defaultdict(list), limp=[], limp_ab=[], drone=[],
                                             cli=None, cluster=None, nome=None))
    for t in gestao.get('tarefas', []):
        if 'teste' in str(t.get('usina', '')).lower():
            continue
        k = K(t.get('usina'))
        u = U[k]
        u['nome'] = u['nome'] or t.get('usina')
        u['cli'] = u['cli'] or t.get('cliente')
        u['cluster'] = u['cluster'] or t.get('cluster')
        nm = str(t.get('tarefa') or '')
        if re.search(r'\bMPA\b', nm) and not re.search(r'pend[êe]ncia', nm, re.I):
            u['mpa'][t['os']].append(t)
        if re.search(r'limpeza.{0,25}m[óo]dulos|limpeza geral em m|lavagem de m[óo]dulos|'
                     r'limpeza pontual (dos|em|de) m', nm, re.I) and not re.search(r'TCU|teste', nm, re.I):
            (u['limp'] if t.get('estado') == 'Finalizada' else u['limp_ab']).append(t)
        if re.search(r'termografia com drone', nm, re.I):
            u['drone'].append(t)
    zel = {}
    for r in zel_rows:
        zel.setdefault(K(r['usina']), r)
    eng = collections.defaultdict(list)
    for r in eng_rows:
        eng[K(r['usina'])].append(r)

    def info(k):
        o = dict(k=k, oss=[], n=0, nf=0, modab=False, modfin=None, ini=None, prog=None, ref=None,
                 limp=None, limp_ab=[], drone=[])
        a = aux.get(k)
        if a:
            o.update(aux_nome=a.get('UFV'), cidade=a.get('CIDADE'), uf=a.get('UF'), lat=num(a.get('LATITUDE')),
                     lon=num(a.get('LONGITUDE')), cli_aux=a.get('CLIENTE'), cluster_aux=a.get('CLUSTER'))
        z = zel.get(k)
        o['zel'] = z['status'] if z else None
        u = U.get(k)
        if not u:
            return o
        o.update(nome=u['nome'], cli=u['cli'], cluster=u['cluster'])
        oss = []
        for os_, ts in u['mpa'].items():
            progs = [D(t.get('dataProg')) for t in ts if D(t.get('dataProg'))]
            if not progs or max(progs) < CICLO:
                continue
            fin = [t for t in ts if t.get('estado') == 'Finalizada']
            oss.append(dict(
                os=os_, n=len(ts), nf=len(fin), prog=min(progs),
                ini=min([D(t.get('dataInicio')) for t in ts if D(t.get('dataInicio'))], default=None),
                fim=max([D(t.get('dataFinal')) for t in fin if D(t.get('dataFinal'))], default=None),
                mod=[(t.get('estado'), D(t.get('dataFinal'))) for t in ts
                     if re.search(r'm[óo]dulo|string e conjunto', str(t.get('tarefa') or ''), re.I)]))
        oss.sort(key=lambda x: x['prog'])
        o['oss'] = oss
        o['n'] = sum(x['n'] for x in oss)
        o['nf'] = sum(x['nf'] for x in oss)
        modfin = sorted(d for x in oss for e, d in x['mod'] if e == 'Finalizada' and d)
        o['modab'] = any(e != 'Finalizada' for x in oss for e, d in x['mod'])
        o['prog'] = oss[0]['prog'] if oss else None
        o['ini'] = min([x['ini'] for x in oss if x['ini']], default=None)
        o['modfin'] = modfin[0] if modfin else None
        o['ref'] = o['modfin'] or o['ini']
        lim = sorted(D(t.get('dataFinal')) for t in u['limp'] if D(t.get('dataFinal')))
        o['limp'] = lim[-1] if lim else None
        o['limp_ab'] = [(t['os'], str(t.get('estado') or ''), t.get('dataProg')) for t in u['limp_ab']]
        o['drone'] = [(t.get('estado'), D(t.get('dataFinal'))) for t in u['drone']]
        return o

    def termo_feita(k, o):
        ref = o.get('ref') or o.get('prog')
        lim = (ref - dt.timedelta(days=JANELA_TERMO)) if ref else CICLO
        for r in eng.get(k, []):
            d = D(r['termo']) if isinstance(r['termo'], (dt.date, dt.datetime)) or re.match(r'\d{4}-', str(r['termo'] or '')) else None
            if d and d >= lim:
                return 'ENG %s' % d.strftime('%d/%m/%Y')
        for e, d in o.get('drone', []):
            if e == 'Finalizada' and d and d >= lim:
                return 'Fracttal drone %s' % d.strftime('%d/%m/%Y')
        return None

    def termo_na(k, o):
        oss = {str(x['os']) for x in o.get('oss', [])}
        for r in eng.get(k, []):
            if r['ativ'] == 'MPA' and str(r['termo']).upper() == 'N/A' and \
                    any(s in oss for s in re.split(r'[/ ,]+', str(r['os']))):
                return True
        return False

    akeys = {a[0] for a in ROTA_A}
    pend, excl, depois = [], [], []
    for k in list(U):
        if k in akeys:
            continue
        o = info(k)
        if not o['oss']:
            continue
        if k in auxfin:
            excl.append((k, 'AUXILIAR com STATUS FINALIZADO'))
            continue
        if termo_na(k, o):
            excl.append((k, 'termografia N/A na ENG para esta MPA'))
            continue
        tf = termo_feita(k, o)
        if tf:
            excl.append((k, 'termografia registrada (' + tf + ')'))
            continue
        if not (o['modfin'] or (o['n'] and o['nf'] / o['n'] >= 0.5)):
            depois.append((k, 'MPA %d/%d, módulos não executados' % (o['nf'], o['n'])))
            continue
        o['origem'] = 'MPA'
        pend.append(o)
    pk = {o['k'] for o in pend}
    for k in list(eng):
        if k in akeys or k in pk or k in auxfin:
            continue
        ps = [r for r in eng[k] if r['ativ'] == 'MPS' and str(r['termo']).upper() == 'PENDENTE']
        if ps:
            o = info(k)
            r = ps[-1]
            o.update(origem='MPS', ref=r['fin'], mps_os=r['os'], mps_ini=r['ini'], mps_fin=r['fin'])
            pend.append(o)
    for o in pend:
        o['debt'] = (hoje - o['ref']).days if o.get('ref') else None

    # Rota A (fixa): sai quem ja tem termografia registrada ou contrato encerrado
    rota_a = []
    for k, ob, li in ROTA_A:
        o = info(k)
        if k in auxfin:
            excl.append((k, 'Rota A: AUXILIAR com STATUS FINALIZADO'))
            continue
        tf = termo_feita(k, o)
        if tf:
            excl.append((k, 'Rota A: termografia registrada (' + tf + ')'))
            continue
        rota_a.append((o, ob, li))

    ctx = dict(hoje=hoje, corte_limp=corte_limp, eng=eng, p52=p52)
    linhas, chaves, resumo = [], [], []

    def add(rota, ordem, o, ant, extra, limp_inf=None, prefixo=None):
        ln, p, d = _linha(ctx, rota, ordem, o, ant, extra, limp_inf)
        if prefixo:
            ln[I_OBS] = prefixo + ' | ' + ln[I_OBS]
        linhas.append(ln)
        chaves.append(o['k'])
        return p, d

    # Drone Grid A
    ant, km = None, 0
    for i, (o, ob, li) in enumerate(rota_a, 1):
        p, d = add('Drone Grid A', i, o, ant, [ob], li)
        ant = p or ant
        km += d or 0
    resumo.append(('Drone Grid A', len(rota_a), km, 'Ordem fixa do PCM (lista do Fabrício)'))

    # blocos: Terceiro = semente com a maior divida de MPA + vizinhas no raio
    resto = {o['k']: o for o in pend}
    terc = []
    for _ in range(BLOCOS_TERCEIRO):
        cand = [o for o in resto.values() if o['origem'] == 'MPA' and o['debt'] is not None and _pt(o)]
        if not cand:
            break
        sem = max(cand, key=lambda o: o['debt'])
        bl = [o for o in resto.values() if _pt(o) and hav(_pt(sem), _pt(o)) <= RAIO_BLOCO]
        for o in bl:
            resto.pop(o['k'])
        terc.append(bl)
    blocos_b = _agrupar(list(resto.values()))
    blocos_b = _ordenar_blocos(blocos_b)

    pts_a = [(o, _pt(o)) for o, _, _ in rota_a if _pt(o)]

    def rota_blocos(rota, blocos, rotulo):
        ant, km, n, comp = None, 0, 0, []
        for b, bl in enumerate(blocos, 1):
            nome_b = rotulo(b, bl)
            kb = 0
            for j, o in enumerate(_nn(bl)):
                n += 1
                extra = [nome_b]
                pa = _pt(o)
                for oa, ppa in pts_a:
                    dd = hav(pa, ppa)
                    if dd is not None and dd <= PERTO_A:
                        extra.append('a ~%d km de %s (Drone Grid A): avaliar encaixe na Rota A'
                                     % (round(dd), oa.get('aux_nome') or oa.get('nome') or oa['k']))
                p, d = add(rota, n, o, ant, extra, prefixo='deslocamento entre blocos' if ant and j == 0 else None)
                if not (ant and j == 0):
                    kb += d or 0
                ant = p or ant
                km += d or 0
            comp.append('%s: %d km' % (nome_b, kb))
        return n, km, '; '.join(comp) + (' (total inclui deslocamentos entre blocos)' if len(blocos) > 1 else '')

    n, km, comp = rota_blocos('Terceiro', terc, lambda b, bl: 'Bloco %d – %s' % (b, _ufs(bl)))
    resumo.append(('Terceiro', n, km, comp))
    n, km, comp = rota_blocos('Drone Grid B', blocos_b, lambda b, bl: 'Bloco ' + _ufs(bl))
    resumo.append(('Drone Grid B', n, km, comp))
    return dict(linhas=linhas, chaves=chaves, resumo=resumo, excl=excl, depois=depois, hoje=hoje,
                corte_limp=corte_limp)


def _pt(o):
    return (o['lat'], o['lon']) if o.get('lat') is not None and o.get('lon') is not None else None


def _ufs(bl):
    vis = []
    for o in sorted(bl, key=lambda o: -(o.get('debt') or 0)):
        uf = str(o.get('uf') or '?').strip().upper()
        if uf not in vis:
            vis.append(uf)
    return '/'.join(vis)


def _agrupar(itens):
    """blocos por ligacao simples: <= RAIO_BLOCO km ou mesma UF."""
    pai = list(range(len(itens)))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i
    for i in range(len(itens)):
        for j in range(i + 1, len(itens)):
            a, b = itens[i], itens[j]
            d = hav(_pt(a), _pt(b))
            mesma_uf = a.get('uf') and str(a.get('uf')).strip().upper() == str(b.get('uf') or '').strip().upper()
            if (d is not None and d <= RAIO_BLOCO) or mesma_uf:
                pai[raiz(i)] = raiz(j)
    g = collections.defaultdict(list)
    for i, o in enumerate(itens):
        g[raiz(i)].append(o)
    return list(g.values())


def _nn(itens):
    """vizinho mais proximo, comecando pela maior divida; sem coordenada vai ao fim."""
    com = sorted([o for o in itens if _pt(o)], key=lambda o: -(o.get('debt') or 0))
    sem = [o for o in itens if not _pt(o)]
    seq = [com.pop(0)] if com else []
    while com:
        p = _pt(seq[-1])
        com.sort(key=lambda o: hav(p, _pt(o)))
        seq.append(com.pop(0))
    return seq + sem


def _ordenar_blocos(blocos):
    """comeca pelo bloco com a maior divida; depois o bloco mais proximo do ultimo ponto."""
    if not blocos:
        return []
    rest = sorted(blocos, key=lambda bl: -max((o.get('debt') or 0) for o in bl))
    seq = [rest.pop(0)]
    while rest:
        fim = next((_pt(o) for o in reversed(_nn(seq[-1])) if _pt(o)), None)

        def dist(bl):
            ini = _nn(bl)[0]
            d = hav(fim, _pt(ini))
            return d if d is not None else 1e9
        rest.sort(key=dist)
        seq.append(rest.pop(0))
    return seq


def _status(o, rota):
    if rota == 'Drone Grid A' and o['k'] == MARIALVA:
        return 'Em andamento (lista do Fabrício)'
    if o.get('origem') == 'MPS':
        return 'Pendente – termografia da MPS (ENG: PENDENTE)'
    if not o['oss']:
        return 'Pendente – sem OS de MPA no ciclo (Fracttal)'
    if o['nf'] == 0:
        return 'Pendente – MPA não iniciada (0/%d)' % o['n']
    if o['modfin'] and not o['modab']:
        return ('Pendente – MPA com módulos executados em %s; sem registro de termografia aérea'
                % o['modfin'].strftime('%d/%m'))
    if o['modfin']:
        return 'Pendente – MPA em execução (%d/%d); parte dos módulos em aberto' % (o['nf'], o['n'])
    return 'Pendente – MPA em execução (%d/%d); módulos em aberto' % (o['nf'], o['n'])


def _linha(ctx, rota, ordem, o, ant, extra_obs, limp_inf=None):
    hoje = ctx['hoje']
    p = _pt(o)
    dd = hav(ant, p)
    dist = round(dd) if dd is not None else None
    oss = ', '.join(str(x['os']) for x in o['oss']) or \
        (str(o.get('mps_os')) + ' (MPS)' if o.get('mps_os') else '—')
    if o.get('origem') == 'MPS':
        dmpa = 'MPS exec %s a %s' % (f(o.get('mps_ini')), f(o.get('mps_fin')))
    else:
        ex = o['modfin']
        dmpa = '52s %s · prog %s · %s' % (
            f(ctx['p52'].get(o['k'])), f(o.get('prog')),
            ('exec módulos %s' % f(ex)) if ex else
            ('em exec. desde %s' % f(o['ini']) if o.get('ini') else 'não iniciada'))
    debt = o.get('debt')
    if rota == 'Drone Grid A':
        debt = (hoje - o['ref']).days if o.get('ref') and o['nf'] else None
    limp = o.get('limp')
    limp_ref = limp or limp_inf
    dl = (hoje - limp_ref).days if limp_ref else None
    if debt is None:
        prio = 'Baixa'
    elif debt > 90:
        prio = 'Alta'
    elif debt > 30:
        prio = 'Média'
    else:
        prio = 'Baixa'
    if rota == 'Drone Grid A':
        prio = 'Rota fixa · ' + prio if debt is not None else 'Rota fixa'
    obs = list(extra_obs)
    if not limp_ref or limp_ref < ctx['corte_limp']:
        obs.insert(0, 'LIMPEZA ANTES DA TERMOGRAFIA RECOMENDADA (última limpeza %s)'
                   % ('desconhecida' if not limp_ref else f(limp_ref)))
    if not limp and limp_inf:
        obs.append('limpeza não localizada no Fracttal; usada a data da lista do Fabrício')
    for os_, est, dp in o.get('limp_ab', []):
        obs.append('limpeza de módulos aberta no Fracttal: OS %s (%s, prog %s) – encaixar a termografia logo depois'
                   % (os_, est.lower(), f(D(dp))))
    if o.get('zel'):
        obs.append('Gerencial (Zeladoria e MPAS): %s' % o['zel'])
    if o.get('origem') != 'MPS' and any(str(r['termo']).upper() == 'PENDENTE' and r['ativ'] == 'MPS'
                                        for r in ctx['eng'].get(o['k'], [])):
        obs.append('ENG também aponta termografia da MPS pendente')
    if not p:
        obs.append('SEM COORDENADA NA AUXILIAR')
    cid = '%s/%s' % (o.get('cidade') or '?', o.get('uf') or '?')
    nome = o.get('aux_nome') or o.get('nome') or o['k']
    return [rota, ordem, nome, o.get('cli_aux') or o.get('cli'), o.get('cluster') or o.get('cluster_aux'), cid,
            o.get('lat'), o.get('lon'), dist, oss, dmpa, _status(o, rota), debt, limp, dl, prio,
            ' | '.join(obs), 'ver lista do Fabrício'], p, dist


# ── aba ──────────────────────────────────────────────────────────────
def montar_aba(wb, gestao, obs_antigas=None, obs_col='Observações do time', hoje=None):
    """Cria a aba NOME em wb. obs_antigas = {chave: texto} lido da versao anterior."""
    R = calcular(gestao, hoje)
    obs_antigas = obs_antigas or {}
    hoje = R['hoje']
    ws = wb.create_sheet(NOME)
    thin = Border(bottom=Side(style='thin', color='E3E3EA'))
    branco = Font(bold=True, color='FFFFFF', size=10)
    navy = PatternFill('solid', fgColor=NAVY)
    ws['A1'] = 'Plano de Ação Drone – Termografia aérea pós-MPA'
    ws['A1'].font = Font(bold=True, size=14, color=NAVY)
    ws['A2'] = ('Gerado em %s · fontes: Fracttal (gestão de %s), Gerencial PCM 2026 (Zeladoria e MPAS + '
                'ENG - Acompanhamento), PCM 52 Semanas R04, AUXILIAR (Operacoes_1) · distâncias em linha reta '
                '(haversine) · preencham só a coluna amarela "%s"' % (
                    dt.datetime.now().strftime('%d/%m/%Y %H:%M'),
                    str(gestao.get('geradoEm', ''))[:16].replace('T', ' '), obs_col))
    ws['A2'].font = Font(size=10, color=CINZA)
    for j, h in enumerate(['Rota', 'Usinas', 'km linha reta', 'km rodoviário estimado (×1,3)', 'Composição'], 1):
        c = ws.cell(4, j, h)
        c.font, c.fill = branco, navy
    r0 = 5
    for i, (rota, n, km, comp) in enumerate(R['resumo']):
        for j, v in enumerate([rota, n, round(km), round(km * 1.3), comp], 1):
            c = ws.cell(r0 + i, j, v)
            c.fill = PatternFill('solid', fgColor=COR[rota])
            c.border = thin
            if j in (3, 4):
                c.number_format = '#,##0'
    tot = r0 + len(R['resumo'])
    kmt = sum(r[2] for r in R['resumo'])
    for j, v in enumerate(['Total', sum(r[1] for r in R['resumo']), round(kmt), round(kmt * 1.3), ''], 1):
        c = ws.cell(tot, j, v)
        c.font = Font(bold=True)
        if j in (3, 4):
            c.number_format = '#,##0'

    H = tot + 2
    cab = CAB + [obs_col, '_chave']
    larg = LARG + [48, 2]
    for j, h in enumerate(cab, 1):
        c = ws.cell(H, j, h)
        c.font, c.fill = branco, navy
        c.alignment = Alignment(wrap_text=True, vertical='center')
    ws.row_dimensions[H].height = 30
    amar = PatternFill('solid', fgColor=AMAR)
    for i, (ln, k) in enumerate(zip(R['linhas'], R['chaves']), H + 1):
        fill = PatternFill('solid', fgColor=COR[ln[0]])
        for j, v in enumerate(ln, 1):
            c = ws.cell(i, j, v)
            c.fill, c.border = fill, thin
            c.alignment = Alignment(vertical='top', wrap_text=(larg[j - 1] >= 40))
            if j in (7, 8) and v is not None:
                c.number_format = '0.000000'
            if j in (9, 13, 15) and v is not None:
                c.number_format = '#,##0'
            if j == 14 and v is not None:
                c.number_format = 'dd/mm/yyyy'
            if j == I_OBS + 1 and 'LIMPEZA ANTES' in str(v):
                c.font = Font(color='9C0006')
        oc = ws.cell(i, len(CAB) + 1, obs_antigas.get(k, ''))
        oc.fill, oc.border = amar, thin
        oc.alignment = Alignment(vertical='top', wrap_text=True)
        kc = ws.cell(i, len(CAB) + 2, k)
        kc.font = Font(size=6, color='CCCCCC')
    for j, w in enumerate(larg, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.column_dimensions[get_column_letter(len(cab))].hidden = True
    ult = H + max(len(R['linhas']), 1)
    tab = Table(displayName='tb_PlanodeAcaoDrone', ref='A%d:%s%d' % (H, get_column_letter(len(cab)), ult))
    tab.tableStyleInfo = TableStyleInfo(name='TableStyleLight1', showFirstColumn=False, showLastColumn=False,
                                        showRowStripes=False, showColumnStripes=False)
    ws.add_table(tab)
    ws.freeze_panes = 'D%d' % (H + 1)

    # usinas com observacao do time que sairam do plano: lista abaixo (nao perde o texto)
    sairam = {k: v for k, v in obs_antigas.items() if k not in set(R['chaves'])}
    C = ult + 2
    d_ = hoje.strftime('%d/%m/%Y')
    fora = '; '.join('%s (%s)' % (k, m) for k, m in R['excl']) or '—'
    dep = '; '.join('%s (%s)' % (k, m) for k, m in R['depois']) or '—'
    crit = [
        'Critérios',
        '1. Termografia pendente = usina com OS de MPA do ciclo (programada a partir de %s) no Fracttal cuja tarefa '
        'de módulos foi executada, ou com ≥ 50%% das tarefas da MPA finalizadas, sem registro de termografia aérea.'
        % CICLO.strftime('%d/%m/%Y'),
        '2. Registro aceito: data na coluna "Termografia de módulos" da aba ENG - Acompanhamento Manutenção '
        '(Gerencial) ou tarefa "Termografia com Drone" finalizada no Fracttal, até %d dias antes da MPA. "N/A" na '
        'linha da MPA exclui a usina. Quem ganha o registro sai do plano na atualização seguinte.' % JANELA_TERMO,
        '3. Também entram usinas cuja termografia da MPS consta como PENDENTE na aba ENG e que não têm MPA no ciclo.',
        '4. Dias em atraso = %s menos a execução da tarefa de módulos da MPA; com módulos em aberto, desde o início '
        'da MPA; para MPS, desde o fim da MPS.' % d_,
        '5. Última limpeza de módulos = tarefa de limpeza finalizada no Fracttal. Limpeza anterior a %s (mais de %d '
        'dias) ou desconhecida → "LIMPEZA ANTES DA TERMOGRAFIA RECOMENDADA".'
        % ((hoje - dt.timedelta(days=JANELA_LIMP)).strftime('%d/%m/%Y'), JANELA_LIMP),
        '6. Drone Grid A: ordem fixa do PCM. Terceiro: os %d blocos com a dívida de MPA mais antiga (usinas a até '
        '%d km da mais atrasada). Drone Grid B: as demais, em blocos regionais (até %d km entre vizinhas ou mesma '
        'UF), começando pelo bloco de maior dívida. Dentro do bloco: vizinho mais próximo a partir da maior dívida.'
        % (BLOCOS_TERCEIRO, RAIO_BLOCO, RAIO_BLOCO),
        '7. Prioridade: Alta > 90 dias · Média 31–90 · Baixa ≤ 30. Distâncias em linha reta entre as coordenadas da '
        'AUXILIAR; o rodoviário é estimado em ×1,3.',
        '8. Fora do plano: ' + fora + '.',
        '9. Entram quando os módulos forem executados: ' + dep + '.',
        '10. Ponto de entrega do drone: ver lista do Fabrício (endereços e contatos não são copiados para cá).',
    ]
    if sairam:
        crit.append('11. Observações do time de usinas que saíram do plano: ' +
                    ' | '.join('%s: %s' % (k, v) for k, v in sairam.items()))
    for i, t in enumerate(crit):
        c = ws.cell(C + i, 1, t)
        c.font = Font(bold=True, size=11, color=NAVY) if i == 0 else Font(size=10, color='333333')
    ws.sheet_properties.tabColor = NAVY
    return dict((r[0], r[1]) for r in R['resumo'])
