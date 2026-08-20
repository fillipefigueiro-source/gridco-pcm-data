// ─────────────────────────────────────────────────────────────────────────────
// auth.js — Melhoria 5: login Microsoft via Azure Static Web Apps (18/08/2026)
// Script clássico, carrega DEPOIS de app.js/navegacao.js, mesmo escopo global.
//
// MODO DUPLO, de propósito (decisão 28 — o corte do acesso antigo é o ÚLTIMO
// passo): enquanto o site for servido pelo GitHub Pages, /.auth/me não existe
// e este arquivo NÃO muda nada — a tela de senha atual continua valendo.
// Quando o mesmo repositório passar a ser servido pelo Azure SWA, /.auth/me
// responde, e aí o login vira Microsoft de verdade:
//   papel "admin"   -> visão Admin completa (a tela de senha some)
//   papel "equipe"  -> leitura interna: todos os clientes, sem abas restritas
//   papel "cli-*"   -> a visão daquele cliente (decisões 26/27)
//   sem papel       -> autenticou mas não foi convidado: aviso, sem dados
//                      (as rotas dos .json também bloqueiam no servidor)
// ─────────────────────────────────────────────────────────────────────────────

const AUTH_CLI = {
  'cli-2c': '2C', 'cli-alves-lima': 'Alves Lima', 'cli-athon': 'Athon',
  'cli-axis': 'Axis', 'cli-gd-energy': 'GD Energy', 'cli-greenyellow': 'Greenyellow',
  'cli-renogrid': 'RenoGrid', 'cli-sal-energia': 'Sal Energia', 'cli-semp': 'Semp',
  'cli-thopen': 'Thopen', 'cli-utragaz': 'Utragaz',
};

let AUTH_PRINCIPAL = null;   // preenchido quando o SWA responde

// Devolve: o principal (logado) | 'EXPIRADO' (no SWA, sem sessao) | null (legado).
// A distincao entre 'EXPIRADO' e null e o ponto todo: os dois davam null e o
// painel caia na tela de senha antiga, que no SWA nao funciona -- os .json sao
// restritos por papel, entao o fetch tomava 302, vinha HTML e a tela dizia
// "Falha ao carregar", sem pista de que era so refazer o login. (20/08/2026)
async function authDescobrir() {
  try {
    const r = await fetch('/.auth/me', { cache: 'no-store' });
    // o SWA mandou para o login: estamos NELE e a sessao caiu
    if (r.redirected && String(r.url || '').indexOf('/.auth/login') >= 0) return 'EXPIRADO';
    if (r.status === 404) return null;               // Pages/local: a rota nao existe
    if (!r.ok) return null;
    const ct = r.headers.get('content-type') || '';
    if (ct.indexOf('json') < 0) return null;         // Pages devolve o 404 em HTML
    const j = await r.json();
    if (j && j.clientPrincipal) return j.clientPrincipal;
    return 'EXPIRADO';                               // respondeu JSON, mas sem ninguem logado
  } catch (e) {
    return null;                                     // file:// ou servidor local
  }
}

function authIrParaLogin() {
  // preserva a aba em que a pessoa estava (o hash), para voltar no mesmo lugar
  const volta = encodeURIComponent(location.pathname + location.search + location.hash);
  location.replace('/.auth/login/aad?post_login_redirect_uri=' + volta);
}

function authAvisoSemPapel(email) {
  const err = document.getElementById('l-err');
  if (err) {
    err.style.display = 'block';
    err.textContent = 'Sua conta (' + email + ') autenticou, mas ainda não tem papel ' +
      'neste painel. Peça o convite ao PCM da Grid Co.';
  }
}

async function authEntrar(p) {
  AUTH_PRINCIPAL = p;
  const roles = (p.userRoles || []).filter(x => x !== 'anonymous' && x !== 'authenticated');
  const cliRole = roles.find(x => AUTH_CLI[x]);
  if (!roles.includes('admin') && !roles.includes('equipe') && !cliRole) {
    authAvisoSemPapel(p.userDetails || '');
    return;                                          // fica na tela, sem dados
  }
  // FASE 2 (decisão 25 — filtro no servidor): no SWA, TODOS os papéis leem os
  // dados por /api/dados; o cliente recebe do servidor apenas as linhas dele.
  // No Pages/local não há /api, e CONFIG.JSON_URL continua o arquivo estático.
  CONFIG.JSON_URL = '/api/dados';
  await loadDB();
  if (roles.includes('admin')) {
    S.isAdmin = true; S.user = 'Admin';
    // a chave da Gestão MPAS continua sendo pedida na aba (o mpas.json é cifrado)
    launch('Grid Co. — Todos os Clientes', true);
  } else if (roles.includes('equipe')) {
    S.isAdmin = false; S.user = 'Grid Co.';
    launch('Grid Co. — Leitura interna', false);
  } else {
    const nome = AUTH_CLI[cliRole];
    S.isAdmin = false; S.user = nome;
    launch(nome, false);
  }
  // Sair passa a encerrar a sessão Microsoft, não só a variável local
  const _logoutOrig = (typeof doLogout === 'function') ? doLogout : null;
  window.doLogout = function () {
    if (_logoutOrig) try { _logoutOrig(); } catch (e) {}
    location.href = '/.auth/logout?post_logout_redirect_uri=/';
  };
}

(async function authBoot() {
  const p = await authDescobrir();
  if (p === 'EXPIRADO') { authIrParaLogin(); return; }   // sessao caiu: refaz o login
  if (!p) return;                                    // modo legado (Pages/local): nada muda
  // espera o app.js terminar de declarar as funções de boot
  for (let i = 0; i < 40 && typeof launch !== 'function'; i++) {
    await new Promise(r => setTimeout(r, 100));
  }
  if (typeof launch === 'function') await authEntrar(p);
})();
