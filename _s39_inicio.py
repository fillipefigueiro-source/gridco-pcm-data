# -*- coding: utf-8 -*-
"""Inicio Semana 39 — Desafios (21 a 25/09/2026), padrao visual S36. R00.
Dados: _semana39_dados.json + _s39_mpas_obs.json (API Fracttal em 21/09)."""
import io, json
import re as _re
from collections import defaultdict
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

NAVY = RGBColor(0x19, 0x15, 0x28)
LIME = RGBColor(0xA9, 0xDB, 0x21)
BODY = RGBColor(0x50, 0x4C, 0x63)
INK = RGBColor(0x23, 0x20, 0x3A)
CALL = RGBColor(0xF0, 0xF1, 0xF4)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREEN = RGBColor(0x2E, 0x7D, 0x32)
AMBER = RGBColor(0xB9, 0x77, 0x0E)
RED = RGBColor(0xB3, 0x26, 0x1E)
F = 'Calibri'
RODAPE = 'Semana 39 - 21/09 a 25/09 - PCM Grid Co.'

D = json.load(io.open('_semana39_dados.json', encoding='utf-8'))
G = D['geral']
CLIS = D['clientes']
NOME = {'Utragaz': 'Ultragaz'}  # typo no cadastro do Fracttal

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]


def tx(s, x, y, w, h, texto, sz, cor=INK, bold=False, alinha=PP_ALIGN.LEFT):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    linhas = texto if isinstance(texto, list) else [texto]
    for i, ln in enumerate(linhas):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = alinha
        if i:
            p.space_before = Pt(4)
        partes = ln if isinstance(ln, list) else [(ln, cor, bold, sz)]
        for t_, c_, b_, z_ in partes:
            r = p.add_run(); r.text = t_
            r.font.name, r.font.size, r.font.bold = F, Pt(z_), b_
            r.font.color.rgb = c_
    return tb


def caixa(s, x, y, w, h, fill, radius=0.06):
    sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y),
                            Inches(w), Inches(h))
    sh.fill.solid(); sh.fill.fore_color.rgb = fill
    sh.line.fill.background(); sh.shadow.inherit = False
    sh.adjustments[0] = radius
    return sh


def slide(titulo, kicker):
    s = prs.slides.add_slide(BLANK)
    tx(s, 0.55, 0.32, 12.2, 0.3, kicker.upper(), 12, BODY, True)
    tx(s, 0.55, 0.62, 12.2, 0.7, titulo, 28, NAVY, True)
    ln = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.55), Inches(1.28),
                            Inches(12.23), Emu(9525))
    ln.fill.solid(); ln.fill.fore_color.rgb = LIME
    ln.line.fill.background(); ln.shadow.inherit = False
    tx(s, 0.55, 7.08, 8.0, 0.3, RODAPE, 9, BODY)
    return s


def kpi(s, x, y, w, valor, rotulo, cor=NAVY, sz=30):
    caixa(s, x, y, w, 1.05, CALL)
    tx(s, x + 0.15, y + 0.1, w - 0.3, 0.55, valor, sz, cor, True)
    tx(s, x + 0.15, y + 0.66, w - 0.3, 0.38, rotulo, 10, BODY)


def tabela(s, x, y, w, cols, largs, linhas, hrow=0.3, sz=10):
    t = s.shapes.add_table(len(linhas) + 1, len(cols), Inches(x), Inches(y),
                           Inches(w), Inches(hrow) * (len(linhas) + 1)).table
    t.first_row = False
    t.horz_banding = False
    for i, lg in enumerate(largs):
        t.columns[i].width = Inches(lg)
    for r_ in t.rows:
        r_.height = Inches(hrow)

    def cel(c, txt_, cor, bold, fundo, z=sz):
        c.margin_left = c.margin_right = Emu(50000)
        c.margin_top = c.margin_bottom = Emu(12000)
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        if fundo is None:
            c.fill.background()
        else:
            c.fill.solid(); c.fill.fore_color.rgb = fundo
        p = c.text_frame.paragraphs[0]
        r = p.add_run(); r.text = str(txt_)
        r.font.name, r.font.size, r.font.bold = F, Pt(z), bold
        r.font.color.rgb = cor

    for j, h in enumerate(cols):
        cel(t.cell(0, j), h, WHITE, True, NAVY)
    for i, linha in enumerate(linhas, 1):
        zebra = CALL if i % 2 == 0 else None
        for j, v in enumerate(linha):
            txt_, cor, bold = v if isinstance(v, tuple) else (v, BODY, False)
            cel(t.cell(i, j), txt_, cor, bold, zebra)
    return t


def usina_curta(u):
    m = _re.match(r'^[^-]+?\s*-\s*(.+?)\s*-\s*[A-Za-z]{2}$', ' '.join(str(u).split()))
    return m.group(1).strip() if m else u


def nome_cli(c):
    return NOME.get(c, c)


def cli_por(nome):
    return next((c for c in CLIS if c['cli'] == nome), None)


tho = cli_por('Thopen')
ath = cli_por('Athon')
axi = cli_por('Axis')

# ── 1 CAPA ───────────────────────────────────────────────────────────
s = prs.slides.add_slide(BLANK)
bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
bg.fill.solid(); bg.fill.fore_color.rgb = NAVY
bg.line.fill.background(); bg.shadow.inherit = False
tx(s, 0.9, 2.1, 11.5, 0.4, 'PCM - REUNIAO DE SEMANA', 15, LIME, True)
tx(s, 0.9, 2.55, 11.5, 1.0, 'Semana 39 — nossos desafios', 44, WHITE, True)
tx(s, 0.9, 3.75, 11.5, 0.4, '21 a 25 de setembro de 2026', 16,
   RGBColor(0xCF, 0xCB, 0xDA))
tx(s, 0.9, 6.6, 11.5, 0.4,
   'Equipe de PCM - Grid Co. - dados da API Fracttal em 21/09 (R00)', 11,
   RGBColor(0x9B, 0x96, 0xAD))

# ── 2 AGENDA ─────────────────────────────────────────────────────────
s = slide('A semana em uma página', 'PCM - Agenda')
itens = [
    ('1', 'MPM de setembro — última semana', '%d%% (%d de %d tarefas) — o mês fecha na quarta 30/09 (slide 7)'
     % (G['mpm_pct'], G['mpm_fei'], G['mpm_tot'])),
    ('2', 'MPA vencidas', 'subiram para %d OS — Petrolina 2 (Axis) chegou a 104 dias (slide 8)'
     % G['mpa_venc']),
    ('3', 'MPS vencidas', '%d OS, todas Thopen — a OS 6340 (118d) FECHOU; a mais antiga agora é Araçoiaba da Serra 1 (81d)'
     % G['mps_venc']),
    ('4', 'Handover', '%d OS abertas, todas Thopen — Inhapi 1 fechou; a mais antiga é Coração 1 e 2 (65d) (slide 9)' % G['ho_ab']),
    ('5', 'Corretivas', 'caíram para %d abertas (eram 126); %d com +30 dias — backlog por supervisor (slide 10)'
     % (G['corr_ab'], G['corr_30d'])),
    ('6', 'Pontos por cliente', 'Ultragaz zerou corretivas e fechou MPM — risco concentra em Thopen, Athon, Axis e RenoGrid (slides 4 a 6)'),
    ('7', 'Análise de óleo', '%d OS abertas — manter a logística enviar / rota / usina / laboratório' % G['oleo_ab']),
    ('8', 'Ritmo da semana passada', 'S38 fechou %d OS; entraram %d corretivas novas'
     % (G['fin_s37'], G['corr_criadas_s37'])),
]
y = 1.55
for num, t_, d_ in itens:
    caixa(s, 0.55, y, 0.42, 0.42, LIME, 0.5)
    tx(s, 0.55, y + 0.06, 0.42, 0.3, num, 14, NAVY, True, PP_ALIGN.CENTER)
    tx(s, 1.15, y + 0.02, 11.4, 0.4,
       [[(t_ + ' — ', INK, True, 13), (d_, BODY, False, 12)]], 13)
    y += 0.66

# ── 3 PANORAMA POR CLIENTE ───────────────────────────────────────────
s = slide('Panorama por cliente — onde está o risco', 'PCM - Portfólio')
kpi(s, 0.55, 1.5, 2.9, str(G['corr_ab']), 'corretivas abertas', AMBER)
kpi(s, 3.6, 1.5, 2.9, str(G['mpa_venc'] + G['mps_venc']), 'MPA/MPS vencidas', RED)
kpi(s, 6.65, 1.5, 2.9, '%d%%' % G['mpm_pct'], 'MPM de setembro', AMBER)
kpi(s, 9.7, 1.5, 3.05, str(G['backlog_os']), 'OS paradas há +30 dias', RED)


def fmt_mpm(c):
    if c['mpm_pct'] is None:
        return ('—', BODY, False)
    cor = GREEN if c['mpm_pct'] >= 80 else (AMBER if c['mpm_pct'] >= 45 else RED)
    return ('%d%%' % c['mpm_pct'], cor, True)


linhas = []
for c in CLIS:
    ant = c['antiga']
    linhas.append((
        (nome_cli(c['cli']), NAVY, True),
        '%d em %d usinas' % (c['corr_ab'], c['usinas_corr']) if c['corr_ab'] else '—',
        (str(c['corr_30d']), RED if c['corr_30d'] >= 5 else BODY, c['corr_30d'] >= 5),
        '%d / %d' % (c['mpa_ab'], c['mpa_venc']) if c['mpa_ab'] else '—',
        '%d / %d' % (c['mps_ab'], c['mps_venc']) if c['mps_ab'] else '—',
        fmt_mpm(c),
        ('OS %s · %s · %dd' % (ant['os'], usina_curta(ant['u'])[:18], ant['dias']),
         RED if ant and ant['dias'] > 60 else BODY, False) if ant else '—'))
tabela(s, 0.55, 2.85, 12.2,
       ['Cliente', 'Corretivas abertas', '+30d', 'MPA ab/venc', 'MPS ab/venc',
        'MPM set', 'OS aberta mais antiga'],
       [1.55, 1.95, 0.7, 1.35, 1.35, 1.0, 4.3], linhas, hrow=0.29)

# ── 4 THOPEN ─────────────────────────────────────────────────────────
c = tho
s = slide('Thopen — maior volume do portfólio', 'PCM - Pontos por cliente 1/3')
kpi(s, 0.55, 1.5, 2.9, str(c['corr_ab']), 'corretivas abertas em %d usinas' % c['usinas_corr'], AMBER)
kpi(s, 3.6, 1.5, 2.9, str(c['mpa_venc']), 'MPA vencidas (%d abertas)' % c['mpa_ab'], RED)
kpi(s, 6.65, 1.5, 2.9, str(c['mps_venc']), 'MPS vencidas (%d abertas)' % c['mps_ab'], RED)
kpi(s, 9.7, 1.5, 3.05, '%d%%' % c['mpm_pct'], 'MPM set (%d/%d tarefas)' % (c['mpm_fei'], c['mpm_tot']), AMBER)
tx(s, 0.55, 2.85, 12.2, 0.3, 'Usinas com mais corretivas abertas:', 12, INK, True)
linhas = [((usina_curta(u['u']), NAVY, True), ('%d OS' % u['n'], AMBER, True))
          for u in c['top_usinas']]
tabela(s, 0.55, 3.25, 5.6, ['Usina', 'Corretivas'], [4.0, 1.6], linhas)
caixa(s, 6.55, 3.25, 6.2, 1.85, CALL)
tx(s, 6.8, 3.45, 5.7, 1.6, [
    [('Vitória da semana: ', NAVY, True, 12),
     ('a OS 6340 (MPS de Aparecida do Taboado, 118 dias — a mais antiga do portfólio) '
      'foi FECHADA.', GREEN, True, 12)],
    [('Mais antiga agora: ', NAVY, True, 11),
     ('OS %s — %s (%s), programada em %s — ' % (c['antiga']['os'],
      usina_curta(c['antiga']['u']), c['antiga']['t'][:30], c['antiga']['d']),
      BODY, False, 11),
     ('%d dias' % c['antiga']['dias'], RED, True, 11)]], 12)
caixa(s, 0.55, 5.6, 12.2, 1.15, CALL)
lider = ' e '.join(usina_curta(u['u']) for u in c['top_usinas'][:2])
tx(s, 0.75, 5.75, 11.8, 0.9, [
    [('Desafio da semana: ', NAVY, True, 12),
     ('fechar o mês — MPM em %d%% com %d usinas pendentes; '
      % (c['mpm_pct'], len(c['mpm_pend_usinas'])), INK, False, 12),
     ('%d MPA e %d MPS vencidas (Araçoiaba SPDA e Mandaguaçu caixa d\'água com 81d) '
      'e %d handovers abertos (slide 9).'
      % (c['mpa_venc'], c['mps_venc'], c['ho_ab']), INK, False, 12)],
    [('%s seguem liderando em corretivas — revisar na programação de hoje.' % lider,
      BODY, False, 11)]], 12)

# ── 5 ATHON + AXIS ───────────────────────────────────────────────────
s = slide('Athon e Axis — atenção concentrada', 'PCM - Pontos por cliente 2/3')


def bloco_cli(x, c, bullets):
    caixa(s, x, 1.55, 5.95, 5.3, CALL)
    tx(s, x + 0.25, 1.8, 5.4, 0.4, nome_cli(c['cli']), 18, NAVY, True)
    kpis = [('%d' % c['corr_ab'], 'corretivas abertas', AMBER),
            ('%d' % c['corr_30d'], 'com +30 dias', RED if c['corr_30d'] else NAVY),
            ('%d%%' % (c['mpm_pct'] or 0), 'MPM setembro',
             RED if (c['mpm_pct'] or 0) < 45 else AMBER)]
    kx = x + 0.25
    for v, r_, cor in kpis:
        caixa(s, kx, 2.35, 1.75, 0.95, WHITE)
        tx(s, kx + 0.12, 2.44, 1.5, 0.5, v, 24, cor, True)
        tx(s, kx + 0.12, 2.95, 1.55, 0.3, r_, 9, BODY)
        kx += 1.88
    tx(s, x + 0.25, 3.55, 5.5, 3.1,
       [[('•  ', NAVY, True, 11.5), (b, INK, False, 11.5)] for b in bullets], 11.5)


bloco_cli(0.55, ath, [
    'OS 8338 — Timon 1: trackers parados, aberta há %d dias (desde 24/06).' % ath['antiga']['dias'],
    '%d das %d corretivas com +30 dias — Marabá 2 e Santa Maria do Pará (5 OS cada) lideram agora.'
    % (ath['corr_30d'], ath['corr_ab']),
    'MPM de setembro em %d%% — %d usinas pendentes para fechar até 30/09.'
    % (ath['mpm_pct'], len(ath['mpm_pend_usinas'])),
    'MPA de Mãe do Rio 1 venceu dia 17/09 — está em execução (plano de ação com a Athon).',
])
bloco_cli(6.8, axi, [
    'As %d MPA abertas estão TODAS vencidas — e agora inclui Marialva 1 (crítica, pendente de envio de relatório).'
    % axi['mpa_ab'],
    'Petrolina 2 chegou a %d dias (desde 08/06) — cobrar a execução do desligamento combinado com o Caio.'
    % axi['mpa_antiga']['dias'],
    'MPM de setembro em %d%% — %d usinas pendentes.'
    % (axi['mpm_pct'], len(axi['mpm_pend_usinas'])),
    '%d corretivas abertas em %d usinas — Marialva 1 concentra 3.'
    % (axi['corr_ab'], axi['usinas_corr']),
])

# ── 6 DEMAIS CLIENTES ────────────────────────────────────────────────
s = slide('Demais clientes — um ponto por linha', 'PCM - Pontos por cliente 3/3')
resto = [
    ('RenoGrid', '5 MPA abertas, TODAS vencidas e Muito Crítico na Gerencial (cluster com 1 técnico só); MPM em 0%.', RED),
    ('GD Energy', 'MPM em 20%; exaustores do trafo de Guajirú seguem abertos há 62 dias (2 corretivas +30d).', RED),
    ('Alves Lima', 'MPM de setembro em 0% (12 tarefas em Morada Nova 1) — corretivas zeradas.', RED),
    ('Sal Energia', 'MPM subiu de 8% para 44% — bom avanço; reparo de estruturas de Aquiraz 2 chegou a 32d.', AMBER),
    ('Greenyellow', 'MPM em 94%; seguem as 3 MPA vencidas — Cedro 1 (79d) com falta de ferramentas relatada.', AMBER),
    ('2C', 'MPM em 68% (entraram usinas novas no plano); chamado STI de Sete Lagoas 2 há 55d; MPA de Tupi Paulista vencida.', AMBER),
    ('Ultragaz', 'ZEROU as corretivas e fechou a MPM em 100% — restam só as 2 MPA vencidas de Ibirapuã (41d).', GREEN),
    ('Semp', 'MPM 100%; análise do descasamento de geração de Tucano 1 completou 30 dias.', GREEN),
]
y = 1.65
for nome, txt_, cor in resto:
    caixa(s, 0.55, y, 12.2, 0.52, CALL, 0.12)
    barra = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.55), Inches(y),
                               Inches(0.09), Inches(0.52))
    barra.fill.solid(); barra.fill.fore_color.rgb = cor
    barra.line.fill.background(); barra.shadow.inherit = False
    tx(s, 0.85, y + 0.11, 1.85, 0.3, nome, 12, NAVY, True)
    tx(s, 2.75, y + 0.12, 9.9, 0.3, txt_, 11, INK)
    y += 0.62

# ── 7 MPM SETEMBRO ───────────────────────────────────────────────────
s = slide('MPM de setembro — última semana, %d%% feito' % G['mpm_pct'],
          'PCM - Preventiva mensal')
kpi(s, 0.55, 1.5, 2.9, '%d%%' % G['mpm_pct'], '%d de %d tarefas' % (G['mpm_fei'], G['mpm_tot']), AMBER)
kpi(s, 3.6, 1.5, 2.9, 'Ultragaz · Semp', 'já fecharam 100%', GREEN, sz=18)
kpi(s, 6.65, 1.5, 2.9, 'Reno · GD · Alves', 'em 0–20% — foco da semana', RED, sz=17)
kpi(s, 9.7, 1.5, 3.05, '30/09', 'o mês fecha quarta — meta 100%', NAVY, sz=26)
mpms = sorted([c for c in CLIS if c['mpm_tot']], key=lambda c: c['mpm_pct'])
linhas = [((nome_cli(c['cli']), NAVY, True),
           '%d/%d' % (c['mpm_fei'], c['mpm_tot']),
           fmt_mpm(c),
           str(len(c['mpm_pend_usinas'])),
           ', '.join(usina_curta(u) for u in c['mpm_pend_usinas'][:4])[:62]
           + (' …' if len(c['mpm_pend_usinas']) > 4 else ''))
          for c in mpms]
tabela(s, 0.55, 2.85, 12.2,
       ['Cliente', 'Feitas', '%', 'Usinas pend.', 'Onde falta'],
       [1.7, 1.1, 0.8, 1.2, 7.4], linhas, hrow=0.31)

# ── 8 MPA E MPS POR CLIENTE ──────────────────────────────────────────
OBS = json.load(io.open('_s39_mpas_obs.json', encoding='utf-8'))
CRIT_RANK = {'muito crítico': 0, 'crítico': 1, 'alto': 2, 'médio': 3, 'baixo': 4}
CRIT_COR = {0: RED, 1: RED, 2: AMBER, 3: AMBER, 4: GREEN}


def crit_obs(cli):
    ent = OBS.get(cli, [])
    if not ent:
        return None
    ent = sorted(ent, key=lambda e: (CRIT_RANK.get(e['crit'].lower(), 9),
                                     not e['obs']))
    e = ent[0]
    rank = CRIT_RANK.get(e['crit'].lower(), 9)
    partes = [p.strip() for p in e['obs'].replace('\n', ' ').split('•') if p.strip()]
    obs = partes[-1] if partes else ''
    if obs:
        obs = '%s: %s' % (usina_curta(e['u']), obs)
    return (e['crit'] or '—', CRIT_COR.get(rank, BODY), rank <= 1, obs)


def fmt_dias(d):
    if d > 0:
        return ('%dd' % d, RED if d > 45 else AMBER, d > 45)
    return ('no prazo', GREEN, False) if d < 0 else ('hoje', AMBER, False)


def fmt_ant(a):
    if not a:
        return '—'
    idade, cor, b = fmt_dias(a['dias'])
    return ('OS %s · %s · %s' % (a['os'], usina_curta(a['u'])[:16], idade), cor, b)


s = slide('MPA e MPS — abertas e vencidas por cliente', 'PCM - Anuais e semestrais')
kpi(s, 0.55, 1.5, 2.9, str(G['mpa_ab']), 'OS de MPA abertas', AMBER)
kpi(s, 3.6, 1.5, 2.9, str(G['mpa_venc']), 'MPA já vencidas', RED)
kpi(s, 6.65, 1.5, 2.9, str(G['mps_ab']), 'OS de MPS abertas', AMBER)
kpi(s, 9.7, 1.5, 3.05, str(G['mps_venc']), 'MPS vencidas (todas Thopen)', RED)
camp = [c for c in CLIS if c['mpa_ab'] or c['mps_ab']]
camp.sort(key=lambda c: -(c['mpa_venc'] + c['mps_venc']))
linhas = []
for c in camp:
    onde = sorted({usina_curta(u) for u in c['mpa_usinas'] + c['mps_usinas']})
    co = crit_obs(c['cli'])
    linhas.append((
        (nome_cli(c['cli']), NAVY, True),
        ('%d / %d' % (c['mpa_ab'], c['mpa_venc']),
         RED if c['mpa_venc'] >= 3 else BODY, c['mpa_venc'] >= 3),
        fmt_ant(c['mpa_antiga']),
        ('%d / %d' % (c['mps_ab'], c['mps_venc']),
         RED if c['mps_venc'] >= 3 else BODY, c['mps_venc'] >= 3) if c['mps_ab'] else '—',
        fmt_ant(c['mps_antiga']),
        (', '.join(onde[:2]) + (' +%d' % (len(onde) - 2) if len(onde) > 2 else ''))[:28],
        (co[0], co[1], co[2]) if co else '—',
        ((co[3][:76] + ('…' if len(co[3]) > 76 else '')) if co and co[3] else '—')))
tabela(s, 0.55, 2.7, 12.2,
       ['Cliente', 'MPA ab/venc', 'MPA mais antiga', 'MPS ab/venc',
        'MPS mais antiga', 'Onde', 'Criticidade', 'Observações'],
       [1.15, 0.9, 1.95, 0.9, 1.9, 1.6, 0.95, 2.85], linhas, hrow=0.46, sz=8.5)
tx(s, 4.7, 7.08, 8.05, 0.3,
   'Criticidade e observações: Gerencial - PCM_2026_R00, aba MPAS (usina mais '
   'crítica de cada cliente) · 21/09.', 8.5, BODY, False, PP_ALIGN.RIGHT)

# ── 9 HANDOVER ───────────────────────────────────────────────────────
s = slide('Handover — pendências de entrada de usina', 'PCM - Handover')
HO = D['handover']
ho_venc = [h for h in HO if h['antiga'] and h['antiga']['dias'] > 0]
kpi(s, 0.55, 1.5, 2.9, str(G['ho_ab']), 'OS de handover abertas (todas Thopen)', AMBER)
kpi(s, 3.6, 1.5, 2.9, str(len(HO)), 'usinas com handover aberto', NAVY)
kpi(s, 6.65, 1.5, 2.9, str(len(ho_venc)), 'já passaram da data', RED)
kpi(s, 9.7, 1.5, 3.05, '%dd' % HO[0]['antiga']['dias'],
    'a mais antiga (%s)' % usina_curta(HO[0]['u']), RED)
linhas = [((usina_curta(h['u']), NAVY, True),
           ('OS %s' % ' / '.join(h['oss']), NAVY, False),
           str(h['tarefas']),
           h['antiga']['t'].replace('Handover – ', '').replace('Handover - ', '')
           .replace(' (Seco/Óleo)', '')[:40],
           h['antiga']['d'],
           fmt_dias(h['antiga']['dias']))
          for h in HO]
tabela(s, 0.55, 2.85, 12.2,
       ['Usina', 'OS', 'Tarefas', 'Escopo mais antigo', 'Programada', 'Idade'],
       [2.9, 1.35, 0.85, 4.1, 1.2, 1.8], linhas, hrow=0.222, sz=9)

# ── 10 BACKLOG +30D POR SUPERVISOR ───────────────────────────────────
s = slide('O estoque antigo por supervisor — %d OS há +30 dias' % G['backlog_os'],
          'PCM - Backlog')
BL = D['backlog']
grupos = defaultdict(list)
for x in BL:
    grupos[x.get('sup') or 'Sem cluster'].append(x)
ordem = sorted(grupos.items(), key=lambda kv: -len(kv[1]))
col_y = {0.55: 1.45, 6.78: 1.45}
CHIP_W, CHIP_H, HEAD_H = 2.93, 0.21, 0.27
for sup, oss in ordem:
    oss.sort(key=lambda x: -x['dias'])
    alt = HEAD_H + 0.03 + ((len(oss) + 1) // 2) * CHIP_H + 0.06
    x0 = min(col_y, key=lambda k: col_y[k])
    y0 = col_y[x0]
    caixa(s, x0, y0, 5.95, HEAD_H - 0.02, NAVY, 0.16)
    tx(s, x0 + 0.14, y0 + 0.028, 4.4, 0.22, sup, 10.5, WHITE, True)
    tx(s, x0 + 4.3, y0 + 0.028, 1.5, 0.22, '%d OS' % len(oss), 10.5, LIME, True,
       PP_ALIGN.RIGHT)
    for i, x in enumerate(oss):
        cx = x0 + (i % 2) * (CHIP_W + 0.09)
        cy = y0 + HEAD_H + 0.03 + (i // 2) * CHIP_H
        cor = RED if x['dias'] > 60 else AMBER
        caixa(s, cx, cy, CHIP_W, 0.185, CALL, 0.2)
        tx(s, cx + 0.08, cy + 0.018, CHIP_W - 0.14, 0.16,
           [[('OS %s ' % x['os'], NAVY, True, 8.5),
             ('%dd ' % x['dias'], cor, True, 8.5),
             ('· %s' % usina_curta(x['u'])[:19], BODY, False, 8)]], 8.5)
    col_y[x0] = y0 + alt

# ── 11 DESAFIOS DA SEMANA ────────────────────────────────────────────
s = slide('Nossos desafios — o combinado da segunda', 'PCM - Semana 39')
desafios = [
    ('Fechar a MPM de setembro (100% até 30/09)',
     'o mês fecha na quarta — foco em RenoGrid, GD Energy e Alves Lima (0–20%%) e nas %d usinas pendentes da Thopen.'
     % len(tho['mpm_pend_usinas'])),
    ('Zerar as MPA vencidas mais antigas',
     'Petrolina 2 (Axis, 104d — cobrar o desligamento), Mandaguaçu 1 (81d), Cedro 1 (79d) e as 5 da RenoGrid (Muito Crítico).'),
    ('Decidir as %d MPS vencidas da Thopen' % G['mps_venc'],
     'a 6340 fechou — agora a mais antiga é a SPDA de Araçoiaba da Serra 1 (81d): faz, reprograma ou cancela.'),
    ('Destravar os handovers mais antigos',
     'Coração 1 e 2 (65d), Colorado 1 (45d) e Diamantino 1 (41d) — plano por usina no slide 9.'),
    ('Reduzir o estoque de corretivas +30d',
     '%d OS — começar pelas %d da Athon (Timon 1: trackers parados há %dd); cada supervisor olha o seu bloco do slide 10.'
     % (G['corr_30d'], ath['corr_30d'], ath['antiga']['dias'])),
    ('Análise de óleo',
     '%d OS abertas — atualizar o estágio logístico (enviar / rota / usina / laboratório) na OS.' % G['oleo_ab']),
    ('Fechamento na sexta',
     'na sexta (25/09) revisamos estes pontos com os dados novos da API — o que fechou, o que ficou.'),
]
y = 1.5
for i, (t_, d_) in enumerate(desafios, 1):
    caixa(s, 0.55, y, 0.4, 0.4, LIME, 0.5)
    tx(s, 0.55, y + 0.055, 0.4, 0.28, str(i), 13, NAVY, True, PP_ALIGN.CENTER)
    tx(s, 1.12, y, 11.5, 0.72,
       [[(t_ + ' — ', INK, True, 12.5)], [(d_, BODY, False, 11)]], 12.5)
    y += 0.78

DEST = (r'C:\Users\Fabricio Barreto\OneDrive - GRID CO\Shortcuts'
        r'\GRID CO_ - 4. O&M\11.Pré-Operação\9. Reuniões\0. Grid Interno'
        r'\1. Inicio e Fechamento da Semana\Inicio Semana39_Desafios_PCM_R00.pptx')
prs.save(DEST)
prs.save('_s39_inicio.pptx')
print('ok -> %s (%d slides)' % (DEST, len(prs.slides._sldIdLst)))
