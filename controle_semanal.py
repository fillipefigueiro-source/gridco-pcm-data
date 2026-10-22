# -*- coding: utf-8 -*-
"""PCM - Controle Semanal (Excel vivo).
Gera/atualiza PCM_Controle_Semanal_GridCo.xlsx na pasta
"...\\9. Reuniões\\0. Grid Interno\\0. PCM - Controle Semanal" com dados
frescos da nuvem, PRESERVANDO a coluna "Observações do time" preenchida na
versao anterior (casamento por OS/usina/tarefa).

Regras: OS em Finalizados OU Verificação = concluida (fora das pendencias);
usinas de teste fora; Responsavel = designado da OS no Fracttal
(resp_os da Programacao; fallback BD da API); Supervisor = Responsavel O&M.
"""
import datetime as dt, io, json, os, re, urllib.request
from collections import defaultdict
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

BASE = os.path.dirname(os.path.abspath(__file__))
URL = 'https://fillipefigueiro-source.github.io/gridco-pcm-data/'
DEST_DIR = (r'C:\Users\Fabricio Barreto\OneDrive - GRID CO\Shortcuts'
            r'\GRID CO_ - 4. O&M\11.Pré-Operação\Modelo pasta - PCM'
            r'\00_PCM 52 Semanas\0. PCM - Controle Semanal')
DEST = os.path.join(DEST_DIR, 'PCM_Controle_Semanal_GridCo.xlsx')
FECH = ('finalizados', 'finalizado', 'verificação', 'verificacao')
OBS_COL = 'Observações do time'


def baixar(nome):
    dst = os.path.join(BASE, '_auto_' + nome)
    urllib.request.urlretrieve(URL + nome, dst)
    return json.load(io.open(dst, encoding='utf-8'))


g = baixar('gestao_pcm.json')
b = baixar('banco_dados.json')
AGORA = dt.datetime.now()
base_sem = AGORA + dt.timedelta(days=2)
seg = base_sem - dt.timedelta(days=base_sem.weekday())
ano, ww, _ = seg.isocalendar()
WTAG = '%d-W%02d' % (ano, ww)

T = [t for t in g['tarefas'] if 'teste' not in str(t.get('usina', '')).lower()]
AB = [t for t in T if t.get('aberta')
      and str(t.get('osStatus', '')).strip().lower() not in FECH]
sem = next((s for s in b.get('semanas', []) if s.get('week') == WTAG), None)
rows = [r for r in (sem or {}).get('rows', [])
        if 'teste' not in str(r.get('usina', '')).lower()]

# ── responsavel da OS: programacao (todas as semanas) + BD da API ────
RESP = {}
for s_ in b.get('semanas', []):
    for r in s_.get('rows', []):
        ro = ' '.join(str(r.get('resp_os') or '').split())
        if ro:
            RESP.setdefault(str(r.get('os_id')), ro)
try:
    import fonte_bd_api as F
    _df = F.df_semanal(ttl_min=720)[['OSs ID', 'Responsável']].dropna()
    for _r in _df.to_dict('records'):
        RESP.setdefault(str(_r['OSs ID']), ' '.join(str(_r['Responsável']).split()))
except Exception as e:
    print('AVISO: fallback BD API indisponivel (%s); usando so a Programacao' % e)


def resp_de(os_):
    return RESP.get(str(os_), '')


def curta(u):
    m = re.match(r'^[^-]+?\s*-\s*(.+?)\s*-\s*[A-Za-z]{2}\s*$', ' '.join(str(u).split()))
    return (m.group(1) if m else str(u)).strip()


def cli(u):
    return str(u).split(' - ')[0].strip().replace('Utragaz', 'Ultragaz')


def reg(c):
    m = re.match(r'^([A-Z]{2})\b', str(c).strip())
    return m.group(1) if m else 'Outros'


rxA, rxS = re.compile(r'\bMPA\b', re.I), re.compile(r'\bMPS\b', re.I)
is_ho = lambda t: 'handover' in (str(t.get('tipo', '')) + str(t.get('tarefa', ''))).lower()
is_corr = lambda t: 'corretiva' in str(t.get('tipo', '')).lower()
is_mpas = lambda t: bool(rxA.search(str(t.get('tarefa', '')) + str(t.get('tipo', '')))
                         or rxS.search(str(t.get('tarefa', '')) + str(t.get('tipo', ''))))
is_rel = lambda t: 'religamento' in str(t.get('tipo', '')).lower()

# ── observacoes antigas (preservar) ──────────────────────────────────
OBS_OLD = {}
if os.path.exists(DEST):
    try:
        old = openpyxl.load_workbook(DEST, read_only=True, data_only=True)
        for sh in old.sheetnames:
            ws = old[sh]
            # cabecalho na linha 1 (abas comuns) ou abaixo de um bloco de resumo
            # (Plano de Acao Drone): procura nas 15 primeiras linhas
            h_lin, head = None, None
            for n_, rr in enumerate(ws.iter_rows(min_row=1, max_row=15, values_only=True), 1):
                if rr and OBS_COL in rr and '_chave' in rr:
                    h_lin, head = n_, list(rr)
                    break
            if not head:
                continue
            i_obs, i_key = head.index(OBS_COL), head.index('_chave')
            d = {}
            for rr in ws.iter_rows(min_row=h_lin + 1, values_only=True):
                if len(rr) > max(i_obs, i_key) and rr[i_key] and rr[i_obs]:
                    d[str(rr[i_key])] = str(rr[i_obs])
            OBS_OLD[sh] = d
        old.close()
        print('observacoes preservadas:', {k: len(v) for k, v in OBS_OLD.items() if v})
    except Exception as e:
        print('AVISO: nao li observacoes antigas (%s)' % e)

NAVY, AMAR = '1C1F3B', 'FFF2CC'
wb = openpyxl.Workbook()
thin = Border(bottom=Side(style='thin', color='E3E3EA'))


def aba(nome, cab, linhas, larguras, chaves=None):
    """chaves = lista (mesma ordem de linhas) p/ casar observacoes antigas."""
    ws = wb.create_sheet(nome)
    obs = chaves is not None
    cab2 = list(cab) + ([OBS_COL, '_chave'] if obs else [])
    larg2 = list(larguras) + ([48, 2] if obs else [])
    for j, h in enumerate(cab2, 1):
        c = ws.cell(1, j, h)
        c.font = Font(bold=True, color='FFFFFF', size=10)
        c.fill = PatternFill('solid', fgColor=NAVY)
    antigas = OBS_OLD.get(nome, {})
    for i, ln in enumerate(linhas, 2):
        for j, v in enumerate(ln, 1):
            c = ws.cell(i, j, v)
            c.border = thin
            c.alignment = Alignment(vertical='top', wrap_text=(larg2[j - 1] >= 40))
        if obs:
            k = str(chaves[i - 2])
            oc = ws.cell(i, len(cab) + 1, antigas.get(k, ''))
            oc.fill = PatternFill('solid', fgColor=AMAR)
            oc.alignment = Alignment(vertical='top', wrap_text=True)
            kc = ws.cell(i, len(cab) + 2, k)
            kc.font = Font(size=6, color='CCCCCC')
    for j, w in enumerate(larg2, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    if obs:
        ws.column_dimensions[get_column_letter(len(cab2))].hidden = True
    ws.freeze_panes = 'A2'
    # tabela do Excel com linhas zebradas
    nome_tab = 'tb_' + re.sub(r'[^A-Za-z0-9]', '', nome)
    ref = 'A1:%s%d' % (get_column_letter(len(cab2)), max(len(linhas) + 1, 2))
    tab = Table(displayName=nome_tab, ref=ref)
    tab.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showFirstColumn=False,
                                        showLastColumn=False, showRowStripes=True,
                                        showColumnStripes=False)
    ws.add_table(tab)


# ── Resumo ───────────────────────────────────────────────────────────
ws = wb.active
ws.title = 'Resumo'
ws['A1'] = 'PCM · Controle Semanal · Semana %d (%s a %s)' % (
    ww, seg.strftime('%d/%m'), (seg + dt.timedelta(days=4)).strftime('%d/%m'))
ws['A1'].font = Font(bold=True, size=14, color=NAVY)
ws['A2'] = ('Atualizado em %s · fontes da nuvem (gestão de %s) · as observações do '
            'time são preservadas a cada atualização'
            % (AGORA.strftime('%d/%m/%Y %H:%M'), str(g.get('geradoEm', ''))[:16].replace('T', ' ')))
ws['A2'].font = Font(size=10, color='6B6880')
kpis = [
    ('Tarefas na programação da semana', len(rows)),
    ('Corretivas abertas (OS pendentes)', len({t['os'] for t in AB if is_corr(t)})),
    ('Tarefas atrasadas há mais de 35 dias', sum(1 for t in AB if (t.get('dias') or 0) > 35)),
    ('Tarefas de MPA/MPS atrasadas', sum(1 for t in AB if is_mpas(t) and (t.get('dias') or 0) > 0)),
    ('Religamentos em aberto', sum(1 for t in AB if is_rel(t))),
]
for i, (k, v) in enumerate(kpis, 4):
    ws.cell(i, 1, k).font = Font(size=11)
    ws.cell(i, 2, v).font = Font(bold=True, size=12, color=NAVY)
regras = [
    'Regras: OS em Finalizados ou Verificação = concluída · tarefas de OS finalizada não contam · '
    'usinas de teste fora.',
    'Responsável = designado da OS no Fracttal · Supervisor = Responsável O&M do cluster.',
    'MPM mensal: mês fechado mostra o que foi CONCLUÍDO nele; tarefa não concluída é reprogramada e aparece no mês corrente (por isso meses fechados tendem a 100%).',
    'Preencham só a coluna amarela "%s"; o resto é regravado a cada atualização (diária, 6h, e sexta 12h).' % OBS_COL,
]
for i, r in enumerate(regras, 11):
    ws.cell(i, 1, r).font = Font(size=10, color='55526a')
ws.column_dimensions['A'].width = 115
ws.column_dimensions['B'].width = 12

# ── Plano por tipo / Supervisor x Dia / Responsavel x Dia (HH) ───────
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


DIAS = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira']
PL = defaultdict(int)
SUP = defaultdict(lambda: defaultdict(float))
RSP = defaultdict(lambda: defaultdict(float))
for r in rows:
    PL[grupo_b(r)] += 1
    d = r.get('dia')
    hh = float(r.get('duracao') or 0)
    s_ = r.get('responsavel') or 'Sem supervisor'
    SUP[s_][d] += 1
    SUP[s_]['tot'] += 1
    ro = ' '.join(str(r.get('resp_os') or '').split()) or 'Sem responsável'
    RSP[ro][d] += 1
    RSP[ro]['tot'] += 1
    RSP[ro]['hh_' + str(d)] += hh
    RSP[ro]['hh_tot'] += hh
aba('Plano por tipo', ['Tipo', 'Tarefas'],
    sorted(PL.items(), key=lambda kv: -kv[1]), [34, 10])
aba('Supervisor x Dia', ['Supervisor', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Total'],
    [[s] + [int(d.get(x, 0)) for x in DIAS] + [int(d['tot'])]
     for s, d in sorted(SUP.items(), key=lambda kv: -kv[1]['tot'])],
    [24, 7, 7, 7, 7, 7, 9])
aba('Responsável x Dia (HH)',
    ['Responsável', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Total',
     'HH Seg', 'HH Ter', 'HH Qua', 'HH Qui', 'HH Sex', 'HH Total'],
    [[s] + [int(d.get(x, 0)) for x in DIAS] + [int(d['tot'])]
     + [round(d.get('hh_' + x, 0), 1) for x in DIAS] + [round(d.get('hh_tot', 0), 1)]
     for s, d in sorted(RSP.items(), key=lambda kv: -kv[1]['tot'])],
    [26, 6, 6, 6, 6, 6, 8, 8, 8, 8, 8, 8, 9])

# ── Usinas atencao ───────────────────────────────────────────────────
UR = defaultdict(lambda: dict(n=0, corr=set(), dias=0, oss=defaultdict(int), sup=''))
for t in AB:
    e = UR[t['usina']]
    e['n'] += 1
    e['dias'] = max(e['dias'], t.get('dias') or 0)
    e['oss'][t['os']] += 1
    e['sup'] = t.get('responsavel') or ''
    if is_corr(t):
        e['corr'].add(t['os'])
rk = sorted(UR.items(), key=lambda kv: -kv[1]['n'])[:30]
aba('Usinas atenção',
    ['#', 'Usina', 'Cliente', 'Em aberto', 'Corretivas (OS)', 'Mais antiga (d)',
     'Responsável (OS com mais tarefas)', 'Supervisor'],
    [[i, curta(u), cli(u), e['n'], len(e['corr']), e['dias'],
      resp_de(max(e['oss'], key=e['oss'].get)), e['sup']]
     for i, (u, e) in enumerate(rk, 1)],
    [5, 30, 14, 11, 14, 14, 24, 18],
    chaves=[curta(u) + '|' + cli(u) for u, _ in rk])

# ── Rolagens ─────────────────────────────────────────────────────────
porv = {}
for r in rows:
    o = str(r.get('os_id'))
    v = int(r.get('vezes') or 1)
    if o not in porv or v > porv[o]['v']:
        porv[o] = dict(v=v, u=r.get('usina', ''), t=r.get('tarefa', ''), tp=str(r.get('tipo', '')), sup=r.get('responsavel') or '')
rl = sorted(porv.items(), key=lambda kv: -kv[1]['v'])[:15]
aba('Rolagens top 15', ['OS', 'Usina', 'Tarefa', 'Tipo', 'Rolagens', 'Responsável', 'Supervisor'],
    [[o, curta(e['u']), e['t'], e['tp'], e['v'], resp_de(o), e['sup']] for o, e in rl],
    [9, 24, 56, 16, 10, 22, 18], chaves=[o for o, _ in rl])

# ── Atrasadas +35d por OS ────────────────────────────────────────────
tot_os = defaultdict(int)
for t in T:
    tot_os[t['os']] += 1
O35 = defaultdict(lambda: dict(n=0, dias=0, u='', obs='', etq='', ts=set(), sup=''))
for t in AB:
    if (t.get('dias') or 0) > 35:
        e = O35[t['os']]
        e['n'] += 1
        d = t.get('dias') or 0
        if d >= e['dias']:
            e['dias'] = d
            e['obs'] = str(t.get('obs') or '')
            e['etq'] = ', '.join(t.get('etiquetas') or [])
        e['u'] = t['usina']
        e['sup'] = t.get('responsavel') or ''
        e['ts'].add(str(t.get('tarefa', ''))[:40])
o35 = sorted(O35.items(), key=lambda kv: -kv[1]['dias'])
aba('Atrasadas +35d (por OS)',
    ['Dias', 'OS', 'Cliente', 'Usina', 'Tarefas abertas', 'Faltam', 'Tarefa(s)',
     'Etiqueta', 'Responsável', 'Supervisor', 'Observação no Fracttal'],
    [[e['dias'], o, cli(e['u']), curta(e['u']), e['n'],
      '%d/%d' % (e['n'], tot_os[o]), ' · '.join(sorted(e['ts'])[:4]), e['etq'],
      resp_de(o), e['sup'], ' '.join(e['obs'].split())[:250]]
     for o, e in o35],
    [7, 9, 13, 24, 13, 9, 46, 16, 22, 18, 58], chaves=[o for o, _ in o35])

# ── Religamentos ─────────────────────────────────────────────────────
RL = defaultdict(lambda: dict(n=0, dias=0, u='', tp='', sup=''))
for t in AB:
    if is_rel(t):
        e = RL[t['os']]
        e['n'] += 1
        e['dias'] = max(e['dias'], t.get('dias') or 0)
        e['u'] = t['usina']
        e['tp'] = str(t.get('tipo', ''))
        e['sup'] = t.get('responsavel') or ''
rls = sorted(RL.items(), key=lambda kv: -kv[1]['dias'])
aba('Religamentos', ['Dias', 'OS', 'Usina', 'Cliente', 'Tipo', 'Responsável', 'Supervisor'],
    [[e['dias'], o, curta(e['u']), cli(e['u']), e['tp'], resp_de(o), e['sup']] for o, e in rls],
    [7, 9, 28, 13, 20, 22, 18], chaves=[o for o, _ in rls])

# ── MPAS por usina ───────────────────────────────────────────────────
MU = defaultdict(lambda: dict(n=0, dias=0, oss=defaultdict(int), tipos=set(), sup=''))
for t in AB:
    if is_mpas(t) and (t.get('dias') or 0) > 0:
        e = MU[t['usina']]
        e['n'] += 1
        e['dias'] = max(e['dias'], t.get('dias') or 0)
        e['oss'][t['os']] += 1
        e['sup'] = t.get('responsavel') or ''
        e['tipos'].add('MPS' if rxS.search(str(t.get('tarefa', '')) + str(t.get('tipo', ''))) else 'MPA')
mus = sorted(MU.items(), key=lambda kv: -kv[1]['dias'])
aba('MPAS atrasadas (usina)',
    ['Usina', 'Cliente', 'Tipo', 'OS', 'Tarefas abertas', 'Mais antiga (d)', 'Responsável', 'Supervisor'],
    [[curta(u), cli(u), '/'.join(sorted(e['tipos'])), ', '.join(sorted(e['oss'])),
      e['n'], e['dias'], resp_de(max(e['oss'], key=e['oss'].get)), e['sup']]
     for u, e in mus],
    [28, 14, 10, 20, 13, 13, 22, 18], chaves=[curta(u) for u, _ in mus])

# ── Handovers ────────────────────────────────────────────────────────
HU = defaultdict(lambda: dict(n=0, atr=0, dias=0, oss=defaultdict(int), sup=''))
for t in AB:
    if is_ho(t):
        e = HU[t['usina']]
        e['n'] += 1
        if t.get('atrasado'):
            e['atr'] += 1
        e['dias'] = max(e['dias'], t.get('dias') or 0)
        e['oss'][t['os']] += 1
        e['sup'] = t.get('responsavel') or ''
hus = sorted(HU.items(), key=lambda kv: -kv[1]['dias'])
aba('Handovers',
    ['Usina', 'Cliente', 'OS', 'Tarefas', 'Atrasadas', 'Mais antiga (d)', 'Responsável', 'Supervisor'],
    [[curta(u), cli(u), ' / '.join(sorted(e['oss'])), e['n'], e['atr'], e['dias'],
      resp_de(max(e['oss'], key=e['oss'].get)), e['sup']]
     for u, e in hus],
    [30, 13, 14, 9, 10, 13, 22, 18], chaves=[curta(u) for u, _ in hus])

# ── Backlog detalhado ────────────────────────────────────────────────
det, chaves = [], []
for t in AB:
    if not t.get('atrasado'):
        continue
    det.append([reg(t.get('cluster', '')), str(t.get('cluster') or ''),
                curta(t['usina']), cli(t['usina']), str(t['os']),
                str(t.get('tipo', '')), str(t.get('tarefa', ''))[:90],
                t.get('dias') or 0, resp_de(t['os']), t.get('responsavel') or ''])
ordem = sorted(range(len(det)), key=lambda i: (det[i][0], det[i][1], -det[i][7]))
det = [det[i] for i in ordem]
chaves = [d[4] + '|' + d[6][:50] for d in det]
aba('Backlog detalhado',
    ['Região', 'Cluster', 'Usina', 'Cliente', 'OS', 'Tipo', 'Tarefa', 'Dias',
     'Responsável', 'Supervisor'],
    det, [8, 14, 24, 13, 9, 18, 56, 7, 22, 18], chaves=chaves)

# ── MPM mes a mes (jan ate o mes corrente) ───────────────────────────
rxM = re.compile(r'\bMPM\b|preventiva mensal', re.I)
MESES_N = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']


def mes_de(t):
    for k in ('dataProg', 'dataFinal', 'dataInicio'):
        v = str(t.get(k) or '')
        if v[:4] == '2026':
            try:
                return int(v[5:7])
            except ValueError:
                pass
    return None


def concluida(t):
    return (not t.get('aberta')) or str(t.get('osStatus', '')).strip().lower() in FECH


MPM = defaultdict(lambda: defaultdict(lambda: dict(n=0, ok=0, cli='', clu='', sup='')))
for t in T:
    txt = str(t.get('tarefa', '')) + ' ' + str(t.get('tipo', ''))
    if not rxM.search(txt) or 'spare' in txt.lower():
        continue
    m = mes_de(t)
    if not m or m > AGORA.month:
        continue
    e = MPM[m][t['usina']]
    e['n'] += 1
    if concluida(t):
        e['ok'] += 1
    e['cli'] = cli(t['usina'])
    e['clu'] = str(t.get('cluster') or '')
    e['sup'] = t.get('responsavel') or ''

res_rows = []
for m in sorted(MPM):
    us = MPM[m]
    n = sum(e['n'] for e in us.values())
    ok = sum(e['ok'] for e in us.values())
    cem = sum(1 for e in us.values() if e['ok'] >= e['n'])
    res_rows.append([MESES_N[m - 1], n, ok, round(100.0 * ok / n) if n else 0,
                     len(us), cem, len(us) - cem])
aba('MPM mensal (resumo)',
    ['Mês', 'Tarefas MPM', 'Concluídas', 'Aderência %', 'Usinas com MPM',
     'Usinas 100%', 'Usinas pendentes'],
    res_rows, [8, 12, 12, 12, 14, 12, 14])

usi_rows, usi_keys = [], []
for m in sorted(MPM):
    for u, e in sorted(MPM[m].items(), key=lambda kv: kv[1]['ok'] / kv[1]['n'] if kv[1]['n'] else 1):
        usi_rows.append([MESES_N[m - 1], m, curta(u), e['cli'], e['clu'], e['sup'],
                         e['n'], e['ok'], e['n'] - e['ok'],
                         round(100.0 * e['ok'] / e['n']) if e['n'] else 0])
        usi_keys.append('%02d|%s' % (m, curta(u)))
aba('MPM mensal (usina)',
    ['Mês', 'Nº mês', 'Usina', 'Cliente', 'Cluster', 'Supervisor',
     'Tarefas', 'Concluídas', 'Pendentes', '%'],
    usi_rows, [7, 7, 26, 13, 13, 18, 9, 11, 10, 7], chaves=usi_keys)

# ── MPM matriz usina x mes: % (feitas/total) ─────────────────────────
meses_ativos = sorted(MPM)
POR_US = defaultdict(dict)
for m in meses_ativos:
    for u, e in MPM[m].items():
        POR_US[u][m] = e
mat_rows, mat_keys = [], []
for u in sorted(POR_US, key=lambda u: (next(iter(POR_US[u].values()))['clu'], u)):
    ms = POR_US[u]
    qq = next(iter(ms.values()))
    linha = [curta(u), qq['cli'], qq['clu']]
    for m in meses_ativos:
        e = ms.get(m)
        linha.append('%d%% (%d/%d)' % (round(100.0 * e['ok'] / e['n']), e['ok'], e['n'])
                     if e and e['n'] else '-')
    mat_rows.append(linha)
    mat_keys.append(curta(u))
aba('MPM % usina x mês',
    ['Usina', 'Cliente', 'Cluster'] + [MESES_N[m - 1] for m in meses_ativos],
    mat_rows, [26, 13, 13] + [12] * len(meses_ativos), chaves=mat_keys)

# ── Plano de Acao Drone (termografia pos-MPA; le planilhas locais) ───
try:
    import plano_drone
    print('Plano de Ação Drone:', plano_drone.montar_aba(
        wb, g, OBS_OLD.get(plano_drone.NOME, {}), OBS_COL))
except Exception as e:
    print('AVISO: aba Plano de Ação Drone nao gerada (%s: %s)' % (type(e).__name__, e))
    if 'Plano de Ação Drone' in wb.sheetnames:
        del wb['Plano de Ação Drone']

os.makedirs(DEST_DIR, exist_ok=True)
import time
for tent in range(6):
    try:
        wb.save(DEST)
        print('ok ->', DEST)
        break
    except PermissionError:
        if tent == 5:
            alt = DEST.replace('.xlsx', '_%s.xlsx' % AGORA.strftime('%H%M'))
            wb.save(alt)
            print('arquivo aberto/bloqueado; salvo como', alt)
        else:
            time.sleep(10)
print('abas:', wb.sheetnames)
