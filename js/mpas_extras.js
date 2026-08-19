// ─────────────────────────────────────────────────────────────────────────────
// mpas_extras.js — Gestão MPAS: Cronograma (Gantt), % de conclusão e planilha
// geral. Criado em 14/08/2026. Script clássico, mesmo escopo global do app.js.
//
// 1) mpPct(r)      — % de conclusão vindo do FRACTTAL, não da planilha.
//    A coluna B da aba MPAS pode trazer VÁRIAS OS ("3637/5430", e há casos com
//    quatro). O percentual é o das tarefas de TODAS elas somadas: finalizadas
//    sobre total. Sem OS cadastrada ou sem cruzamento, devolve null — e a tela
//    escreve "sem OS", em vez de fingir 0%.
// 2) mpGantt()     — cronograma por mês, navegável, com a barra preenchida na
//    proporção do % acima.
// 3) mpGeral()     — planilha geral no fim da aba, respeitando os filtros.
// 4) mpAcao()      — painel "O que precisa da sua atenção" (19/08/2026):
//    organiza por AÇÃO em vez de por cluster, com dono em cada cartão, e
//    traz as observações da planilha. Os cartões são filtros da aba.
// ─────────────────────────────────────────────────────────────────────────────

let MP_GANTT_MES = null;             // 'YYYY-MM' em exibição
let MP_GERAL_ABERTO = false;

function mpOSs(r){                    // "3637/5430" -> ['3637','5430']
  return String(r.os || '').split(/[\/,;]+/).map(s => s.trim()).filter(Boolean);
}

function mpPct(r){
  const bd = (MP && MP.bd) || {};
  let tot = 0, fin = 0, achou = false;
  mpOSs(r).forEach(o => {
    const b = bd[o];
    if (!b) return;
    achou = true;
    tot += (b.total || 0);
    fin += (b.fin || 0);
  });
  if (!achou || !tot) return null;
  return Math.round(100 * fin / tot);
}

function mpPctInfo(r){
  const p = mpPct(r);
  if (p === null) return { p: null, txt: mpOSs(r).length ? 'sem cruzamento' : 'sem OS' };
  return { p: p, txt: p + '%' };
}

// ── 1) CRONOGRAMA (GANTT) ───────────────────────────────────────────────────
function mpGanttMeses(){
  const s = new Set();
  (MP && MP.manut || []).forEach(r => { if (r.prevista) s.add(String(r.prevista).slice(0, 7)); });
  return [...s].sort();
}

function mpGanttNav(delta){
  const ms = mpGanttMeses();
  const i = ms.indexOf(MP_GANTT_MES);
  const j = Math.min(ms.length - 1, Math.max(0, (i < 0 ? 0 : i) + delta));
  MP_GANTT_MES = ms[j];
  mpGantt();
}
function mpGanttSet(v){ MP_GANTT_MES = v; mpGantt(); }

function mpGantt(){
  const box = document.getElementById('mp-gantt');
  if (!box || !MP) return;
  const ms = mpGanttMeses();
  if (!ms.length) { box.innerHTML = ''; return; }
  if (!MP_GANTT_MES || ms.indexOf(MP_GANTT_MES) < 0) {
    const hoje = new Date().toISOString().slice(0, 7);
    MP_GANTT_MES = ms.indexOf(hoje) >= 0 ? hoje : ms[ms.length - 1];
  }
  const mes = MP_GANTT_MES;
  const [ano, mm] = mes.split('-').map(Number);
  const dias = new Date(ano, mm, 0).getDate();
  const hojeISO = new Date().toISOString().slice(0, 10);

  // respeita os filtros da aba; o mês manda no recorte
  const base = (typeof mpFilt === 'function' ? mpFilt() : MP.manut);
  const lin = base.filter(r => String(r.prevista || '').slice(0, 7) === mes)
                  .sort((a, b) => String(a.prevista).localeCompare(String(b.prevista)));
  const atrasadas = base.filter(r => r.prevista && r.prevista < hojeISO
                                  && mpSit(r).k !== 'Concluída').length;

  const opts = ms.map(v => {
    const n = base.filter(r => String(r.prevista || '').slice(0, 7) === v).length;
    const d = new Date(Number(v.slice(0, 4)), Number(v.slice(5, 7)) - 1, 1);
    const nome = d.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });
    return '<option value="' + v + '"' + (v === mes ? ' selected' : '') + '>'
         + nome.charAt(0).toUpperCase() + nome.slice(1) + ' (' + n + ')</option>';
  }).join('');

  let h = '<div class="gt-box"><div class="gt-top">'
    + '<div class="gt-tit">Cronograma (Gantt)</div>'
    + '<div class="gt-nav">'
    + '<button class="gt-b" onclick="mpGanttNav(-1)" title="Mês anterior">&#8249;</button>'
    + '<select class="gt-sel" onchange="mpGanttSet(this.value)">' + opts + '</select>'
    + '<button class="gt-b" onclick="mpGanttNav(1)" title="Próximo mês">&#8250;</button>'
    + '<span class="gt-info">' + lin.length + ' no mês'
    + (atrasadas ? ' &middot; <b class="gt-atr">&#9888; ' + atrasadas + ' atrasadas</b>' : '')
    + '</span></div></div>';

  if (!lin.length) {
    h += '<div class="gt-vazio">Nenhuma manutenção prevista neste mês com os filtros atuais.</div></div>';
    box.innerHTML = h; return;
  }

  h += '<div class="gt-rows">';
  lin.forEach(r => {
    const ini = String(r.prevista).slice(0, 10);
    const dIni = Number(ini.slice(8, 10));
    // duração: se há início e término reais, usa-os; senão, 1 semana de janela
    let dur = 7;
    if (r.inicio && r.termino) {
      const a = new Date(r.inicio), b = new Date(r.termino);
      if (!isNaN(a) && !isNaN(b) && b >= a) dur = Math.max(1, Math.round((b - a) / 864e5) + 1);
    }
    const left = ((dIni - 1) / dias) * 100;
    const width = Math.min(dur / dias * 100, 100 - left);
    const info = mpPctInfo(r);
    const sit = mpSit(r);
    const cor = (r.tipo === 'MPA') ? '#b45309' : '#1d4ed8';
    const atrasada = ini < hojeISO && sit.k !== 'Concluída';
    h += '<div class="gt-row" onclick="mpModal(\'' + esc(String(r.os || '')) + '|'
       + esc(r.usina || '') + '|' + esc(r.tipo || '') + '|' + esc(r.prevista || '') + '\')">'
       + '<div class="gt-lb"><div class="gt-u">' + esc(r.usina_curta || r.usina || '—')
       + (atrasada ? ' <span class="gt-atr">&#9888;</span>' : '') + '</div>'
       + '<div class="gt-c">' + esc([r.cliente, r.cluster, r.tipo].filter(Boolean).join(' · '))
       + ' &middot; <b>' + esc(r.status || '') + '</b></div>'
       + '<div class="gt-os">' + (r.os ? 'OS ' + esc(r.os) : '<i>sem OS</i>')
       + ' &middot; ' + info.txt + '</div></div>'
       + '<div class="gt-tk"><div class="gt-bar" style="left:' + left + '%;width:' + width
       + '%;background:' + cor + '">'
       + (info.p ? '<span class="gt-fill" style="width:' + info.p + '%"></span>' : '')
       + '<span class="gt-d">' + ini.slice(8, 10) + '/' + ini.slice(5, 7) + '</span></div></div></div>';
  });
  h += '</div><div class="gt-scale"><span>1</span><span>' + Math.round(dias / 4) + '</span><span>'
     + Math.round(dias / 2) + '</span><span>' + Math.round(3 * dias / 4) + '</span><span>'
     + dias + '</span></div></div>';
  box.innerHTML = h;
}

// ── 2) PLANILHA GERAL ───────────────────────────────────────────────────────
const MP_GERAL_COLS = [
  ['Cliente',      r => r.cliente],
  ['Usina',        r => r.usina_curta || r.usina],
  ['Cluster',      r => r.cluster],
  ['Tipo',         r => r.tipo],
  ['OS',           r => r.os],
  ['Prevista',     r => mpDia(r.prevista)],
  ['Início',       r => mpDia(r.inicio)],
  ['Término',      r => mpDia(r.termino)],
  ['Status',       r => r.status],
  ['Situação',     r => mpSit(r).k],
  ['% concluído',  r => mpPctInfo(r).txt],
  ['Prioridade',   r => r.prioridade],
  ['Ciclo',        r => r.ciclo],
  ['Supervisor',   r => r.supervisor],
  // 19/08: as duas colunas que explicam a linha — o motivo concreto (colunas de
  // pendência da planilha) e a última observação com a data dela. Vão junto no
  // CSV, que é como o time leva a lista para a reunião.
  ['Por que está parado', r => (typeof mpMotivo === 'function' ? mpMotivo(r).txt : '')],
  ['Última observação',   r => { if (typeof mpObsInfo !== 'function') return '';
                                 const o = mpObsInfo(r);
                                 return o.txt ? ((o.iso ? o.iso.split('-').reverse().join('/') + ': ' : '') + o.txt) : ''; }],
];

function mpGeralTog(){ MP_GERAL_ABERTO = !MP_GERAL_ABERTO; mpGeral(); }

function mpGeral(){
  const box = document.getElementById('mp-geral');
  if (!box || !MP) return;
  const rows = (typeof mpFilt === 'function' ? mpFilt() : MP.manut);
  let h = '<div class="mpg-top"><div class="mpg-tit">Planilha geral</div>'
    + '<div><span class="mpg-n">' + rows.length + ' linha(s) &middot; respeita os filtros acima</span>'
    + '<button class="mpg-b" onclick="mpGeralCSV()">&#8595; CSV</button>'
    + '<button class="mpg-b" onclick="mpGeralTog()">' + (MP_GERAL_ABERTO ? '&#9650; Ocultar' : '&#9660; Mostrar')
    + '</button></div></div>';
  if (MP_GERAL_ABERTO) {
    h += '<div class="mpg-wrap"><table class="mpg-tbl"><thead><tr>'
       + MP_GERAL_COLS.map(c => '<th>' + c[0] + '</th>').join('') + '</tr></thead><tbody>';
    rows.forEach(r => {
      h += '<tr>' + MP_GERAL_COLS.map(c => '<td>' + esc(c[1](r) ?? '') + '</td>').join('') + '</tr>';
    });
    h += '</tbody></table></div>';
  }
  box.innerHTML = h;
}

function mpGeralCSV(){
  const rows = (typeof mpFilt === 'function' ? mpFilt() : MP.manut);
  if (!rows.length) { toast('Nada para exportar com os filtros atuais.'); return; }
  const esc2 = v => { v = String(v ?? ''); return /[";\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
  const linhas = [MP_GERAL_COLS.map(c => c[0]).join(';')];
  rows.forEach(r => linhas.push(MP_GERAL_COLS.map(c => esc2(c[1](r))).join(';')));
  const blob = new Blob(['﻿' + linhas.join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'Gestao_MPAS_' + new Date().toISOString().slice(0, 10) + '.csv';
  a.click(); URL.revokeObjectURL(a.href);
  toast('CSV: ' + rows.length + ' linha(s)');
}

// ─────────────────────────────────────────────────────────────────────────────
// 3) PAINEL DE AÇÃO — "O que precisa da sua atenção" (19/08/2026)
//
// A aba nasceu por Equipe Cluster, que é a chave de quem EXECUTA. O gerente
// operacional e o financeiro não achavam o que era deles: o atraso ficava
// diluído na árvore e o bloqueio por compra aparecia só como rodapé do bloco de
// frentes. Este painel entra no topo e organiza por AÇÃO, com dono em cada
// cartão. Os cartões são FILTROS (MP_ACAO, no app.js): clicar recorta a aba
// inteira, porque KPIs, Gantt, árvore e planilha geral passam por mpFilt().
//
// As observações vêm de três lugares diferentes da planilha Gerencial:
//   · aba MPAS, col. "Observação"          -> histórico datado (o que houve)
//   · aba MPAS, cols. de pendência          -> o motivo concreto (por que parou)
//   · aba "Compra Equip MPA 2026", col. obs -> a nota do PCM sobre cada kit
// ─────────────────────────────────────────────────────────────────────────────

// A planilha NÃO padroniza o separador da data: convivem "• 06/07/2026: texto"
// e "• 03/06/2026 - texto" (e travessão). Aceitar só os dois-pontos fazia o
// parser enxergar 50 de 118 observações e descartar as outras 68.
const MP_RX_OBS = /^•\s*(\d{2})\/(\d{2})\/(\d{4})\s*[:–—-]\s*(.+)$/;

function mpIdadeDias(iso){
  const h = new Date(); h.setHours(0,0,0,0);
  return Math.round((h - new Date(iso + 'T00:00:00')) / 864e5);
}

// Devolve a nota MAIS RECENTE + a idade dela. Uma nota de dois meses atrás não
// descreve a situação de hoje, e o gerente precisa enxergar isso.
function mpObsInfo(r){
  const t = String(r.obs || '').trim();
  if (!t) return { txt:'', iso:null, br:'', idade:null, hist:'' };
  const notas = [], base = [];
  t.split(/\r?\n/).forEach(ln => {
    ln = ln.trim(); if (!ln) return;
    const m = MP_RX_OBS.exec(ln);
    if (m) notas.push({ iso: m[3]+'-'+m[2]+'-'+m[1], br: m[1]+'/'+m[2], txt: m[4].trim() });
    else base.push(ln);
  });
  notas.sort((a,b) => a.iso.localeCompare(b.iso));
  const hist = (base.length ? ['Contexto: ' + base.join(' ')] : [])
    .concat(notas.map(n => n.iso.split('-').reverse().join('/') + ': ' + n.txt)).join('\n');
  if (notas.length){
    const u = notas[notas.length - 1];
    return { txt:u.txt, iso:u.iso, br:u.br, idade:mpIdadeDias(u.iso), hist:hist };
  }
  // sem bullet datado ainda É observação — antes essas sumiam e a usina
  // aparecia "sem observação" tendo o texto mais explicativo da carteira
  return { txt: base.join(' '), iso:null, br:'', idade:null, hist:hist };
}

// "Não" respondido é diferente de vazio no Excel, mas para a tela os dois
// significam "nada a mostrar aqui".
const mpVazio = v => {
  const s = String(v == null ? '' : v).trim();
  return (!s || s === '—' || s === 'False' || s === 'Não' || s === '0') ? '' : s;
};

// O MOTIVO concreto de estar parado, em uma frase; detalhe completo no title.
function mpMotivo(r){
  const p = [], det = [];
  const nlin = v => v.split(/\r?\n/).filter(x => x.trim()).length;
  const fe = mpVazio(r.falta_eq), ff = mpVazio(r.falta_fer);
  const cp = mpVazio(r.compra_princ), dl = mpVazio(r.deslig);
  if (fe){ p.push('falta ' + nlin(fe) + ' equip. do escopo');
           det.push('Equipamentos do escopo faltantes:\n' + fe); }
  if (ff){ p.push('falta ' + nlin(ff) + ' ferramenta(s)');
           det.push('Ferramentas auxiliares faltantes:\n' + ff); }
  if (cp){ const c0 = cp.split(/\r?\n/)[0];
           p.push(/oberto/.test(c0) ? 'compra coberta por outro cluster' : 'kit a comprar');
           det.push('Compra de equipamentos principais:\n' + cp); }
  if (dl){ const ls = dl.split(/\r?\n/).filter(x => x.trim());
           const ruim = ls.filter(x => /inviabiliz|chuva/i.test(x)).length;
           p.push(ls.length + ' desligamento(s)' + (ruim ? ' · ' + ruim + ' perdido(s)' : ''));
           det.push('Desligamentos programados:\n' + dl); }
  return { txt: p.join(' · '), det: det.join('\n\n') };
}

// selo de data da última observação, colorido pela idade
function mpObsSelo(o){
  if (!o.txt) return '';
  if (o.iso == null) return '<span class="mp-obsd od-sd">sem data</span>';
  const c = o.idade > 30 ? 'od-old' : (o.idade > 14 ? 'od-med' : 'od-ok');
  const extra = o.idade > 14 ? ' · ' + o.idade + 'd atrás' : '';
  return '<span class="mp-obsd ' + c + '">' + o.br + extra + '</span>';
}

function mpAcaoUsina(u){          // clicar na usina do ranking filtra a aba nela
  MP_SEL.usina.clear(); MP_SEL.usina.add(u);
  mpBuildPop('usina'); mpMsLabel('usina'); renderMpas();
}

function mpAcao(){
  const box = document.getElementById('mp-acao');
  if (!box || !MP) return;
  // a base respeita os DEMAIS filtros, mas não o próprio filtro de ação —
  // senão os números dos cartões colapsariam ao clicar num deles
  const base = (MP.manut || []).filter(mpVisBase);
  const cat = { bloq:[], atraso:[], prox:[], ok:[], futuro:[] };
  base.forEach(r => cat[mpCat(r)].push(r));

  // ATENÇÃO ao número que vai para o financeiro: só entram os kits que ainda
  // têm MPA travada. Clusters com âncora vencida cujas MPAs já foram todas
  // executadas não precisam de compra nenhuma — somá-los infla o pedido.
  const trav = mpTrav(), kits = {};
  cat.bloq.forEach(r => { if (trav[r.cluster]) kits[r.cluster] = trav[r.cluster]; });
  const lkits = Object.values(kits);
  // O bloco de frentes, logo abaixo, mostra o plano INTEIRO (jun-dez). Este
  // cartao mostra so a fatia vencida que ainda trava MPA. Sao numeros
  // diferentes na mesma tela de proposito -- dizer "X de Y" evita que pareca
  // contradicao e liga um bloco ao outro.
  const totKits = ((MP.compras && MP.compras.clusters) || []).length;
  const custo = lkits.reduce((s,c) => s + (c.valorA || 0), 0);
  const semOS = cat.atraso.concat(cat.prox).filter(r => !String(r.os||'').trim()).length;

  const acion = cat.bloq.concat(cat.atraso, cat.prox);
  const infos = new Map(acion.map(r => [r, mpObsInfo(r)]));
  const semNota = acion.filter(r => !infos.get(r).txt && !mpMotivo(r).txt).length;
  const velhas  = acion.filter(r => { const i = infos.get(r); return i.idade != null && i.idade > 30; }).length;
  const pend    = lkits.filter(c => c.pendencia);
  const custoPend = pend.reduce((s,c) => s + (c.valorA || 0), 0);

  const card = (k, cls, cor, rot, n, txt, dono) =>
    '<div class="mpa-card ' + cls + (MP_ACAO === k ? ' sel' : '') + '" onclick="mpAcaoSet(&quot;' + k + '&quot;)" '
    + 'title="clique para filtrar a aba inteira por isto">'
    + '<div class="top" style="background:' + cor + '"></div>'
    + '<div class="cl">' + rot + '</div><div class="cv">' + n + '</div>'
    + '<div class="cs">' + txt + '</div><div class="cd">' + dono + '</div></div>';

  let h = '<div class="mpa-wrap"><div class="mpa-cap">O que precisa da sua atenção · '
        + 'clique num cartão para filtrar</div><div class="mpa-grid">'
    + card('bloq','mpa-r','#b91c1c','Travadas — falta comprar', cat.bloq.length,
        'Não podem ser executadas: o kit do cluster já venceu e não foi comprado ('
        + lkits.length + ' de ' + totKits + ' kits do plano, abaixo)',
        'FINANCEIRO · ' + mpBRL(custo))
    + card('atraso','mpa-a','#b45309','Atrasadas', cat.atraso.length,
        'Passaram da data prevista e não dependem de compra', 'OPERAÇÃO')
    + card('prox','mpa-b','#1d4ed8','Vencem em 30 dias', cat.prox.length,
        'Ainda dá tempo — <b>' + semOS + '</b> sem OS criada no Fracttal', 'PCM')
    + card('ok','mpa-g','#15803d','Concluídas', cat.ok.length,
        'Executadas no período filtrado', 'EM DIA')
    + '</div>';

  const av = [];
  if (pend.length)
    av.push('<b>' + pend.length + ' kit(s)</b> (' + mpBRL(custoPend) + ') estão com a '
      + '<b>tensão da usina em branco</b> na aba MPAS — sem isso o aterramento não é '
      + 'dimensionado e a compra nem pode ser cotada. Preencher é do PCM e destrava o financeiro.');
  const pn = [];
  if (semNota) pn.push('<b>' + semNota + '</b> sem observação nem motivo registrado');
  if (velhas)  pn.push('<b>' + velhas + '</b> com a última observação há mais de 30 dias');
  if (pn.length)
    av.push('Dos <b>' + acion.length + '</b> itens que pedem ação, ' + pn.join(' e ')
      + '. Sem nota atual não dá para saber se parou por falta de equipe, de peça ou de acesso.');
  av.forEach(a => { h += '<div class="mpa-av"><span>&#128221;</span><div>' + a + '</div></div>'; });

  // ── ranking de usinas ─────────────────────────────────────────────────────
  const sc = new Map();
  base.forEach(r => {
    const u = r.usina_curta || r.usina || '—';
    let v = sc.get(u);
    if (!v){ v = { atr:0, dmax:0, bloq:0, prox:0, cli:r.cliente||'', cl:r.cluster||'',
                   obs:null, mot:null }; sc.set(u, v); }
    const c = mpCat(r);
    if (c === 'atraso'){ v.atr++;
      const d = r.prevista ? mpIdadeDias(r.prevista) : 0;
      if (d > v.dmax) v.dmax = d; }
    if (c === 'bloq') v.bloq++;
    if (c === 'prox') v.prox++;
    if (c !== 'ok'){
      const o = infos.get(r) || mpObsInfo(r);
      // nota COM data ganha da sem data; mas uma sem data ainda é melhor que nada
      if (o.txt && (!v.obs || (o.iso && (!v.obs.iso || o.iso > v.obs.iso)))) v.obs = o;
      if (!v.mot){ const mm = mpMotivo(r); if (mm.txt) v.mot = mm; }
    }
  });
  const rank = [...sc.entries()].filter(([,v]) => v.atr || v.bloq);
  rank.forEach(([,v]) => { v.score = v.atr*10 + Math.min(v.dmax,200)/10 + v.bloq*6 + v.prox*2; });
  rank.sort((a,b) => b[1].score - a[1].score);

  if (rank.length){
    h += '<div class="mpa-rank"><div class="mpa-rank-h"><div class="t">Usinas que pedem atenção</div>'
       + '<div class="s">ordenadas por gravidade — atraso, bloqueio e prazo combinados · '
       + 'clique para filtrar a usina</div></div><div class="mpa-rank-w"><table class="mpa-tbl">'
       + '<thead><tr><th></th><th>Usina</th><th>Cliente</th><th>Situação e última notícia</th>'
       + '<th>O que fazer</th></tr></thead><tbody>';
    rank.slice(0, 15).forEach(([u, v]) => {
      const cor = (v.atr && v.dmax > 60) ? '#b91c1c' : (v.atr ? '#b45309' : '#1d4ed8');
      const prob = [];
      if (v.atr)  prob.push('<b>' + v.atr + ' atrasada(s)</b> · máx ' + v.dmax + 'd');
      if (v.bloq) prob.push(v.bloq + ' travada(s) por compra');
      if (v.prox) prob.push(v.prox + ' vence(m) em 30d');
      const acao = (v.atr && v.bloq) ? 'Liberar compra + executar'
                 : v.atr ? 'Executar / reprogramar'
                 : v.bloq ? 'Liberar compra do kit' : 'Criar OS';
      let ln = prob.join(' · ');
      if (v.mot) ln += '<div class="mpa-nota mot" title="' + esc(v.mot.det) + '">&#9888; '
                     + esc(v.mot.txt) + '</div>';
      if (v.obs){
        const sel = v.obs.iso ? ('<b>' + v.obs.br + '</b>'
              + (v.obs.idade > 14 ? ' · há ' + v.obs.idade + 'd' : '') + ': ') : '<b>sem data</b>: ';
        const t = v.obs.txt.length > 95 ? v.obs.txt.slice(0,94) + '…' : v.obs.txt;
        ln += '<div class="mpa-nota" title="' + esc(v.obs.hist) + '">&#128221; ' + sel + esc(t) + '</div>';
      } else if (!v.mot){
        ln += '<div class="mpa-nota mpa-mut">&#128221; sem observação registrada</div>';
      }
      h += '<tr class="cl-row" onclick="mpAcaoUsina(&quot;' + esc(u) + '&quot;)">'
         + '<td><i class="mpa-dot" style="background:' + cor + '"></i></td>'
         + '<td class="mpa-u">' + esc(u) + '<div class="mpa-mut">' + esc(v.cl) + '</div></td>'
         + '<td>' + esc(v.cli) + '</td><td>' + ln + '</td>'
         + '<td class="mpa-acao">' + acao + '</td></tr>';
    });
    h += '</tbody></table></div></div>';
  }
  box.innerHTML = h + '</div>';
}

// ── engate: roda junto com o render da aba ──────────────────────────────────
if (typeof renderMpas === 'function') {
  const _renderMpasOrig = renderMpas;
  renderMpas = function(){
    _renderMpasOrig.apply(this, arguments);
    try { mpGantt(); } catch (e) { console.warn('gantt:', e); }
    try { mpGeral(); } catch (e) { console.warn('planilha geral:', e); }
  };
}
