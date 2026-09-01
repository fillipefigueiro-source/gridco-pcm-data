// Acorda o robô da Programação Semanal sob demanda, a pedido do painel.
//
// Por que existe: o robô roda de 15 em 15 min. Quando alguém mexe no Fracttal e
// quer ver agora, resta esperar. Este endpoint dispara o mesmo
// `repository_dispatch` que o /api/fracttal já usa — a máquina é a dele, o
// gatilho é que passa a ser humano.
//
// O cliente do GitHub é cópia do padrão de api/fracttal/index.js, que está no ar
// e validado. Aquele arquivo não pode ser alterado, então foi copiado.
//
// LIMITE conhecido: só o semanal.yml escuta este evento. O gestao-pcm.yml não,
// então a Gestão PCM continua no ciclo dela. O painel diz isso na tela — não
// adianta o botão prometer o que o pipeline não entrega.

const REPO = process.env.GITHUB_REPO || 'fillipefigueiro-source/gridco-pcm-data';
const TIPO = process.env.FRACTTAL_DISPATCH_TIPO || 'fracttal-mudou';

function principalDe(req) {
  try {
    const h = req.headers['x-ms-client-principal'];
    if (!h) return null;
    return JSON.parse(Buffer.from(h, 'base64').toString('utf8'));
  } catch (e) {
    return null;
  }
}

module.exports = async function (context, req) {
  const responder = (status, body) => {
    context.res = {
      status: status,
      headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' },
      body: JSON.stringify(body),
    };
  };

  const p = principalDe(req);
  const papeis = ((p && p.userRoles) || []).filter(r => r !== 'anonymous' && r !== 'authenticated');
  if (!p) return responder(401, { erro: 'não autenticado' });

  // Só admin. Isto dispara o pipeline inteiro: decisão do PCM em 01/09/2026.
  // A equipe recarrega o que já foi publicado; acordar o robô é do admin.
  if (!papeis.includes('admin')) {
    return responder(403, { erro: 'só o admin pode acordar o robô' });
  }

  const tok = process.env.GITHUB_DISPATCH_TOKEN;
  if (!tok) {
    context.log.error('acordar: GITHUB_DISPATCH_TOKEN não configurado');
    return responder(500, { erro: 'o token de disparo não está configurado no SWA' });
  }

  try {
    const r = await fetch('https://api.github.com/repos/' + REPO + '/dispatches', {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + tok,
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'Content-Type': 'application/json',
        'User-Agent': 'gridco-pcm-painel',
      },
      body: JSON.stringify({ event_type: TIPO }),
    });

    // 204 é o sucesso do endpoint dispatches. Qualquer outra coisa precisa
    // aparecer: um token vencido devolve 401 e falharia calado, e o usuário
    // ficaria esperando sete minutos por nada.
    if (r.status !== 204) {
      const t = await r.text().catch(() => '');
      context.log.error('acordar: GitHub respondeu ' + r.status + ': ' + t.slice(0, 200));
      return responder(502, { erro: 'o GitHub recusou o pedido (HTTP ' + r.status + ')' });
    }

    context.log('acordar: robô acordado por ' + ((p && p.userDetails) || '?'));
    responder(200, {
      ok: true,
      quem: (p && p.userDetails) || '',
      em: new Date().toISOString(),
      aviso: 'só a Programação Semanal; a Gestão PCM segue o ciclo dela',
    });
  } catch (e) {
    context.log.error('acordar: ' + (e && e.message));
    responder(502, { erro: 'não foi possível falar com o GitHub agora' });
  }
};
