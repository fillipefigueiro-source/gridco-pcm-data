// ─────────────────────────────────────────────────────────────────────────────
// mpas_aging.js — Gestão PCM: "MPA & MPS — Envelhecimento e Pendências" (16/09/2026)
// Script clássico, carrega DEPOIS de app.js e preventivas.js (mesmo escopo global).
//
// O QUE É: bloco executivo das anuais/semestrais — as mais ANTIGAS primeiro
// (Data Prevista da Gerencial ↑), com a Data Programada do Fracttal ao lado,
// dias de atraso, criticidade e a ÚLTIMA observação datada. KPIs de topo são
// FILTROS (clicáveis). Fonte: mpas.json CIFRADO (repo público) — o bloco tem
// desbloqueio inline com a senha de admin; cliente logado não vê o bloco.
//
// NARRATIVA (spec 16/09): atraso nunca aparece sozinho — sempre com a causa
// (observação datada) e a próxima data (programada). Régua: ≤30d monitorar,
// 31–90 atenção, >90 crítico. "Sem OS"/"sem data" é pendência de GESTÃO
// (chip tracejado), não falha vermelha — vermelho é só atraso real.
//
// REGRA DE OURO: usa mpSit() (situação pela TAREFA via MP.bd), nunca Status da OS.
// Prefixo gma- em tudo; reusa gpvMpUltObs/gpvMpCls/GPV_MP_DATA do preventivas.js.
// ─────────────────────────────────────────────────────────────────────────────

let GMA = { tipo: 'todos', pend: 'todas', busca: '', ordem: 'prev', desc: false,
            aberto: null, estado: 'nao', erro: '' };

const gmaEsc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const gmaFmtD = iso => iso ? iso.slice(8, 10) + '/' + iso.slice(5, 7) + '/' + iso.slice(2, 4) : '';
function gmaDias(iso) {           // dias corridos de iso até hoje (positivo = passado)
  if (!iso) return null;
  return Math.floor((Date.now() - new Date(iso + 'T12:00:00').getTime()) / 86400000);
}
const gmaHoje = () => new Date().toISOString().slice(0, 10);

// ── carga (mesmo cofre da aba Gestão MPAS) ──────────────────────────────────
async function gmaCarregar() {
  if (GMA.estado === 'carregando' || GMA.estado === 'ok') return;
  let senha = ''; try { senha = sessionStorage.getItem('gc_mp_k') || ''; } catch (e) {}
  if (!MP && !senha) { GMA.estado = 'trancado'; return; }
  GMA.estado = 'carregando';
  try {
    const dados = MP || await mpDecifrar(await mpCarregarPack(), senha);
    if (!MP) MP = dados;          // destrava também a aba Gestão MPAS e a matriz
    GMA.estado = 'ok';
  } catch (e) { GMA.estado = 'trancado'; GMA.erro = ''; }
  gmaRender();
}
async function gmaAbrir() {
  const inp = document.getElementById('gma-pwd'), err = document.getElementById('gma-err');
  const senha = (inp && inp.value || '').trim();
  if (!senha) { if (err) err.textContent = 'Digite a senha.'; return; }
  if (err) err.textContent = 'Abrindo…';
  try {
    const dados = await mpDecifrar(await mpCarregarPack(), senha);
    MP = dados;
    try { sessionStorage.setItem('gc_mp_k', senha); } catch (e) {}
    GMA.estado = 'ok';
    gmaRender();
    try { GPV_MP.estado = 'nao'; gpvRender(); } catch (e) {}   // matriz destrava junto
  } catch (e) { if (err) err.textContent = 'Senha incorreta — verifique e tente novamente.'; }
}

// ── modelo: uma linha por manutenção (MPA/MPS) ──────────────────────────────
function gmaLinhas() {
  const hoje = gmaHoje();
  const out = [];
  ((MP && MP.manut) || []).forEach(m => {
    const tipo = String(m.tipo || '').toUpperCase().indexOf('MPS') >= 0 ? 'MPS' : 'MPA';
    // OS: campo pode trazer "123/456" — vale a primeira achada no Fracttal
    let os = '', bd = null;
    String(m.os || '').split(/[\/,;]/).map(x => x.trim()).filter(Boolean).forEach(p => {
      if (!bd && MP.bd && MP.bd[p]) { os = p; bd = MP.bd[p]; }
      if (!os) os = p;
    });
    // Data Programada (Fracttal) = 1ª data programada entre as tarefas da OS
    let prog = null;
    if (bd && bd.tasks) bd.tasks.forEach(t => { if (t.prog && (!prog || t.prog < prog)) prog = t.prog; });
    const sit = mpSit(m);                                    // situação pela TAREFA
    const conclu = sit.k === 'Concluída';
    const atraso = (!conclu && m.prevista && m.prevista < hoje) ? gmaDias(m.prevista) : null;
    const obs = gpvMpUltObs(m.obs);
    const od = GPV_MP_DATA.exec(obs);
    const obsIso = od ? od[3] + '-' + od[2] + '-' + od[1] : null;
    out.push({
      cliente: m.cliente || '—', usina: m.usina_curta || m.usina || '—',
      nome: (m.cliente ? m.cliente + ' – ' : '') + (m.usina_curta || m.usina || '—'),
      cluster: m.cluster || '', tipo, crit: m.criticidade || '',
      prev: m.prevista || null, prog, atraso,
      os, semOS: !os, osSemPar: !!os && !bd, semData: !!bd && !prog,
      sit, conclu, obs, obsIso, obsVelha: obsIso ? (gmaDias(obsIso) > 60) : false,
      equipe: m.equipe || '', apoio: m.apoio || '', statusPlan: m.status || '',
      bdFin: bd ? bd.fin : null, bdTot: bd ? bd.total : null,
      diverge: !!(m.prevista && prog && Math.abs(gmaDias(m.prevista) - gmaDias(prog)) > 30),
    });
  });
  return out;
}

const gmaFxAtraso = d => d == null || d <= 0 ? '' : d <= 30 ? 'f1' : d <= 90 ? 'f2' : 'f3';

// ── render ──────────────────────────────────────────────────────────────────
function gmaRender() {
  const box = document.getElementById('gp-mpas-aging');
  if (!box) return;
  // restrito: cliente logado não vê o bloco (dados internos da Gerencial)
  if (typeof S !== 'undefined' && S && S.isAdmin === false) { box.innerHTML = ''; return; }

  if (GMA.estado === 'nao') { gmaCarregar(); }
  if (GMA.estado === 'carregando') {
    box.innerHTML = '<div class="gp-b"><h3>MPA &amp; MPS — Envelhecimento e Pendências</h3>'
      + '<div class="gma-trava">Abrindo os dados da Gerencial…</div></div>';
    return;
  }
  if (GMA.estado !== 'ok') {
    box.innerHTML = '<div class="gp-b"><h3>MPA &amp; MPS — Envelhecimento e Pendências'
      + '<span class="gp-obs">fonte: Gerencial (aba MPAS) + Fracttal</span></h3>'
      + '<div class="gma-trava"><div class="gma-cad">&#128274;</div>'
      + '<b>Dados restritos da Gerencial</b>'
      + '<p>Este bloco usa o plano MPA/MPS cifrado. Digite a senha de administrador para '
      + 'desbloquear — vale apenas nesta sessão.</p>'
      + '<div class="gma-form"><input type="password" id="gma-pwd" placeholder="senha de admin" '
      + 'onkeydown="if(event.key===\'Enter\')gmaAbrir()">'
      + '<button onclick="gmaAbrir()">Desbloquear</button></div>'
      + '<div class="gma-err" id="gma-err"></div></div></div>';
    return;
  }

  let ls = gmaLinhas();

  // KPIs (sempre do universo inteiro, antes dos filtros — são eles os filtros)
  const kAtr = ls.filter(x => x.sit.k === 'Atrasada').length;
  const kSem = ls.filter(x => (x.semOS || x.osSemPar) && !x.conclu).length;
  const kSd  = ls.filter(x => x.semData && !x.conclu).length;
  const kOk  = ls.filter(x => x.conclu).length;
  const kpi = (id, v, rot, cls) => '<div class="gma-kpi ' + cls + (GMA.pend === id ? ' on' : '')
    + '" onclick="gmaSet(\'pend\',\'' + (GMA.pend === id ? 'todas' : id) + '\')">'
    + '<div class="v">' + v + '</div><div class="l">' + rot + '</div></div>';

  // filtros do bloco
  if (GMA.tipo !== 'todos') ls = ls.filter(x => x.tipo === GMA.tipo);
  if (GMA.pend === 'atraso') ls = ls.filter(x => x.sit.k === 'Atrasada');
  if (GMA.pend === 'semos') ls = ls.filter(x => (x.semOS || x.osSemPar) && !x.conclu);
  if (GMA.pend === 'semdata') ls = ls.filter(x => x.semData && !x.conclu);
  if (GMA.pend === 'concl') ls = ls.filter(x => x.conclu);
  if (GMA.busca) {
    const q = GMA.busca.toLowerCase();
    ls = ls.filter(x => (x.nome + ' ' + x.os).toLowerCase().indexOf(q) >= 0);
  }

  // ordenação (default: Data Prevista ↑ — o bloco existe p/ ver as mais antigas)
  const chave = { prev: x => x.prev || '9999', prog: x => x.prog || '9999',
    atraso: x => -(x.atraso || -1), nome: x => x.nome.toLowerCase(),
    crit: x => ({ 'crit': 0, 'and': 1, 'ok': 2, '': 3 })[gpvMpCls(x.crit)] }[GMA.ordem]
    || (x => x.prev || '9999');
  ls.sort((a, b) => { const x = chave(a), y = chave(b);
    return (x < y ? -1 : x > y ? 1 : 0) * (GMA.desc ? -1 : 1); });

  const th = (id, rot, w) => '<th' + (w ? ' style="width:' + w + '"' : '')
    + ' class="' + (GMA.ordem === id ? 'ativo' : '') + '" onclick="gmaOrd(\'' + id + '\')">'
    + rot + '<span class="gpv-ord">' + (GMA.ordem === id ? (GMA.desc ? '&#9660;' : '&#9650;') : '&#8597;') + '</span></th>';
  const seg = (campo, ops) => '<div class="gpv-seg">' + ops.map(([v, r]) =>
    '<button class="' + (GMA[campo] === v ? 'on' : '') + '" onclick="gmaSet(\'' + campo + '\',\'' + v + '\')">'
    + r + '</button>').join('') + '</div>';

  let h = '<div class="gp-b"><h3>MPA &amp; MPS — Envelhecimento e Pendências'
    + '<span class="gp-obs">Gerencial (aba MPAS) + Fracttal · controles próprios — ignora a barra acima</span></h3>'
    + '<div class="gma-kpis">'
    + kpi('atraso', kAtr, 'atrasadas', 'red')
    + kpi('semos', kSem, 'sem OS no Fracttal', 'amb')
    + kpi('semdata', kSd, 'com OS, sem data programada', 'amb')
    + kpi('concl', kOk + '<small>/' + gmaLinhas().length + '</small>', 'concluídas', 'grn')
    + '</div>'
    + '<div class="gma-ctl">' + seg('tipo', [['todos', 'MPA + MPS'], ['MPA', 'MPA'], ['MPS', 'MPS']])
    + '<input class="gma-busca" placeholder="filtrar usina ou OS…" value="' + gmaEsc(GMA.busca) + '"'
    + ' oninput="GMA.busca=this.value;gmaRender();'
    + 'var i=document.querySelector(\'#gp-mpas-aging .gma-busca\');if(i){i.focus();i.setSelectionRange(i.value.length,i.value.length);}">'
    + '<span class="gma-n">' + ls.length + ' manutenç' + (ls.length === 1 ? 'ão' : 'ões') + '</span></div>';

  h += '<div class="gpv-rolo"><table class="gpv-tbl gma-tbl"><thead><tr>'
    + th('nome', 'Cliente – Usina', '220px') + th('tipo', 'Tipo', '58px')
    + th('crit', 'Criticidade', '92px')
    + th('prev', 'Prevista <small>(Gerencial)</small>', '104px')
    + th('prog', 'Programada <small>(Fracttal)</small>', '108px')
    + th('atraso', 'Atraso', '72px') + '<th style="width:86px">OS</th>'
    + '<th style="width:104px">Situação</th><th class="gpv-obs-th">Última observação</th>'
    + '</tr></thead><tbody>';

  if (!ls.length) h += '<tr><td colspan="9" class="gpv-vazio">Nada com esses filtros.</td></tr>';
  ls.forEach((x, i) => {
    const fx = gmaFxAtraso(x.atraso);
    const osTd = x.semOS ? '<span class="gma-semos" title="atividade ainda sem OS criada no Fracttal">sem OS</span>'
      : x.osSemPar ? '<span class="gma-semos" title="OS ' + gmaEsc(x.os) + ' da planilha não localizada no Fracttal">' + gmaEsc(x.os) + ' ?</span>'
      : gmaEsc(x.os);
    const progTd = x.prog
      ? gmaFmtD(x.prog) + (x.diverge ? ' <span class="gma-div" title="programada difere da prevista em mais de 30 dias">&#9679;</span>' : '')
      : (x.semData ? '<span class="gma-nulo" title="OS criada, sem data programada no Fracttal">—</span>' : '<span class="gma-nulo">—</span>');
    const obsData = x.obsIso ? '<b class="' + (x.obsVelha ? 'gma-obs-velha' : '') + '">' + gmaFmtD(x.obsIso) + '</b> ' : '';
    // a entrada já começa com a própria data — sem tirar, ela apareceria duas vezes
    const obsTxt = x.obs.replace(/^\d{2}\/\d{2}\/\d{4}\s*[-–—:]*\s*/, '');
    h += '<tr class="gma-lin' + (x.conclu ? ' gma-ok' : '') + (GMA.aberto === i ? ' aberta' : '')
      + '" onclick="gmaExp(' + i + ')">'
      + '<td class="rotlin"><b>' + gmaEsc(x.nome) + '</b></td>'
      + '<td><span class="gma-tipo">' + x.tipo + '</span></td>'
      + '<td>' + (x.crit ? '<span class="gpv-crit ' + gpvMpCls(x.crit) + '">' + gmaEsc(x.crit) + '</span>' : '<span class="gma-nulo">—</span>') + '</td>'
      + '<td class="gma-dt">' + (x.prev ? gmaFmtD(x.prev) : '<span class="gma-nulo">—</span>') + '</td>'
      + '<td class="gma-dt">' + progTd + '</td>'
      + '<td>' + (x.atraso != null ? '<span class="gma-atr ' + fx + '">' + x.atraso + ' d</span>'
                  : (x.conclu ? '<span class="gma-check">&#10003;</span>' : '<span class="gma-nulo">—</span>')) + '</td>'
      + '<td>' + osTd + '</td>'
      + '<td><span class="gma-sit ' + x.sit.cls + '">' + gmaEsc(x.sit.k) + '</span></td>'
      + '<td class="gpv-obs" title="' + gmaEsc(x.obs) + '">' + obsData + (obsTxt ? gmaEsc(obsTxt.slice(0, 110)) : '<span class="gma-nulo">—</span>') + '</td></tr>';
    if (GMA.aberto === i) {
      h += '<tr class="gma-det"><td colspan="9"><div class="gma-det-in">'
        + (x.obs ? '<p><b>Observação (última entrada):</b> ' + gmaEsc(x.obs) + '</p>' : '')
        + '<p>' + (x.equipe ? '<b>Equipe:</b> ' + gmaEsc(x.equipe.split('\n')[0]) + ' · ' : '')
        + (x.apoio ? '<b>Apoio:</b> ' + gmaEsc(x.apoio) + ' · ' : '')
        + (x.statusPlan ? '<b>Status na planilha:</b> ' + gmaEsc(x.statusPlan) + ' · ' : '')
        + (x.bdTot != null ? '<b>Tarefas no Fracttal:</b> ' + x.bdFin + '/' + x.bdTot + ' finalizadas' : '')
        + '</p></div></td></tr>';
    }
  });
  h += '</tbody></table></div>';

  h += '<div class="gpv-leg">'
    + '<span><i style="background:#fdf0d4"></i>atraso 1–30 d</span>'
    + '<span><i style="background:#f8dfb8"></i>31–90 d</span>'
    + '<span><i style="background:#fbe0e0"></i>&gt;90 d</span>'
    + '<span>chip tracejado = pendência de gestão (sem OS / sem par no Fracttal)</span>'
    + '<span class="gpv-fim">atraso = hoje − Data Prevista · clique na linha para o detalhe · situação pela TAREFA, nunca pelo Status da OS</span>'
    + '</div></div>';
  box.innerHTML = h;
}

// ── handlers ────────────────────────────────────────────────────────────────
function gmaSet(campo, v) { GMA[campo] = v; GMA.aberto = null; gmaRender(); }
function gmaOrd(id) {
  if (GMA.ordem === id) GMA.desc = !GMA.desc;
  else { GMA.ordem = id; GMA.desc = (id === 'atraso' || id === 'crit') ? false : false; }
  GMA.aberto = null; gmaRender();
}
function gmaExp(i) { GMA.aberto = (GMA.aberto === i ? null : i); gmaRender(); }

// ── engate: roda junto com o render da aba (padrão do preventivas.js) ───────
if (typeof renderGestao === 'function') {
  const _renderGestaoOrigGma = renderGestao;
  renderGestao = function () {
    _renderGestaoOrigGma.apply(this, arguments);
    try { gmaRender(); } catch (e) { console.warn('mpas_aging:', e); }
  };
}
