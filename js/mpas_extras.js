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

// ── engate: roda junto com o render da aba ──────────────────────────────────
if (typeof renderMpas === 'function') {
  const _renderMpasOrig = renderMpas;
  renderMpas = function(){
    _renderMpasOrig.apply(this, arguments);
    try { mpGantt(); } catch (e) { console.warn('gantt:', e); }
    try { mpGeral(); } catch (e) { console.warn('planilha geral:', e); }
  };
}
