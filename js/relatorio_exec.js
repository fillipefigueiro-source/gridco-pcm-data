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
// "aberta de verdade" = tarefa aberta E a OS ainda viva. Tarefa aberta dentro
// de OS já concluída é registro histórico (ninguém vai agir nela) — não entra
// em ranking, listas nem cards de backlog (pedido de 22/09, caso OS 6308).
const rexAbertaViva = t => t.aberta && String(t.osStatus || '') !== 'Finalizados';
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
// grupos da tabela da semana. Religamento REMOTO é tratado à parte: não entra
// em nenhum cálculo (não mobiliza campo) — vira só nota informativa.
const REX_GRUPOS = ['Preventivas', 'Corretiva', 'Corretiva Emergencial', 'Religamento', 'Demais'];
function rexGrupoBd(tipo) {
  const t = String(tipo || '');
  if (/^Religamento Remoto/i.test(t)) return 'Remoto';
  if (/^Religamento/i.test(t)) return 'Religamento';
  if (/^Corretiva Emergencial/i.test(t)) return 'Corretiva Emergencial';
  if (/^Corretiva/i.test(t)) return 'Corretiva';
  if (/^MP/i.test(t) || /^Preventiva/i.test(t)) return 'Preventivas';
  return 'Demais';                     // Handover, Inspeção, Administrativa, Zeladoria…
}
const REX_DIA = { 'Segunda-feira': 'Seg', 'Terça-feira': 'Ter', 'Quarta-feira': 'Qua',
                  'Quinta-feira': 'Qui', 'Sexta-feira': 'Sex', 'Sábado': 'Sáb', 'Domingo': 'Dom' };
const REX_DIAS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex'];
// aderência: meta 85% (verde), 60–84 âmbar, <60 vermelho — reusa as classes gpv-cel
const rexFx = p => p >= 85 ? 'ok' : p >= 60 ? 'and' : 'crit';
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
    const rowsAll = (w.rows || []).filter(r => rexEscopoFiltro(r) && !r.foraDoPlano);
    if (!rowsAll.length) return;
    const rows = rowsAll.filter(r => rexGrupoBd(r.tipo) !== 'Remoto');   // remoto fora do cálculo
    const dom = rexIso(new Date(new Date(seg + 'T12:00:00').getTime() + 6 * 86400000));
    // CORTE DO PLANO = quando a planilha da semana foi GERADA (carimbo interno
    // do xlsx, w.geradaEm, em UTC) — mesma régua do card "criadas após o plano"
    // do pcm.gridco.com.br. Sem carimbo (semanas antigas): sexta anterior 00h.
    const _loc = d => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
    const corte = w.geradaEm && !isNaN(new Date(w.geradaEm))
      ? _loc(new Date(w.geradaEm))
      : rexIso(new Date(new Date(seg + 'T12:00:00').getTime() - 3 * 86400000)) + 'T00:00:00';
    const osPlan = new Set(rowsAll.map(r => String(r.os_id)));
    // plano da semana: por grupo + por cluster/dia (tático) + abertas do plano.
    // OS CRIADA DEPOIS DO CORTE (geração da planilha) não pode ter estado no plano da
    // sexta — mesmo encaixada na planilha (relida continuamente), conta como
    // NÃO PLANEJADA (caso OS 14478, 24/09; o congelamento real fica p/ depois)
    const G = {}, NP = {}, CLM = new Map(), abertasPlano = [];
    let plan = 0, fin = 0, npT = 0, npF = 0;
    rows.forEach(r => {
      const feito = rexFinBd(r.status);
      const gk = rexGrupoBd(r.tipo);
      if (String(r.dataCriacao || '').slice(0, 19) >= corte) {   // nasceu depois do plano
        const o = NP[gk] || (NP[gk] = { p: 0, f: 0 });
        o.p++; npT++;
        if (feito) { o.f++; npF++; }
        return;
      }
      const g = G[gk] || (G[gk] = { p: 0, f: 0 });
      g.p++; plan++;
      if (feito) { g.f++; fin++; }
      const cl = CLM.get(r.cluster) || { cluster: r.cluster || '—', usinas: new Set(), p: 0, f: 0, dias: {} };
      cl.usinas.add(rexUsiCurta(r.usina)); cl.p++;
      const dk = REX_DIA[String(r.dia || '')] || '—';
      const dd = cl.dias[dk] || (cl.dias[dk] = { p: 0, f: 0 });
      dd.p++;
      if (feito) { cl.f++; dd.f++; }
      CLM.set(r.cluster, cl);
      if (!feito) abertasPlano.push({ tarefa: r.tarefa, usina: rexUsiCurta(r.usina),
        cluster: r.cluster || '—', tipo: r.tipo, dia: dk, os: String(r.os_id) });
    });
    const CL = Array.from(CLM.values()).map(c => ({ ...c, usinas: Array.from(c.usinas).sort() }))
      .sort((x, y) => (x.p ? x.f / x.p : 1) - (y.p ? y.f / y.p : 1) || String(x.cluster).localeCompare(y.cluster));
    // não planejadas: tarefas com atividade na semana CHEIA (seg→dom) fora da
    // planilha — criadas na semana ou finalizadas nela; remoto vira só a nota
    const T = gpScopedTarefas().filter(rexEscopoFiltro);
    let remotos = 0;
    T.forEach(t => {
      const g = rexGrupoBd(t.tipo);
      const fimSem = rexFin(t) && rexRange(t.dataFinal, seg, dom);
      if (g === 'Remoto') { if (fimSem) remotos++; return; }
      if (osPlan.has(String(t.os))) return;
      const criSem = rexRange(t.criacao, corte.slice(0, 10), dom);
      if (!criSem && !fimSem) return;
      const o = NP[g] || (NP[g] = { p: 0, f: 0 });
      o.p++; npT++;
      if (fimSem) { o.f++; npF++; }
    });
    // reprogramadas: 1 linha por OS, com o maior nº de vezes
    const porOS = new Map();
    rows.forEach(r => {
      const v = +r.vezes || 0, k = String(r.os_id);
      const cur = porOS.get(k);
      if (!cur || v > cur.vezes)
        porOS.set(k, { os: k, usina: r.usina, tarefa: r.tarefa, tipo: r.tipo,
                       vezes: v, fin: rexFinBd(r.status) });
    });
    const rolagens = Array.from(porOS.values()).filter(x => x.vezes >= 2)
      .sort((x, y) => y.vezes - x.vezes).slice(0, 10);
    // não coube na semana + motivos (o programador registra o porquê)
    const pend = (w.pendentes || []).filter(rexEscopoFiltro);
    const motivos = {};
    pend.forEach(p => { const m = String(p.motivo || '—'); motivos[m] = (motivos[m] || 0) + 1; });
    const topMot = Object.entries(motivos).sort((x, y) => y[1] - x[1]).slice(0, 3);
    out.push({ week: w.week, label: w.label, seg, sex, plan, fin, G, NP, npT, npF,
      remotos, CL, abertasPlano, rolagens, corte, pend: pend.length, topMot,
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
  const corrAbertas = T.filter(t => rexCorretiva(t) && rexAbertaViva(t));
  const mais30 = T.filter(t => rexAbertaViva(t) && (t.dias || 0) > 30);
  const horas = finalizadas.reduce((s, t) => s + (+t.dur || 0), 0);

  // plano preventivo do período, por sigla (fração p/ MPA/MPS — spec Plano&Fila)
  const sig = {};
  prog.forEach(t => {
    const m = GPV_RX.exec(String(t.tarefa || ''));
    if (!m) return;
    const s = sig[m[1]] || (sig[m[1]] = { f: 0, t: 0 });
    s.t++; if (rexFin(t)) s.f++;
  });

  // ranking "usinas que pedem atenção": TAREFAS EM ABERTO hoje (todos os
  // tipos) ordena; mais antiga dá a profundidade; OSs corretivas criadas no
  // período ficam de contexto (spec 22/09 — antes ordenava por criadas)
  const porUsina = new Map();
  const u = n => { let x = porUsina.get(n); if (!x) { x = { abertas: 0, corrAb: new Set(), criadas: new Set(), emerg: new Set(), maisAntiga: 0, tarefas: [] }; porUsina.set(n, x); } return x; };
  T.forEach(t => {
    const x = u(t.usina);
    if (rexAbertaViva(t)) {
      x.abertas++;
      if (rexCorretiva(t)) x.corrAb.add(t.os);
      if ((t.dias || 0) > x.maisAntiga) x.maisAntiga = t.dias || 0;
      x.tarefas.push(t);                       // p/ a lista tática das críticas
    }
    if (rexCorretiva(t) && rexRange(t.criacao, a, b)) {
      x.criadas.add(t.os);
      if (rexEmerg(t)) x.emerg.add(t.os);
    }
  });
  let rank = Array.from(porUsina, ([usina, x]) => ({ usina,
    abertas: x.abertas, corrAb: x.corrAb.size, criadas: x.criadas.size,
    emerg: x.emerg.size, maisAntiga: x.maisAntiga,
    tarefas: x.tarefas.sort((p, q) => (q.dias || 0) - (p.dias || 0)) }))
    .filter(x => x.abertas > 0 || x.criadas > 0)
    .sort((x, y) => y.abertas - x.abertas || y.maisAntiga - x.maisAntiga);

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
    if (cri) o.criadas++; if (fin) o.fin++; if (cri && rexAbertaViva(t)) o.abertas++;
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
  const fam = {}, ativos = [], porUsina = [];
  cf.clientes.forEach(c => {
    if (REX.cliente && c.cliente !== REX.cliente) return;
    (c.usinas || []).forEach(u => {
      if (REX.usinas.length && REX.usinas.indexOf(u.usina) < 0) return;
      if (usinasCluster && !usinasCluster.has(u.usina)) return;
      const ativosU = [];
      (u.ativos || []).forEach(at => {
        const n = +at.n || 0;
        if (!n) return;
        const f = rexFamilia(at.ativo, u.usina);
        const o = fam[f] || (fam[f] = { n: 0, up: 0, rep: 0, ativos: 0 });
        o.n += n; o.up += (+at.mtbf || 0) * n; o.rep += (+at.mttr || 0) * n; o.ativos++;
        const reg = { ativo: at.ativo, usina: u.usina, n, mtbf: +at.mtbf || 0,
                      mttr: +at.mttr || 0, disp: +at.disp || 0 };
        ativos.push(reg); ativosU.push(reg);
      });
      if (ativosU.length)
        porUsina.push({ usina: u.usina, mtbf: +u.mtbf || 0, mttr: +u.mttr || 0,
          disp: +u.disp || 0, n: +u.n || 0,
          ativos: ativosU.sort((x, y) => y.n - x.n) });
    });
  });
  porUsina.sort((x, y) => y.n - x.n);
  const linhas = Object.entries(fam).map(([f, o]) => {
    const mtbf = o.up / o.n, mttr = o.rep / o.n;
    return { fam: f, ativos: o.ativos, n: o.n, mtbf, mttr,
             disp: (mtbf + mttr) ? mtbf / (mtbf + mttr) : 0 };
  }).sort((x, y) => y.n - x.n);
  // piores ativos individuais (mín. 3 falhas — 1 azar não é tendência)
  const piores = ativos.filter(x => x.n >= 3).sort((x, y) => x.disp - y.disp).slice(0, 5);
  return linhas.length ? { linhas, piores, porUsina, geradoEm: cf.geradoEm || '' } : null;
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
  const pctT = (f, t) => t ? Math.round(100 * f / t) : 0;
  const SW = SEM.length ? SEM[SEM.length - 1] : null;   // semana mais recente (Tático)
  const sintese = 'Em ' + rexFmt(M.a) + '–' + rexFmt(M.b) + ', ' + escopo + ' executou <b>'
    + rexN(M.osFin) + ' OSs</b>' + (pctPlano !== null ? ' (' + pctPlano + '% do programado no período)' : '')
    + (SW && SW.plan ? '; execução total da ' + rexEsc(SW.label.split(' · ')[0]).toLowerCase()
      + ': <b>' + pctT(SW.fin + SW.npF, SW.plan + SW.npT) + '%</b>' : '')
    + '; <b>' + rexN(new Set(M.corrAbertas.map(t => t.os)).size) + ' corretivas abertas</b>'
    + (topo && topo.abertas ? ' — <b>' + rexEsc(topo.usina.replace(/\s*-\s*[A-Z]{2}\s*$/, ''))
      + '</b> lidera o backlog (' + topo.abertas + ' tarefas em aberto, mais antiga '
      + topo.maisAntiga + ' d)' : '') + '.';

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

  // ═════════ PARTE 1 · VISÃO GERENCIAL ═════════
  h += '<div class="rex-parte">Visão Gerencial — a semana em um olhar</div>';

  // G1+G2 — programação da semana: execução total + tabela de tipos
  if (SEM.length) {
    h += '<section><h2>' + sec('Programação da semana — planejado × executado')
      + ' <small>foto do programador semanal · religamentos remotos fora do cálculo</small></h2>';
    SEM.forEach(s => {
      const adP = pctT(s.fin, s.plan), adN = pctT(s.npF, s.npT), adT = pctT(s.fin + s.npF, s.plan + s.npT);
      const _c = s.corte || '';
      h += '<div class="rex-h3">' + rexEsc(s.label) + (s.atual ? ' <em>— semana corrente, parcial</em>' : '')
        + (_c ? ' <em>· plano fechado em ' + _c.slice(8, 10) + '/' + _c.slice(5, 7) + ' às ' + _c.slice(11, 16) + '</em>' : '') + '</div>'
        // card largo: manchete "Execução total" + as duas componentes com micro-barras
        + '<div class="rex-ade"><div class="rex-ade-m"><b class="' + rexFx(adT) + '">' + adT + '%</b>'
        + '<span>Execução total<br><small>tudo que foi feito ÷ tudo que havia · '
        + rexN(s.fin + s.npF) + '/' + rexN(s.plan + s.npT) + '</small></span></div>'
        + '<div class="rex-ade-c">'
        + '<div class="rex-ade-l"><span>Aderência ao plano <small>executadas ÷ planejadas na semana</small></span>'
        + '<i><b class="' + rexFx(adP) + '" style="width:' + adP + '%"></b></i><em>' + adP + '% · ' + rexN(s.fin) + '/' + rexN(s.plan) + '</em></div>'
        + '<div class="rex-ade-l"><span>Resposta ao imprevisto <small>resolvidas ÷ surgidas fora do plano</small></span>'
        + '<i><b class="' + rexFx(adN) + '" style="width:' + adN + '%"></b></i><em>' + adN + '% · ' + rexN(s.npF) + '/' + rexN(s.npT) + '</em></div>'
        + '</div></div>'
        // tabela de tipos — grupos "Do plano | Fora do plano" com divisória
        // vertical, "Resolvidas" à direita (evita 2× "Executadas") e TOTAL
        + (function () {
            const gs = REX_GRUPOS.filter(g => s.G[g] || s.NP[g]);
            const tot = { p: 0, f: 0, np: 0, nf: 0 };
            const mut = '<span class="rex-mut">—</span>';
            // célula de % no formato pedido: "50% (20/40)"
            const pctCel = (f, t, div) => {
              if (!t) return '<td class="' + (div || '') + '">' + mut + '</td>';
              const p = pctT(f, t);
              return '<td class="' + (div ? div + ' ' : '') + (p < 60 ? 'rex-red' : p >= 85 ? 'rex-grn' : '')
                + '"><b>' + p + '%</b> <small>(' + rexN(f) + '/' + rexN(t) + ')</small></td>';
            };
            const linhas = gs.map(g => {
              const x = s.G[g] || { p: 0, f: 0 }, n = s.NP[g] || { p: 0, f: 0 };
              tot.p += x.p; tot.f += x.f; tot.np += n.p; tot.nf += n.f;
              return '<tr><td class="rex-esq">' + g + '</td>'
                + '<td class="rex-div">' + (x.p ? rexN(x.p) : mut) + '</td>'
                + '<td>' + (x.p ? rexN(x.f) : mut) + '</td>' + pctCel(x.f, x.p)
                + '<td class="rex-div">' + (n.p ? rexN(n.p) : mut) + '</td>'
                + '<td>' + (n.p ? rexN(n.f) : mut) + '</td>' + pctCel(n.f, n.p) + '</tr>';
            }).join('');
            return '<table class="rex-tbl rex-tipos">'
              + '<colgroup><col style="width:22%"><col style="width:12%"><col style="width:12%">'
              + '<col style="width:15%"><col style="width:12%"><col style="width:12%"><col style="width:15%"></colgroup>'
              + '<tr><th rowspan="2" style="vertical-align:bottom">Tipo</th>'
              + '<th colspan="3" class="rex-th-g rex-div">Do plano da semana</th>'
              + '<th colspan="3" class="rex-th-g rex-th-g2 rex-div">Fora do plano</th></tr>'
              + '<tr><th class="rex-div">Planejadas</th><th>Executadas</th><th>%</th>'
              + '<th class="rex-div rex-th-g2">Não planejadas</th><th class="rex-th-g2">Executadas</th><th class="rex-th-g2">%</th></tr>'
              + linhas
              + '<tr class="rex-total"><td class="rex-esq"><b>TOTAL</b></td>'
              + '<td class="rex-div"><b>' + rexN(tot.p) + '</b></td><td><b>' + rexN(tot.f) + '</b></td>' + pctCel(tot.f, tot.p)
              + '<td class="rex-div"><b>' + rexN(tot.np) + '</b></td><td><b>' + rexN(tot.nf) + '</b></td>' + pctCel(tot.nf, tot.np)
              + '</tr></table>';
          })()
        + '<div class="rex-nota"><b>Religamentos remotos na semana: ' + rexN(s.remotos)
        + '</b> — não entram no cálculo: atendimento remoto, sem mobilização do time de campo.</div>'
        + (s.pend ? '<div class="rex-nota"><b>Não coube na semana:</b> ' + rexN(s.pend) + ' tarefa(s)'
            + (s.topMot.length ? ' — motivos: ' + s.topMot.map(([m, n]) => rexEsc(m) + ' (' + n + ')').join('; ') : '') + '</div>' : '');
    });
    h += '<div class="rex-nota">Plano = a planilha da Programação da semana; tarefa criada DEPOIS do fechamento do plano '
      + '(momento em que a planilha foi gerada) conta como não planejada, mesmo quando encaixada nela · executado = tarefa Finalizada · '
      + 'não planejada = criada após o fechamento ou executada sem estar na planilha (até domingo) · '
      + 'preventiva mede cumprimento do plano; corretiva mede resposta à demanda.</div></section>';
  }

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
      + '<div class="rex-nota"><b>Os indicadores por família são um termômetro da tendência geral; a leitura '
      + 'conclusiva de confiabilidade é feita ativo a ativo</b> (Parte Tática) — o agregado não substitui essa análise. '
      + 'MTBF = tempo médio entre falhas · MTTR = tempo médio de reparo · Disp. inerente = MTBF ÷ (MTBF + MTTR) · '
      + 'agregação ponderada pelo nº de falhas · dados de ' + rexEsc(String(CF.geradoEm).slice(0, 16).replace('T', ' ')) + '.</div></section>';
  }

  // G4 — usinas que pedem atenção (ordena por TAREFAS EM ABERTO — spec 22/09)
  const top = M.rank.slice(0, 10);
  const resto = M.rank.slice(10);
  const mxR = Math.max(1, ...top.map(x => x.abertas));
  h += '<section class="rex-quebra"><h2>' + sec('Usinas que pedem atenção')
    + ' <small>ordenado por tarefas em aberto hoje · detalhe das tarefas na Parte Tática</small></h2>'
    + '<table class="rex-tbl rex-rank"><tr><th>#</th><th>Usina</th><th>Tarefas em aberto</th><th>OSs corretivas abertas</th><th>Mais antiga</th><th>OSs corretivas criadas no período</th></tr>'
    + top.map((x, i) => '<tr><td>' + (i + 1) + '</td><td class="rex-esq">' + rexEsc(x.usina) + '</td>'
      + '<td class="rex-esq"><i class="rex-barra" style="width:' + Math.round(100 * x.abertas / mxR) + '%"></i><b>' + rexN(x.abertas) + '</b></td>'
      + '<td>' + (x.corrAb ? '<b class="rex-red">' + x.corrAb + '</b>' : '—') + '</td>'
      + '<td>' + (x.maisAntiga ? x.maisAntiga + ' d' : '—') + '</td>'
      + '<td>' + (x.criadas || '—') + (x.emerg ? ' <small>(' + x.emerg + ' emerg.)</small>' : '') + '</td></tr>').join('')
    + (resto.length ? '<tr class="rex-resto"><td></td><td class="rex-esq">demais usinas (' + resto.length + ')</td><td class="rex-esq"><b>'
      + resto.reduce((s, x) => s + x.abertas, 0) + '</b></td><td>' + resto.reduce((s, x) => s + x.corrAb, 0) + '</td><td></td><td>'
      + resto.reduce((s, x) => s + x.criadas, 0) + '</td></tr>' : '')
    + '</table></section>';

  // G5 — top 10 que mais rolaram (todas as semanas do período, 1 linha por OS)
  const rolMap = new Map();
  SEM.forEach(s => s.rolagens.forEach(x => {
    const cur = rolMap.get(x.os);
    if (!cur || x.vezes > cur.vezes) rolMap.set(x.os, x);
  }));
  const rol10 = Array.from(rolMap.values()).sort((x, y) => y.vezes - x.vezes).slice(0, 10);
  if (rol10.length) {
    h += '<section><h2>' + sec('Top 10 — tarefas que mais rolaram')
      + ' <small>nº de semanas em que a OS entrou na programação</small></h2>'
      + '<table class="rex-tbl"><tr><th>OS</th><th>Usina</th><th>Tarefa</th><th>Tipo</th><th>Rolagens</th><th>Situação</th></tr>'
      + rol10.map(x => '<tr><td>' + rexEsc(x.os) + '</td><td class="rex-esq">' + rexEsc(rexUsiCurta(x.usina)) + '</td>'
        + '<td class="rex-esq">' + rexEsc(String(x.tarefa || '').replace(/^\[[^\]]*\]\s*-?\s*/, '').slice(0, 55)) + '</td>'
        + '<td>' + rexEsc(x.tipo) + '</td><td><b class="' + (x.vezes >= 6 ? 'rex-red' : '') + '">' + x.vezes + '×</b></td>'
        + '<td>' + (x.fin ? '<span class="gpv-cel ok">feita</span>' : '<span class="gpv-cel crit">em aberto</span>') + '</td></tr>').join('')
      + '</table></section>';
  }

  // ═════════ PARTE 2 · VISÃO TÁTICA ═════════
  if (SW || (CF && CF.porUsina && CF.porUsina.length)) {
    h += '<div class="rex-parte rex-quebra">Visão Tática — cluster a cluster, usina a usina'
      + '<small>A partir daqui, os mesmos resultados abertos no detalhe: cada cluster, cada usina, cada atividade em aberto.</small></div>';
  }

  // T1 — programação por cluster × dia (heatmap da semana mais recente)
  if (SW && SW.CL.length) {
    h += '<section><h2>' + sec('Programação por cluster e dia') + ' <small>' + rexEsc(SW.label)
      + ' · executadas/planejadas por dia · pior aderência primeiro</small></h2>'
      + '<table class="rex-tbl"><tr><th>Cluster</th>' + REX_DIAS.map(d => '<th>' + d + '</th>').join('')
      + '<th>Semana</th></tr>'
      + SW.CL.map(c => {
          const p = pctT(c.f, c.p);
          return '<tr><td class="rex-esq"><b>' + rexEsc(c.cluster) + '</b><br><small>'
            + rexEsc(c.usinas.join(', ').slice(0, 90)) + '</small></td>'
            + REX_DIAS.map(d => {
                const x = c.dias[d];
                if (!x || !x.p) return '<td><span class="gpv-cel nulo">—</span></td>';
                return '<td><span class="gpv-cel ' + rexFx(pctT(x.f, x.p)) + '">' + x.f + '/' + x.p + '</span></td>';
              }).join('')
            + '<td><span class="gpv-cel ' + rexFx(p) + '"><b>' + p + '%</b></span></td></tr>';
        }).join('')
      + '</table></section>';
  }

  // T2 — tarefas do plano da semana ainda em aberto
  if (SW && SW.abertasPlano.length) {
    const ab = SW.abertasPlano.slice(0, 40);
    h += '<section><h2>' + sec('O que ficou em aberto do plano da semana')
      + ' <small>' + rexN(SW.abertasPlano.length) + ' tarefa(s) · ' + rexEsc(SW.label) + '</small></h2>'
      + '<table class="rex-tbl"><tr><th>Cluster</th><th>Usina</th><th>Tarefa</th><th>Tipo</th><th>Dia</th><th>OS</th></tr>'
      + ab.map(x => '<tr><td class="rex-esq">' + rexEsc(x.cluster) + '</td><td class="rex-esq">' + rexEsc(x.usina) + '</td>'
        + '<td class="rex-esq">' + rexEsc(String(x.tarefa || '').replace(/^\[[^\]]*\]\s*-?\s*/, '').slice(0, 50)) + '</td>'
        + '<td>' + rexEsc(x.tipo) + '</td><td>' + x.dia + '</td><td>' + rexEsc(x.os) + '</td></tr>').join('')
      + (SW.abertasPlano.length > 40 ? '<tr class="rex-resto"><td></td><td class="rex-esq" colspan="5">+'
        + (SW.abertasPlano.length - 40) + ' não listadas — a lista completa vai no Excel da semana</td></tr>' : '')
      + '</table></section>';
  }

  // T3 — confiabilidade por usina: top 5 usinas (por falhas) × top 5 ativos
  if (CF && CF.porUsina && CF.porUsina.length) {
    const nf = (v, c) => (+v).toFixed(c).replace('.', ',');
    const topU = CF.porUsina.slice(0, 5);
    const restoU = CF.porUsina.slice(5);
    h += '<section><h2>' + sec('Confiabilidade ativo a ativo — usinas com mais falhas')
      + ' <small>top 5 usinas · top 5 ativos de cada · ordem por nº de falhas</small></h2>';
    topU.forEach(u => {
      const at = u.ativos.slice(0, 5);
      const restoN = u.ativos.slice(5).reduce((s, x) => s + x.n, 0);
      h += '<div class="rex-h3">' + rexEsc(u.usina) + ' <em>· MTBF ' + nf(u.mtbf, 0) + ' h · MTTR '
        + nf(u.mttr, 2) + ' h · Disp. ' + nf(100 * u.disp, 1) + '% · ' + rexN(u.n) + ' falhas</em></div>'
        + '<table class="rex-tbl"><tr><th>Ativo</th><th>Falhas</th><th>MTBF (h)</th><th>MTTR (h)</th><th>Disp. inerente</th></tr>'
        + at.map(x => '<tr><td class="rex-esq">' + rexEsc(String(x.ativo).slice(0, 55)) + '</td><td>' + rexN(x.n) + '</td>'
          + '<td>' + nf(x.mtbf, 0) + '</td><td>' + nf(x.mttr, 2) + '</td>'
          + '<td class="' + (x.disp < 0.9 ? 'rex-red' : '') + '"><b>' + nf(100 * x.disp, 1) + '%</b></td></tr>').join('')
        + (restoN ? '<tr class="rex-resto"><td class="rex-esq">demais ativos (' + (u.ativos.length - 5) + ')</td><td>'
          + rexN(restoN) + '</td><td></td><td></td><td></td></tr>' : '')
        + '</table>';
    });
    if (restoU.length)
      h += '<div class="rex-nota">Demais usinas do recorte (falhas): '
        + restoU.slice(0, 30).map(u => rexEsc(rexUsiCurta(u.usina)) + ' (' + u.n + ')').join(', ')
        + (restoU.length > 30 ? '…' : '') + '.</div>';
    h += '</section>';
  }

  // T4 — tarefas em aberto das usinas críticas (top 5 do ranking)
  const criticas = M.rank.filter(x => x.abertas > 0).slice(0, 5);
  if (criticas.length) {
    h += '<section><h2>' + sec('Usinas críticas — o que está em aberto')
      + ' <small>top 5 do ranking · até 8 tarefas por usina, da mais antiga para a mais nova</small></h2>';
    criticas.forEach(x => {
      h += '<div class="rex-h3">' + rexEsc(x.usina) + ' <em>· ' + rexN(x.abertas) + ' em aberto · mais antiga '
        + (x.maisAntiga || 0) + ' d</em></div>'
        + '<table class="rex-tbl"><tr><th>Tarefa</th><th>Tipo</th><th>Aberta há</th><th>OS</th></tr>'
        + x.tarefas.slice(0, 8).map(t => '<tr><td class="rex-esq">'
          + rexEsc(String(t.tarefa || '').replace(/^\[[^\]]*\]\s*-?\s*/, '').slice(0, 60)) + '</td>'
          + '<td>' + rexEsc(t.tipo) + '</td><td>' + ((t.dias || 0) + ' d') + '</td><td>' + rexEsc(t.os) + '</td></tr>').join('')
        + (x.abertas > 8 ? '<tr class="rex-resto"><td class="rex-esq" colspan="4">+' + (x.abertas - 8) + ' tarefas não listadas</td></tr>' : '')
        + '</table>';
    });
    h += '</section>';
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
    + ' · corretivas contadas por OS distinta · concluído = tarefa Finalizada (nunca o Status da OS) · '
    + 'tarefas de OS já concluída não contam como abertas · Grid Co. — PCM</footer>'
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
