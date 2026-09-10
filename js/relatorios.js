/* Relatórios sob demanda — tela "Relatórios" do painel (novo.html).
   Monta no navegador, com os JSON que o painel já serve, os mesmos quatro relatórios que o
   robô manda por e-mail (relatorio_diario.py / relatorios_semana.py): Diário, Recuperação da
   tarde, Fechamento da semana e Alerta da programação. Regras iguais às do Python — quando
   mudar lá, mudar aqui. "Imprimir / PDF" usa a impressão do navegador, como o FMEA.
   Só regras fixas — nada de IA. Aprovado por mockup em 10/09/2026. */
(function () {
  "use strict";
  const META = 85, HH_DIA = 8.8, HORA_CORTE_MANHA = 12;
  const TIPOS_NAO_PROG = ["Corretiva", "Corretiva Emergencial", "Religamento", "Religamento Remoto"];
  const DIAS_PT = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"];
  const DIAS_KEY = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"];
  const CAT = { campo: "em campo", remoto: "remoto (COS)", queda: "queda de energia", emergencial: "emergencial", programado: "programado" };
  const CAT_D = { campo: "Em campo", remoto: "Remoto (COS)", queda: "Queda de energia", emergencial: "Emergencial", programado: "Programado" };

  const h = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pct = (a, b) => b ? 100 * a / b : 0;
  const n = v => Math.round(v || 0).toLocaleString("pt-BR");
  const f1 = v => (v || 0).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const f0 = v => Math.round(v || 0).toLocaleString("pt-BR");
  const cor = p => p >= META ? "ok" : p >= 70 ? "mid" : "mal";
  const cel = p => `<span class="cel ${cor(p)}">${Math.round(p)}%</span>`;
  const fin = x => x.status === "Finalizados";
  const andando = x => x.status === "Em progresso" || x.status === "pausado";
  const usinaCurta = u => (u || "").replace(/^[^-]+ - /, "").replace(/ - [^-]*$/, "");
  const tarefaCurta = t => (t || "").replace(/^\[.*?\]\s*-?\s*/, "");
  const janelaOk = x => /^\d\d/.test(x.h_fim || "") && parseInt(x.h_fim.slice(0, 2), 10) < 24;
  const hh = x => (x.duracao || 0) + (x.desloc || 0);
  const mins = s => { const m = /^(\d+):(\d+)/.exec(String(s || "")); return m ? +m[1] * 60 + +m[2] : null; };
  const horaIni = x => { const m = /^(\d\d)/.exec(x.h_ini || ""); return m ? +m[1] : 99; };
  const norm = s => String(s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const iso = d => d.toISOString().slice(0, 10);
  const dataDe = s => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s || "")); return m ? new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])) : null; };
  const addDias = (d, k) => new Date(d.getTime() + k * 86400000);
  const ddmm = d => `${String(d.getUTCDate()).padStart(2, "0")}/${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
  const ddmmaaaa = d => `${ddmm(d)}/${d.getUTCFullYear()}`;
  const wd = d => (d.getUTCDay() + 6) % 7;                       // 0 = segunda
  function isoSemana(d) {                                       // "AAAA-Wnn"
    const t = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
    const dia = t.getUTCDay() || 7; t.setUTCDate(t.getUTCDate() + 4 - dia);
    const a1 = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
    return `${t.getUTCFullYear()}-W${String(Math.ceil(((t - a1) / 86400000 + 1) / 7)).padStart(2, "0")}`;
  }
  function segundaDe(week) {                                    // segunda-feira da semana ISO
    const [a, w] = week.split("-W").map(Number);
    const j4 = new Date(Date.UTC(a, 0, 4)); const seg1 = addDias(j4, -((j4.getUTCDay() + 6) % 7));
    return addDias(seg1, (w - 1) * 7);
  }
  const conta = (arr, f) => { const c = new Map(); for (const x of arr) { const k = f(x); c.set(k, (c.get(k) || 0) + 1); } return [...c.entries()].sort((a, b) => b[1] - a[1]); };
  const agrupa = (arr, f) => { const g = new Map(); for (const x of arr) { const k = f(x); if (!g.has(k)) g.set(k, []); g.get(k).push(x); } return g; };
  const tabela = (linhas, cab, cols, vazio) => !linhas.length ? `<div class="vazio">${h(vazio || "nada a listar")}</div>`
    : `<table><thead><tr>${cab.map(([t, c]) => `<th class="${c}">${t}</th>`).join("")}</tr></thead><tbody>${linhas.map(l => `<tr>${l.map((v, i) => `<td class="${cols[i] || ""}">${v}</td>`).join("")}</tr>`).join("")}</tbody></table>`;

  // ── folha (CSS igual ao Python; vira .rp-folha no painel e body na nova aba) ──
  const CSS_FOLHA = `
.pg{page-break-after:always}.pg:last-child{page-break-after:auto}
.top{display:flex;align-items:flex-start;gap:14px;padding-bottom:8px;margin-bottom:9px;border-bottom:3px solid #191528}
.top.verde{border-bottom-color:#A9DB21}.top.laranja{border-bottom-color:#c2410c}.top.ambar{border-bottom-color:#a04408}
.top .logo{height:20px;width:auto;display:block;margin-top:4px}.top .t{flex:1;min-width:0}
.top h1{margin:0;font-size:15pt;font-weight:800;white-space:nowrap}.top .s{font-size:9pt;color:#68667d;white-space:nowrap}
.top .d{text-align:right;font-size:9pt;color:#3a3550;white-space:nowrap}.top .d b{display:block;font-size:12pt;color:#191528}
.kpis{display:grid;gap:6px;margin:8px 0 9px}.kpi{border:1px solid #e4e4ef;border-left:3px solid #cbcbdd;border-radius:6px;padding:5px 8px}
.kpi.g{border-left-color:#A9DB21}.kpi.r{border-left-color:#c2410c}.kpi.m{border-left-color:#a04408}
.kpi .v{font-size:14pt;font-weight:800;line-height:1.05}.kpi .n{font-size:7.8pt;color:#68667d;text-transform:uppercase;letter-spacing:.04em;margin-top:2px}.kpi .m{font-size:8pt;color:#68667d}
.sec{margin:8px 0 4px;font-size:8.5pt;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:#68667d;display:flex;align-items:center;gap:8px}.sec::after{content:"";flex:1;height:1px;background:#e4e4ef}
table{width:100%;border-collapse:collapse;font-size:8.4pt;min-width:0}td,th{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:230px}td.quebra{white-space:normal;max-width:none}
th{text-align:left;font-size:7.4pt;text-transform:uppercase;letter-spacing:.04em;color:#68667d;padding:3px 6px;border-bottom:1px solid #cbcbdd;background:#f6f7fa}
td{padding:2.4px 6px;border-bottom:1px solid #eceef4;vertical-align:top;color:#191528}.r{text-align:right}th.r{text-align:right}.mono{font-family:Consolas,monospace;font-size:8.8pt}
.cel{display:inline-block;min-width:38px;text-align:center;padding:1px 5px;border-radius:4px;font-weight:700}.cel.ok{background:#e3f6ea;color:#1f7a4d}.cel.mid{background:#fdf0d5;color:#a04408}.cel.mal{background:#fde2e2;color:#b02525}
.est{font-size:7.6pt;padding:1px 5px;border-radius:3px;background:#f0f0f6;color:#3a3550}.est.pausado{background:#fdf0d5;color:#a04408}.est.em{background:#e6efff;color:#1d4ed8}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:12px}.g2b{display:grid;grid-template-columns:1.25fr 1fr;gap:12px}.g3{display:grid;grid-template-columns:1.1fr 1fr 1fr;gap:12px}
.ins{margin:0;padding-left:16px}.ins li{margin:2.5px 0;font-size:9.1pt}
.bars{display:flex;gap:10px;align-items:flex-end;height:80px;padding:4px 6px 0}.bar{flex:1;display:flex;flex-direction:column;align-items:center;gap:3px;height:100%}.bar .col{flex:1;width:100%;display:flex;gap:2px;align-items:flex-end;justify-content:center}
.bar .col i,.bar .col b{display:block;width:14px;border-radius:2px 2px 0 0}.bar .col i{background:#cbcbdd}.bar .col b{background:#191528}.bar span{font-size:8.5pt;font-weight:700}.bar small{display:block;font-weight:400;color:#68667d;font-size:7.5pt}.bar.fut{opacity:.45}
.nota{background:#fbfbe8;border-left:3px solid #A9DB21;padding:5px 9px;font-size:8.6pt;color:#3a3550;margin-top:5px}.nota.aviso{background:#fdf0d5;border-left-color:#c2410c}
.pe{margin-top:9px;border-top:1px solid #e4e4ef;padding-top:6px;font-size:7.8pt;color:#68667d;display:flex;justify-content:space-between;gap:10px}
.al{color:#b02525;font-weight:700}.cinza{color:#68667d}.vazio{color:#68667d;font-size:8.6pt;padding:3px 2px}.chips{font-size:9.5pt;color:#3a3550;margin:2px 0 6px}
.al-bloco{border:1px solid #e4e4ef;border-radius:6px;padding:5px 9px;margin:5px 0;break-inside:avoid}
.al-cab{display:flex;align-items:center;gap:8px;font-size:9.6pt}.al-txt{font-size:8.3pt;color:#3a3550;margin:1px 0 3px}
.sev{font-size:7.3pt;font-weight:800;text-transform:uppercase;letter-spacing:.05em;padding:1px 6px;border-radius:3px}.sev.mal{background:#fde2e2;color:#b02525}.sev.mid{background:#fdf0d5;color:#a04408}.sev.ok{background:#e3f6ea;color:#1f7a4d}
i.ab{font-style:normal;color:#b02525;font-weight:700;font-size:8pt}`;
  const cssPrefixada = pref => CSS_FOLHA.replace(/(^|\})\s*([^{}]+)\{/g, (m, a, sel) => a + sel.split(",").map(s => pref + " " + s.trim()).join(",") + "{");

  function logoHtml() {
    const img = document.querySelector(".marca-img");
    return img ? `<img class="logo" src="${img.src}" alt="Grid Co.">` : '<div class="logo-txt">Grid Co.</div>';
  }

  // ── estado ──
  const RP = { estado: "vazio", erro: "", bd: null, g: null, ger: null, eng: null, op: null, idx: null, fer: [],
    tipo: "diario", dia: "", semana: "", cliente: "", cluster: "", html: "", titulo: "", gerado: null };

  async function pegar(nome, opcional) {
    try { const r = await fetch(nome + "?t=" + Date.now(), { cache: "no-store" }); if (r.ok) return await r.json(); if (opcional) return null; throw new Error("HTTP " + r.status + " em " + nome); }
    catch (e) { if (opcional) return null; throw e; }
  }
  async function carregar() {
    if (RP.estado === "carregando" || RP.estado === "pronto") return;
    RP.estado = "carregando"; window.pintar && window.pintar();
    try {
      [RP.bd, RP.g, RP.ger, RP.eng, RP.op, RP.idx, RP.fer] = await Promise.all([
        pegar("banco_dados.json"), pegar("gestao_pcm.json"), pegar("gerencial.json", true), pegar("engenharia.json", true),
        pegar("operacoes.json", true), pegar("relatorios/indice.json", true), pegar("relatorios/feriados.json", true)]);
      RP.ger = RP.ger || { usinas: [], eventos: [] }; RP.eng = RP.eng || { ativos: [], kpi: {} }; RP.op = RP.op || { usinas: [], clusters: [] }; RP.fer = RP.fer || [];
      const hoje = new Date(); const ontem = addDias(new Date(Date.UTC(hoje.getFullYear(), hoje.getMonth(), hoje.getDate())), -1);
      RP.dia = iso(ontem); RP.semana = RP.bd.semana_ativa || (RP.bd.semanas[0] || {}).week || isoSemana(ontem);
      RP.estado = "pronto";
    } catch (e) { RP.estado = "erro"; RP.erro = e.message; }
    window.pintar && window.pintar();
  }

  // ── recorte por cliente / cluster ──
  function rowsDe(w) {
    let r = (w && w.rows) || [];
    if (RP.cliente) r = r.filter(x => (x.cliente || "") === RP.cliente);
    if (RP.cluster) r = r.filter(x => (x.cluster || "") === RP.cluster || (x.responsavel || "") === RP.cluster);
    return r;
  }
  function tarefasG() {
    let t = RP.g.tarefas || [];
    if (RP.cliente) t = t.filter(x => (x.cliente || "") === RP.cliente);
    if (RP.cluster) t = t.filter(x => (x.cluster || "") === RP.cluster || (x.responsavel || "") === RP.cluster);
    return t;
  }
  function eventosGer() {
    const U = RP.ger.usinas || [];
    let e = RP.ger.eventos || [];
    if (RP.cliente) e = e.filter(x => ((U[x.u] || {}).cliente || "") === RP.cliente);
    if (RP.cluster) e = e.filter(x => ((U[x.u] || {}).cluster || "") === RP.cluster || (RP.op.usinas || []).some(u => u.usina === (U[x.u] || {}).usina && (u.cluster === RP.cluster || u.responsavel === RP.cluster)));
    return e;
  }
  const semanaDo = d => (RP.bd.semanas || []).find(w => w.week === isoSemana(d));
  const recorte = () => (RP.cliente ? " · " + RP.cliente : "") + (RP.cluster ? " · " + RP.cluster : "");

  // ═══════════════ DIÁRIO ═══════════════
  function diario(dia) {
    const w = semanaDo(dia); const nome = DIAS_PT[wd(dia)]; const avisos = [];
    let todos = [];
    if (w) { const esp = ddmm(dia); if ((w.dates || {})[DIAS_KEY[wd(dia)]] && w.dates[DIAS_KEY[wd(dia)]] !== esp) avisos.push(`a semana ${w.week} do banco não bate com a data ${esp}`); todos = rowsDe(w).filter(r => String(r.dia || "").toLowerCase().startsWith(nome.slice(0, 3).toLowerCase())); }
    else avisos.push(`o banco não tem a semana de ${ddmm(dia)} — aderência fica sem dado`);
    const rows = todos.filter(r => !r.foraDoPlano), foraPlano = todos.length - rows.length;
    const prog = rows.length, fim = rows.filter(fin).length, and_ = rows.filter(andando).length, nao = prog - fim - and_;
    const bloco = f => [...agrupa(rows, r => f(r) || "—").entries()].map(([k, L]) => [k, L.length, L.filter(fin).length, L.filter(andando).length, L.filter(r => r.reprog === "Sim").length]).sort((a, b) => b[1] - a[1]);
    const cli = bloco(r => r.cliente), resp = bloco(r => r.responsavel);
    const naoFeitas = rows.filter(r => !fin(r));
    const semana = w ? DIAS_PT.slice(0, 5).map((d, i) => { const rs = rowsDe(w).filter(r => r.dia === d && !r.foraDoPlano); return [d.slice(0, 3), rs.length, rs.filter(fin).length, i > wd(dia)]; }) : [];
    const ds = iso(dia); const T = tarefasG();
    const cri = T.filter(t => (t.criacao || "").slice(0, 10) === ds && TIPOS_NAO_PROG.includes(t.tipo));
    const naoProg = { n: cri.length, tipos: conta(cri, t => t.tipo), clientes: conta(cri, t => t.cliente || "—"), lista: cri };
    const criadasTotal = T.filter(t => (t.criacao || "").slice(0, 10) === ds).length, finGestao = T.filter(t => (t.dataFinal || "").slice(0, 10) === ds).length;
    const backlog = RP.cliente || RP.cluster ? { abertas: T.filter(t => t.aberta).length, atrasadas: T.filter(t => t.aberta && t.atrasado).length } : { abertas: RP.g.totalAbertas || 0, atrasadas: RP.g.totalAtrasadas || 0 };
    const U = RP.ger.usinas || []; const ev = eventosGer();
    const relig = ev.filter(e => (e.ini || "").slice(0, 10) === ds).map(e => ({ os: e.os, cat: e.cat, usina: (U[e.u] || {}).usina || e.ativo || "", regiao: (U[e.u] || {}).regiao || "", hDia: e.hDia }));
    const relig7 = []; for (let i = 7; i >= 1; i--) { const k = iso(addDias(dia, -i)); relig7.push(ev.filter(e => (e.ini || "").slice(0, 10) === k).length); }
    const criticos = (RP.eng.ativos || []).filter(a => a.nivel === "critico"), sinal = (RP.eng.kpi || {}).ativosSinal || 0;
    const D = { dia, w, avisos, rows, foraPlano, prog, fim, and_, nao, cli, resp, naoFeitas, semana, naoProg, criadasTotal, finGestao, backlog, relig, relig7, criticos, sinal,
      semanaLabel: (w && w.label) || `Semana ${isoSemana(dia).slice(-2)}`, semanaNum: isoSemana(dia).slice(-2) };
    D.ins = analiseDiario(D);
    return D;
  }
  function analiseDiario(D) {
    const ader = pct(D.fim, D.prog), hrel = D.relig.reduce((s, r) => s + (r.hDia || 0), 0), med7 = D.relig7.reduce((a, b) => a + b, 0) / 7, ins = [];
    if (D.prog) ins.push(`<b>Aderência de ${Math.round(ader)}% no dia</b> — ${n(D.fim)} das ${n(D.prog)} OS programadas finalizadas, ${ader >= META ? "acima" : "abaixo"} da meta de ${META}%. ${n(D.nao)} não iniciadas e ${n(D.and_)} em andamento passam para hoje.` + (D.foraPlano ? ` Fora do plano, a equipe ainda fechou ${n(D.foraPlano)} tarefas que não estavam programadas.` : ""));
    else ins.push("<b>Sem OS programadas para o dia</b> na Programação Semanal — o relatório traz só o que entrou e os religamentos.");
    const tipos = D.naoProg.tipos.map(([t, c]) => `<b>${n(c)}</b> ${h(t)}`).join(" · ") || "nenhuma";
    if (D.naoProg.n) { const cl = D.naoProg.clientes[0]; ins.push(`<b>${n(D.naoProg.n)} OS não programadas entraram</b> (${tipos}). ${h(cl[0])} concentra ${n(cl[1])} delas. Cada uma compete com a programação de hoje pelo mesmo HH.`); }
    else ins.push("<b>Nenhuma OS não programada entrou</b> no dia.");
    if (D.relig.length || med7) { const tom = D.relig.length < med7 * 0.7 ? "Dia mais calmo que a semana." : D.relig.length > med7 * 1.3 ? "Dia acima do padrão da semana." : "Dentro do padrão da semana."; ins.push(`<b>Religamentos: ${n(D.relig.length)} no dia</b> (${f1(hrel)} h diurnas de parada), contra média de ${f0(med7)}/dia nos 7 dias anteriores. ${tom}`); }
    const clOk = D.cli.filter(r => r[1] >= 10), rsOk = D.resp.filter(r => r[1] >= 10 && r[0] !== "—");
    if (clOk.length) { const pc = clOk.reduce((a, b) => pct(b[2], b[1]) < pct(a[2], a[1]) ? b : a); let fr = `<b>${h(pc[0])} teve a menor aderência entre os clientes</b> (${Math.round(pct(pc[2], pc[1]))}% de ${n(pc[1])})`; if (rsOk.length) { const pr = rsOk.reduce((a, b) => pct(b[2], b[1]) < pct(a[2], a[1]) ? b : a); fr += `; por supervisor, ${h(pr[0])} (${Math.round(pct(pr[2], pr[1]))}% de ${n(pr[1])})`; } ins.push(fr + "."); }
    const saldo = D.criadasTotal - D.finGestao;
    ins.push(`<b>Backlog segue em ${n(D.backlog.atrasadas)} tarefas atrasadas</b> de ${n(D.backlog.abertas)} abertas. No dia o Gestão PCM registrou ${n(D.criadasTotal)} tarefas criadas e ${n(D.finGestao)} finalizadas — saldo ${saldo > 0 ? "+" : ""}${n(saldo)}.`);
    const crit = D.criticos.slice(0, 2).map(a => `${h(a.nome)} (${h(a.usina)}, ${a.nFalha} falhas)`).join("; ");
    ins.push(`<b>${n(D.sinal)} ativos com sinal de recorrência</b>, ${n(D.criticos.length)} crítico(s)${crit ? ": " + crit : ""}. Estão no módulo Confiabilidade, com ticket.`);
    return ins;
  }
  function htmlDiario(D, gerado) {
    const ader = pct(D.fim, D.prog), hrel = D.relig.reduce((s, r) => s + (r.hDia || 0), 0), med7 = D.relig7.reduce((a, b) => a + b, 0) / 7, logo = logoHtml();
    const tit = `${DIAS_PT[wd(D.dia)]}, ${ddmmaaaa(D.dia)}`;
    const cli = D.cli.slice(0, 8).map(([k, p, f, a]) => [h(k), n(p), n(f), n(a), n(p - f - a), cel(pct(f, p))]);
    const resp = D.resp.slice(0, 7).map(([k, p, f, a, rp]) => [h(k === "—" ? "sem responsável no BD" : k), n(p), n(f), n(rp), cel(pct(f, p))]);
    const tiposNp = D.naoProg.tipos.map(([t, c]) => `<b>${n(c)}</b> ${h(t)}`).join(" · ") || "nenhuma no dia";
    const listaNp = D.naoProg.lista.slice(0, 8).map(t => [`#${h(t.os)}`, h((t.tipo || "").replace("Religamento Remoto", "Relig. remoto")), h(usinaCurta(t.usina).slice(0, 22)), h(tarefaCurta(t.tarefa).slice(0, 30)), h(t.cluster)]);
    const listaRel = D.relig.slice(0, 8).map(r => [`#${h(r.os)}`, h(CAT_D[r.cat] || r.cat), h((r.usina || "").slice(0, 18)) + ` <span class="cinza">· ${h(r.regiao)}</span>`, r.hDia == null ? '<i class="ab">aberta</i>' : `${f1(r.hDia)} h`]);
    const mx = Math.max(1, ...D.semana.map(s => s[1]));
    const barras = D.semana.map(([d, p, f, fut]) => `<div class="bar${fut ? " fut" : ""}"><div class="col"><i style="height:${Math.round(100 * p / mx)}%"></i><b style="height:${Math.round(100 * f / mx)}%"></b></div><span>${d}<small>${n(f)}/${n(p)}</small></span></div>`).join("");
    const naoFeitas = D.naoFeitas.slice(0, 8).map(r => [`#${h(r.os_id)}`, h((r.tarefa || "").slice(0, 44)), h(r.cliente), h(r.cluster), h(r.status)]);
    const totSem = D.semana.reduce((s, x) => s + x[1], 0); let notaSem = "";
    if (D.semana.length && totSem) { const m = D.semana.reduce((a, b) => b[1] > a[1] ? b : a); if (pct(m[1], totSem) >= 35) notaSem = `<div class="nota">${h(m[0])} concentra ${n(m[1])} programadas — ${Math.round(pct(m[1], totSem))}% da semana num só dia. Vale nivelar na próxima programação.</div>`; }
    const mais = (tot, k) => tot > k ? ` <span class="cinza">(+${n(tot - k)} no painel)</span>` : "";
    const saldo = D.criadasTotal - D.finGestao;
    const avisos = D.avisos.map(a => `<div class="nota aviso">${h(a)}</div>`).join("");
    return `<div class="pg">
<div class="top verde">${logo}<div class="t"><h1>Relatório diário de manutenção</h1><div class="s">Grid Co. · Operação de Ativos · o que aconteceu no dia${h(recorte())}</div></div>
  <div class="d"><b>${tit}</b>gerado ${ddmm(gerado)} às ${String(gerado.getUTCHours()).padStart(2, "0")}:${String(gerado.getUTCMinutes()).padStart(2, "0")} · uso interno (PCM e engenharia)</div></div>${avisos}
<div class="kpis" style="grid-template-columns:repeat(6,1fr)">
  <div class="kpi g"><div class="v">${D.prog ? Math.round(ader) + "%" : "—"}</div><div class="n">Aderência do dia</div><div class="m">${n(D.fim)} de ${n(D.prog)} programadas · +${n(D.foraPlano)} fora do plano</div></div>
  <div class="kpi"><div class="v">${n(D.nao + D.and_)}</div><div class="n">Passam para hoje</div><div class="m">${n(D.nao)} não iniciadas · ${n(D.and_)} em andamento</div></div>
  <div class="kpi r"><div class="v">${n(D.naoProg.n)}</div><div class="n">Não programadas geradas</div><div class="m">corretivas e religamentos</div></div>
  <div class="kpi"><div class="v">${n(D.relig.length)}</div><div class="n">Religamentos</div><div class="m">${f1(hrel)} h diurnas · média 7 d: ${f0(med7)}/dia</div></div>
  <div class="kpi r"><div class="v">${n(D.backlog.atrasadas)}</div><div class="n">Backlog atrasado</div><div class="m">de ${n(D.backlog.abertas)} abertas · saldo do dia ${saldo > 0 ? "+" : ""}${n(saldo)}</div></div>
  <div class="kpi"><div class="v">${n(D.sinal)}</div><div class="n">Ativos com sinal</div><div class="m">${n(D.criticos.length)} crítico(s) no Confiabilidade</div></div>
</div>
<div class="sec">Programação do dia — por cliente</div>
${tabela(cli, [["Cliente", ""], ["Programadas", "r"], ["Finalizadas", "r"], ["Em andamento", "r"], ["Não iniciadas", "r"], ["Aderência", "r"]], ["", "r", "r", "r", "r", "r"], "sem OS programadas para este dia")}
<div class="g2b"><div><div class="sec">Não programadas geradas no dia${mais(D.naoProg.lista.length, 8)}</div><div class="chips">${tiposNp}</div>
  ${tabela(listaNp, [["OS", ""], ["Tipo", ""], ["Usina", ""], ["Tarefa", ""], ["Cluster", ""]], ["mono", "", "", "", ""], "nenhuma OS não programada criada no dia")}</div>
  <div><div class="sec">Religamentos do dia${mais(D.relig.length, 8)}</div>
  ${tabela(listaRel, [["OS", ""], ["Como resolveu", ""], ["Usina · região", ""], ["Parada", "r"]], ["mono", "", "", "r"], "nenhum religamento no dia")}
  <div class="nota">Parada = horas diurnas (6h–18h) entre o incidente e o fim da tarefa. "aberta" = ainda sem data final na geração.</div></div></div>
<div class="sec">Análise gerencial do dia</div><ul class="ins">${D.ins.map(x => `<li>${x}</li>`).join("")}</ul>
<div class="pe"><span>Página 1 de 2 · Relatório gerado pela plataforma PCM · pcm.gridco.com.br</span><span>Fontes: Programação Semanal S${D.semanaNum}, Gestão PCM, Confiabilidade e Gerencial (Fracttal via robô)</span></div></div>
<div class="pg">
<div class="top verde">${logo}<div class="t"><h1>Detalhe do dia</h1><div class="s">por supervisor, semana até aqui e o que ficou para hoje</div></div><div class="d"><b>${tit}</b>página 2 de 2</div></div>
<div class="g2"><div><div class="sec">Por supervisor (Responsável O&amp;M)</div>
  ${tabela(resp, [["Supervisor", ""], ["Prog.", "r"], ["Final.", "r"], ["Reprog.", "r"], ["Aderência", "r"]], ["", "r", "r", "r", "r"], "sem OS programadas para este dia")}
  ${D.resp.some(r => r[0] === "—") ? '<div class="nota">"sem responsável no BD" são OS cujo cluster não tem Responsável O&amp;M preenchido no BD_Operacoes — cadastro, não execução.</div>' : ""}</div>
  <div><div class="sec">${h(D.semanaLabel)} — programadas × finalizadas</div><div class="bars">${barras || '<div class="vazio">semana sem programação carregada</div>'}</div>${notaSem}</div></div>
<div class="sec">O que ficou para hoje — programadas do dia não finalizadas (${n(D.prog - D.fim)})${mais(D.naoFeitas.length, 8)}</div>
${tabela(naoFeitas, [["OS", ""], ["Tarefa", ""], ["Cliente", ""], ["Cluster", ""], ["Estado", ""]], ["mono", "", "", "", ""], "tudo que estava programado foi finalizado")}
<div class="nota">Lista completa e o motivo de cada rolagem no painel → Semana → filtro "não finalizadas". O cliente não recebe este relatório — ele vê o resultado, não o processo.</div>
<div class="sec">Ativos críticos no Confiabilidade</div><ul class="ins">${D.criticos.map(a => `<li><b>${h(a.nome)}</b> — ${h(a.usina)} · ${a.nFalha} falhas em 30 dias · ver ticket no painel</li>`).join("") || "<li>nenhum crítico hoje</li>"}</ul>
<div class="pe"><span>Página 2 de 2 · Responder este e-mail não registra nada — assuma tickets e justifique rolagens no painel.</span><span>Aderência = finalizadas ÷ programadas do dia. Não programadas = OS criadas no dia dos tipos Corretiva, Corretiva Emergencial, Religamento e Religamento Remoto.</span></div></div>`;
  }

  // ═══════════════ RECUPERAÇÃO DA TARDE ═══════════════
  function matinal(dia) {
    const w = semanaDo(dia); const nome = DIAS_PT[wd(dia)]; const avisos = [];
    let todos = [];
    if (w) todos = rowsDe(w).filter(r => String(r.dia || "").toLowerCase().startsWith(nome.slice(0, 3).toLowerCase())); else avisos.push(`o banco não tem a semana de ${ddmm(dia)} — sem programação para comparar`);
    const rows = todos.filter(r => !r.foraDoPlano), foraPlano = todos.length - rows.length;
    const manha = rows.filter(r => horaIni(r) < HORA_CORTE_MANHA), tarde = rows.filter(r => horaIni(r) >= HORA_CORTE_MANHA && horaIni(r) < 24), fora = rows.filter(r => horaIni(r) >= 24 || !janelaOk(r));
    const pend = manha.filter(r => !fin(r));
    const HH = L => L.filter(janelaOk).reduce((s, r) => s + hh(r), 0);
    const grp = agrupa(pend, r => r.os_id); for (const L of grp.values()) L.sort((a, b) => (a.h_ini || "").localeCompare(b.h_ini || ""));
    const os = [...grp.entries()].sort((a, b) => Math.max(...b[1].map(r => r.vezes || 1)) - Math.max(...a[1].map(r => r.vezes || 1)) || (a[1][0].h_ini || "").localeCompare(b[1][0].h_ini || ""));
    const reincid = os.filter(([, L]) => Math.max(...L.map(r => r.vezes || 1)) >= 3).length;
    const nomes = [...new Set([...manha, ...tarde].map(r => r.responsavel || "—"))].sort();
    const resp = nomes.map(nm => { const m = manha.filter(r => (r.responsavel || "—") === nm), p = pend.filter(r => (r.responsavel || "—") === nm), t = tarde.filter(r => (r.responsavel || "—") === nm); return [nm, m.length, m.length - p.length, p.length, HH(p), HH(t)]; }).sort((a, b) => b[3] - a[3]);
    const ds = iso(dia); const npg = tarefasG().filter(t => (t.criacao || "").slice(0, 10) === ds && TIPOS_NAO_PROG.includes(t.tipo));
    const D = { dia, avisos, foraPlano, totalDia: rows.length, manha, tarde, fora, pend, hhPend: HH(pend), hhTarde: HH(tarde), os, reincid, resp, naoProg: { n: npg.length, tipos: conta(npg, t => t.tipo) },
      cluster: conta(pend, r => r.cluster || "—"), cliente: conta(pend, r => r.cliente || "—"), HH };
    D.ins = analiseMatinal(D); return D;
  }
  function analiseMatinal(D) {
    const m = D.manha.length, p = D.pend.length, feitas = m - p, carga = D.hhPend + D.hhTarde, ins = [];
    if (!m) return ["<b>Sem tarefas programadas para a manhã de hoje</b> na Programação Semanal — nada a recuperar."];
    ins.push(`<b>A manhã fechou ${Math.round(pct(feitas, m))}%</b> — ${n(feitas)} das ${n(m)} tarefas programadas até ${String(HORA_CORTE_MANHA).padStart(2, "0")}:00 estão finalizadas no Fracttal. Restam <b>${n(p)} tarefas em ${n(D.os.length)} OS</b>, somando ${f0(D.hhPend)} h de execução.`);
    if (p) {
      const aperto = D.hhPend > 0 ? (carga > 2 * Math.max(D.hhTarde, 1) ? "muito acima" : "acima") : "dentro";
      ins.push(`<b>A tarde já tem ${n(D.tarde.length)} tarefas programadas</b> (${f0(D.hhTarde)} h). Somando o que ficou da manhã, a carga da tarde vai a <b>${f0(carga)} h</b> — ${aperto} do que o dia comporta. A lista acima está ordenada por quem rolou mais vezes.`);
      if (D.reincid) ins.push(`<b>${n(D.reincid)} OS já rolaram 3 vezes ou mais</b> e estão pendentes de novo. São as que devem furar a fila da tarde — cada nova rolagem empurra a OS para a semana seguinte.`);
      const cli = D.cliente[0] || ["—", 0], cl = D.cluster[0] || ["—", 0], tipos = D.naoProg.tipos.map(([t, c]) => `<b>${n(c)}</b> ${h(t)}`).join(" · ") || "nenhuma";
      ins.push(`<b>${h(cli[0])} concentra ${n(cli[1])} das pendências</b> e o cluster ${h(cl[0])} tem ${n(cl[1])}. Hoje entraram ainda ${n(D.naoProg.n)} OS não programadas (${tipos}), que disputam o mesmo HH da tarde.`);
      ins.push("<b>Atenção ao apontamento:</b> uma tarefa feita e não fechada no Fracttal aparece aqui como pendente. Se a lista tiver OS já executadas, o problema é de fechamento — e resolvê-lo é mais rápido que reprogramar.");
    } else ins.push("<b>Nenhuma pendência da manhã</b> — tudo que estava programado até o meio-dia está fechado no Fracttal.");
    return ins;
  }
  function htmlMatinal(D, gerado) {
    const m = D.manha.length, p = D.pend.length, carga = D.hhPend + D.hhTarde, logo = logoHtml(), LIN = 12;
    const curto = nm => (nm && nm !== "—" && nm.split(" ").length > 1) ? nm.split(" ")[0] + " " + nm.split(" ").pop()[0] + "." : (nm || "—");
    const linhas = D.os.slice(0, LIN).map(([os, L]) => { const r = L[0], v = Math.max(...L.map(x => x.vezes || 1)); const est = L.some(x => x.status === "pausado") ? "pausado" : L.some(x => x.status === "Em progresso") ? "em progresso" : "não iniciada";
      return [`#${h(os)}`, h(r.h_ini), h(usinaCurta(r.usina).slice(0, 20)), h(tarefaCurta(r.tarefa).slice(0, 32)) + (L.length > 1 ? ` <span class="cinza">+${L.length - 1}</span>` : ""), h(curto(r.responsavel)), `${f1(D.HH(L))} h`, v >= 3 ? `<b class="al">${v}ª</b>` : `${v}ª`, `<span class="est ${est.split(" ")[0]}">${est}</span>`]; });
    const resp = D.resp.slice(0, 8).map(([nm, qm, qf, qp, hp, ht]) => [h(nm === "—" ? "sem responsável no BD" : nm), n(qm), n(qf), n(qp), `${f0(hp)} h`, `${f0(ht)} h`, `<span class="cel ${hp + ht > 40 ? "mal" : hp + ht > 25 ? "mid" : "ok"}">${f0(hp + ht)} h</span>`]);
    const resto = D.os.length - LIN; let aviso = "";
    if (D.fora.length) aviso += `<div class="nota aviso">${n(D.fora.length)} tarefa(s) com janela impossível na programação (fim depois da meia-noite) ficaram fora da conta de HH: ${[...new Set(D.fora.map(r => "#" + r.os_id))].sort().slice(0, 6).join(", ")}. Vale corrigir a duração no plano.</div>`;
    aviso += D.avisos.map(a => `<div class="nota aviso">${h(a)}</div>`).join("");
    const hm = `${String(gerado.getUTCHours()).padStart(2, "0")}:${String(gerado.getUTCMinutes()).padStart(2, "0")}`;
    return `<div class="top laranja">${logo}<div class="t"><h1>Recuperação da tarde</h1><div class="s">Grid Co. · o programado para a manhã que ainda não fechou${h(recorte())}</div></div>
  <div class="d"><b>${DIAS_PT[wd(D.dia)]}, ${ddmmaaaa(D.dia)}</b>corte às ${hm} · uso interno (PCM, supervisores e engenharia)</div></div>
<div class="kpis" style="grid-template-columns:repeat(5,1fr)">
  <div class="kpi"><div class="v">${n(m)}</div><div class="n">Programadas na manhã</div><div class="m">de ${n(D.totalDia)} no dia · +${n(D.foraPlano)} fora do plano</div></div>
  <div class="kpi g"><div class="v">${n(m - p)}</div><div class="n">Fechadas</div><div class="m">${Math.round(pct(m - p, m))}% da manhã</div></div>
  <div class="kpi r"><div class="v">${n(p)}</div><div class="n">Pendentes</div><div class="m">em ${n(D.os.length)} OS · ${f0(D.hhPend)} h</div></div>
  <div class="kpi"><div class="v">${n(D.tarde.length)}</div><div class="n">Já na tarde</div><div class="m">${f0(D.hhTarde)} h a partir das ${String(HORA_CORTE_MANHA).padStart(2, "0")}:00</div></div>
  <div class="kpi r"><div class="v">${f0(carga)} h</div><div class="n">Carga da tarde</div><div class="m">pendente + programado</div></div></div>
<div class="sec">Prioridade de recuperação — OS da manhã ainda abertas</div>
${tabela(linhas, [["OS", ""], ["Hora", ""], ["Usina", ""], ["Tarefa", ""], ["Responsável", ""], ["Execução", "r"], ["Rolagem", "r"], ["Estado", ""]], ["mono", "mono", "", "", "", "r", "r", ""], "nenhuma pendência da manhã — tudo fechado no Fracttal")}
${resto > 0 ? `<div class="nota">Ordenado por número de rolagens: a coluna <b>Rolagem</b> mostra quantas vezes a OS já foi empurrada. As ${n(resto)} OS restantes estão no painel → Semana → filtro "não finalizadas". "+N" na tarefa = a OS tem mais tarefas pendentes além da mostrada.</div>` : ""}
<div class="sec">Onde há espaço na tarde — por supervisor</div>
${tabela(resp, [["Supervisor", ""], ["Manhã", "r"], ["Fechou", "r"], ["Pendente", "r"], ["HH a recuperar", "r"], ["HH já na tarde", "r"], ["Carga da tarde", "r"]], ["", "r", "r", "r", "r", "r", "r"], "sem programação no dia")}${aviso}
<div class="sec">Leitura do meio-dia</div><ul class="ins">${D.ins.map(x => `<li>${x}</li>`).join("")}</ul>
<div class="pe"><span>Relatório gerado pela plataforma PCM · pcm.gridco.com.br · o cliente não recebe este relatório</span><span>Manhã = tarefas com início programado antes das ${String(HORA_CORTE_MANHA).padStart(2, "0")}:00. Pendente = não finalizada no Fracttal no momento do corte.</span></div>`;
  }

  // ═══════════════ FECHAMENTO DA SEMANA ═══════════════
  function semanal(week) {
    const W = new Map((RP.bd.semanas || []).map(w => [w.week, w])); const w = W.get(week); if (!w) return null;
    const MON = segundaDe(week), SUN = addDias(MON, 6);
    const todos = rowsDe(w), plan = todos.filter(x => !x.foraDoPlano), fora = todos.filter(x => x.foraDoPlano);
    const prog = plan.length, feitas = plan.filter(fin).length, ader = pct(feitas, prog), rol = plan.filter(x => x.reprog === "Sim").length;
    const dias = DIAS_PT.slice(0, 5).map(d => [d.slice(0, 3), plan.filter(x => x.dia === d).length, plan.filter(x => x.dia === d && fin(x)).length]);
    const bloco = (k, top, minimo) => [...agrupa(plan, x => x[k] || "—").entries()].map(([kk, L]) => [kk, L.length, L.filter(fin).length, L.filter(x => x.reprog === "Sim").length]).filter(r => r[1] >= (minimo || 1)).sort((a, b) => b[1] - a[1]).slice(0, top || 8);
    const cli = bloco("cliente"), resp = bloco("responsavel", 8), piores = bloco("cluster", 60, 10).sort((a, b) => pct(a[2], a[1]) - pct(b[2], b[1])).slice(0, 6);
    const T = tarefasG(), EV = eventosGer(); const inDt = (s, a, b) => { const d = dataDe(s); return d && d >= a && d <= b; };
    const tend = [];
    for (let i = 3; i >= 0; i--) { const wk = isoSemana(addDias(MON, -7 * i)); if (!W.has(wk)) continue; const mon = segundaDe(wk), sun = addDias(mon, 6); const r = rowsDe(W.get(wk)).filter(x => !x.foraDoPlano);
      const npw = T.filter(t => TIPOS_NAO_PROG.includes(t.tipo) && inDt(t.criacao, mon, sun)).length, rw = EV.filter(e => inDt(e.ini, mon, sun));
      tend.push([wk.slice(-2), r.length, r.filter(fin).length, r.filter(x => x.reprog === "Sim").length, npw, rw.length, rw.reduce((s, e) => s + (e.hDia || 0) * (e.peso || 1), 0)]); }
    const grp = agrupa(plan.filter(x => (x.vezes || 1) >= 4 && !fin(x)), x => x.os_id);
    const reinc = [...grp.entries()].sort((a, b) => Math.max(...b[1].map(t => t.vezes || 1)) - Math.max(...a[1].map(t => t.vezes || 1)));
    const npg = T.filter(t => TIPOS_NAO_PROG.includes(t.tipo) && inDt(t.criacao, MON, SUN));
    const U = RP.ger.usinas || []; const ev = EV.filter(e => inDt(e.ini, MON, SUN));
    const hrel = ev.reduce((s, e) => s + (e.hDia || 0) * (e.peso || 1), 0);
    const reg = conta(ev, e => (U[e.u] || {}).regiao || "—"), cat = conta(ev, e => e.cat);
    const hpM = new Map(); for (const e of ev) { const k = (U[e.u] || {}).usina || e.ativo || "—"; hpM.set(k, (hpM.get(k) || 0) + (e.hDia || 0)); } const hp = [...hpM.entries()].sort((a, b) => b[1] - a[1]);
    const causasM = new Map(); for (const p of (w.pendentes || [])) { const m = (p.motivo || "").replace(/^\[\+\d+d em andamento\]\s*/, ""); const k = /defina o dia/.test(m) ? "MPA noturna sem dia definido" : /não recebeu dia/.test(m) ? "usina sem dia na semana" : /Deslocada por OS/.test(m) ? "deslocada por OS grande" : /Rolagem/.test(m) ? "rolagem sem capacidade" : "sem capacidade nos dias da usina"; causasM.set(k, (causasM.get(k) || 0) + 1); }
    const causas = [...causasM.entries()].sort((a, b) => b[1] - a[1]); const cz = k => causasM.get(k) || 0;
    const crit = (RP.eng.ativos || []).filter(a => a.nivel === "critico"), aten = (RP.eng.ativos || []).filter(a => a.nivel === "atencao").length, kpi = RP.eng.kpi || {};
    const tAder = tend.map(([, p, f]) => pct(f, p)); let seguidas = 0; for (let i = tAder.length - 1; i > 0; i--) { if (tAder[i] < tAder[i - 1]) seguidas++; else break; }
    const tendencia = seguidas >= 2 ? "caindo" : (tAder.length >= 3 && tAder[2] > tAder[1] && tAder[1] > tAder[0]) ? "subindo" : "oscilando";
    const piorDia = prog ? dias.reduce((a, b) => pct(b[2], b[1]) < pct(a[2], a[1]) ? b : a) : ["—", 0, 0];
    const respOk = resp.filter(r => r[0] !== "—" && r[0] !== "TBD"), ins = [];
    if (prog) { const seq = tAder.map(x => Math.round(x) + "%").join(" → ");
      ins.push(`<b>Aderência de ${Math.round(ader)}% na semana</b> — ${n(feitas)} das ${n(prog)} tarefas programadas finalizadas, ${ader >= META ? "acima" : "abaixo"} da meta de ${META}%. ` + (tendencia === "caindo" ? `É a ${["", "segunda", "terceira", "quarta"][Math.min(seguidas, 3)]} semana seguida em queda: ${seq}.` : `Últimas semanas: ${seq}.`));
      ins.push(`<b>${n(rol)} tarefas rolaram</b> (${Math.round(pct(rol, prog))}% da programação). ${n(reinc.length)} OS já rolaram 4 vezes ou mais e seguem abertas — são o tema crítico nº 1: cada uma dessas está há mais de um mês sendo empurrada.`);
      if (cli.length && respOk.length) ins.push(`<b>${h(piorDia[0])} foi o pior dia</b> (${Math.round(pct(piorDia[2], piorDia[1]))}% de ${n(piorDia[1])}). Por cliente, ${h(cli.reduce((a, b) => pct(b[2], b[1]) < pct(a[2], a[1]) ? b : a)[0])} teve a menor aderência; por supervisor, ${h(respOk.reduce((a, b) => pct(b[2], b[1]) < pct(a[2], a[1]) ? b : a)[0])}.`);
    } else ins.push("<b>Semana sem programação carregada</b> no banco de dados — só o que entrou e os religamentos.");
    const ant = tend.length >= 2 ? tend[tend.length - 2][4] : null;
    ins.push(`<b>${n(npg.length)} OS não programadas entraram</b> (${conta(npg, t => t.tipo).map(([t, c]) => `${n(c)} ${h(t)}`).join(" · ") || "nenhuma"})` + (ant != null ? `, ${npg.length > ant ? "mais" : "menos"} que na semana anterior (${n(ant)}).` : ".") + " Isso consumiu HH que estava reservado ao plano.");
    if (ev.length) ins.push(`<b>${n(ev.length)} religamentos</b> somaram ${f0(hrel)} h ponderadas de indisponibilidade. ${h(hp[0][0])} sozinha respondeu por ${f0(hp[0][1])} h — vale abrir análise de causa raiz.`);
    if (fora.length) ins.push(`<b>Fora do plano, a equipe executou ${n(fora.length)} tarefas</b> que não estavam programadas. É trabalho real, mas invisível na aderência — e sinal de que o plano não reflete o que o campo faz.`);
    if (causas.length) ins.push(`<b>${n(causas.reduce((s, c) => s + c[1], 0))} tarefas não couberam na semana</b>: ${n(cz("MPA noturna sem dia definido"))} MPA noturnas esperam um dia nas observações e ${n(cz("usina sem dia na semana"))} são de usinas que não receberam dia. Essas duas causas dependem do PCM, não do campo.`);
    return { w, week, label: w.label || `Semana ${week.slice(-2)}`, plan, fora, prog, feitas, ader, rol, dias, cli, resp, piores, tend, reinc, npg, ev, hrel, reg, cat, hp, causas, crit, aten, kpi, ins };
  }
  function htmlSemanal(D, gerado) {
    const logo = logoHtml(), mx = Math.max(1, ...D.dias.map(d => d[1]));
    const barras = D.dias.map(([d, p, f]) => `<div class="bar"><div class="col"><i style="height:${Math.round(100 * p / mx)}%"></i><b style="height:${Math.round(100 * f / mx)}%"></b></div><span>${d}<small>${n(f)}/${n(p)}</small></span></div>`).join("");
    const hm = `${String(gerado.getUTCHours()).padStart(2, "0")}:${String(gerado.getUTCMinutes()).padStart(2, "0")}`;
    return `<div class="pg">
<div class="top">${logo}<div class="t"><h1>Fechamento da semana</h1><div class="s">Grid Co. · aderência, temas críticos e o que fica para a próxima semana${h(recorte())}</div></div>
  <div class="d"><b>${h(D.label)}</b>fechado ${DIAS_PT[wd(gerado)].slice(0, 3).toLowerCase()} ${ddmm(gerado)} às ${hm} · uso interno</div></div>
<div class="kpis" style="grid-template-columns:repeat(6,1fr)">
  <div class="kpi ${D.ader >= META ? "g" : "r"}"><div class="v">${D.prog ? Math.round(D.ader) + "%" : "—"}</div><div class="n">Aderência da semana</div><div class="m">${n(D.feitas)} de ${n(D.prog)} · meta ${META}%</div></div>
  <div class="kpi r"><div class="v">${n(D.rol)}</div><div class="n">Tarefas que rolaram</div><div class="m">${Math.round(pct(D.rol, D.prog))}% da programação</div></div>
  <div class="kpi"><div class="v">${n(D.fora.length)}</div><div class="n">Fora do plano</div><div class="m">executadas sem estar programadas</div></div>
  <div class="kpi r"><div class="v">${n(D.npg.length)}</div><div class="n">Não programadas</div><div class="m">corretivas e religamentos criados</div></div>
  <div class="kpi"><div class="v">${n(D.ev.length)}</div><div class="n">Religamentos</div><div class="m">${f0(D.hrel)} h ponderadas de parada</div></div>
  <div class="kpi r"><div class="v">${n(RP.g.totalAtrasadas || 0)}</div><div class="n">Backlog atrasado</div><div class="m">de ${n(RP.g.totalAbertas || 0)} abertas no fechamento</div></div></div>
<div class="g2"><div><div class="sec">Aderência por dia — programadas × finalizadas</div><div class="bars">${barras}</div></div>
  <div><div class="sec">Quatro semanas — tendência</div><table><thead><tr><th>Semana</th><th class="r">Prog.</th><th class="r">Aderência</th><th class="r">Rolaram</th><th class="r">Não prog.</th><th class="r">Relig.</th><th class="r">h parada</th></tr></thead><tbody>
  ${D.tend.map(([s, p, f, r, np, rl, hp]) => `<tr><td>S${s}</td><td class="r">${n(p)}</td><td class="r">${cel(pct(f, p))}</td><td class="r">${n(r)}</td><td class="r">${n(np)}</td><td class="r">${n(rl)}</td><td class="r">${f0(hp)}</td></tr>`).join("")}</tbody></table></div></div>
<div class="g2"><div><div class="sec">Por cliente</div>${tabela(D.cli.map(([k, p, f, r]) => [h(k), n(p), n(f), n(r), cel(pct(f, p))]), [["Cliente", ""], ["Prog.", "r"], ["Final.", "r"], ["Rolaram", "r"], ["Aderência", "r"]], ["", "r", "r", "r", "r"], "sem programação")}</div>
  <div><div class="sec">Por supervisor (Responsável O&amp;M)</div>${tabela(D.resp.map(([k, p, f, r]) => [h(k === "—" ? "sem responsável no BD" : k), n(p), n(f), n(r), cel(pct(f, p))]), [["Supervisor", ""], ["Prog.", "r"], ["Final.", "r"], ["Rolaram", "r"], ["Aderência", "r"]], ["", "r", "r", "r", "r"], "sem programação")}</div></div>
<div class="sec">Temas críticos da semana</div><ul class="ins">${D.ins.map(x => `<li>${x}</li>`).join("")}</ul>
<div class="pe"><span>Página 1 de 2 · Relatório gerado pela plataforma PCM · pcm.gridco.com.br</span><span>Aderência = finalizadas ÷ programadas (linhas do plano; fora do plano contadas à parte). Meta ${META}%.</span></div></div>
<div class="pg">
<div class="top">${logo}<div class="t"><h1>Detalhe da semana</h1><div class="s">reincidentes, religamentos, o que não coube e a engenharia</div></div><div class="d"><b>${h(D.label)}</b>página 2 de 2</div></div>
<div class="sec">Reincidentes — OS com 4 rolagens ou mais que seguem abertas (${n(D.reinc.length)})</div>
${tabela(D.reinc.slice(0, 10).map(([k, L]) => [`#${h(k)}`, h(usinaCurta(L[0].usina).slice(0, 24)), h(tarefaCurta(L[0].tarefa).slice(0, 40)), h(L[0].tipo), h(L[0].responsavel || "—"), `<span class="al">${Math.max(...L.map(t => t.vezes || 1))}ª</span>`]), [["OS", ""], ["Usina", ""], ["Tarefa", ""], ["Tipo", ""], ["Responsável", ""], ["Rolagem", "r"]], ["mono", "", "", "", "", "r"], "nenhuma OS com 4 rolagens ou mais em aberto")}
<div class="nota">Cada rolagem é uma semana perdida. Acima de 4, a causa raramente é capacidade: é peça, acesso, escopo ou a OS não cabe no dia. Vale decidir uma a uma na reunião de programação.</div>
<div class="g3"><div><div class="sec">Clusters com pior aderência (≥10 tarefas)</div>${tabela(D.piores.map(([k, p, f]) => [h(k), n(p), n(f), cel(pct(f, p))]), [["Cluster", ""], ["Prog.", "r"], ["Final.", "r"], ["Ader.", "r"]], ["", "r", "r", "r"])}</div>
  <div><div class="sec">Religamentos por região</div>${tabela(D.reg.map(([k, v]) => [h(k), n(v), `${Math.round(pct(v, D.ev.length))}%`]), [["Região", ""], ["Eventos", "r"], ["Parte", "r"]], ["", "r", "r"], "nenhum religamento")}${D.cat.length ? `<div class="nota">${D.cat.map(([k, v]) => `<b>${n(v)}</b> ${CAT[k] || k}`).join(" · ")}</div>` : ""}</div>
  <div><div class="sec">Usinas com mais horas de parada</div>${tabela(D.hp.slice(0, 6).map(([k, v]) => [h(String(k).slice(0, 24)), `${f0(v)} h`]), [["Usina", ""], ["Diurnas", "r"]], ["", "r"], "—")}</div></div>
<div class="g2"><div><div class="sec">Não programadas da semana — por cliente</div>${tabela(conta(D.npg, t => t.cliente || "—").slice(0, 6).map(([k, v]) => [h(k), n(v), `${Math.round(pct(v, D.npg.length))}%`]), [["Cliente", ""], ["OS", "r"], ["Parte", "r"]], ["", "r", "r"], "nenhuma")}</div>
  <div><div class="sec">O que não coube na semana — por causa</div>${tabela(D.causas.map(([k, v]) => [h(k), n(v)]), [["Causa", ""], ["Tarefas", "r"]], ["", "r"], "tudo coube")}<div class="nota">"MPA noturna sem dia" e "usina sem dia" dependem do PCM: defina o dia nas Observações da Semana e a próxima programação absorve.</div></div></div>
<div class="sec">Engenharia — Confiabilidade no fechamento</div><ul class="ins">
  <li><b>${n(D.kpi.ativosSinal || 0)} ativos com sinal de recorrência</b>, ${n(D.crit.length)} crítico(s) e ${n(D.aten)} em atenção. Crítico: ${D.crit.map(a => `${h(a.nome)} (${h(a.usina)}, ${a.nFalha} falhas em 30 dias)`).join("; ") || "nenhum"}.</li>
  <li><b>MTTR de ${f1(D.kpi.mttr || 0)} h</b> e MTBF de ${n(D.kpi.mtbf || 0)} h na frota monitorada. ${n(D.kpi.abaixo85 || 0)} ativos abaixo de 85% de disponibilidade.</li></ul>
<div class="pe"><span>Página 2 de 2 · o cliente não recebe este relatório — ele vê o resultado, não o processo</span><span>Fontes: Programação Semanal, Gestão PCM, Gerencial e Confiabilidade (Fracttal via robô)</span></div></div>`;
  }

  // ═══════════════ ALERTA DA PROGRAMAÇÃO ═══════════════
  function alerta(week) {
    const w = (RP.bd.semanas || []).find(x => x.week === week); if (!w) return null;
    const MON = segundaDe(week), rows = rowsDe(w).filter(x => !x.foraDoPlano), resumo = w.resumo || {}, P = w.pendentes || [], op = RP.op, A = [];
    const bl = (sev, tit, txt, linhas, cab, cols) => A.push({ sev, tit, txt, linhas, cab, cols });
    const imp = agrupa(rows.filter(x => (x.duracao || 0) > 8 || !janelaOk(x)), x => x.os_id);
    bl("alta", `Duração implausível ou janela impossível — ${n(imp.size)} OS, ${n([...imp.values()].reduce((s, L) => s + L.length, 0))} tarefas`, "Tarefa com mais de 8 h numa janela, ou fim depois da meia-noite. Distorce o HH do cluster e empurra as outras. Corrigir a duração no plano de manutenção do Fracttal.",
      [...imp.entries()].sort((a, b) => (b[1][0].duracao || 0) - (a[1][0].duracao || 0)).slice(0, 4).map(([k, L]) => [`#${h(k)}`, h(usinaCurta(L[0].usina).slice(0, 22)), h(tarefaCurta(L[0].tarefa).slice(0, 30)), `${f1(L[0].duracao)} h`, h(L[0].h_ini), h(L[0].h_fim), n(L.length)]),
      [["OS", ""], ["Usina", ""], ["Tarefa", ""], ["Duração", "r"], ["Início", ""], ["Fim", ""], ["Linhas", "r"]], ["mono", "", "", "r", "mono", "mono", "r"]);
    const capL = Object.entries(resumo).filter(([, v]) => v.hh_disp && v.hh_util > v.hh_disp).map(([k, v]) => [k, v.hh_util, v.hh_disp, v.pend || 0]).sort((a, b) => b[1] / b[2] - a[1] / a[2]);
    bl("alta", `Clusters acima da capacidade semanal — ${n(capL.length)} de ${n(Object.keys(resumo).length)}`, "HH programado maior que as horas da semana do cluster. Vai rolar por construção. Ou tira tarefa, ou muda a capacidade no BD de Operações.",
      capL.slice(0, 5).map(([k, u, d, p]) => [h(k), `${f0(u)} h`, `${d} h`, `<span class="cel ${u / d > 1.5 ? "mal" : "mid"}">${Math.round(pct(u, d))}%</span>`, n(p)]), [["Cluster", ""], ["Programado", "r"], ["Capacidade", "r"], ["Uso", "r"], ["Ficou fora", "r"]], ["", "r", "r", "r", "r"]);
    const dc = new Map(); for (const x of rows) if (janelaOk(x)) { const k = x.dia + "|" + (x.cluster || "—"); dc.set(k, (dc.get(k) || 0) + hh(x)); }
    const over = [...dc.entries()].filter(([, v]) => v > HH_DIA).sort((a, b) => b[1] - a[1]);
    bl("media", `Dias com mais de ${f1(HH_DIA)} h num cluster — ${n(over.length)} de ${n(dc.size)} combinações dia × cluster`, "Mais horas num dia do que uma pessoa executa. O programador aceita porque a capacidade é semanal; o campo não. Redistribuir entre os dias.",
      over.slice(0, 5).map(([k, v]) => [h(k.split("|")[0].slice(0, 3)), h(k.split("|")[1]), `${f0(v)} h`, `<span class="cel ${v > 2 * HH_DIA ? "mal" : "mid"}">${(v / HH_DIA).toFixed(1)}×</span>`]), [["Dia", ""], ["Cluster", ""], ["Programado", "r"], ["Vs. 1 pessoa", "r"]], ["", "", "r", "r"]);
    const pd = conta(rows, x => x.dia); const dias = DIAS_PT.slice(0, 6).map(d => [d.slice(0, 3), (pd.find(([k]) => k === d) || [d, 0])[1]]).filter(d => d[1]);
    if (dias.length) { const mx = dias.reduce((a, b) => b[1] > a[1] ? b : a), mn = dias.reduce((a, b) => b[1] < a[1] ? b : a);
      bl(pct(mx[1], rows.length) >= 35 ? "media" : "baixa", `Semana desbalanceada — ${h(mx[0])} tem ${n(mx[1])} tarefas, ${h(mn[0])} tem ${n(mn[1])}`, `${Math.round(pct(mx[1], rows.length))}% da semana num só dia. Um dia de chuva ou uma corretiva grande derruba a aderência da semana inteira.`,
        [dias.map(([d, v]) => `<b>${h(d)}</b> ${n(v)}`)], dias.map(([d]) => [d, ""]), dias.map(() => "")); }
    const byk = agrupa(rows.filter(x => janelaOk(x) && x.h_ini && x.h_fim), x => x.dia + "|" + (x.cluster || "")); const sob = [];
    for (const [k, L] of byk) { L.sort((a, b) => (mins(a.h_ini) || 0) - (mins(b.h_ini) || 0)); for (let i = 1; i < L.length; i++) if (mins(L[i].h_ini) != null && mins(L[i - 1].h_fim) != null && mins(L[i].h_ini) < mins(L[i - 1].h_fim) && L[i].os_id !== L[i - 1].os_id) sob.push([k.split("|")[0].slice(0, 3), k.split("|")[1], L[i - 1].os_id, L[i].os_id, L[i - 1].usina !== L[i].usina]); }
    bl("media", `Janelas sobrepostas no mesmo cluster e dia — ${n(sob.length)} pares`, "Duas OS diferentes ocupando a mesma hora da mesma equipe. Se são usinas diferentes, uma delas vai rolar.",
      sob.slice(0, 4).map(([d, c, a, b, dif]) => [h(d), h(c), `#${h(a)} × #${h(b)}`, dif ? "usinas diferentes" : "mesma usina"]), [["Dia", ""], ["Cluster", ""], ["OS", ""], ["Onde", ""]], ["", "", "mono", ""]);
    const v5 = agrupa(rows.filter(x => (x.vezes || 1) >= 5), x => x.os_id);
    bl("media", `OS com 5 rolagens ou mais programadas de novo — ${n(v5.size)} OS`, "Já rolaram cinco vezes ou mais e voltaram para a semana sem nada mudar. A chance de rolar de novo é alta. Decidir: peça, acesso, escopo ou tirar do plano.",
      [...v5.entries()].sort((a, b) => Math.max(...b[1].map(t => t.vezes || 1)) - Math.max(...a[1].map(t => t.vezes || 1))).slice(0, 5).map(([k, L]) => [`#${h(k)}`, h(usinaCurta(L[0].usina).slice(0, 22)), h(tarefaCurta(L[0].tarefa).slice(0, 34)), h(L[0].responsavel || "—"), `<b class="al">${Math.max(...L.map(t => t.vezes || 1))}ª</b>`]),
      [["OS", ""], ["Usina", ""], ["Tarefa", ""], ["Responsável", ""], ["Rolagem", "r"]], ["mono", "", "", "", "r"]);
    const tbd = rows.filter(x => (x.responsavel || "TBD") === "TBD");
    bl("baixa", `Tarefas sem responsável definido — ${n(tbd.length)} (TBD)`, "O cluster não tem Responsável O&M no BD de Operações. Ninguém recebe o alerta do dia dessas tarefas.", conta(tbd, x => x.cluster || "—").slice(0, 6).map(([c, v]) => [h(c), n(v)]), [["Cluster", ""], ["Tarefas", "r"]], ["", "r"]);
    const mpa = new Set(), semdia = new Map(), desloc = new Map();
    for (const p of P) { const m = (p.motivo || "").replace(/^\[\+\d+d em andamento\]\s*/, ""); if (/defina o dia/.test(m)) mpa.add(p.os_id); else if (/não recebeu dia/.test(m)) { const mm = /Usina "([^"]+)"/.exec(m); const k = mm ? mm[1] : "?"; semdia.set(k, (semdia.get(k) || 0) + 1); } else if (/Deslocada por OS/.test(m)) { const mm = /OS #(\d+)/.exec(m); const k = mm ? mm[1] : "?"; desloc.set(k, (desloc.get(k) || 0) + 1); } }
    const semdiaL = [...semdia.entries()].sort((a, b) => b[1] - a[1]), descL = [...desloc.entries()].sort((a, b) => b[1] - a[1]), mpaL = [...mpa].sort();
    bl(mpa.size || semdia.size ? "alta" : "baixa", `Ficou fora da semana por decisão pendente — ${n(mpa.size)} OS de MPA noturna e ${n(semdia.size)} usinas sem dia`, "O programador não decide sozinho: MPA noturna precisa de um dia nas Observações da Semana; usina sem dia precisa entrar na distribuição do cluster. Enquanto isso, essas tarefas envelhecem no backlog.",
      [mpa.size ? ["MPA noturna sem dia", mpaL.slice(0, 10).map(k => "#" + k).join(", ") + (mpaL.length > 10 ? ` +${mpaL.length - 10}` : "")] : null, semdia.size ? ["Usinas sem dia na semana", semdiaL.slice(0, 6).map(([u]) => usinaCurta(u)).join(", ") + (semdiaL.length > 6 ? ` +${semdiaL.length - 6}` : "")] : null, desloc.size ? ["Deslocadas por OS grande", descL.slice(0, 4).map(([k, v]) => `#${k} empurrou ${n(v)}`).join(" · ")] : null].filter(Boolean).map(([a, b]) => [h(a), h(b)]),
      [["Situação", ""], ["Quem", ""]], ["", "quebra"]);
    const ufDe = us => (us || "").replace(/^.* - /, "").trim().slice(0, 2);
    const fl = (RP.fer || []).map(f => ({ ...f, d: dataDe(f.data) })).filter(f => f.d && f.d >= MON && f.d <= addDias(MON, 5)).map(f => { const pr = rows.filter(x => x.dia === DIAS_PT[wd(f.d)] && (f.uf === "TODOS" || ufDe(x.usina) === f.uf)).length; return [h(DIAS_PT[wd(f.d)].slice(0, 3) + " " + ddmm(f.d)), h(f.nome), h(f.uf), n(pr), pr]; });
    bl(fl.some(l => l[4]) ? "alta" : "baixa", `Feriados na semana — ${n(fl.length)}`, "Tarefa programada em feriado da UF da usina só roda se a equipe trabalhar no feriado. Confirmar ou mover.", fl.map(l => l.slice(0, 4)), [["Data", ""], ["Feriado", ""], ["UF", ""], ["Tarefas no dia", "r"]], ["", "", "", "r"]);
    const qa = (w.qualidade || []).filter(q => q.tipo !== "REMOVIDA");
    bl("baixa", `Avisos de cadastro — ${n(qa.length)} · ${n((w.qualidade || []).length - qa.length)} linhas de teste removidas`, "Erros de nome no Fracttal que fazem a distribuição de dias contar errado.", qa.map(q => [h((q.item || "").slice(0, 34)), h((q.detalhe || "").slice(0, 60)), h((q.acao || "").slice(0, 40))]), [["Item", ""], ["Problema", ""], ["Ação", ""]], ["", "", ""]);
    // viabilidade de campo
    const cid = new Map((op.usinas || []).map(u => [norm(u.usina), (u.cidade || "").trim()]));
    const cidade = us => { let c = cid.get(norm(usinaCurta(us))); if (!c) { const base = usinaCurta(us).replace(/\s*\d+\s*(\(.*\))?$/, ""); c = cid.get(norm(base)) || ("UF " + ufDe(us)); } return c; };
    const gd = agrupa(rows.filter(janelaOk), x => x.dia + "|" + (x.cluster || "—"));
    const multi = []; for (const [k, L] of gd) { const cids = conta(L, t => cidade(t.usina)); if (cids.length >= 2) multi.push([k, cids, L.reduce((s, t) => s + (t.desloc || 0), 0), L.length]); }
    multi.sort((a, b) => b[1].length - a[1].length || b[2] - a[2]);
    bl(multi.some(m => m[1].length >= 3) ? "alta" : multi.length ? "media" : "baixa", `Equipe em mais de uma cidade no mesmo dia — ${n(multi.length)} de ${n(gd.size)} dias × cluster (${n(multi.filter(m => m[1].length >= 3).length)} com 3 ou mais)`, "A mesma equipe programada em usinas de cidades diferentes no mesmo dia. Duas pode ser rotina; três ou mais raramente cabe com deslocamento, almoço e apontamento.",
      multi.slice(0, 6).map(([k, c, d, nt]) => [h(k.split("|")[0].slice(0, 3)), h(k.split("|")[1]), n(c.length), h(c.slice(0, 4).map(([ci, v]) => `${ci} (${v})`).join(" · ").slice(0, 58)), `${f1(d)} h`, n(nt)]), [["Dia", ""], ["Cluster", ""], ["Cidades", "r"], ["Onde (tarefas)", ""], ["Desloc.", "r"], ["Tarefas", "r"]], ["", "", "r", "", "r", "r"]);
    const dsl = [...gd.entries()].map(([k, L]) => [k, L.reduce((s, t) => s + (t.desloc || 0), 0), new Set(L.map(t => cidade(t.usina))).size]).filter(x => x[1] > 3).sort((a, b) => b[1] - a[1]);
    bl(dsl.length ? "media" : "baixa", `Mais de 3 h de deslocamento num dia — ${n(dsl.length)} dias × cluster`, "Deslocamento somado das tarefas do dia. Acima de 3 h, sobra menos de 6 h de execução real.", dsl.slice(0, 5).map(([k, d, c]) => [h(k.split("|")[0].slice(0, 3)), h(k.split("|")[1]), `${f1(d)} h`, n(c)]), [["Dia", ""], ["Cluster", ""], ["Deslocamento", "r"], ["Cidades", "r"]], ["", "", "r", "r"]);
    const seq = []; for (const [k, L] of gd) { const Ls = [...L].sort((a, b) => (mins(a.h_ini) || 0) - (mins(b.h_ini) || 0)); for (let i = 1; i < Ls.length; i++) { const a = Ls[i - 1], b = Ls[i]; if (a.usina !== b.usina && mins(b.h_ini) != null && mins(a.h_fim) != null) { const gap = mins(b.h_ini) - mins(a.h_fim), need = (b.desloc || 0) * 60; if (gap < 0 || gap < need - 5) seq.push([k.split("|")[0].slice(0, 3), k.split("|")[1], a.os_id, b.os_id, gap, need, cidade(a.usina), cidade(b.usina)]); } } }
    bl(seq.length ? "media" : "baixa", `Troca de usina sem tempo de deslocamento — ${n(seq.length)} casos`, "A tarefa seguinte começa em outra usina antes de a anterior terminar, ou sem o tempo de estrada que o próprio plano calcula.", seq.slice(0, 5).map(([d, c, a, b, g, nd, ca, cb]) => [h(d), h(c), `#${h(a)} → #${h(b)}`, h(`${ca} → ${cb}`.slice(0, 30)), `${g} min`, `${Math.round(nd)} min`]), [["Dia", ""], ["Cluster", ""], ["OS", ""], ["Trajeto", ""], ["Folga", "r"], ["Precisa", "r"]], ["", "", "mono", "", "r", "r"]);
    const fh = agrupa(rows.filter(x => janelaOk(x) && !/NOTURNO/i.test(x.dia) && x.tipo !== "MPA" && mins(x.h_ini) != null && (mins(x.h_ini) < 360 || (mins(x.h_fim) || 0) > 19 * 60)), x => x.os_id);
    bl(fh.size ? "media" : "baixa", `Fora do horário de campo (06:00–19:00) — ${n(fh.size)} OS, ${n([...fh.values()].reduce((s, L) => s + L.length, 0))} tarefas`, "Diurna programada antes das 6 h ou terminando depois das 19 h. MPA noturna e janelas marcadas NOTURNO ficam fora desta checagem.",
      [...fh.entries()].slice(0, 5).map(([k, L]) => [`#${h(k)}`, h(usinaCurta(L[0].usina).slice(0, 22)), h(tarefaCurta(L[0].tarefa).slice(0, 30)), h(L[0].tipo), h(L[0].h_ini), h(L[0].h_fim)]), [["OS", ""], ["Usina", ""], ["Tarefa", ""], ["Tipo", ""], ["Início", ""], ["Fim", ""]], ["mono", "", "", "", "mono", "mono"]);
    const cnt = [...gd.entries()].filter(([, L]) => L.length > 12).map(([k, L]) => [k, L.length, new Set(L.map(t => t.os_id)).size]).sort((a, b) => b[1] - a[1]);
    bl(cnt.length ? "media" : "baixa", `Mais de 12 tarefas para uma equipe num dia — ${n(cnt.length)} dias × cluster`, "Mesmo que o HH feche, cada tarefa tem abertura, execução, foto e fechamento no Fracttal. Acima de 12 por dia o apontamento não acompanha.", cnt.slice(0, 5).map(([k, c, o]) => [h(k.split("|")[0].slice(0, 3)), h(k.split("|")[1]), n(c), n(o)]), [["Dia", ""], ["Cluster", ""], ["Tarefas", "r"], ["OS", "r"]], ["", "", "r", "r"]);
    const fds = rows.filter(x => /^(Sáb|Dom)/.test(x.dia));
    bl("baixa", `Programação em fim de semana — ${n(fds.length)} tarefas`, "Só vale se a equipe trabalha no sábado. Senão, rola por construção.", conta(fds, x => x.cluster || "—").slice(0, 4).map(([c, v]) => [h(c), n(v)]), [["Cluster", ""], ["Tarefas", "r"]], ["", "r"]);
    const pes = new Map((op.clusters || []).map(c => [c.cluster, c.pessoas || 0])); const sp = conta(rows.filter(x => pes.has(x.cluster) && pes.get(x.cluster) === 0), x => x.cluster);
    bl(sp.length ? "alta" : "baixa", `Cluster com programação mas sem pessoa no BD de Operações — ${n(sp.length)}`, "A capacidade da semana vem de zero pessoas. Ou o colaborador não está na Relação Geral, ou o cluster está com o nome diferente.", sp.slice(0, 5).map(([c, v]) => [h(c), n(v)]), [["Cluster", ""], ["Tarefas", "r"]], ["", "r"]);
    const ORD = { alta: 0, media: 1, baixa: 2 }; A.sort((a, b) => ORD[a.sev] - ORD[b.sev]);
    const cont = { alta: 0, media: 0, baixa: 0 }; for (const a of A) cont[a.sev]++;
    const hhTot = rows.filter(janelaOk).reduce((s, x) => s + hh(x), 0), capTot = Object.values(resumo).reduce((s, v) => s + (v.hh_disp || 0), 0);
    return { w, week, label: w.label || `Semana ${week.slice(-2)}`, rows, A, cont, hhTot, capTot, multi, P, resumo };
  }
  function htmlAlerta(D, gerado) {
    const SEV = { alta: ["Alta", "mal"], media: ["Média", "mid"], baixa: ["Baixa", "ok"] }, logo = logoHtml();
    const blocos = D.A.map(a => `<div class="al-bloco"><div class="al-cab"><span class="sev ${SEV[a.sev][1]}">${SEV[a.sev][0]}</span><b>${a.tit}</b></div><div class="al-txt">${a.txt}</div>${tabela(a.linhas, a.cab, a.cols, "nada encontrado")}</div>`).join("");
    const hm = `${String(gerado.getUTCHours()).padStart(2, "0")}:${String(gerado.getUTCMinutes()).padStart(2, "0")}`;
    return `<div class="top ambar">${logo}<div class="t"><h1>Alerta da programação</h1><div class="s">Grid Co. · checagem da programação recém-gerada, antes de ir para o campo${h(recorte())}</div></div>
  <div class="d"><b>${h(D.label)}</b>gerado ${DIAS_PT[wd(gerado)].slice(0, 3).toLowerCase()} ${ddmm(gerado)} às ${hm} · uso interno (PCM)</div></div>
<div class="kpis" style="grid-template-columns:repeat(5,1fr)">
  <div class="kpi"><div class="v">${n(D.rows.length)}</div><div class="n">Tarefas programadas</div><div class="m">em ${n(new Set(D.rows.map(x => x.os_id)).size)} OS · ${n(Object.keys(D.resumo).length)} clusters</div></div>
  <div class="kpi ${D.hhTot > D.capTot ? "r" : "g"}"><div class="v">${Math.round(pct(D.hhTot, D.capTot))}%</div><div class="n">HH ÷ capacidade</div><div class="m">${f0(D.hhTot)} h de ${n(D.capTot)} h na semana</div></div>
  <div class="kpi r"><div class="v">${n(D.cont.alta)}</div><div class="n">Severidade alta</div><div class="m">resolver antes de segunda</div></div>
  <div class="kpi m"><div class="v">${n(D.cont.media)}</div><div class="n">Severidade média</div><div class="m">vão virar rolagem</div></div>
  <div class="kpi m"><div class="v">${n(D.multi.length)}</div><div class="n">Dias em 2+ cidades</div><div class="m">mesma equipe · ${n(D.P.length)} tarefas não couberam</div></div></div>
${blocos}
<div class="pe"><span>Relatório gerado pela plataforma PCM · pcm.gridco.com.br · o cliente não recebe este relatório</span><span>Fonte: Programação Semanal publicada (banco_dados.json) e BD de Operações. Corrija na planilha ou nas Observações e rode o programador de novo.</span></div>`;
  }

  // ═══════════════ TELA ═══════════════
  const TIPOS = [
    ["diario", "D", "Relatório diário de manutenção", "o que aconteceu num dia · 2 páginas · automático às 06:00"],
    ["matinal", "T", "Recuperação da tarde", "programado para a manhã e ainda aberto · 1 página · automático às 13:00"],
    ["semanal", "S", "Fechamento da semana", "aderência, tendência e temas críticos · 2 páginas · sexta 17:00"],
    ["alerta", "A", "Alerta da programação", "17 checagens da semana publicada · ao publicar"]];
  const ROT = { diario: "Diário", matinal: "Recuperação da tarde", semanal: "Fechamento", alerta: "Alerta" };

  function gerar() {
    const agora = new Date(); const ger = new Date(Date.UTC(agora.getFullYear(), agora.getMonth(), agora.getDate(), agora.getHours(), agora.getMinutes()));
    let html = "", titulo = "";
    try {
      if (RP.tipo === "diario") { const d = dataDe(RP.dia); if (!d) throw new Error("escolha um dia"); const D = diario(d); html = htmlDiario(D, ger); titulo = `Relatorio_Diario_${RP.dia}`; }
      else if (RP.tipo === "matinal") { const d = dataDe(RP.dia); if (!d) throw new Error("escolha um dia"); const D = matinal(d); html = htmlMatinal(D, ger); titulo = `Recuperacao_da_Tarde_${RP.dia}`; }
      else if (RP.tipo === "semanal") { const D = semanal(RP.semana); if (!D) throw new Error("o banco não tem a semana " + RP.semana); html = htmlSemanal(D, ger); titulo = `Fechamento_da_Semana_${RP.semana}`; }
      else { const D = alerta(RP.semana); if (!D) throw new Error("o banco não tem a semana " + RP.semana); html = htmlAlerta(D, ger); titulo = `Alerta_da_Programacao_${RP.semana}`; }
      RP.html = html; RP.titulo = titulo; RP.erroGer = "";
    } catch (e) { RP.html = ""; RP.erroGer = e.message; }
    RP.gerado = ger;
  }
  function abrirNovaAba() {
    if (!RP.html) return;
    const w = window.open("", "_blank"); if (!w) return;
    w.document.write(`<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>${h(RP.titulo.replace(/_/g, " "))}</title><style>@page{size:A4;margin:11mm 12mm 12mm}*{box-sizing:border-box}body{margin:0;font-family:"Segoe UI",Arial,sans-serif;font-size:9.5pt;color:#191528;line-height:1.3;background:#fff;padding:12mm}@media print{body{padding:0}}${cssPrefixada("body")}</style></head><body>${RP.html}</body></html>`);
    w.document.close();
  }
  function imprimir() {
    if (!RP.html) return;
    document.body.classList.add("rp-imprimindo");
    // @page não aceita condição por classe: entra só durante esta impressão, para não
    // mudar o one-pager do Gerencial (paisagem) nem o FMEA.
    const pg = document.createElement("style"); pg.id = "rp-page"; pg.textContent = "@page{size:A4 portrait;margin:11mm 12mm 12mm}"; document.head.appendChild(pg);
    const fim = () => { document.body.classList.remove("rp-imprimindo"); pg.remove(); window.removeEventListener("afterprint", fim); };
    window.addEventListener("afterprint", fim); setTimeout(fim, 60000);
    window.print();
  }

  window.vRel = function () {
    if (RP.estado === "vazio") { carregar(); return '<div class="gp-carga">Carregando os relatórios…</div>'; }
    if (RP.estado === "carregando") return '<div class="gp-carga">Carregando <b>banco_dados.json</b> e companhia…</div>';
    if (RP.estado === "erro") return `<div class="gp-carga erro"><b>Não foi possível carregar.</b><span>${h(RP.erro)}</span></div>`;
    const semanas = (RP.bd.semanas || []).map(w => w.week).sort().reverse();
    const rows = (RP.bd.semanas || []).flatMap(w => w.rows || []);
    const clientes = [...new Set(rows.map(r => r.cliente).filter(Boolean))].sort();
    const clusters = [...new Set(rows.map(r => r.cluster).filter(Boolean))].sort(), resps = [...new Set(rows.map(r => r.responsavel).filter(x => x && x !== "TBD"))].sort();
    const porSemana = RP.tipo === "semanal" || RP.tipo === "alerta";
    const idx = (RP.idx && RP.idx.emissoes) || [];
    return `<div class="rp-tela">
<div class="rp-esq">
  <div class="rp-card"><h3>1 · Tipo</h3><div class="rp-tipos">${TIPOS.map(([k, ic, t, s]) => `<div class="rp-tipo${RP.tipo === k ? " on" : ""}" data-rpt="${k}"><div class="ic">${ic}</div><div><b>${t}</b><span>${s}</span></div></div>`).join("")}
    <div class="rp-tipo" data-rpt="fmea"><div class="ic">E</div><div><b>FMEA · Causa Raiz</b><span>por ativo, no módulo Confiabilidade → abre lá</span></div></div></div></div>
  <div class="rp-card"><h3>2 · Período e recorte</h3>
    <div class="rp-row"><div><label>Dia</label><input type="date" data-rpk="dia" value="${h(RP.dia)}"${porSemana ? " disabled" : ""}></div>
      <div><label>Semana</label><select data-rpk="semana"${porSemana ? "" : " disabled"}>${semanas.map(s => `<option value="${s}"${s === RP.semana ? " selected" : ""}>${h(((RP.bd.semanas || []).find(w => w.week === s) || {}).label || s)}</option>`).join("")}</select></div></div>
    <div class="rp-row"><div><label>Cliente</label><select data-rpk="cliente"><option value="">Todos</option>${clientes.map(c => `<option${c === RP.cliente ? " selected" : ""}>${h(c)}</option>`).join("")}</select></div>
      <div><label>Cluster / supervisor</label><select data-rpk="cluster"><option value="">Todos</option><optgroup label="Cluster">${clusters.map(c => `<option${c === RP.cluster ? " selected" : ""}>${h(c)}</option>`).join("")}</optgroup><optgroup label="Supervisor">${resps.map(c => `<option${c === RP.cluster ? " selected" : ""}>${h(c)}</option>`).join("")}</optgroup></select></div></div>
    <div class="rp-acoes"><button class="bt forte" id="rp-gerar">Gerar</button><button class="bt" id="rp-aba"${RP.html ? "" : " disabled"}>Abrir em nova aba</button></div>
    ${RP.erroGer ? `<div class="rp-erro">${h(RP.erroGer)}</div>` : ""}</div>
  <div class="rp-card"><h3>Emitidos automaticamente · últimos 30 dias</h3>
    ${idx.length ? `<table class="rp-hist"><tr><th>Quando</th><th>Relatório</th><th>E-mail</th><th></th></tr>${idx.slice(0, 40).map(e => `<tr><td>${h((e.geradoEm || "").slice(8, 10))}/${h((e.geradoEm || "").slice(5, 7))} ${h((e.geradoEm || "").slice(11, 16))}</td><td>${h(ROT[e.janela] || e.janela)} · ${h(e.rotulo || e.ref)}</td><td>${e.enviado ? `<span class="rp-tag env">enviado · ${e.para || ""}</span>` : `<span class="rp-tag nao">${h(e.motivo || "não enviado")}</span>`}</td><td>${e.pdf ? `<a href="${h(e.arquivo)}" target="_blank" rel="noopener">PDF</a>` : `<a href="${h((e.arquivo || "").replace(/\.pdf$/, ".html"))}" target="_blank" rel="noopener">HTML</a>`}</td></tr>`).join("")}</table>`
      : '<div class="rp-vazio">Nenhuma emissão automática registrada ainda. Elas aparecem aqui depois da primeira rodada do robô com o passo de relatórios.</div>'}</div>
</div>
<div class="rp-dir">
  <div class="rp-prev"><div class="rp-bar"><button class="bt verde" id="rp-print"${RP.html ? "" : " disabled"}>Imprimir / PDF</button><span class="dica">${RP.html ? `${h(RP.titulo.replace(/_/g, " "))} · gerado agora com o dado do painel` : "escolha o tipo e o período e clique em Gerar"}</span></div>
    <div class="rp-papel">${RP.html ? `<div class="rp-folha">${RP.html}</div>` : '<div class="rp-vazio" style="padding:40px;text-align:center">A folha aparece aqui.</div>'}</div></div>
  <div class="rp-nota"><b>Como funciona:</b> o relatório é montado aqui no navegador, com os mesmos dados que o painel já carrega, e "Imprimir / PDF" usa a impressão do navegador, igual ao FMEA. Nada vai para o servidor. As regras são as mesmas dos e-mails automáticos.</div>
</div></div>`;
  };
  window.rpPintar = function () {
    if (RP.estado !== "pronto") return;
    document.querySelectorAll(".rp-tipo[data-rpt]").forEach(el => el.onclick = () => { if (el.dataset.rpt === "fmea") { const b = document.querySelector('.lat-i[data-v="conf"]'); if (b) b.click(); return; } RP.tipo = el.dataset.rpt; RP.html = ""; RP.erroGer = ""; window.pintar(); });
    document.querySelectorAll("[data-rpk]").forEach(el => el.onchange = () => { RP[el.dataset.rpk] = el.value; });
    const g = document.getElementById("rp-gerar"); if (g) g.onclick = () => { gerar(); window.pintar(); if (RP.html) { const p = document.querySelector(".rp-dir"); if (p) p.scrollIntoView({ behavior: "smooth", block: "start" }); } };
    const a = document.getElementById("rp-aba"); if (a) a.onclick = abrirNovaAba;
    const p = document.getElementById("rp-print"); if (p) p.onclick = imprimir;
  };
  // CSS da tela + folha, injetado uma vez
  const st = document.createElement("style");
  st.textContent = `
.rp-tela{display:grid;grid-template-columns:360px minmax(0,1fr);gap:18px;align-items:start}
@media (max-width:1100px){.rp-tela{grid-template-columns:1fr}}
.rp-card{background:var(--surf);border:1px solid var(--line);border-radius:var(--r,10px);padding:14px 16px;margin-bottom:12px}
.rp-card h3{margin:0 0 10px;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--ink3)}
.rp-tipos{display:grid;gap:8px}.rp-tipo{border:1px solid var(--line);border-radius:8px;padding:9px 11px;cursor:pointer;display:flex;gap:10px;align-items:flex-start}
.rp-tipo.on{border-color:#A9DB21;background:color-mix(in srgb,#A9DB21 14%,var(--surf))}.rp-tipo b{display:block;font-size:13.5px}.rp-tipo span{font-size:12px;color:var(--ink3)}
.rp-tipo .ic{width:30px;height:30px;border-radius:7px;background:var(--surf2);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:12px;color:var(--ink2);flex:none}.rp-tipo.on .ic{background:#A9DB21;color:#191528}
.rp-card label{display:block;font-size:12px;color:var(--ink3);margin:8px 0 3px}.rp-card select,.rp-card input{width:100%;border:1px solid var(--line2);border-radius:6px;padding:7px 9px;font:inherit;font-size:13px;background:var(--surf);color:var(--ink)}
.rp-row{display:grid;grid-template-columns:1fr 1fr;gap:10px}.rp-acoes{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
.rp-acoes .bt.forte{background:var(--navy,#191528);color:#fff;border-color:var(--navy,#191528);font-weight:700}.bt.verde{background:#A9DB21;border-color:#A9DB21;color:#191528;font-weight:700}
.rp-erro{margin-top:10px;background:#fde2e2;color:#b02525;border-radius:6px;padding:8px 10px;font-size:12.5px}
.rp-hist{width:100%;border-collapse:collapse;font-size:12.5px}.rp-hist th{text-align:left;font-size:11px;color:var(--ink3);text-transform:uppercase;letter-spacing:.04em;padding:6px 8px;border-bottom:1px solid var(--line2)}.rp-hist td{padding:6px 8px;border-bottom:1px solid var(--line)}
.rp-tag{font-size:11px;padding:1px 7px;border-radius:4px;background:var(--surf2);color:var(--ink2);white-space:nowrap}.rp-tag.env{background:#e3f6ea;color:#1f7a4d}.rp-tag.nao{background:#fdf0d5;color:#a04408}
.rp-vazio{color:var(--ink3);font-size:12.5px}
.rp-prev{background:var(--surf);border:1px solid var(--line);border-radius:var(--r,10px);overflow:hidden}
.rp-bar{display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid var(--line);background:var(--surf2)}.rp-bar .dica{color:var(--ink3);font-size:12px;margin-left:auto}
.rp-papel{background:#d8dae5;padding:22px;overflow:auto}
.rp-folha{background:#fff;color:#191528;width:210mm;max-width:100%;margin:0 auto;box-shadow:0 6px 24px rgba(25,21,40,.18);padding:11mm 12mm;font-family:"Segoe UI",Arial,sans-serif;font-size:9.5pt;line-height:1.3}
.rp-folha .pg{padding-bottom:10mm;margin-bottom:10mm;border-bottom:1px dashed #cbcbdd}.rp-folha .pg:last-child{border-bottom:0;margin-bottom:0;padding-bottom:0}
${cssPrefixada(".rp-folha")}
.rp-nota{margin-top:12px;background:color-mix(in srgb,#A9DB21 12%,var(--surf));border-left:3px solid #A9DB21;padding:8px 11px;font-size:12.5px;color:var(--ink2);border-radius:0 6px 6px 0}
@media print{
  body.rp-imprimindo *{visibility:hidden}
  body.rp-imprimindo .rp-folha,body.rp-imprimindo .rp-folha *{visibility:visible}
  body.rp-imprimindo .rp-folha{position:absolute;left:0;top:0;width:100%;max-width:none;box-shadow:none;padding:0;margin:0}
  body.rp-imprimindo .rp-folha .pg{border:0;padding:0;margin:0}
  body.rp-imprimindo{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  body.rp-imprimindo .lat,body.rp-imprimindo .topo,body.rp-imprimindo .rp-esq,body.rp-imprimindo .rp-bar,body.rp-imprimindo .rp-nota{display:none!important}
}`;
  document.head.appendChild(st);
})();
