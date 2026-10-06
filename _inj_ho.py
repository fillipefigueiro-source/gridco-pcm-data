# -*- coding: utf-8 -*-
"""Injeta o bloco 7 (Handovers em andamento) na pagina 2 do R08 -> R09."""
import io, json, re

HO = json.load(io.open('_ho_vivo.json', encoding='utf-8'))


def curta(u):
    m = re.match(r'^[^-]+?\s*-\s*(.+?)\s*-\s*[A-Za-z]{2}\s*$', ' '.join(str(u).split()))
    return (m.group(1) if m else u).strip()


def trunc(s_, n):
    s_ = str(s_).strip()
    return s_ if len(s_) <= n else s_[:n].rsplit(' ', 1)[0] + '…'


def dcor(d):
    return 'red' if d > 60 else ('amber' if d > 35 else '')


tot_t = sum(e['n'] for e in HO)
linhas = []
for e in HO:
    linhas.append(
        '<tr><td class="navy">%s (Thopen)</td><td class="navy">OS %s</td>'
        '<td class="n">%d</td><td class="n">%d</td>'
        '<td class="n %s"><b>%d d</b></td><td class="navy">%s</td><td>%s</td></tr>'
        % (curta(e['u']), ' / '.join(e['oss']), e['n'], e['atr'],
           dcor(e['dias']), e['dias'], trunc(e['resp'], 24), trunc(e['sup'], 20)))
BLOCO = ('<div class="row" style="grid-template-columns: 1fr; margin-top: 12px;">'
         '<div class="card"><div class="tag">7 · HANDOVERS EM ANDAMENTO</div>'
         '<h2>Entrada de usinas: %d tarefas vivas em %d usinas (14 OS), todas Thopen</h2>'
         '<table><tr><th>Usina</th><th>OS</th><th class="n">Tarefas</th>'
         '<th class="n">Atrasadas</th><th class="n">Mais antiga</th>'
         '<th>Responsável</th><th>Supervisor</th></tr>%s</table>'
         '<div class="nota">Só OS vivas (handover de OS finalizada não conta). '
         'Guatambú (56 tarefas) e Assis Chateaubriand (61) são os maiores pacotes; '
         'Coração 1 e 2 é o mais antigo (80 d).</div></div></div>\n'
         % (tot_t, len(HO), ''.join(linhas)))

html = io.open('_onepage_semana41_r08.html', encoding='utf-8').read()
alvo = '<div class="foot">\n  <span>Grid Co. · PCM · Semana 41 · página 2 de 2'
assert alvo in html
html = html.replace(alvo, BLOCO + alvo)
html = html.replace('<div class="t">MPAS atrasadas e usinas críticas</div>',
                    '<div class="t">MPAS atrasadas, handovers em andamento e usinas críticas</div>')
html = html.replace('7 · Backlog atrasado por região, cluster e usina',
                    '8 · Backlog atrasado por região, cluster e usina')
html = html.replace('Emitido em 05/10 · R08', 'Emitido em 05/10 · R09')
io.open('_onepage_semana41_r09.html', 'w', encoding='utf-8').write(html)
print('ok -> _onepage_semana41_r09.html (%d usinas no bloco)' % len(HO))
