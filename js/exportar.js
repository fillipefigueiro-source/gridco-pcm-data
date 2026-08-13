// ─────────────────────────────────────────────────────────────────────────────
// exportar.js — CSV + impressão por aba (13/08/2026)
// Script clássico, mesmo escopo global do app.js (carrega depois dele).
//
// 1) exportCSV(): o botão "↓ CSV" do topo chamava uma função que NUNCA existiu
//    (quebrado desde sempre, herdado do arquivo original). Exporta a semana
//    visível respeitando TODOS os filtros ativos — inclusive o Responsável.
// 2) Impressão por aba: o "🖨 PDF" imprimia bem só a Programação Semanal.
//    Agora Gestão PCM e Gestão MPAS saem com cabeçalho próprio e sem cortes
//    de rolagem (ver o bloco de @media print no css/base.css).
// ─────────────────────────────────────────────────────────────────────────────

function exportCSV() {
  const rows = GD();
  if (!rows.length) { toast('Nada para exportar com os filtros atuais.'); return; }
  const cols = [
    ['OS', r => r.os_id], ['SS', r => r.solic_orig],
    ['Cliente', r => r.cliente], ['Usina', r => r.usina],
    ['Equipe Cluster', r => r.cluster], ['Tipo', r => r.tipo],
    ['Tarefa', r => r.tarefa], ['Dia', r => r.dia],
    ['Hora Início', r => r.h_ini], ['Hora Fim', r => r.h_fim],
    ['Duração (h)', r => r.duracao],
    ['Responsável O&M', r => r.responsavel],
    ['Responsável', r => r.resp_os],
    ['Estado da Tarefa', r => estadoTarefaInfo(r).l],
    ['Status OS', r => r.statusPai],
    ['Reprogramada', r => r.reprog],
    ['Etiqueta', r => _etqDesc(r.etiquetas) || ''],
  ];
  // ; como separador e BOM: é o que o Excel pt-BR abre certo com dois cliques
  const esc = v => { v = String(v ?? ''); return /[";\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
  const linhas = [cols.map(c => c[0]).join(';')];
  rows.forEach(r => linhas.push(cols.map(c => esc(c[1](r))).join(';')));
  const w = AW();
  const blob = new Blob(['﻿' + linhas.join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'Programacao_' + (w?.week || 'semana') + '.csv';
  a.click();
  URL.revokeObjectURL(a.href);
  toast('CSV: ' + rows.length + ' OS exportada(s)');
}

// ── impressão por aba ────────────────────────────────────────────────────────
const _PRINT_LBL = {
  semana: 'Programação Semanal', gestaoPcm: 'Gestão PCM', gestaoMpas: 'Gestão MPAS',
  religamentos: 'Religamentos', chamadosGarantia: 'Garantia', performance: 'Performance',
  engenharia: 'Engenharia', emVerificacao: 'Em Verificação', sugestoesIA: 'Sugestões IA',
};

function _printPrep() {
  const v = S.topView || 'semana';
  document.body.setAttribute('data-printview', v);
  const ph = document.getElementById('ph-w');
  if (ph && !ph.dataset.orig) {
    ph.dataset.orig = ph.textContent;
    const w = AW();
    ph.textContent = (_PRINT_LBL[v] || 'Painel') + ' · ' + (w?.label || '') + ' — Grid Co. O&M';
  }
}

function _printDone() {
  document.body.removeAttribute('data-printview');
  const ph = document.getElementById('ph-w');
  if (ph && ph.dataset.orig) { ph.textContent = ph.dataset.orig; delete ph.dataset.orig; }
}

window.addEventListener('beforeprint', _printPrep);
window.addEventListener('afterprint', _printDone);
