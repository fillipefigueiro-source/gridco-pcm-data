// ─────────────────────────────────────────────────────────────────────────────
// relatorio_exec.js — Relatório Executivo sob demanda (17/09/2026)
// Script clássico, carrega DEPOIS de app.js e preventivas.js (escopo global).
//
// Botão na aba Gestão PCM → modal (período com presets + cliente/cluster/
// usinas) → relatório A4 imprimível gerado 100% no navegador a partir do
// gestao_pcm.json (+ resumo MPA/MPS da Gerencial quando decifrada).
//
// NARRATIVA (spec dos agentes, 17/09): síntese de 1 linha + números-farol →
// saúde do plano preventivo → pressão corretiva com o ranking "Usinas que
// pedem atenção" (criadas no período ordena; tendência ▲▼ vs período anterior
// dá o contexto justo) → grandes manutenções (Gerencial) → esforço → AÇÕES.
// Termina em ação, não em dado. Versão CLIENTE (1 cliente no recorte ou login
// de cliente): sem responsáveis, sem Gerencial, sem comparação entre clientes.
//
// REGRA DE OURO: concluído = estado 'Finalizada' (TAREFA), nunca o Status da OS.
// Corretivas contam OS DISTINTA por usina (tarefa duplicada não infla ranking).
// Prefixo rex- em tudo.
// ─────────────────────────────────────────────────────────────────────────────

let REX = { de: '', ate: '', cliente: '', cluster: '', usinas: [] };

const rexEsc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const rexIso = d => d.toISOString().slice(0, 10);
const rexFmt = iso => iso ? iso.slice(8, 10) + '/' + iso.slice(5, 7) + '/' + iso.slice(0, 4) : '—';
const rexHoje = () => rexIso(new Date());
const rexN = n => Number(n || 0).toLocaleString('pt-BR');

// ── presets de período ───────────────────────────────────────────────────────
function rexPreset(p) {
  const hj = new Date(); hj.setHours(12);
  const d = new Date(hj);
  if (p === 'sem') { d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); REX.de = rexIso(d); REX.ate = rexHoje(); }
  else if (p === 'semp') { d.setDate(d.getDate() - ((d.getDay() + 6) % 7) - 7); const f = new Date(d); f.setDate(f.getDate() + 6); REX.de = rexIso(d); REX.ate = rexIso(f); }
  else if (p === 'mes') { REX.de = rexIso(new Date(d.getFullYear(), d.getMonth(), 1, 12)); REX.ate = rexHoje(); }
  else if (p === 'mesp') { REX.de = rexIso(new Date(d.getFullYear(), d.getMonth() - 1, 1, 12)); REX.ate = rexIso(new Date(d.getFullYear(), d.getMonth(), 0, 12)); }
  else if (p === '30d') { d.setDate(d.getDate() - 29); REX.de = rexIso(d); REX.ate = rexHoje(); }
  const de = document.getElementById('rex-de'), ate = document.getElementById('rex-ate');
  if (de) de.value = REX.de; if (ate) ate.value = REX.ate;
  document.querySelectorAll('#rex-modal .rex-chip').forEach(b => b.classList.toggle('on', b.dataset.p === p));
}

// ── modal ────────────────────────────────────────────────────────────────────
function rexAbrirModal() {
  rexFecharModal();
  const F = (GESTAO_DB && GESTAO_DB.filtros) || {};
  const ehCliente = (typeof S !== 'undefined' && S && S.isAdmin === false);
  const clientes = ehCliente ? [] : (F.clientes || []);
  const opt = (arr, sel) => arr.map(v => '<option value="' + rexEsc(v) + '"' + (sel === v ? ' selected' : '') + '>' + rexEsc(v) + '</option>').join('');
  const m = document.createElement('div');
  m.id = 'rex-modal';
  m.innerHTML = '<div class="rex-m-fundo" onclick="rexFecharModal()"></div>'
    + '<div class="rex-m-caixa">'
    + '<h3>&#128196; Relatório executivo</h3>'
    + '<div class="rex-m-sec">Período</div>'
    + '<div class="rex-chips">'
    + [['sem', 'Esta semana'], ['semp', 'Semana passada'], ['mes', 'Este mês'], ['mesp', 'Mês passado'], ['30d', 'Últimos 30 dias']]
      .map(([p, r]) => '<button type="button" class="rex-chip" data-p="' + p + '" onclick="rexPreset(\'' + p + '\')">' + r + '</button>').join('')
    + '</div>'
    + '<div class="rex-m-linha"><label>De <input type="date" id="rex-de"></label>'
    + '<label>Até <input type="date" id="rex-ate"></label></div>'
    + '<div class="rex-m-sec">Escopo <small>(deixe em Todos para o portfólio)</small></div>'
    + (ehCliente ? '' : '<div class="rex-m-linha"><label>Cliente <select id="rex-cli" onchange="rexEscopoMuda()">'
      + '<option value="">Todos os clientes</option>' + opt(clientes) + '</select></label>'
      + '<label>Equipe Cluster <select id="rex-clu"><option value="">Todos</option>' + opt(F.clusters || []) + '</select></label></div>')
    + '<label class="rex-m-usinas">Usinas <small>(ctrl+clique para várias; vazio = todas do escopo)</small>'
    + '<select id="rex-usi" multiple size="7">' + opt(F.usinas || []) + '</select></label>'
    + '<div class="rex-m-acoes"><button type="button" class="rex-btn-2" onclick="rexFecharModal()">Cancelar</button>'
    + '<button type="button" class="rex-btn" onclick="rexGerar()">Gerar relatório</button></div>'
    + '</div>';
  document.body.appendChild(m);
  rexPreset('mes');                               // default: "como estão as coisas" deste mês
}
function rexFecharModal() { const m = document.getElementById('rex-modal'); if (m) m.remove(); }
function rexEscopoMuda() {
  // cascata: escolher o cliente filtra a lista de usinas
  const cli = (document.getElementById('rex-cli') || {}).value || '';
  const sel = document.getElementById('rex-usi');
  if (!sel) return;
  const F = (GESTAO_DB && GESTAO_DB.filtros) || {};
  const usinas = (F.usinas || []).filter(u => !cli || String(u).startsWith(cli));
  sel.innerHTML = usinas.map(v => '<option value="' + rexEsc(v) + '">' + rexEsc(v) + '</option>').join('');
}

// ── modelo: tudo calculado do gestao_pcm.json (escopo + período) ─────────────
const rexCorretiva = t => String(t.tipo || '').toLowerCase().indexOf('corretiva') >= 0;
const rexEmerg = t => String(t.tipo || '').toLowerCase().indexOf('emergencial') >= 0;
const rexRelig = t => String(t.tipo || '').toLowerCase().indexOf('religa') >= 0;
const rexFin = t => String(t.estado || '') === 'Finalizada';
const rexRange = (v, a, b) => { const d = String(v || '').slice(0, 10); return d >= a && d <= b; };

function rexEscopoFiltro(t) {
  if (REX.cliente && t.cliente !== REX.cliente) return false;
  if (REX.cluster && t.cluster !== REX.cluster) return false;
  if (REX.usinas.length && REX.usinas.indexOf(t.usina) < 0) return false;
  return true;
}

// ── programação semanal: banco_dados.json (a foto do programador que abastece
// pcm.gridco.com.br — mesmo repo, mesmos nomes de cliente/usina/cluster).
// Guarda as últimas 4 semanas; "planejado" = o que estava no programador,
// "executado" = tarefa Finalizada. Pedido das reuniões de 21/09 (Ilaneide:
// planejadas × executadas × corretivas por semana; Davi: rolagem e fora do plano).
let REX_BD = { estado: 'nao', dados: null };   // nao|ok|erro
async function rexBdCarregar() {
  if (REX_BD.estado !== 'nao') return REX_BD.dados;
  try {
    const r = await fetch('banco_dados.json', { cache: 'no-store' });
    REX_BD.dados = await r.json();
    REX_BD.estado = 'ok';
  } catch (e) { REX_BD.estado = 'erro'; REX_BD.dados = null; }
  return REX_BD.dados;
}
function rexSemanaSeg(week) {          // '2026-W38' -> segunda-feira ISO
  const m = /^(\d{4})-W(\d{1,2})$/.exec(String(week || ''));
  if (!m) return null;
  const d = new Date(Date.UTC(+m[1], 0, 4));               // 4/jan está sempre na W1
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7) + (+m[2] - 1) * 7);
  return d.toISOString().slice(0, 10);
}
const rexFinBd = s => String(s || '').toLowerCase().indexOf('finaliz') >= 0;
function rexGrupoBd(tipo) {
  const t = String(tipo || '');
  if (/^MP/i.test(t) || /^Preventiva/i.test(t)) return 'Preventivas';
  if (/^Corretiva/i.test(t)) return 'Corretivas';
  if (/^Religamento/i.test(t)) return 'Religamentos';
  return 'Demais';                     // Handover, Inspeção, Administrativa, Zeladoria…
}
const rexUsiCurta = u => String(u || '').replace(/\s*-\s*[A-Z]{2}\s*$/, '').replace(/^[^-]+-\s*/, '');
function rexSemanas(bd) {
  if (!bd || !bd.semanas) return [];
  const out = [];
  bd.semanas.forEach(w => {
    const seg = rexSemanaSeg(w.week);
    if (!seg) return;
    const sex = rexIso(new Date(new Date(seg + 'T12:00:00').getTime() + 4 * 86400000));
    if (sex < REX.de || seg > REX.ate) return;             // fora do período pedido
    // PLANO = a planilha da Programação da semana (ajustes até o fechamento
    // contam — não é foto de sexta 8h). O gerador injeta linhas extras com
    // foraDoPlano:true, mas só de seg→sáb 00h; por isso o "fora do plano"
    // daqui é recalculado do Fracttal com a semana CHEIA (seg→dom).
    const rows = (w.rows || []).filter(r => rexEscopoFiltro(r) && !r.foraDoPlano);
    if (!rows.length) return;
    const dom = rexIso(new Date(new Date(seg + 'T12:00:00').getTime() + 6 * 86400000));
    const osPlan = new Set(rows.map(r => String(r.os_id)));
    const G = {};
    let plan = 0, fin = 0, emergPlan = 0;
    rows.forEach(r => {
      const g = G[rexGrupoBd(r.tipo)] || (G[rexGrupoBd(r.tipo)] = { p: 0, f: 0 });
      g.p++; plan++;
      if (rexFinBd(r.status)) { g.f++; fin++; }
      if (/emergencial/i.test(r.tipo || '')) emergPlan++;
    });
    // fora do plano — executadas na semana (seg→dom) sem estar na planilha
    const T = gpScopedTarefas().filter(rexEscopoFiltro);
    const fora = T.filter(t => rexFin(t) && rexRange(t.dataFinal, seg, dom) && !osPlan.has(String(t.os)));
    // reprogramadas: 1 linha por OS, com o maior nº de vezes
    const porOS = new Map();
    rows.forEach(r => {
      const v = +r.vezes || 0, k = String(r.os_id);
      const cur = porOS.get(k);
      if (!cur || v > cur.vezes)
        porOS.set(k, { os: k, usina: r.usina, vezes: v, fin: rexFinBd(r.status) });
    });
    const rolagens = Array.from(porOS.values()).filter(x => x.vezes >= 4)
      .sort((x, y) => y.vezes - x.vezes).slice(0, 6);
    // não coube na semana + motivos (o programador registra o porquê)
    const pend = (w.pendentes || []).filter(rexEscopoFiltro);
    const motivos = {};
    pend.forEach(p => { const m = String(p.motivo || '—'); motivos[m] = (motivos[m] || 0) + 1; });
    const topMot = Object.entries(motivos).sort((x, y) => y[1] - x[1]).slice(0, 3);
    out.push({ week: w.week, label: w.label, seg, sex, plan, fin, G, emergPlan,
      fora: fora.length, foraCorr: new Set(fora.filter(rexCorretiva).map(t => t.os)).size,
      rolagens, pend: pend.length, topMot,
      atual: bd.semana_ativa === w.week });
  });
  return out.sort((x, y) => (x.week < y.week ? -1 : 1));
}

function rexModelo() {
  const a = REX.de, b = REX.ate;
  const T = gpScopedTarefas().filter(rexEscopoFiltro);
  const criadas = T.filter(t => rexRange(t.criacao, a, b));
  const finalizadas = T.filter(t => rexFin(t) && rexRange(t.dataFinal, a, b));
  const prog = T.filter(t => rexRange(t.dataProg, a, b));
  const progFin = prog.filter(rexFin);
  const corrAbertas = T.filter(t => rexCorretiva(t) && t.aberta);
  const mais30 = T.filter(t => t.aberta && (t.dias || 0) > 30);
  const horas = finalizadas.reduce((s, t) => s + (+t.dur || 0), 0);

  // plano preventivo do período, por sigla (fração p/ MPA/MPS — spec Plano&Fila)
  const sig = {};
  prog.forEach(t => {
    const m = GPV_RX.exec(String(t.tarefa || ''));
    if (!m) return;
    const s = sig[m[1]] || (sig[m[1]] = { f: 0, t: 0 });
    s.t++; if (rexFin(t)) s.f++;
  });

  // ranking: OS DISTINTA de corretiva por usina, criada no período
  const len = Math.round((new Date(b) - new Date(a)) / 86400000) + 1;
  const aPrev = rexIso(new Date(new Date(a + 'T12:00:00').getTime() - len * 86400000));
  const bPrev = rexIso(new Date(new Date(a + 'T12:00:00').getTime() - 86400000));
  const porUsina = new Map();
  const u = n => { let x = porUsina.get(n); if (!x) { x = { criadas: new Set(), emerg: new Set(), prev: new Set(), abertas: new Set(), maisAntiga: 0 }; porUsina.set(n, x); } return x; };
  T.forEach(t => {
    if (!rexCorretiva(t)) return;
    const x = u(t.usina);
    if (rexRange(t.criacao, a, b)) { x.criadas.add(t.os); if (rexEmerg(t)) x.emerg.add(t.os); }
    if (rexRange(t.criacao, aPrev, bPrev)) x.prev.add(t.os);
    if (t.aberta) { x.abertas.add(t.os); if ((t.dias || 0) > x.maisAntiga) x.maisAntiga = t.dias || 0; }
  });
  let rank = Array.from(porUsina, ([usina, x]) => ({ usina,
    criadas: x.criadas.size, emerg: x.emerg.size, prev: x.prev.size,
    abertas: x.abertas.size, maisAntiga: x.maisAntiga }))
    .filter(x => x.criadas > 0 || x.abertas > 0)
    .sort((x, y) => y.criadas - x.criadas || y.abertas - x.abertas);

  // emergenciais do período (OS distinta)
  const emergVistas = new Set();
  const emergs = criadas.filter(t => rexEmerg(t) && !emergVistas.has(t.os) && emergVistas.add(t.os));

  // tendência semanal criadas × finalizadas
  const semanas = [];
  for (let d = new Date(a + 'T12:00:00'); rexIso(d) <= b;) {
    const ini = rexIso(d); d.setDate(d.getDate() + 6);
    const fim = rexIso(d) <= b ? rexIso(d) : b; d.setDate(d.getDate() + 1);
    semanas.push({ rot: ini.slice(8, 10) + '/' + ini.slice(5, 7),
      criadas: criadas.filter(t => rexRange(t.criacao, ini, fim)).length,
      fin: finalizadas.filter(t => rexRange(t.dataFinal, ini, fim)).length });
  }

  // volume por tipo (agrupando a cauda em "Outros")
  const tipos = {};
  const tipoDe = t => rexEmerg(t) ? 'Corretiva Emergencial' : rexCorretiva(t) ? 'Corretiva'
    : rexRelig(t) ? 'Religamentos' : /prevent|inspe|predit/i.test(t.tipo || '') ? 'Preventiva/Inspeção' : 'Outros';
  // "abertas" = das CRIADAS NO PERÍODO, as que seguem abertas (não a foto de
  // hoje inteira — senão preventivas futuras programadas inflavam o número)
  T.forEach(t => {
    const cri = rexRange(t.criacao, a, b), fin = rexFin(t) && rexRange(t.dataFinal, a, b);
    if (!cri && !fin) return;
    const k = tipoDe(t);
    const o = tipos[k] || (tipos[k] = { criadas: 0, fin: 0, abertas: 0 });
    if (cri) o.criadas++; if (fin) o.fin++; if (cri && t.aberta) o.abertas++;
  });

  // grandes (Gerencial), quando decifrada — respeitando o escopo
  let ger = null;
  try {
    if (typeof GPV_MP !== 'undefined' && GPV_MP.estado === 'ok' && MP) {
      let fila = gpvFilaLinhas();
      if (REX.cliente) fila = fila.filter(x => gpvMpNorm(x.nome).startsWith(gpvMpNorm(REX.cliente)));
      if (REX.usinas.length) {
        const alvos = REX.usinas.map(gpvMpNorm);
        fila = fila.filter(x => alvos.some(al => { const k = gpvMpNorm(x.nome); return k === al || k.startsWith(al) || al.startsWith(k) || (k.length >= 8 && al.indexOf(k) >= 0) || (al.length >= 8 && k.indexOf(al) >= 0); }));
      }
      ger = { atr: fila.filter(x => x.sit.k === 'Atrasada'),
              semos: fila.filter(x => (x.semOS || x.osSemPar) && !x.conclu).length,
              csd: fila.filter(x => x.critSemData).sort((x, y) => (y.atraso || 0) - (x.atraso || 0)) };
    }
  } catch (e) { ger = null; }

  return { a, b, T, criadas, finalizadas, prog, progFin, corrAbertas, mais30,
           horas, sig, rank, emergs, semanas, tipos, ger,
           osCriadas: new Set(criadas.map(t => t.os)).size,
           osFin: new Set(finalizadas.map(t => t.os)).size };
}

// ── confiabilidade por FAMÍLIA de ativo (pedido Athon 21/09) ─────────────────
// confiabilidade.json: clientes → usinas → ativos {mtbf, mttr, disp, n}.
// Família = palavra-chave no nome do ativo. Agregação ponderada pelo nº de
// falhas: mtbf_fam = Σ(mtbf·n)/Σn (= uptime total ÷ falhas totais — mantém a
// fórmula oficial), idem mttr; disp_fam = mtbf/(mtbf+mttr).
let REX_CF = { estado: 'nao', dados: null };
async function rexCfCarregar() {
  if (REX_CF.estado !== 'nao') return REX_CF.dados;
  try {
    const r = await fetch('confiabilidade.json', { cache: 'no-store' });
    REX_CF.dados = await r.json();
    REX_CF.estado = 'ok';
  } catch (e) { REX_CF.estado = 'erro'; REX_CF.dados = null; }
  return REX_CF.dados;
}
function rexFamilia(ativo, usina) {
  const a = String(ativo || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  if (ativo && usina && ativo === usina) return 'Usina (religamentos)';
  if (a.indexOf('inversor') >= 0) return 'Inversores';
  if (a.indexOf('cabine') >= 0) return 'Cabines';
  if (a.indexOf('transformador') >= 0 || a.indexOf('trafo') >= 0) return 'Transformadores';
  if (a.indexOf('tracker') >= 0 || a.indexOf('rastread') >= 0) return 'Trackers';
  if (a.indexOf('meteo') >= 0 || a.indexOf('estacao') >= 0) return 'Estação Meteorológica';
  if (a.indexOf('string') >= 0 || a.indexOf('modulo') >= 0) return 'Strings / Módulos';
  if (a.indexOf('qgbt') >= 0) return 'QGBT';
  if (a.indexOf('cftv') >= 0 || a.indexOf('camera') >= 0) return 'CFTV / Segurança';
  return 'Outros';
}
function rexFamilias(cf) {
  if (!cf || !cf.clientes) return null;
  // cluster não existe no confiabilidade.json — derivamos as usinas do cluster
  // a partir do gestao_pcm.json quando o recorte pede
  let usinasCluster = null;
  if (REX.cluster) {
    usinasCluster = new Set();
    gpScopedTarefas().forEach(t => { if (t.cluster === REX.cluster) usinasCluster.add(t.usina); });
  }
  const fam = {}, ativos = [];
  cf.clientes.forEach(c => {
    if (REX.cliente && c.cliente !== REX.cliente) return;
    (c.usinas || []).forEach(u => {
      if (REX.usinas.length && REX.usinas.indexOf(u.usina) < 0) return;
      if (usinasCluster && !usinasCluster.has(u.usina)) return;
      (u.ativos || []).forEach(at => {
        const n = +at.n || 0;
        if (!n) return;
        const f = rexFamilia(at.ativo, u.usina);
        const o = fam[f] || (fam[f] = { n: 0, up: 0, rep: 0, ativos: 0 });
        o.n += n; o.up += (+at.mtbf || 0) * n; o.rep += (+at.mttr || 0) * n; o.ativos++;
        ativos.push({ ativo: at.ativo, usina: u.usina, n, mtbf: +at.mtbf || 0,
                      mttr: +at.mttr || 0, disp: +at.disp || 0 });
      });
    });
  });
  const linhas = Object.entries(fam).map(([f, o]) => {
    const mtbf = o.up / o.n, mttr = o.rep / o.n;
    return { fam: f, ativos: o.ativos, n: o.n, mtbf, mttr,
             disp: (mtbf + mttr) ? mtbf / (mtbf + mttr) : 0 };
  }).sort((x, y) => y.n - x.n);
  // piores ativos individuais (mín. 3 falhas — 1 azar não é tendência)
  const piores = ativos.filter(x => x.n >= 3).sort((x, y) => x.disp - y.disp).slice(0, 5);
  return linhas.length ? { linhas, piores, geradoEm: cf.geradoEm || '' } : null;
}

// ── render do relatório ─────────────────────────────────────────────────────
async function rexGerar() {
  REX.de = (document.getElementById('rex-de') || {}).value || REX.de;
  REX.ate = (document.getElementById('rex-ate') || {}).value || REX.ate;
  REX.cliente = (document.getElementById('rex-cli') || {}).value || '';
  REX.cluster = (document.getElementById('rex-clu') || {}).value || '';
  const sel = document.getElementById('rex-usi');
  REX.usinas = sel ? Array.from(sel.selectedOptions).map(o => o.value) : [];
  if (!REX.de || !REX.ate || REX.de > REX.ate) { alert('Confira o período.'); return; }
  rexFecharModal();

  const ehCliente = (typeof S !== 'undefined' && S && S.isAdmin === false);
  const modoCliente = ehCliente || !!REX.cliente;   // 1 cliente no recorte = versão cliente
  const M = rexModelo();
  const SEM = rexSemanas(await rexBdCarregar());    // semanas do programador no período
  const CF = rexFamilias(await rexCfCarregar());    // confiabilidade por família
  let nsec = 0;
  const sec = t => (++nsec) + ' · ' + t;
  const escopo = [REX.cliente || (ehCliente ? S.user : 'Todos os clientes'),
                  REX.cluster, REX.usinas.length ? REX.usinas.length + ' usina(s)' : '']
                 .filter(Boolean).join(' · ');
  const pctPlano = M.prog.length ? Math.round(100 * M.progFin.length / M.prog.length) : null;

  // síntese automática (template da narrativa)
  const topo = M.rank[0];
  const tend = topo ? (topo.criadas > topo.prev ? '▲' : topo.criadas < topo.prev ? '▼' : '=') : '';
  const sintese = 'Em ' + rexFmt(M.a) + '–' + rexFmt(M.b) + ', ' + escopo + ' executou <b>'
    + rexN(M.osFin) + ' OSs</b>' + (pctPlano !== null ? ' (' + pctPlano + '% do plano programado do período)' : '')
    + '; <b>' + rexN(new Set(M.corrAbertas.map(t => t.os)).size) + ' corretivas abertas</b>'
    + (topo ? ', <b>' + rexEsc(topo.usina.replace(/\s*-\s*[A-Z]{2}\s*$/, '')) + '</b> concentra a maior pressão ('
      + topo.criadas + ' OSs no período, ' + tend + ' vs anterior)' : '') + '.'
    + (SEM.length === 1 && SEM[0].plan
      ? ' Aderência da programação na ' + rexEsc(SEM[0].label.split(' · ')[0]).toLowerCase()
        + ': <b>' + Math.round(100 * SEM[0].fin / SEM[0].plan) + '%</b>.' : '');

  const kpi = (v, l, cls) => '<div class="rex-kpi ' + (cls || '') + '"><b>' + v + '</b><span>' + l + '</span></div>';
  const logo = (document.querySelector('.a-logo, .l-logo') || {}).src || '';

  let h = '<div class="rex-bar"><button class="rex-btn-2" onclick="rexFechar()">&#8592; Voltar ao painel</button>'
    + '<span>' + (modoCliente ? 'versão cliente — sem dados internos' : 'versão interna') + '</span>'
    + '<button class="rex-btn" onclick="window.print()">&#128424; Imprimir / PDF</button></div>'
    + '<div class="rex-a4">';

  // P1 — cabeçalho + síntese + farol
  h += '<header class="rex-cab">' + (logo ? '<img src="' + logo + '" alt="Grid Co.">' : '<b class="rex-marca">Grid Co.</b>')
    + '<div><h1>' + (modoCliente ? 'Relatório de O&M — o que entregamos e o que vem a seguir'
                                  : 'Relatório Executivo PCM — o que rodou, o que travou, onde agir') + '</h1>'
    + '<div class="rex-meta">' + rexFmt(M.a) + ' a ' + rexFmt(M.b) + ' · ' + rexEsc(escopo)
    + ' · emitido em ' + new Date().toLocaleString('pt-BR').slice(0, 16) + '</div></div></header>'
    + '<p class="rex-sintese">' + sintese + '</p>'
    + '<div class="rex-kpis">'
    + kpi(rexN(M.osCriadas), 'OSs criadas no período')
    + kpi(rexN(M.osFin), 'OSs finalizadas', 'grn')
    + kpi(pctPlano === null ? '—' : pctPlano + '%', 'do plano programado concluído', pctPlano !== null && pctPlano < 60 ? 'red' : pctPlano < 85 ? 'amb' : 'grn')
    + kpi(rexN(new Set(M.corrAbertas.map(t => t.os)).size), 'corretivas abertas hoje', 'red')
    + (M.ger && !modoCliente ? kpi(rexN(M.ger.atr.length), 'MPA/MPS atrasadas', 'amb') : kpi(rexN(M.mais30.length), 'tarefas abertas há +30 dias', 'amb'))
    + '</div>';

  // saúde do plano preventivo
  const sigRow = ['MPM', 'MPT', 'MPS', 'MPA'].filter(s => M.sig[s]).map(s => {
    const x = M.sig[s], p = Math.round(100 * x.f / x.t);
    const txt = (s === 'MPA' || s === 'MPS') ? x.f + '/' + x.t : p + '%';
    const cls = p >= 100 ? 'ok' : p < 40 ? 'crit' : 'and';
    return '<div class="rex-sig"><b>' + s + '</b><span class="gpv-cel ' + cls + '">' + txt + '</span></div>';
  }).join('');
  if (sigRow) h += '<section><h2>' + sec('Saúde do plano preventivo') + ' <small>tarefas programadas no período</small></h2>'
    + '<div class="rex-sigs">' + sigRow + '</div></section>';

  // programação da semana: planejado × executado (foto do programador)
  if (SEM.length) {
    h += '<section><h2>' + sec('Programação da semana — planejado × executado')
      + ' <small>foto do programador semanal · semanas dentro do período</small></h2>';
    SEM.forEach(s => {
      const ad = s.plan ? Math.round(100 * s.fin / s.plan) : 0;
      h += '<div class="rex-h3">' + rexEsc(s.label) + (s.atual ? ' <em>— semana corrente, parcial</em>' : '') + '</div>'
        + '<div class="rex-kpis">'
        + kpi(ad + '%', 'aderência ao plano da semana', ad < 60 ? 'red' : ad < 85 ? 'amb' : 'grn')
        + kpi(rexN(s.plan), 'tarefas no plano')
        + kpi(rexN(s.fin), 'executadas do plano', 'grn')
        + kpi(rexN(s.fora), 'executadas fora do plano · ' + s.foraCorr + ' OSs corretivas', 'amb')
        + '</div>'
        + '<table class="rex-tbl rex-rank"><tr><th>Tipo</th><th>Planejadas</th><th>Executadas</th><th>%</th></tr>'
        + ['Preventivas', 'Corretivas', 'Religamentos', 'Demais'].filter(g => s.G[g]).map(g => {
            const x = s.G[g], p = Math.round(100 * x.f / x.p);
            return '<tr><td class="rex-esq">' + g
              + (g === 'Corretivas' && s.emergPlan ? ' <small>(' + s.emergPlan + ' emergenciais)</small>' : '') + '</td>'
              + '<td>' + rexN(x.p) + '</td>'
              + '<td class="rex-esq"><i class="rex-barra" style="width:' + p + '%"></i><b>' + rexN(x.f) + '</b></td>'
              + '<td class="' + (p < 60 ? 'rex-red' : p >= 85 ? 'rex-grn' : '') + '">' + p + '%</td></tr>';
          }).join('')
        + '</table>'
        + (s.rolagens.length ? '<div class="rex-nota"><b>Reprogramadas 4× ou mais:</b> '
            + s.rolagens.map(x => '#' + x.os + ' ' + rexEsc(rexUsiCurta(x.usina)) + ' (' + x.vezes + '×' + (x.fin ? ', feita' : '') + ')').join(' · ') + '</div>' : '')
        + (s.pend ? '<div class="rex-nota"><b>Não coube na semana:</b> ' + rexN(s.pend) + ' tarefa(s)'
            + (s.topMot.length ? ' — motivos: ' + s.topMot.map(([m, n]) => rexEsc(m) + ' (' + n + ')').join('; ') : '') + '</div>' : '');
    });
    h += '<div class="rex-nota">Plano = a planilha da Programação da semana (ajustes até o fechamento contam; '
      + 'não é a foto de sexta 8h) · executado = tarefa Finalizada · fora do plano = finalizadas de segunda a '
      + 'DOMINGO sem estar na planilha · preventiva mede cumprimento do plano; corretiva mede resposta à demanda.</div></section>';
  }

  // tendência semanal
  if (M.semanas.length > 1) {
    const mx = Math.max(1, ...M.semanas.map(s => Math.max(s.criadas, s.fin)));
    h += '<section><h2>' + sec('Ritmo do período') + ' <small>OSs criadas × finalizadas por semana</small></h2>'
      + '<div class="rex-sems">' + M.semanas.map(s =>
        '<div class="rex-sem"><div class="rex-sem-b"><i style="height:' + Math.round(64 * s.criadas / mx) + 'px"></i>'
        + '<i class="f" style="height:' + Math.round(64 * s.fin / mx) + 'px"></i></div>'
        + '<span>' + s.rot + '</span><small>' + s.criadas + '·' + s.fin + '</small></div>').join('')
      + '</div><div class="rex-leg"><span><i class="c1"></i>criadas</span><span><i class="c2"></i>finalizadas</span></div></section>';
  }

  // volume por tipo
  const ordTipos = ['Corretiva', 'Corretiva Emergencial', 'Preventiva/Inspeção', 'Religamentos', 'Outros'].filter(k => M.tipos[k]);
  h += '<section><h2>' + sec('Volume por tipo') + ' <small>tarefas do período</small></h2>'
    + '<table class="rex-tbl"><tr><th>Tipo</th><th>Criadas</th><th>Finalizadas</th><th>Criadas e ainda abertas</th></tr>'
    + ordTipos.map(k => { const o = M.tipos[k]; return '<tr><td>' + k + '</td><td>' + rexN(o.criadas) + '</td><td>' + rexN(o.fin) + '</td><td>' + (o.abertas ? '<b class="rex-red">' + rexN(o.abertas) + '</b>' : '0') + '</td></tr>'; }).join('')
    + '</table><div class="rex-nota">Finalizadas pode superar Criadas: conta tudo que foi concluído no período, '
    + 'inclusive OSs criadas antes dele. "Criadas e ainda abertas" = das criadas no período, as que seguem sem conclusão.</div></section>';

  // confiabilidade por família de equipamento (base histórica — não recorta pelo período)
  if (CF) {
    const nfmt = (v, c) => v.toFixed(c).replace('.', ',');
    const dispMin = Math.min(...CF.linhas.filter(x => x.n >= 10).map(x => x.disp), 1);
    h += '<section><h2>' + sec('Confiabilidade por família de equipamento')
      + ' <small>falhas = corretivas, emergenciais e religamentos · base histórica desde a mobilização de cada usina</small></h2>'
      + '<table class="rex-tbl"><tr><th>Família</th><th>Ativos</th><th>Falhas</th><th>MTBF (h)</th><th>MTTR (h)</th><th>Disp. inerente</th></tr>'
      + CF.linhas.map(x => '<tr><td class="rex-esq">' + rexEsc(x.fam) + '</td>'
        + '<td>' + rexN(x.ativos) + '</td><td>' + rexN(x.n) + '</td>'
        + '<td>' + nfmt(x.mtbf, 1) + '</td><td>' + nfmt(x.mttr, 2) + '</td>'
        + '<td class="' + (x.n >= 10 && x.disp === dispMin ? 'rex-red' : '') + '"><b>'
        + nfmt(100 * x.disp, 1) + '%</b></td></tr>').join('')
      + '</table>'
      + (CF.piores.length ? '<table class="rex-tbl" style="margin-top:8px"><tr>'
        + '<th>Ativos com pior disponibilidade <small>(mín. 3 falhas)</small></th><th>Usina</th><th>Falhas</th><th>MTTR (h)</th><th>Disp.</th></tr>'
        + CF.piores.map(p => '<tr><td class="rex-esq">' + rexEsc(String(p.ativo).slice(0, 45)) + '</td>'
          + '<td class="rex-esq">' + rexEsc(rexUsiCurta(p.usina)) + '</td><td>' + p.n + '</td>'
          + '<td>' + nfmt(p.mttr, 2) + '</td><td class="rex-red"><b>' + nfmt(100 * p.disp, 1) + '%</b></td></tr>').join('')
        + '</table>' : '')
      + '<div class="rex-nota">MTBF = tempo médio entre falhas · MTTR = tempo médio de reparo · '
      + 'Disp. inerente = MTBF ÷ (MTBF + MTTR) · agregação ponderada pelo nº de falhas de cada ativo · '
      + 'dados de ' + rexEsc(String(CF.geradoEm).slice(0, 16).replace('T', ' ')) + '.</div></section>';
  }

  // P2 — ranking (a estrela)
  const top = M.rank.slice(0, 10);
  const resto = M.rank.slice(10);
  const mxR = Math.max(1, ...top.map(x => x.criadas));
  h += '<section class="rex-quebra"><h2>' + sec('Usinas que pedem atenção') + ' <small>corretivas por OS distinta · ordenado pelas criadas no período</small></h2>'
    + '<table class="rex-tbl rex-rank"><tr><th>#</th><th>Usina</th><th>Criadas no período</th><th>Emerg.</th><th>Tend.</th><th>Abertas hoje</th><th>Mais antiga</th></tr>'
    + top.map((x, i) => '<tr><td>' + (i + 1) + '</td><td class="rex-esq">' + rexEsc(x.usina) + '</td>'
      + '<td class="rex-esq"><i class="rex-barra" style="width:' + Math.round(100 * x.criadas / mxR) + '%"></i><b>' + x.criadas + '</b></td>'
      + '<td>' + (x.emerg || '—') + '</td>'
      + '<td class="' + (x.criadas > x.prev ? 'rex-red' : x.criadas < x.prev ? 'rex-grn' : '') + '">'
      + (x.criadas > x.prev ? '▲ +' + (x.criadas - x.prev) : x.criadas < x.prev ? '▼ −' + (x.prev - x.criadas) : '=') + '</td>'
      + '<td>' + (x.abertas ? '<b class="rex-red">' + x.abertas + '</b>' : '0') + '</td>'
      + '<td>' + (x.maisAntiga ? x.maisAntiga + ' d' : '—') + '</td></tr>').join('')
    + (resto.length ? '<tr class="rex-resto"><td></td><td class="rex-esq">demais usinas (' + resto.length + ')</td><td class="rex-esq"><b>'
      + resto.reduce((s, x) => s + x.criadas, 0) + '</b></td><td>' + resto.reduce((s, x) => s + x.emerg, 0) + '</td><td></td><td>'
      + resto.reduce((s, x) => s + x.abertas, 0) + '</td><td></td></tr>' : '')
    + '</table><div class="rex-nota">Tend. = criadas neste período vs período anterior de mesmo tamanho (' + rexFmt(M.a) + ' p/ trás).</div></section>';

  // emergenciais
  if (M.emergs.length) {
    h += '<section><h2>' + sec('Corretivas emergenciais do período') + ' <small>' + M.emergs.length + ' OS</small></h2>'
      + '<table class="rex-tbl"><tr><th>OS</th><th>Usina</th><th>Tarefa</th><th>Situação</th></tr>'
      + M.emergs.slice(0, 8).map(t => '<tr><td>' + rexEsc(t.os) + '</td><td class="rex-esq">' + rexEsc(t.usina) + '</td>'
        + '<td class="rex-esq">' + rexEsc(String(t.tarefa || '').slice(0, 60)) + '</td>'
        + '<td>' + (rexFin(t) ? '<span class="gpv-cel ok">resolvida</span>' : t.aberta ? '<span class="gpv-cel crit">aberta' + (t.dias ? ' · ' + t.dias + 'd' : '') + '</span>' : rexEsc(t.estado)) + '</td></tr>').join('')
      + (M.emergs.length > 8 ? '<tr class="rex-resto"><td></td><td class="rex-esq" colspan="3">+' + (M.emergs.length - 8) + ' não listadas</td></tr>' : '')
      + '</table></section>';
  }

  // grandes manutenções (interno + Gerencial decifrada)
  if (M.ger && !modoCliente) {
    h += '<section><h2>' + sec('Grandes manutenções (MPA/MPS)') + ' <small>Gerencial + Fracttal, foto de hoje</small></h2>'
      + '<div class="rex-kpis rex-kpis-3">'
      + kpi(rexN(M.ger.atr.length), 'atrasadas', 'red') + kpi(rexN(M.ger.semos), 'sem OS no Fracttal', 'amb')
      + kpi(rexN(M.ger.csd.length), 'críticas sem data futura', 'amb') + '</div>'
      + (M.ger.csd.length ? '<table class="rex-tbl"><tr><th>Usina</th><th>Tipo</th><th>Criticidade</th><th>Atraso</th><th>Última observação</th></tr>'
        + M.ger.csd.slice(0, 5).map(x => '<tr><td class="rex-esq">' + rexEsc(x.nome) + '</td><td>' + x.tipo + '</td>'
          + '<td><span class="gpv-crit ' + x.critCls + '">' + rexEsc(x.crit) + '</span></td>'
          + '<td>' + (x.atraso != null ? x.atraso + ' d' : '—') + '</td>'
          + '<td class="rex-esq rex-obs">' + rexEsc(String(x.obs || '').slice(0, 80)) + '</td></tr>').join('') + '</table>' : '');
    h += '</section>';
  }

  // esforço (interno)
  if (!modoCliente) {
    const porResp = {};
    M.finalizadas.forEach(t => { const r = t.responsavel || '—'; porResp[r] = (porResp[r] || 0) + (+t.dur || 0); });
    const resp = Object.entries(porResp).sort((x, y) => y[1] - x[1]).slice(0, 8);
    h += '<section><h2>' + sec('Esforço do período') + ' <small>' + rexN(Math.round(M.horas)) + ' h executadas</small></h2>'
      + '<table class="rex-tbl"><tr><th>Supervisão / Responsável</th><th>Horas</th></tr>'
      + resp.map(([r, hrs]) => '<tr><td class="rex-esq">' + rexEsc(r) + '</td><td>' + rexN(Math.round(hrs)) + ' h</td></tr>').join('')
      + '</table></section>';
  }

  // ações — termina em ação, não em dado
  h += '<section class="rex-acoes"><h2>' + sec('Ações e compromissos') + '</h2>'
    + '<div class="rex-acao-l">1. ____________________________________________ resp.: __________ até __/__</div>'
    + '<div class="rex-acao-l">2. ____________________________________________ resp.: __________ até __/__</div>'
    + '<div class="rex-acao-l">3. ____________________________________________ resp.: __________ até __/__</div></section>';

  h += '<footer class="rex-pe">Fonte: CMMS Fracttal via gestao_pcm.json (dados de '
    + rexEsc((GESTAO_DB && GESTAO_DB.geradoEm || '').slice(0, 16).replace('T', ' ')) + ')'
    + (M.ger && !modoCliente ? ' + Gerencial (aba MPAS)' : '')
    + ' · corretivas contadas por OS distinta · concluído = tarefa Finalizada (nunca o Status da OS) · Grid Co. — PCM</footer>'
    + '</div>';

  let v = document.getElementById('rex-view');
  if (!v) { v = document.createElement('div'); v.id = 'rex-view'; document.body.appendChild(v); }
  v.innerHTML = h;
  document.body.classList.add('rex-on');
  window.scrollTo(0, 0);
}
function rexFechar() {
  const v = document.getElementById('rex-view'); if (v) v.remove();
  document.body.classList.remove('rex-on');
}

// ── botão na aba Gestão PCM (injeta ao lado do "Limpar") ────────────────────
function rexBotao() {
  if (document.getElementById('rex-abrir')) return;
  const ref = document.querySelector('#s-gestaopcm .gp-clear, .gp-clear');
  if (!ref) return;
  const b = document.createElement('button');
  b.id = 'rex-abrir'; b.className = 'rex-btn'; b.type = 'button';
  b.innerHTML = '&#128196; Relatório executivo';
  b.onclick = rexAbrirModal;
  ref.parentNode.insertBefore(b, ref.nextSibling);
}
if (typeof renderGestao === 'function') {
  const _renderGestaoOrigRex = renderGestao;
  renderGestao = function () {
    _renderGestaoOrigRex.apply(this, arguments);
    try { rexBotao(); } catch (e) { console.warn('relatorio_exec:', e); }
  };
}
