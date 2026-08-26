// Recebe o aviso de que o painel nao conseguiu montar a tela.
//
// Por que existe: o /api/dados registra que a carga foi ENTREGUE, nao que ela
// foi RENDERIZADA. Se a API devolve 200 e o JavaScript quebra depois, do lado
// do servidor parece sucesso e o usuario fica olhando para um erro. Foi
// exatamente assim que a falha do papel cliente passou despercebida ate o
// cliente mandar um print.
//
// Regras: nunca falha de volta (um relator que quebra a pagina e pior que nao
// ter relator), e nunca confia no texto recebido — ele vira log.

function principalDe(req) {
  try {
    const h = req.headers['x-ms-client-principal'];
    if (!h) return null;
    return JSON.parse(Buffer.from(h, 'base64').toString('utf8'));
  } catch (e) {
    return null;
  }
}

// texto de usuario vai para o log: tira quebra de linha (que forjaria uma
// entrada nova) e limita o tamanho.
function limpar(v, max) {
  return String(v == null ? '' : v)
    .replace(/[\r\n\t]+/g, ' ')
    .slice(0, max);
}

module.exports = async function (context, req) {
  try {
    const p = principalDe(req);
    const quem = (p && (p.userDetails || p.userId)) || 'anonimo';
    const papeis = ((p && p.userRoles) || [])
      .filter(r => r !== 'anonymous' && r !== 'authenticated');
    const b = (req && req.body) || {};

    context.log('falha-painel: ' + quem +
                ' | papeis=' + (papeis.join(',') || '-') +
                ' | onde=' + limpar(b.onde, 40) +
                ' | msg=' + limpar(b.mensagem, 300));
  } catch (e) {
    // nem o relator pode derrubar a pagina de quem ja esta com problema
    try { context.log.error('falha-painel: relator falhou: ' + (e && e.message)); } catch (_) {}
  }
  context.res = { status: 204 };
};
