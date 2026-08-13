// ─────────────────────────────────────────────────────────────────────────────
// navegacao.js — Melhoria 0.10, Fase 3 (roteador com hash na URL)
// Criado em 13/08/2026. Carrega DEPOIS de js/app.js e no MESMO escopo global
// (script clássico): ele embrulha setTopView/launch por reatribuição, sem
// tocar no código legado.
//
// O que passa a funcionar:
//   · cada aba tem URL própria (#semana, #gestao-pcm, …) — dá para mandar link
//   · F5 recarrega e cai na MESMA aba (antes caía numa tela inconsistente)
//   · botão voltar/avançar do navegador navega entre as abas
//   · o alerta da Melhoria 3 pode apontar direto para a aba do supervisor
//
// O que ele NÃO faz: bypass de login (rota só se aplica com S.user) e bypass
// das abas restritas (não-admin cai em #semana, como o launch já fazia).
// ─────────────────────────────────────────────────────────────────────────────

// hash (bonito, estável, minúsculo) ↔ slug interno do setTopView
const ROTAS = {
  'semana':        'semana',
  'religamentos':  'religamentos',
  'gestao-pcm':    'gestaoPcm',
  'gestao-mpas':   'gestaoMpas',
  'garantia':      'chamadosGarantia',
  'performance':   'performance',
  'engenharia':    'engenharia',
  'verificacao':   'emVerificacao',
  'sugestoes':     'sugestoesIA',
};
const HASH_DE = {};
Object.keys(ROTAS).forEach(h => { HASH_DE[ROTAS[h]] = h; });

// mesmas abas que o launch() esconde de não-admin (Task #130) — manter em sincronia
const ROTAS_ADMIN = ['religamentos', 'emVerificacao', 'sugestoesIA', 'gestaoMpas'];

let _navAplicando = false;   // true enquanto a rota está sendo aplicada (evita eco)

// ── setTopView passa a publicar a aba no hash ────────────────────────────────
const _setTopViewOrig = setTopView;
setTopView = function (v) {
  _setTopViewOrig(v);
  const h = HASH_DE[S.topView];
  // pushState não dispara hashchange → sem loop; e cria entrada de histórico,
  // que é o que faz o botão voltar funcionar entre abas
  if (h && !_navAplicando && location.hash !== '#' + h) {
    try { history.pushState(null, '', '#' + h); } catch (e) {}
  }
};

function _rotaDoHash() {
  const h = (location.hash || '').replace(/^#/, '').split('?')[0];
  return ROTAS[h] || null;
}

function _aplicarRota() {
  if (!S.user) return;                       // antes do login o hash só espera
  let slug = _rotaDoHash();
  if (!slug) return;
  if (!S.isAdmin && ROTAS_ADMIN.indexOf(slug) >= 0) {
    slug = 'semana';                         // não-admin não entra em aba restrita
    try { history.replaceState(null, '', '#semana'); } catch (e) {}
  }
  if (slug !== S.topView) {
    _navAplicando = true;
    try { setTopView(slug); } finally { _navAplicando = false; }
  }
}

// clique nas âncoras do <nav> e voltar/avançar do navegador chegam por aqui
window.addEventListener('hashchange', _aplicarRota);

// ── pós-login: aplica a rota da URL; sem rota, publica a aba salva ──────────
const _launchOrig = launch;
launch = function (label, isAdmin) {
  _launchOrig(label, isAdmin);
  if (_rotaDoHash()) {
    _aplicarRota();
  } else {
    // reaplica a aba salva no localStorage — o launch original só trocava a
    // variável, e depois de um F5 a tela ficava inconsistente com S.topView
    _navAplicando = true;
    try { setTopView(S.topView); } finally { _navAplicando = false; }
    const h = HASH_DE[S.topView];
    if (h) { try { history.replaceState(null, '', '#' + h); } catch (e) {} }
  }
};
