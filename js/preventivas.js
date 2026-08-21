// ─────────────────────────────────────────────────────────────────────────────
// preventivas.js — Gestão PCM: matriz de conclusão das preventivas (21/08/2026)
// Script clássico, carrega DEPOIS de app.js, mesmo escopo global.
//
// É a versão embutida do artifact aprovado pelo PCM: tabela dinâmica por OS
// (não por tarefa) respondendo "essa usina já fez a preventiva do mês?".
// Linhas, colunas e valor configuráveis; subtotais; total geral; formatação
// condicional; legenda das colunas acima da tabela.
//
// REGRA DE OURO do projeto: `estado` (da TAREFA) ≠ `osStatus` (da OS).
// Concluído = estado === 'Finalizada'. Nunca o status da OS.
//
// DECISÕES DE INTEGRAÇÃO:
// · Engate por reatribuição de renderGestao (padrão do mpas_extras.js) — o
//   app.js não é tocado.
// · A matriz NÃO segue os filtros da toolbar da aba, de propósito: o filtro de
//   Estado esconderia as finalizadas e todo percentual sairia errado; o de
//   período brigaria com o seletor de mês daqui. Ela usa gpScopedTarefas()
//   (respeita o papel: cliente só vê o dele) + controles próprios. O subtítulo
//   do bloco avisa.
// · Meses são DINÂMICOS: o corrente e os dois anteriores — nada de lista fixa
//   que envelhece.
// · Grupos iniciam FECHADOS: o bloco abre mostrando ~10 linhas de subtotal por
//   cliente (visão executiva), e cada grupo expande no clique.
// · Prefixo de classe gpv- em tudo: a colisão .grupo/.seg no artifact custou
//   uma rodada de depuração — aqui ninguém compartilha nome com o app.js.
// ─────────────────────────────────────────────────────────────────────────────

let GPV = { dim: 'cli', col: 'sig', val: 'pct', mes: 'todos', busca: '',
            ordem: 'pend', desc: true, fechados: null, aberto: true };

const GPV_SIGLAS = ['MPM', 'MPS', 'MPA'];
const GPV_RX = /\b(MP[MSAT])\b/;
const GPV_MESNOME = ['', 'jan', 'fev', 'mar', 'abr', 'mai', 'jun',
                     'jul', 'ago', 'set', 'out', 'nov', 'dez'];

function gpvMeses() {                      // mês corrente + 2 anteriores
  const out = [], d = new Date();
  for (let i = 2; i >= 0; i--) {
    const m = new Date(d.getFullYear(), d.getMonth() - i, 1);
    out.push(m.getFullYear() + '-' + String(m.getMonth() + 1).padStart(2, '0'));
  }
  return out;
}
const gpvRotMes = m => GPV_MESNOME[+m.split('-')[1]] + '/' + m.slice(2, 4);

// ── base atômica: (cliente,usina,cluster,resp,sigla,mês) -> {f,t,os{}} ──────
// Cacheada por geradoEm+usuário: 20 mil tarefas não precisam ser revarridas a
// cada clique de controle.
let _gpvCacheKey = null, _gpvBase = null;

function gpvBase() {
  const key = ((GESTAO_DB && GESTAO_DB.geradoEm) || '') + '|' + (S.user || '');
  if (_gpvBase && _gpvCacheKey === key) return _gpvBase;
  const MESES = gpvMeses(), reg = new Map();
  gpScopedTarefas().forEach(t => {
    const m = GPV_RX.exec(String(t.tarefa || ''));
    if (!m) return;
    const mes = String(t.dataProg || '').slice(0, 7);
    if (MESES.indexOf(mes) < 0) return;
    const sig = m[1] === 'MPT' ? 'MPA' : m[1];      // MPT é raro; agrega na anual? NÃO:
    if (m[1] === 'MPT') return;                     // fora — só MPM/MPS/MPA, como no artifact
    const k = [t.cliente || '—', t.usina || '—', t.cluster || '—',
               t.responsavel || '—', sig, mes].join('');
    let c = reg.get(k);
    if (!c) { c = { f: 0, t: 0, os: {} }; reg.set(k, c); }
    const fin = String(t.estado || '') === 'Finalizada' ? 1 : 0;
    c.f += fin; c.t += 1;
    const o = String(t.os || '—');
    const p = c.os[o] || [0, 0];
    c.os[o] = [p[0] + fin, p[1] + 1];
  });
  _gpvBase = [];
  reg.forEach((c, k) => {
    const [cli, usi, clu, res, sig, mes] = k.split('');
    _gpvBase.push({ cli, usi, clu, res, sig, mes, f: c.f, t: c.t,
      os: Object.keys(c.os).sort().map(o => '#' + o + ' (' + c.os[o][0] + '/' + c.os[o][1] + ')') });
  });
  _gpvCacheKey = key;
  return _gpvBase;
}

// ── pivô ────────────────────────────────────────────────────────────────────
const gpvCols = () => GPV.col === 'sig' ? GPV_SIGLAS : gpvMeses();
const gpvRotCol = c => GPV.col === 'sig' ? c : gpvRotMes(c);
const gpvFaixa = p => p === null ? 'nulo' : (p >= 100 ? 'ok' : (p < 40 ? 'crit' : 'and'));
const gpvSoma = arr => { const o = { f: 0, t: 0 }; arr.forEach(c => { if (c) { o.f += c.f; o.t += c.t; } }); return o; };
const gpvPct = c => (c && c.t) ? Math.round(100 * c.f / c.t) : null;

function gpvPivo() {
  let R = gpvBase();
  if (GPV.mes !== 'todos') R = R.filter(r => r.mes === GPV.mes);
  if (GPV.busca) {
    // sem acento dos dois lados: "jacunda" tem que achar "Jacundá"
    const sem = s => String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    const q = sem(GPV.busca);
    R = R.filter(r => sem(r.usi + ' ' + r.cli + ' ' + r.clu + ' ' + r.res).indexOf(q) >= 0);
  }
  const G = new Map();
  R.forEach(r => {
    const g = GPV.dim === 'usi' ? '—' :
              GPV.dim === 'cli' ? r.cli : GPV.dim === 'clu' ? r.clu : r.res;
    if (!G.has(g)) G.set(g, new Map());
    const M = G.get(g);
    if (!M.has(r.usi)) M.set(r.usi, {});
    const cel = M.get(r.usi), k = GPV.col === 'sig' ? r.sig : r.mes;
    if (!cel[k]) cel[k] = { f: 0, t: 0, os: [] };
    cel[k].f += r.f; cel[k].t += r.t;
    cel[k].os = cel[k].os.concat(r.os);
  });
  return G;
}

function gpvMostra(c) {
  if (!c || !c.t) return { txt: '—', cls: 'nulo' };
  const p = Math.round(100 * c.f / c.t);
  const v = GPV.val === 'pct' ? p + '%' : GPV.val === 'pend' ? (c.t - c.f)
          : GPV.val === 'fei' ? c.f : c.t;
  return { txt: String(v), cls: gpvFaixa(p) };
}

// ── render ──────────────────────────────────────────────────────────────────
function gpvRender() {
  const box = document.getElementById('gp-preventivas');
  if (!box || !GESTAO_DB) return;
  if (GPV.fechados === null) GPV.fechados = new Set();   // preenchido abaixo

  const CS = gpvCols(), G = gpvPivo();

  // grupos iniciam FECHADOS: na primeira renderização (ou troca de dimensão),
  // todos entram no conjunto de fechados
  if (GPV._dimAnterior !== GPV.dim) {
    GPV.fechados = new Set(G.keys());
    GPV._dimAnterior = GPV.dim;
  }

  let grupos = [];
  G.forEach((M, g) => {
    const filhos = [];
    M.forEach((cel, usi) => filhos.push({ nome: usi, cel, tudo: gpvSoma(CS.map(c => cel[c])) }));
    const cel = {};
    CS.forEach(c => { cel[c] = gpvSoma(filhos.map(x => x.cel[c])); });
    grupos.push({ nome: g, filhos, cel, tudo: gpvSoma(CS.map(c => cel[c])) });
  });

  const chave = x => {
    if (GPV.ordem === 'nome') return null;
    if (GPV.ordem === 'pend') return x.tudo.t - x.tudo.f;
    if (GPV.ordem === 'geral') return x.tudo.t ? x.tudo.f / x.tudo.t : 2;
    const c = x.cel[GPV.ordem]; return c ? (c.t ? c.f / c.t : 2) : 3;
  };
  const ord = (a, b) => {
    if (GPV.ordem === 'nome')
      return GPV.desc ? b.nome.localeCompare(a.nome, 'pt-BR') : a.nome.localeCompare(b.nome, 'pt-BR');
    const x = chave(a), y = chave(b);
    return GPV.desc ? y - x : x - y;
  };
  grupos.sort(ord); grupos.forEach(g => g.filhos.sort(ord));

  // ── cabeçalho do bloco ──
  const VAL_ROT = { pct: '% de tarefas finalizadas', pend: 'tarefas que ainda faltam',
                    fei: 'tarefas já finalizadas', tot: 'total de tarefas' };
  let h = '<div class="gpv-box"><div class="gpv-top" onclick="gpvTog()">'
    + '<div><div class="gpv-tit">&#128202; Conclusão das preventivas <span class="gpv-mat">matriz por OS</span></div>'
    + '<div class="gpv-sub">Concluído = todas as tarefas finalizadas · independente dos filtros acima — use os controles do bloco</div></div>'
    + '<span class="gpv-chev">' + (GPV.aberto ? '&#9662;' : '&#9656;') + '</span></div>';

  if (!GPV.aberto) { box.innerHTML = h + '</div>'; return; }

  // ── controles ──
  const seg = (id, ops, atual) => '<div class="gpv-seg">' + ops.map(([v, r]) =>
    '<button type="button" class="' + (v === atual ? 'on' : '') + '" '
    + 'onclick="gpvSet(&quot;' + id + '&quot;,&quot;' + v + '&quot;)">' + r + '</button>').join('') + '</div>';
  h += '<div class="gpv-ctl" onclick="event.stopPropagation()">'
    + '<span class="gpv-rot">Linhas</span>' + seg('dim',
        [['cli', 'Cliente &#9656; Usina'], ['clu', 'Cluster &#9656; Usina'],
         ['res', 'Responsável &#9656; Usina'], ['usi', 'Só usina']], GPV.dim)
    + '<span class="gpv-rot">Colunas</span>' + seg('col', [['sig', 'Tipo'], ['mes', 'Mês']], GPV.col)
    + '<span class="gpv-rot">Valor</span>' + seg('val',
        [['pct', '%'], ['pend', 'Pendentes'], ['fei', 'Feitas'], ['tot', 'Total']], GPV.val)
    + '<span class="gpv-rot">Mês</span>' + seg('mes',
        [['todos', 'Todos']].concat(gpvMeses().map(m => [m, gpvRotMes(m)])), GPV.mes)
    + '<input class="gpv-busca" placeholder="filtrar&hellip;" value="' + gpEsc(GPV.busca) + '" '
    + 'oninput="GPV.busca=this.value;gpvRender();'
    + 'var i=document.querySelector(\'#gp-preventivas .gpv-busca\');if(i){i.focus();i.setSelectionRange(i.value.length,i.value.length);}">'
    + '<button type="button" class="gpv-lnk" onclick="gpvExpTog()">'
    + (GPV.fechados.size ? 'Expandir tudo' : 'Recolher tudo') + '</button></div>';

  // ── legenda das colunas (a lição do print do PA LESTE 01) ──
  h += '<div class="gpv-guia">'
    + '<div><b>MPM</b> mensal</div><div><b>MPS</b> semestral</div><div><b>MPA</b> anual</div>'
    + '<div><b>Geral</b> as três somadas</div><div><b>Pendentes</b> o que falta, em número</div>'
    + '<div><b>Célula</b> ' + VAL_ROT[GPV.val] + '; a cor sempre segue o percentual</div></div>';

  // ── tabela ──
  const rotL = GPV.dim === 'cli' ? 'Cliente &#9656; Usina' : GPV.dim === 'clu' ? 'Equipe Cluster &#9656; Usina'
             : GPV.dim === 'res' ? 'Responsável &#9656; Usina' : 'Usina';
  const th = (id, rot, cls) => '<th class="' + (cls || '') + (GPV.ordem === id ? ' ativo' : '') + '" '
    + 'onclick="gpvOrd(&quot;' + id + '&quot;)">' + rot
    + '<span class="gpv-ord">' + (GPV.ordem === id ? (GPV.desc ? '&#9660;' : '&#9650;') : '&#8597;') + '</span></th>';

  h += '<div class="gpv-rolo"><table class="gpv-tbl">'
    + '<colgroup><col style="width:300px">'
    + CS.map(() => '<col style="width:92px">').join('')
    + '<col style="width:100px"><col style="width:88px"></colgroup>'
    + '<thead><tr>' + th('nome', rotL, 'rotlin')
    + CS.map(c => th(c, gpvRotCol(c))).join('')
    + th('geral', 'Geral') + th('pend', 'Pendentes') + '</tr></thead><tbody>';

  const celTd = c => {
    const m = gpvMostra(c);
    const t = c && c.os && c.os.length ? 'OS — ' + Array.from(new Set(c.os)).sort().join('   ')
            : 'sem preventiva no período';
    return '<td><span class="gpv-cel ' + m.cls + '" title="' + gpEsc(t) + '">' + m.txt + '</span></td>';
  };
  const fimTd = x => {
    const p = gpvPct(x.tudo);
    return '<td><span class="gpv-cel ' + gpvFaixa(p) + '">' + (p === null ? '—' : p + '%')
      + '</span></td><td class="gpv-num">' + (x.tudo.t - x.tudo.f) + '</td>';
  };

  let linhas = 0;
  grupos.forEach(g => {
    const plano = GPV.dim === 'usi';
    if (!plano) {
      const ab = !GPV.fechados.has(g.nome);
      // classe 'gpv-sub', NUNCA 'grupo' — ver cabeçalho deste arquivo
      h += '<tr class="gpv-sub" onclick="gpvAlt(this)" data-g="' + gpEsc(g.nome) + '">'
        + '<td class="rotlin"><span class="gpv-chev2">' + (ab ? '&#9662;' : '&#9656;') + '</span>'
        + '<b>' + gpEsc(g.nome) + '</b> <span class="gpv-mini">' + g.filhos.length + ' usina'
        + (g.filhos.length > 1 ? 's' : '') + '</span></td>'
        + CS.map(c => celTd(g.cel[c])).join('') + fimTd(g) + '</tr>';
      linhas++;
      if (!ab) return;
    }
    g.filhos.forEach(f => {
      h += '<tr class="' + (plano ? '' : 'gpv-filho') + '"><td class="rotlin"><b>'
        + gpEsc(f.nome) + '</b></td>'
        + CS.map(c => celTd(f.cel[c])).join('') + fimTd(f) + '</tr>';
      linhas++;
    });
  });
  if (!linhas) h += '<tr><td colspan="' + (CS.length + 3) + '" class="gpv-vazio">Nada com esse filtro.</td></tr>';

  const totCol = {}; CS.forEach(c => { totCol[c] = gpvSoma(grupos.map(g => g.cel[c])); });
  const totG = gpvSoma(CS.map(c => totCol[c]));
  h += '<tr class="gpv-total"><td class="rotlin"><b>TOTAL GERAL</b> <span class="gpv-mini">'
    + grupos.reduce((s, g) => s + g.filhos.length, 0) + ' usinas</span></td>'
    + CS.map(c => celTd(totCol[c])).join('') + fimTd({ tudo: totG }) + '</tr>';
  h += '</tbody></table></div>';

  h += '<div class="gpv-leg">'
    + '<span><i style="background:#fbe0e0"></i>abaixo de 40%</span>'
    + '<span><i style="background:#fdf0d4"></i>40% a 99%</span>'
    + '<span><i style="background:#dcf2de"></i>100%</span>'
    + '<span><i style="background:#eef0f5"></i>sem preventiva no período</span>'
    + '<span class="gpv-fim">clique no cliente para abrir as usinas · no cabeçalho para ordenar · passe o mouse na célula para ver as OS</span>'
    + '</div></div>';

  box.innerHTML = h;
}

// ── handlers ────────────────────────────────────────────────────────────────
function gpvTog() { GPV.aberto = !GPV.aberto; gpvRender(); }
function gpvSet(campo, v) { GPV[campo] = v; gpvRender(); }
function gpvOrd(id) {
  if (GPV.ordem === id) GPV.desc = !GPV.desc;
  else { GPV.ordem = id; GPV.desc = (id !== 'nome'); }
  gpvRender();
}
function gpvAlt(tr) {
  const g = tr.getAttribute('data-g');
  GPV.fechados.has(g) ? GPV.fechados.delete(g) : GPV.fechados.add(g);
  gpvRender();
}
function gpvExpTog() {
  if (GPV.fechados.size) GPV.fechados = new Set();
  else GPV.fechados = new Set(gpvPivo().keys());
  gpvRender();
}

// ── engate: roda junto com o render da aba (padrão do mpas_extras.js) ──────
if (typeof renderGestao === 'function') {
  const _renderGestaoOrig = renderGestao;
  renderGestao = function () {
    _renderGestaoOrig.apply(this, arguments);
    try { gpvRender(); } catch (e) { console.warn('preventivas:', e); }
  };
}
