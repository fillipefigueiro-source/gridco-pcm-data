// ─────────────────────────────────────────────────────────────────────────────
// preventivas.js — Gestão PCM: "Preventivas — Plano & Fila" (unificado 16/09/2026)
// Script clássico, carrega DEPOIS de app.js, mesmo escopo global.
//
// UM bloco, DOIS modos (decisão aprovada pelo PCM em 16/09, spec dos agentes
// de design e narrativa):
// · PLANO (default) — a matriz por OS de sempre: % de conclusão por
//   cliente▸usina × MPM/MPT/MPS/MPA. Responde "quanto do plano está feito".
//   MPA/MPS aparecem em FRAÇÃO feitas/total (50% de 4 anuais ≠ 50% de 200
//   mensais) e a fração é o drill-down para a Fila.
// · FILA — envelhecimento de MPA/MPS: Data Prevista (Gerencial) × Data
//   Programada (Fracttal), atraso em faixas, criticidade e última observação
//   datada. Responde "o que está velho, por quê, e o que falta".
//   Só entra na Fila quem tem Data Prevista (hoje: MPA/MPS da Gerencial);
//   MPM/MPT ficam desabilitados no seletor com aviso.
// · Faixa de topo com o PAR de números (nunca média única): Rotina % ·
//   Grandes atrasadas/mais antiga · críticas sem data futura.
// · Busca e Tipo persistem entre os modos; o modo fica na sessionStorage.
//
// FONTES: Plano = gestao_pcm.json (aberto, papel-ciente e passando pelos
// FILTROS DO TOPO da aba via gpvTarefasTop — pedido de 17/09).
// Fila = mpas.json CIFRADO (repo público). Sem a senha: admin vê a "versão
// Fracttal" da fila (usina/tipo/programada/OS/situação) + desbloqueio inline;
// cliente vê a mesma versão SEM CTA de senha e nunca vê Gerencial.
//
// REGRA DE OURO: `estado` (da TAREFA) ≠ `osStatus` (da OS).
// Concluído = estado === 'Finalizada'. Nunca o status da OS.
// Engate por reatribuição de renderGestao (padrão do mpas_extras.js).
// Prefixo gpv-/gma- (gma- são as classes CSS da fila, mantidas do bloco antigo).
// ─────────────────────────────────────────────────────────────────────────────

let GPV = { modo: null, tipo: 'todos',                       // linha 1 (persistem)
            dim: 'cli', col: 'sig', val: 'pct', mes: 'todos', busca: '',
            ordem: 'pend', desc: true, fechados: null, aberto: true,
            pend: 'todas', ordemF: 'prev', descF: false, abertoF: null,
            drill: null };                                    // {usina, tipo} do drill-down

// ── Criticidade / Observação / Fila — Gerencial (aba MPAS) ───────────────────
// Fonte cifrada; ver cabeçalho. Observação exibida = ENTRADA DATADA MAIS
// RECENTE do log ("• dd/mm/aaaa - texto") — regra da Gerencial.
let GPV_MP = { estado: 'nao', mapa: null, err: '' };   // nao|carregando|ok|erro|sem-chave

function gpvMpAtivo() {
  if (MP) return true;
  try { return !!sessionStorage.getItem('gc_mp_k'); } catch (e) { return false; }
}
function gpvMpNorm(s) {
  return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[–—]/g, '-').toLowerCase()
    .replace(/\s*-\s*[a-z]{2}\s*$/, '')      // corta o " - UF" do Fracttal
    .replace(/(\d)00\b/g, '$1')              // Gerencial "Marabá 200" ~ Fracttal "Marabá 2"
    .replace(/\butragaz\b/g, 'ultragaz')     // typo histórico do Fracttal (mesmo alias do Python)
    .replace(/[^a-z0-9]+/g, ' ').trim();
}
const GPV_MP_DATA = /(\d{2})\/(\d{2})\/(\d{4})/;
function gpvMpUltObs(txt) {
  const t = String(txt || '').trim();
  if (!t) return '';
  const pedacos = t.split(/\n|(?=•)/).map(x => x.trim()).filter(Boolean);
  let melhor = '', melhorK = '';
  pedacos.forEach(p => {
    const m = GPV_MP_DATA.exec(p);
    const k = m ? m[3] + m[2] + m[1] : '';
    if (!melhor || k >= melhorK) { melhorK = k; melhor = p; }
  });
  return melhor.replace(/^•\s*/, '');
}
async function gpvMpCarregar() {
  if (GPV_MP.estado !== 'nao') return;
  let senha = ''; try { senha = sessionStorage.getItem('gc_mp_k') || ''; } catch (e) {}
  if (!senha && !MP) { GPV_MP.estado = 'sem-chave'; return; }
  GPV_MP.estado = 'carregando';
  try {
    const dados = MP || await mpDecifrar(await mpCarregarPack(), senha);
    if (!MP) MP = dados;              // destrava também a aba Gestão MPAS
    const itens = dados.manut || dados.itens || [];
    const mapa = new Map();
    const grava = (k, it) => {
      if (!k) return;
      const prev = mapa.get(k) || { crit: '', obs: '' };
      if (it.criticidade && (!prev.crit || String(it.tipo || '').toUpperCase().indexOf('MPA') >= 0))
        prev.crit = it.criticidade;
      const o = gpvMpUltObs(it.obs);
      if (o) {
        const dm = GPV_MP_DATA.exec(o), dp = GPV_MP_DATA.exec(prev.obs || '');
        const km = dm ? dm[3] + dm[2] + dm[1] : '', kp = dp ? dp[3] + dp[2] + dp[1] : '';
        if (!prev.obs || km >= kp) prev.obs = o;
      }
      mapa.set(k, prev);
    };
    itens.forEach(it => {
      grava(gpvMpNorm(it.usina), it);
      const curta = gpvMpNorm((it.cliente ? it.cliente + ' ' : '') + (it.usina_curta || ''));
      if (curta && curta !== gpvMpNorm(it.usina)) grava(curta, it);
    });
    GPV_MP.mapa = mapa; GPV_MP.estado = 'ok';
    try { console.info('[gpv] mpas: ' + itens.length + ' itens, ' + mapa.size + ' usinas indexadas'); } catch (e) {}
  } catch (e) {
    GPV_MP.estado = 'erro';
    GPV_MP.err = String((e && e.message) || e);
    try { console.warn('[gpv] mpas indisponível: ' + GPV_MP.err); } catch (x) {}
  }
  gpvRender();
}
async function gpvMpAbrir() {
  const inp = document.getElementById('gma-pwd'), err = document.getElementById('gma-err');
  const senha = (inp && inp.value || '').trim();
  if (!senha) { if (err) err.textContent = 'Digite a senha.'; return; }
  if (err) err.textContent = 'Abrindo…';
  try {
    const dados = await mpDecifrar(await mpCarregarPack(), senha);
    MP = dados;
    try { sessionStorage.setItem('gc_mp_k', senha); } catch (e) {}
    GPV_MP.estado = 'nao';
    gpvRender();
  } catch (e) { if (err) err.textContent = 'Senha incorreta — verifique e tente novamente.'; }
}
function gpvMpCls(c) {
  // sem acento: "Crítico" tem í; "Muito Crítico" começa com M — 'crit' em
  // QUALQUER posição vem antes do balde "Média" (âmbar).
  const s = String(c || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  if (!s) return '';
  if (s.indexOf('crit') >= 0 || s.startsWith('alt')) return 'crit';
  if (s.startsWith('m')) return 'and';
  return 'ok';
}
function gpvMpTd(nomeUsina) {
  if (GPV_MP.estado === 'carregando') return '<td class="gpv-obs">…</td>';
  if (GPV_MP.estado !== 'ok')
    return '<td class="gpv-obs" title="dados da Gerencial cifrados — desbloqueie no modo Fila">🔒</td>';
  const k = gpvMpNorm(nomeUsina);
  let hit = GPV_MP.mapa.get(k);
  if (!hit) {
    for (const [kk, v] of GPV_MP.mapa) {
      if (kk.startsWith(k) || k.startsWith(kk)
          || (kk.length >= 8 && k.indexOf(kk) >= 0) || (k.length >= 8 && kk.indexOf(k) >= 0)) { hit = v; break; }
    }
  }
  if (!hit) return '<td class="gpv-obs">—</td>';
  const badge = hit.crit
    ? '<span class="gpv-crit ' + gpvMpCls(hit.crit) + '">' + gpEsc(hit.crit) + '</span>' : '';
  const obs = hit.obs
    ? gpEsc(hit.obs.length > 90 ? hit.obs.slice(0, 90) + '…' : hit.obs)
    : '<span class="gpv-obs-vazio">—</span>';
  return '<td class="gpv-obs" title="' + gpEsc(hit.obs || '') + '">' + badge + obs + '</td>';
}

const GPV_SIGLAS = ['MPM', 'MPT', 'MPS', 'MPA'];   // ordem de cadência (MPT entrou em 26/08)
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
const gpvFmtD = iso => iso ? iso.slice(8, 10) + '/' + iso.slice(5, 7) + '/' + iso.slice(2, 4) : '';
function gpvDias(iso) {
  if (!iso) return null;
  return Math.floor((Date.now() - new Date(iso + 'T12:00:00').getTime()) / 86400000);
}
const gpvHoje = () => new Date().toISOString().slice(0, 10);

// ── filtros do TOPO da aba valem aqui também (pedido de 17/09) ──────────────
// gpFilteredTarefas = multi-seleção + OS/Solicitação + período; GP.soAtrasadas
// é aplicado à parte (na aba ele troca a árvore por lista, não entra no filtro).
function gpvTarefasTop() {
  let arr = (typeof gpFilteredTarefas === 'function') ? gpFilteredTarefas() : gpScopedTarefas();
  if (typeof GP !== 'undefined' && GP && GP.soAtrasadas) arr = arr.filter(t => t.aberta && t.atrasado);
  return arr;
}
function gpvFiltroKey() {           // entra na chave do cache do gpvBase
  try {
    let k = (typeof GP !== 'undefined' && GP && GP.soAtrasadas) ? 'atr' : '';
    if (typeof GP_SEL !== 'undefined')
      k += '|' + Object.keys(GP_SEL).map(x => x + ':' + [...GP_SEL[x]].sort().join(',')).join('|');
    if (typeof gpVal === 'function')
      k += '|' + ['gp-f-os', 'gp-f-ss', 'gp-f-pini', 'gp-f-pfim', 'gp-f-pmodo'].map(gpVal).join('|');
    return k;
  } catch (e) { return ''; }
}
// Filtros do topo nas linhas da GERENCIAL (modo Fila). Os nomes divergem do
// Fracttal ("Utragaz - Ibirapuã 2 - BA" × "Ultragaz – Ibirapuã 2") — comparação
// normalizada, mesma régua do drill. Responsável/Tipo/Etiqueta/Estado/
// Solicitação não existem na Gerencial, então não filtram a Fila.
function gpvFilaTopOk(x) {
  try {
    if (typeof GP_SEL === 'undefined') return true;
    const bate = (a, k) => a && k && (a === k || a.startsWith(k) || k.startsWith(a)
      || (a.length >= 8 && k.indexOf(a) >= 0) || (k.length >= 8 && a.indexOf(k) >= 0));
    const algum = (set, vals) => [...set].some(s => {
      const a = gpvMpNorm(s);
      return vals.some(v => v && bate(a, gpvMpNorm(v)));
    });
    if (GP_SEL.cliente.size && !algum(GP_SEL.cliente, [x.cli])) return false;
    if (GP_SEL.usina.size && !algum(GP_SEL.usina, [x.usinaFull, x.nome])) return false;
    if (GP_SEL.cluster.size && !algum(GP_SEL.cluster, [x.clu])) return false;
    if (typeof gpVal === 'function') {
      const fOS = gpVal('gp-f-os').toLowerCase();
      if (fOS && String(x.os || '').toLowerCase().indexOf(fOS) < 0) return false;
      const pIni = gpVal('gp-f-pini'), pFim = gpVal('gp-f-pfim');
      if (pIni || pFim) {           // Prevista OU Programada dentro da faixa
        const dentro = d => d && (!pIni || d >= pIni) && (!pFim || d <= pFim);
        if (!dentro(x.prev) && !dentro(x.prog)) return false;
      }
    }
    if (typeof GP !== 'undefined' && GP && GP.soAtrasadas && x.sit.k !== 'Atrasada') return false;
    return true;
  } catch (e) { return true; }
}

// ── base atômica: (cliente,usina,cluster,resp,sigla,mês) -> {f,t,os{}} ──────
// Cacheada por geradoEm+usuário+filtros do topo: 20 mil tarefas não precisam
// ser revarridas a cada clique de controle.
let _gpvCacheKey = null, _gpvBase = null;

function gpvBase() {
  const key = ((GESTAO_DB && GESTAO_DB.geradoEm) || '') + '|' + (S.user || '') + '|' + gpvFiltroKey();
  if (_gpvBase && _gpvCacheKey === key) return _gpvBase;
  const MESES = gpvMeses(), reg = new Map();
  gpvTarefasTop().forEach(t => {
    const m = GPV_RX.exec(String(t.tarefa || ''));
    if (!m) return;
    const mes = String(t.dataProg || '').slice(0, 7);
    if (MESES.indexOf(mes) < 0) return;
    const sig = m[1];
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

// ── pivô (modo Plano) ───────────────────────────────────────────────────────
const gpvCols = () => {
  const base = GPV.col === 'sig' ? GPV_SIGLAS : gpvMeses();
  return (GPV.col === 'sig' && GPV.tipo !== 'todos') ? [GPV.tipo] : base;
};
const gpvRotCol = c => GPV.col === 'sig' ? c : gpvRotMes(c);
const gpvFaixa = p => p === null ? 'nulo' : (p >= 100 ? 'ok' : (p < 40 ? 'crit' : 'and'));
const gpvSoma = arr => { const o = { f: 0, t: 0 }; arr.forEach(c => { if (c) { o.f += c.f; o.t += c.t; } }); return o; };
const gpvPct = c => (c && c.t) ? Math.round(100 * c.f / c.t) : null;

function gpvPivo() {
  let R = gpvBase();
  if (GPV.tipo !== 'todos') R = R.filter(r => r.sig === GPV.tipo);
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

// ── fila (modo Fila): linhas da Gerencial + Fracttal ────────────────────────
function gpvFilaLinhas() {
  const hoje = gpvHoje();
  const out = [];
  ((MP && MP.manut) || []).forEach(m => {
    const tipo = String(m.tipo || '').toUpperCase().indexOf('MPS') >= 0 ? 'MPS' : 'MPA';
    // a célula OS da Gerencial pode trazer VÁRIAS OSs ("123/456") — todas
    // contam: a Programada é a mais cedo entre elas e as tarefas se somam
    const partes = String(m.os || '').split(/[\/,;]/).map(x => x.trim()).filter(Boolean);
    const bds = partes.map(p => (MP.bd && MP.bd[p]) || null).filter(Boolean);
    const os = partes.join(' / ');
    let prog = null, bdFin = null, bdTot = null;
    bds.forEach(b => {
      if (b.tasks) b.tasks.forEach(t => { if (t.prog && (!prog || t.prog < prog)) prog = t.prog; });
      bdFin = (bdFin || 0) + (b.fin || 0); bdTot = (bdTot || 0) + (b.total || 0);
    });
    const bd = bds.length ? { fin: bdFin, total: bdTot } : null;
    const sit = mpSit(m);
    const conclu = sit.k === 'Concluída';
    const atraso = (!conclu && m.prevista && m.prevista < hoje) ? gpvDias(m.prevista) : null;
    const obs = gpvMpUltObs(m.obs);
    const od = GPV_MP_DATA.exec(obs);
    const obsIso = od ? od[3] + '-' + od[2] + '-' + od[1] : null;
    const critCls = gpvMpCls(m.criticidade);
    out.push({
      nome: (m.cliente ? m.cliente + ' – ' : '') + (m.usina_curta || m.usina || '—'),
      usinaFull: m.usina || '', cli: m.cliente || '', clu: m.cluster || '',
      tipo, crit: m.criticidade || '', critCls,
      prev: m.prevista || null, prog, atraso,
      os, semOS: !os, osSemPar: !!os && !bd, semData: !!bd && !prog,
      // "crítica sem data futura": criticidade alta/crítica, não concluída e
      // sem programação à frente — o KPI de GESTÃO (mede funil, não sorte)
      critSemData: !conclu && critCls === 'crit' && (!prog || prog < hoje),
      sit, conclu, obs, obsIso, obsVelha: obsIso ? (gpvDias(obsIso) > 60) : false,
      equipe: m.equipe || '', apoio: m.apoio || '', statusPlan: m.status || '',
      bdFin: bd ? bd.fin : null, bdTot: bd ? bd.total : null,
      diverge: !!(m.prevista && prog && Math.abs(gpvDias(m.prevista) - gpvDias(prog)) > 30),
    });
  });
  return out;
}
// fallback sem a Gerencial (cliente, ou admin sem senha): só o lado Fracttal
function gpvFilaFracttal() {
  const hoje = gpvHoje();
  const porOS = new Map();
  gpvTarefasTop().forEach(t => {
    const m = GPV_RX.exec(String(t.tarefa || ''));
    if (!m || (m[1] !== 'MPA' && m[1] !== 'MPS')) return;
    const os = String(t.os || '').trim();
    if (!os) return;
    let r = porOS.get(os);
    if (!r) { r = { os, tipo: m[1], nome: (t.cliente ? t.cliente + ' – ' : '') + (t.usina || '—'),
                    prog: null, tot: 0, fin: 0, andamento: false }; porOS.set(os, r); }
    r.tot++; if (String(t.estado || '') === 'Finalizada') r.fin++;
    if (String(t.estado || '').toLowerCase().indexOf('progress') >= 0) r.andamento = true;
    const d = String(t.dataProg || '').slice(0, 10);
    if (/^\d{4}-\d{2}-\d{2}$/.test(d) && (!r.prog || d < r.prog)) r.prog = d;
  });
  const out = [];
  porOS.forEach(r => {
    const conclu = r.tot > 0 && r.fin === r.tot;
    let k = conclu ? 'Concluída' : (r.andamento || r.fin > 0) ? 'Em andamento' : 'Não iniciada';
    if (!conclu && r.prog && r.prog < hoje) k = 'Atrasada';
    const cls = { 'Concluída': 'green', 'Em andamento': 'blue', 'Não iniciada': 'amber', 'Atrasada': 'red' }[k];
    out.push({ nome: r.nome, tipo: r.tipo, crit: '', critCls: '', prev: null, prog: r.prog,
      atraso: (!conclu && r.prog && r.prog < hoje) ? gpvDias(r.prog) : null,
      os: r.os, semOS: false, osSemPar: false, semData: !r.prog, critSemData: false,
      sit: { k, cls }, conclu, obs: '', obsIso: null, obsVelha: false,
      equipe: '', apoio: '', statusPlan: '', bdFin: r.fin, bdTot: r.tot, diverge: false });
  });
  return out;
}

const gpvFxAtraso = d => d == null || d <= 0 ? '' : d <= 30 ? 'f1' : d <= 90 ? 'f2' : 'f3';

// ── faixa de topo: o PAR de números (nunca média única) ─────────────────────
function gpvParTopo(fila, temGer) {
  // Rotina = MPM+MPT do mês corrente (o % é a pergunta certa p/ alto volume)
  const mesAtual = gpvMeses()[2];
  const rot = gpvSoma(gpvBase().filter(r => (r.sig === 'MPM' || r.sig === 'MPT') && r.mes === mesAtual));
  const rotPct = gpvPct(rot);
  let h = '<div class="gpv-par">'
    + '<div><small>ROTINA (MPM/MPT · ' + gpvRotMes(mesAtual) + ')</small> '
    + '<b class="' + (rotPct === null ? '' : rotPct >= 75 ? 'ok' : rotPct >= 40 ? 'aviso' : 'mal') + '">'
    + (rotPct === null ? '—' : rotPct + '%') + '</b> <small>do plano do mês concluído</small></div>';
  if (temGer) {
    const atr = fila.filter(x => x.sit.k === 'Atrasada');
    const maisVelha = atr.reduce((m, x) => Math.max(m, x.atraso || 0), 0);
    const csd = fila.filter(x => x.critSemData).length;
    const semOS = fila.filter(x => (x.semOS || x.osSemPar) && !x.conclu).length;
    h += '<div><small>GRANDES (MPA/MPS)</small> <b class="' + (atr.length ? 'mal' : 'ok') + '">'
      + atr.length + ' atrasada' + (atr.length === 1 ? '' : 's') + '</b>'
      + (maisVelha ? ' <small>· mais antiga <b>' + maisVelha + ' d</b></small>' : '') + '</div>'
      + '<div><small>GESTÃO</small> <b class="' + (csd ? 'aviso' : 'ok') + '">' + csd
      + ' crítica' + (csd === 1 ? '' : 's') + ' sem data futura</b> <small>· ' + semOS + ' sem OS</small></div>';
  } else {
    h += '<div><small>GRANDES (MPA/MPS)</small> <small>envelhecimento completo no modo Fila '
      + (typeof S !== 'undefined' && S && S.isAdmin === false ? '' : '— 🔒 requer a senha da Gerencial') + '</small></div>';
  }
  return h + '</div>';
}

// ── render ──────────────────────────────────────────────────────────────────
function gpvRender() {
  const box = document.getElementById('gp-preventivas');
  if (!box || !GESTAO_DB) return;
  if (GPV.fechados === null) GPV.fechados = new Set();
  if (GPV.modo === null) {
    try { GPV.modo = sessionStorage.getItem('gc_gpv_modo') || 'plano'; } catch (e) { GPV.modo = 'plano'; }
  }

  const ehCliente = (typeof S !== 'undefined' && S && S.isAdmin === false);
  if (gpvMpAtivo()) {
    if (MP && GPV_MP.estado !== 'ok' && GPV_MP.estado !== 'carregando') GPV_MP.estado = 'nao';
    gpvMpCarregar();
  }
  const temGer = GPV_MP.estado === 'ok' && MP;
  const fila = temGer ? gpvFilaLinhas().filter(gpvFilaTopOk) : gpvFilaFracttal();

  // ── cabeçalho do bloco ──
  const subt = GPV.modo === 'plano'
    ? 'Plano: % de conclusão por OS · obedece os filtros do topo da aba + controles próprios'
    : 'Fila: envelhecimento de MPA/MPS, da mais antiga para a mais nova · obedece Cliente, Usina, Cluster, OS, Período e Só atrasadas do topo';
  let h = '<div class="gpv-box"><div class="gpv-top" onclick="gpvTog()">'
    + '<div><div class="gpv-tit">&#128202; Preventivas — Plano &amp; Fila <span class="gpv-mat">'
    + (GPV.modo === 'plano' ? 'matriz por OS' : 'Gerencial + Fracttal') + '</span></div>'
    + '<div class="gpv-sub">' + subt + '</div></div>'
    + '<span class="gpv-chev">' + (GPV.aberto ? '&#9662;' : '&#9656;') + '</span></div>';
  if (!GPV.aberto) { box.innerHTML = h + '</div>'; return; }

  h += gpvParTopo(fila, temGer);

  // ── linha 1 (permanente): modo · tipo · busca ──
  const seg = (id, ops, atual, offs) => '<div class="gpv-seg">' + ops.map(([v, r]) => {
    const off = offs && offs.indexOf(v) >= 0;
    return '<button type="button" class="' + (v === atual ? 'on' : '') + (off ? ' off' : '') + '" '
      + (off ? 'title="sem data prevista na Gerencial — acompanhe no Plano" disabled ' : '')
      + 'onclick="gpvSet(&quot;' + id + '&quot;,&quot;' + v + '&quot;)">' + r + '</button>';
  }).join('') + '</div>';
  const tiposOff = GPV.modo === 'fila' ? ['MPM', 'MPT'] : [];
  h += '<div class="gpv-ctl" onclick="event.stopPropagation()">'
    + '<span class="gpv-rot">Modo</span>' + seg('modo', [['plano', 'Plano'], ['fila', 'Fila']], GPV.modo)
    + '<span class="gpv-rot">Tipo</span>' + seg('tipo',
        [['todos', 'Todos']].concat(GPV_SIGLAS.map(s => [s, s])), GPV.tipo, tiposOff)
    + '<input class="gpv-busca" placeholder="filtrar usina, cliente ou OS&hellip;" value="' + gpEsc(GPV.busca) + '" '
    + 'oninput="GPV.busca=this.value;gpvRender();'
    + 'var i=document.querySelector(\'#gp-preventivas .gpv-busca\');if(i){i.focus();i.setSelectionRange(i.value.length,i.value.length);}">'
    + (GPV.modo === 'plano'
      ? '<button type="button" class="gpv-lnk" onclick="gpvExpTog()">'
        + (GPV.fechados.size ? 'Expandir tudo' : 'Recolher tudo') + '</button>' : '')
    + '</div>';

  if (GPV.modo === 'plano') h += gpvRenderPlano();
  else h += gpvRenderFila(fila, temGer, ehCliente);

  box.innerHTML = h + '</div>';
}

// ── modo PLANO (a matriz de sempre + frações MPA/MPS) ───────────────────────
function gpvRenderPlano() {
  const CS = gpvCols(), G = gpvPivo();
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

  const VAL_ROT = { pct: '% de tarefas finalizadas', pend: 'tarefas que ainda faltam',
                    fei: 'tarefas já finalizadas', tot: 'total de tarefas' };
  const seg = (id, ops, atual) => '<div class="gpv-seg">' + ops.map(([v, r]) =>
    '<button type="button" class="' + (v === atual ? 'on' : '') + '" '
    + 'onclick="gpvSet(&quot;' + id + '&quot;,&quot;' + v + '&quot;)">' + r + '</button>').join('') + '</div>';
  let h = '<div class="gpv-ctl gpv-ctl2" onclick="event.stopPropagation()">'
    + '<span class="gpv-rot">Linhas</span>' + seg('dim',
        [['cli', 'Cliente &#9656; Usina'], ['clu', 'Cluster &#9656; Usina'],
         ['res', 'Responsável &#9656; Usina'], ['usi', 'Só usina']], GPV.dim)
    + '<span class="gpv-rot">Colunas</span>' + seg('col', [['sig', 'Tipo'], ['mes', 'Mês']], GPV.col)
    + '<span class="gpv-rot">Valor</span>' + seg('val',
        [['pct', '%'], ['pend', 'Pendentes'], ['fei', 'Feitas'], ['tot', 'Total']], GPV.val)
    + '<span class="gpv-rot">Mês</span>' + seg('mes',
        [['todos', 'Todos']].concat(gpvMeses().map(m => [m, gpvRotMes(m)])), GPV.mes)
    + '</div>';

  h += '<div class="gpv-guia">'
    + '<div><b>MPM</b> mensal</div><div><b>MPT</b> trimestral</div><div><b>MPS</b> semestral</div><div><b>MPA</b> anual</div>'
    + '<div><b>Geral</b> as quatro somadas</div><div><b>Pendentes</b> o que falta, em número</div>'
    + '<div><b>Célula</b> ' + VAL_ROT[GPV.val] + '; MPA/MPS em <b>fração feitas/total</b> — clique nela p/ abrir a Fila</div></div>';

  const rotL = GPV.dim === 'cli' ? 'Cliente &#9656; Usina' : GPV.dim === 'clu' ? 'Equipe Cluster &#9656; Usina'
             : GPV.dim === 'res' ? 'Responsável &#9656; Usina' : 'Usina';
  const th = (id, rot, cls) => '<th class="' + (cls || '') + (GPV.ordem === id ? ' ativo' : '') + '" '
    + 'onclick="gpvOrd(&quot;' + id + '&quot;)">' + rot
    + '<span class="gpv-ord">' + (GPV.ordem === id ? (GPV.desc ? '&#9660;' : '&#9650;') : '&#8597;') + '</span></th>';
  const mpAtivo = gpvMpAtivo();

  h += '<div class="gpv-rolo"><table class="gpv-tbl">'
    + '<colgroup><col style="width:300px">'
    + CS.map(() => '<col style="width:92px">').join('')
    + '<col style="width:100px"><col style="width:88px">'
    + (mpAtivo ? '<col style="width:290px">' : '') + '</colgroup>'
    + '<thead><tr>' + th('nome', rotL, 'rotlin')
    + CS.map(c => th(c, gpvRotCol(c))).join('')
    + th('geral', 'Geral') + th('pend', 'Pendentes')
    + (mpAtivo ? '<th class="gpv-obs-th">Criticidade / Observação</th>' : '')
    + '</tr></thead><tbody>';

  // célula: MPA/MPS em fração (e drill p/ Fila nas linhas de usina); resto como antes
  const celTd = (c, sig, usina) => {
    const grande = GPV.col === 'sig' && (sig === 'MPA' || sig === 'MPS');
    if (!c || !c.t) return '<td><span class="gpv-cel nulo">—</span></td>';
    const p = Math.round(100 * c.f / c.t);
    const tit = (c.os && c.os.length ? 'OS — ' + Array.from(new Set(c.os)).sort().join('   ') : '');
    if (grande && GPV.val === 'pct') {
      const drill = usina ? ' gpv-frac" onclick="event.stopPropagation();gpvDrill(\''
        + gpEsc(usina).replace(/'/g, '&#39;') + '\',\'' + sig + '\')' : '"';
      return '<td><span class="gpv-cel ' + gpvFaixa(p) + drill + '" title="'
        + gpEsc((usina ? 'abrir a Fila desta usina · ' : '') + tit) + '">' + c.f + '/' + c.t + '</span></td>';
    }
    const m = gpvMostra(c);
    return '<td><span class="gpv-cel ' + m.cls + '" title="' + gpEsc(tit || 'sem preventiva no período') + '">' + m.txt + '</span></td>';
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
        + CS.map(c => celTd(g.cel[c], c, null)).join('') + fimTd(g)
        + (mpAtivo ? '<td class="gpv-obs"></td>' : '') + '</tr>';
      linhas++;
      if (!ab) return;
    }
    g.filhos.forEach(f => {
      h += '<tr class="' + (plano ? '' : 'gpv-filho') + '"><td class="rotlin"><b>'
        + gpEsc(f.nome) + '</b></td>'
        + CS.map(c => celTd(f.cel[c], c, f.nome)).join('') + fimTd(f)
        + (mpAtivo ? gpvMpTd(f.nome) : '') + '</tr>';
      linhas++;
    });
  });
  if (!linhas) h += '<tr><td colspan="' + (CS.length + 3 + (mpAtivo ? 1 : 0)) + '" class="gpv-vazio">Nada com esse filtro.</td></tr>';

  const totCol = {}; CS.forEach(c => { totCol[c] = gpvSoma(grupos.map(g => g.cel[c])); });
  const totG = gpvSoma(CS.map(c => totCol[c]));
  h += '<tr class="gpv-total"><td class="rotlin"><b>TOTAL GERAL</b> <span class="gpv-mini">'
    + grupos.reduce((s, g) => s + g.filhos.length, 0) + ' usinas</span></td>'
    + CS.map(c => celTd(totCol[c], c, null)).join('') + fimTd({ tudo: totG })
    + (mpAtivo ? '<td class="gpv-obs"></td>' : '') + '</tr>';
  h += '</tbody></table></div>';

  h += '<div class="gpv-leg">'
    + '<span><i style="background:#fbe0e0"></i>abaixo de 40%</span>'
    + '<span><i style="background:#fdf0d4"></i>40% a 99%</span>'
    + '<span><i style="background:#dcf2de"></i>100%</span>'
    + '<span><i style="background:#eef0f5"></i>sem preventiva no período</span>'
    + (mpAtivo ? '<span><b>Criticidade / Observação</b> — Gerencial (aba MPAS), última entrada datada do log</span>' : '')
    + '<span class="gpv-fim">clique no cliente para abrir as usinas · na fração de MPA/MPS para abrir a Fila · passe o mouse na célula para ver as OS</span>'
    + '</div>';
  return h;
}

// ── modo FILA (envelhecimento MPA/MPS) ──────────────────────────────────────
function gpvRenderFila(fila, temGer, ehCliente) {
  let ls = fila.slice();
  const tot = ls.length;

  // KPIs do universo inteiro — eles SÃO os filtros
  const kAtr = ls.filter(x => x.sit.k === 'Atrasada').length;
  const kSem = ls.filter(x => (x.semOS || x.osSemPar) && !x.conclu).length;
  const kCsd = ls.filter(x => x.critSemData).length;
  const kOk = ls.filter(x => x.conclu).length;
  const kpi = (id, v, rot, cls) => '<div class="gma-kpi ' + cls + (GPV.pend === id ? ' on' : '')
    + '" onclick="gpvSet(\'pend\',\'' + (GPV.pend === id ? 'todas' : id) + '\')">'
    + '<div class="v">' + v + '</div><div class="l">' + rot + '</div></div>';

  let h = '';
  if (temGer) {
    h += '<div class="gma-kpis">'
      + kpi('atraso', kAtr, 'atrasadas', 'red')
      + kpi('semos', kSem, 'sem OS no Fracttal', 'amb')
      + kpi('critsem', kCsd, 'críticas sem data futura', 'amb')
      + kpi('concl', kOk + '<small>/' + tot + '</small>', 'concluídas', 'grn')
      + '</div>';
  } else if (!ehCliente) {
    h += '<div class="gma-trava" style="padding:18px 20px 20px"><div class="gma-cad">&#128274;</div>'
      + '<b>Prevista, criticidade e observações vêm do plano cifrado da Gerencial</b>'
      + '<p>Abaixo está a visão só com o Fracttal. Digite a senha de administrador para completar — vale apenas nesta sessão.</p>'
      + '<div class="gma-form"><input type="password" id="gma-pwd" placeholder="senha de admin" '
      + 'onkeydown="if(event.key===\'Enter\')gpvMpAbrir()">'
      + '<button onclick="gpvMpAbrir()">Desbloquear</button></div>'
      + '<div class="gma-err" id="gma-err"></div></div>';
  }

  // filtros próprios do modo
  if (GPV.drill) {
    // o drill chega com o nome do Fracttal ("Utragaz - Ibirapuã 2 - BA") e a
    // fila usa o da Gerencial ("Ultragaz – Ibirapuã 2") — compara normalizado
    const alvo = gpvMpNorm(GPV.drill.usina);
    ls = ls.filter(x => {
      const k1 = gpvMpNorm(x.nome), k2 = gpvMpNorm(x.usinaFull || '');
      const bate = k => k && (k === alvo || k.startsWith(alvo) || alvo.startsWith(k)
        || (k.length >= 8 && alvo.indexOf(k) >= 0) || (alvo.length >= 8 && k.indexOf(alvo) >= 0));
      return (bate(k1) || bate(k2)) && (!GPV.drill.tipo || x.tipo === GPV.drill.tipo);
    });
    h += '<div class="gpv-chip">&#9673; filtrado: <b>' + gpEsc(GPV.drill.usina)
      + (GPV.drill.tipo ? ' · ' + GPV.drill.tipo : '') + '</b>'
      + '<span class="x" onclick="gpvDrillOff()">&#10005;</span>'
      + '<span class="volta" onclick="gpvSet(\'modo\',\'plano\')">&#8617; voltar ao Plano</span></div>';
  }
  if (GPV.tipo === 'MPA' || GPV.tipo === 'MPS') ls = ls.filter(x => x.tipo === GPV.tipo);
  if (GPV.pend === 'atraso') ls = ls.filter(x => x.sit.k === 'Atrasada');
  if (GPV.pend === 'semos') ls = ls.filter(x => (x.semOS || x.osSemPar) && !x.conclu);
  if (GPV.pend === 'critsem') ls = ls.filter(x => x.critSemData);
  if (GPV.pend === 'concl') ls = ls.filter(x => x.conclu);
  if (GPV.busca) {
    const sem = s => String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    const q = sem(GPV.busca);
    ls = ls.filter(x => sem(x.nome + ' ' + x.os).indexOf(q) >= 0);
  }

  const chave = { prev: x => x.prev || '9999', prog: x => x.prog || '9999',
    atraso: x => -(x.atraso || -1), nome: x => x.nome.toLowerCase(),
    crit: x => ({ 'crit': 0, 'and': 1, 'ok': 2, '': 3 })[x.critCls] }[GPV.ordemF]
    || (x => x.prev || '9999');
  ls.sort((a, b) => { const x = chave(a), y = chave(b);
    return (x < y ? -1 : x > y ? 1 : 0) * (GPV.descF ? -1 : 1); });

  const th = (id, rot, w) => '<th' + (w ? ' style="width:' + w + '"' : '')
    + ' class="' + (GPV.ordemF === id ? 'ativo' : '') + '" onclick="gpvOrdF(\'' + id + '\')">'
    + rot + '<span class="gpv-ord">' + (GPV.ordemF === id ? (GPV.descF ? '&#9660;' : '&#9650;') : '&#8597;') + '</span></th>';
  const segP = temGer ? '<div class="gpv-ctl gpv-ctl2" onclick="event.stopPropagation()">'
    + '<span class="gpv-rot">Pendência</span><div class="gpv-seg">'
    + [['todas', 'Todas'], ['atraso', 'Atrasadas'], ['semos', 'Sem OS'], ['critsem', 'Críticas s/ data']].map(([v, r]) =>
      '<button type="button" class="' + (GPV.pend === v ? 'on' : '') + '" onclick="gpvSet(\'pend\',\'' + v + '\')">' + r + '</button>').join('')
    + '</div><span class="gma-n">' + ls.length + ' manutenç' + (ls.length === 1 ? 'ão' : 'ões') + '</span></div>' : '';
  h += segP;

  h += '<div class="gpv-rolo"><table class="gpv-tbl gma-tbl"><thead><tr>'
    + th('nome', 'Cliente – Usina', '220px') + th('tipo', 'Tipo', '58px')
    + (temGer ? th('crit', 'Criticidade', '92px') : '')
    + (temGer ? th('prev', 'Prevista <small>(Gerencial)</small>', '104px') : '')
    + th('prog', 'Programada <small>(Fracttal)</small>', '108px')
    + th('atraso', 'Atraso', '72px') + '<th style="width:86px">OS</th>'
    + '<th style="width:104px">Situação</th>'
    + (temGer ? '<th class="gpv-obs-th">Última observação</th>' : '<th style="width:110px">Tarefas</th>')
    + '</tr></thead><tbody>';

  const NCOL = temGer ? 9 : 7;
  if (!ls.length) h += '<tr><td colspan="' + NCOL + '" class="gpv-vazio">Nada com esses filtros.</td></tr>';
  ls.forEach((x, i) => {
    const fx = gpvFxAtraso(x.atraso);
    const osTd = x.semOS ? '<span class="gma-semos" title="atividade ainda sem OS criada no Fracttal">sem OS</span>'
      : x.osSemPar ? '<span class="gma-semos" title="OS ' + gpEsc(x.os) + ' da planilha não localizada no Fracttal">' + gpEsc(x.os) + ' ?</span>'
      : gpEsc(x.os);
    const progTd = x.prog
      ? gpvFmtD(x.prog) + (x.diverge ? ' <span class="gma-div" title="programada difere da prevista em mais de 30 dias">&#9679;</span>' : '')
      : '<span class="gma-nulo" title="' + (x.semData ? 'OS criada, sem data programada no Fracttal' : '') + '">—</span>';
    const obsData = x.obsIso ? '<b class="' + (x.obsVelha ? 'gma-obs-velha' : '') + '">' + gpvFmtD(x.obsIso) + '</b> ' : '';
    const obsTxt = x.obs.replace(/^\d{2}\/\d{2}\/\d{4}\s*[-–—:]*\s*/, '');
    h += '<tr class="gma-lin' + (x.conclu ? ' gma-ok' : '') + (GPV.abertoF === i ? ' aberta' : '')
      + '" onclick="gpvExpF(' + i + ')">'
      + '<td class="rotlin"><b>' + gpEsc(x.nome) + '</b></td>'
      + '<td><span class="gma-tipo">' + x.tipo + '</span></td>'
      + (temGer ? '<td>' + (x.crit ? '<span class="gpv-crit ' + x.critCls + '">' + gpEsc(x.crit) + '</span>' : '<span class="gma-nulo">—</span>') + '</td>' : '')
      + (temGer ? '<td class="gma-dt">' + (x.prev ? gpvFmtD(x.prev) : '<span class="gma-nulo">—</span>') + '</td>' : '')
      + '<td class="gma-dt">' + progTd + '</td>'
      + '<td>' + (x.atraso != null ? '<span class="gma-atr ' + fx + '">' + x.atraso + ' d</span>'
                  : (x.conclu ? '<span class="gma-check">&#10003;</span>' : '<span class="gma-nulo">—</span>')) + '</td>'
      + '<td>' + osTd + '</td>'
      + '<td><span class="gma-sit ' + x.sit.cls + '">' + gpEsc(x.sit.k) + '</span></td>'
      + (temGer
        ? '<td class="gpv-obs" title="' + gpEsc(x.obs) + '">' + obsData + (obsTxt ? gpEsc(obsTxt.slice(0, 110)) : '<span class="gma-nulo">—</span>') + '</td>'
        : '<td class="gma-dt">' + (x.bdTot != null ? x.bdFin + '/' + x.bdTot : '—') + '</td>')
      + '</tr>';
    if (GPV.abertoF === i && temGer) {
      h += '<tr class="gma-det"><td colspan="' + NCOL + '"><div class="gma-det-in">'
        + (x.obs ? '<p><b>Observação (última entrada):</b> ' + gpEsc(x.obs) + '</p>' : '')
        + '<p>' + (x.equipe ? '<b>Equipe:</b> ' + gpEsc(x.equipe.split('\n')[0]) + ' · ' : '')
        + (x.apoio ? '<b>Apoio:</b> ' + gpEsc(x.apoio) + ' · ' : '')
        + (x.statusPlan ? '<b>Status na planilha:</b> ' + gpEsc(x.statusPlan) + ' · ' : '')
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
    + '<span class="gpv-fim">atraso = hoje − Data ' + (temGer ? 'Prevista' : 'Programada')
    + ' · clique na linha para o detalhe · situação pela TAREFA, nunca pelo Status da OS</span>'
    + '</div>';
  return h;
}

// ── handlers ────────────────────────────────────────────────────────────────
function gpvTog() { GPV.aberto = !GPV.aberto; gpvRender(); }
function gpvSet(campo, v) {
  GPV[campo] = v;
  if (campo === 'modo') {
    try { sessionStorage.setItem('gc_gpv_modo', v); } catch (e) {}
    // MPM/MPT não existem na Fila: cair no Todos evita tela vazia sem explicação
    if (v === 'fila' && (GPV.tipo === 'MPM' || GPV.tipo === 'MPT')) GPV.tipo = 'todos';
  }
  GPV.abertoF = null;
  gpvRender();
}
function gpvOrd(id) {
  if (GPV.ordem === id) GPV.desc = !GPV.desc;
  else { GPV.ordem = id; GPV.desc = (id !== 'nome'); }
  gpvRender();
}
function gpvOrdF(id) {
  if (GPV.ordemF === id) GPV.descF = !GPV.descF;
  else { GPV.ordemF = id; GPV.descF = false; }
  GPV.abertoF = null; gpvRender();
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
function gpvExpF(i) { GPV.abertoF = (GPV.abertoF === i ? null : i); gpvRender(); }
function gpvDrill(usina, tipo) {
  GPV.drill = { usina, tipo };
  GPV.modo = 'fila'; GPV.pend = 'todas'; GPV.abertoF = null;
  try { sessionStorage.setItem('gc_gpv_modo', 'fila'); } catch (e) {}
  gpvRender();
}
function gpvDrillOff() { GPV.drill = null; gpvRender(); }

// ── engate: roda junto com o render da aba (padrão do mpas_extras.js) ──────
if (typeof renderGestao === 'function') {
  const _renderGestaoOrig = renderGestao;
  renderGestao = function () {
    _renderGestaoOrig.apply(this, arguments);
    try { gpvRender(); } catch (e) { console.warn('preventivas:', e); }
  };
}
