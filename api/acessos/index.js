// ============================================================================
// CADASTRO DE ACESSOS DE CLIENTE — a API por trás da tela
//
// GET    /api/acessos              lista o cadastro + os clientes disponíveis
// POST   /api/acessos {email,papel} cadastra ou atualiza
// DELETE /api/acessos {email}       remove
//
// SÓ ADMIN. A identidade vem do cabeçalho x-ms-client-principal, que o Azure
// injeta DEPOIS de validar a sessão — o navegador não forja. Nunca confiar em
// nada que o corpo da requisição diga sobre quem é o usuário.
// ============================================================================

const { CLIENTES, ler, gravar, normalizar } = require('../_acessos_store');

const RE_EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;

function quemE(req) {
  const b64 = (req.headers && (req.headers['x-ms-client-principal'] || req.headers['X-MS-CLIENT-PRINCIPAL'])) || '';
  if (!b64) return null;
  try {
    const p = JSON.parse(Buffer.from(b64, 'base64').toString('utf8'));
    return {
      email: normalizar(p.userDetails),
      papeis: Array.isArray(p.userRoles) ? p.userRoles : [],
    };
  } catch (e) { return null; }
}

module.exports = async function (context, req) {
  const responder = (status, corpo) => {
    context.res = { status, headers: { 'Content-Type': 'application/json' }, body: corpo };
  };

  const eu = quemE(req);
  if (!eu) return responder(401, { erro: 'sem identidade — faça login' });
  if (!eu.papeis.includes('admin')) {
    // Deliberadamente não diz "você é cli-x": quem não pode não precisa saber
    // como o controle funciona.
    return responder(403, { erro: 'só administradores podem gerir acessos' });
  }

  try {
    if (req.method === 'GET') {
      const { acessos } = await ler();
      return responder(200, {
        acessos: acessos.sort((a, b) => (a.email || '').localeCompare(b.email || '')),
        clientes: Object.entries(CLIENTES).map(([papel, nome]) => ({ papel, nome })),
      });
    }

    const corpo = req.body || {};
    const email = normalizar(corpo.email);

    if (req.method === 'POST') {
      if (!RE_EMAIL.test(email)) return responder(400, { erro: 'e-mail inválido' });
      const papel = String(corpo.papel || '').trim().toLowerCase();
      if (!CLIENTES[papel]) return responder(400, { erro: 'cliente desconhecido: ' + papel });

      // Conta da Grid não se cadastra como cliente: ela já entra pelo tenant, e
      // o cadastro seria ignorado pela função de papéis (interno vence). Deixar
      // cadastrar criaria uma linha que não faz nada — e alguém confiaria nela.
      if (email.endsWith('@gridco.com.br')) {
        return responder(400, { erro: 'conta da Grid já tem acesso pelo login Microsoft — não precisa de cadastro' });
      }

      const { acessos, etag } = await ler();
      const i = acessos.findIndex((a) => normalizar(a.email) === email);
      const registro = {
        email,
        papel,
        cliente: CLIENTES[papel],
        por: eu.email,
        quando: new Date().toISOString(),
      };
      const acao = i >= 0 ? 'atualizado' : 'cadastrado';
      if (i >= 0) acessos[i] = registro; else acessos.push(registro);
      await gravar(acessos, etag);
      context.log(`acessos: ${acao} ${email} -> ${papel} (por ${eu.email})`);
      return responder(200, { ok: true, acao, registro });
    }

    if (req.method === 'DELETE') {
      const { acessos, etag } = await ler();
      const restantes = acessos.filter((a) => normalizar(a.email) !== email);
      if (restantes.length === acessos.length) return responder(404, { erro: 'e-mail não estava cadastrado' });
      await gravar(restantes, etag);
      context.log(`acessos: removido ${email} (por ${eu.email})`);
      return responder(200, { ok: true, acao: 'removido' });
    }

    return responder(405, { erro: 'método não suportado' });
  } catch (e) {
    context.log.error('acessos: ' + (e && e.message));
    // A mensagem sai para a tela de propósito: erro mudo aqui vira "salvei e não
    // salvou", que é pior que erro feio.
    return responder(500, { erro: String((e && e.message) || e) });
  }
};
