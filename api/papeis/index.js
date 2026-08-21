// ============================================================================
// ATRIBUIÇÃO DE PAPÉIS NO LOGIN  —  substitui o sistema de convites
//
// O Azure chama esta função UMA VEZ a cada login bem-sucedido, com a identidade
// já validada, e usa o que ela devolver como os papéis do usuário na sessão.
// Configurada em staticwebapp.config.json via  "auth": { "rolesSource": ... }
//
// ATENÇÃO — enquanto o rolesSource estiver ligado, os CONVITES SÃO IGNORADOS.
// Se esta função quebrar, o login CONTINUA funcionando e a pessoa entra com zero
// papéis: o sintoma fica idêntico ao de quem nunca foi convidado, sem erro em
// lugar nenhum (o catch do runtime em volta desta chamada é vazio — achado do
// Fabrício, 19/08). Por isso existe o papel-sentinela `vivo`, abaixo.
//
// REGRA (nesta ordem, primeira que casar vence):
//   1. Tenant da Grid, não-convidado                -> admin
//   2. E-mail cadastrado para exatamente UM cliente -> cli-<cliente>
//   3. Qualquer outro                                -> nenhum papel
// ============================================================================

const TENANT_GRID = '70958e9f-5279-4fff-9577-93c88901a19e';

// O cadastro de clientes agora mora no Blob e é editado pela tela /acessos.html
// (api/acessos). A lista branca dos 11 papéis vem do mesmo módulo, para não
// existirem duas listas que possam divergir em silêncio — que foi o achado A do
// Fabrício em outra roupagem.
const { CLIENTES, ler, normalizar } = require('../_acessos_store');
const PAPEIS_CLIENTE = new Set(Object.keys(CLIENTES));

// Papel-sentinela: sai em TODO login que passa por esta função, inclusive quem
// não tem papel nenhum. É o que distingue "não cadastrado" de "a função não
// rodou". Sem ele os dois casos são indistinguíveis no /.auth/me, e quem for
// investigar vai procurar um convite em vez de procurar um bug.
// Inerte: nenhuma rota do staticwebapp.config.json o referencia.
const SENTINELA = 'vivo';

// Tipos de claim aceitos, EXATOS. Nada de endsWith: `urn:qualquercoisa/tenantid`
// casaria, e um claim forjado antes do canônico venceria a disputa. (achado D)
const CLAIM_TENANT = [
  'http://schemas.microsoft.com/identity/claims/tenantid',
  'tid',
];
const CLAIM_EMAIL = [
  'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress',
  'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn',
  'email',
  'preferred_username',
  'upn',
];

function lista(valor) {
  return String(valor || '')
    .split(/[,;\s]+/)
    .map(s => s.trim().toLowerCase())
    .filter(Boolean);
}

// Devolve TODOS os valores distintos para os tipos aceitos. Plural de propósito:
// se vier mais de um tenant diferente, isso é ambiguidade e quem chama decide
// fechar — em vez de pegar o primeiro e seguir.
function valoresDoClaim(claims, tipos) {
  const aceitos = new Set(tipos.map(t => t.toLowerCase()));
  const vistos = [];
  for (const c of claims) {
    const t = String((c && c.typ) || '').toLowerCase();
    const v = String((c && c.val) || '').trim();
    if (v && aceitos.has(t) && !vistos.includes(v)) vistos.push(v);
  }
  return vistos;
}

// Escolhe pela ORDEM DOS TIPOS, não pela ordem em que os claims chegaram.
// A diferença importa para convidado B2B: o UPN dele é a forma mutilada
// `joao_thopen.com.br#EXT#@gridco.onmicrosoft.com`, e se ela vencer o
// `emailaddress` o cadastro de cliente nunca casa. Percorrer o array de claims
// pegaria o que viesse primeiro; percorrer os tipos pega o que vale mais.
function primeiroPorPrioridade(claims, tipos) {
  for (const tipo of tipos) {
    const alvo = tipo.toLowerCase();
    for (const c of claims) {
      const t = String((c && c.typ) || '').toLowerCase();
      const v = String((c && c.val) || '').trim();
      if (v && t === alvo) return v;
    }
  }
  return '';
}

// Convidado B2B carrega o tenantid do tenant ANFITRIÃO — ou seja, um convidado
// externo no tenant da Grid passaria na checagem de tenant e viraria `equipe`,
// com acesso ao dado de todos os clientes. O UPN de convidado tem a marca #EXT#.
function ehConvidado(claims) {
  const upns = valoresDoClaim(claims, ['http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn', 'upn', 'preferred_username']);
  return upns.some(u => u.toLowerCase().includes('#ext#'));
}

// Devolve TODOS os cadastros em que o e-mail aparece. Plural de propósito: se
// aparecer em dois, o cadastro está ambíguo e escolher "o primeiro" seria
// decidir por ordem de arquivo. Fecha em vez de adivinhar. (achado B)
async function clientesDoEmail(email) {
  if (!email) return [];
  const { acessos } = await ler();          // se o Blob falhar, propaga e fecha
  return acessos
    .filter((a) => normalizar(a.email) === email)
    .map((a) => ({ variavel: 'cadastro', papel: String(a.papel || '').toLowerCase() }));
}

module.exports = async function (context, req) {
  let papeis = [];
  let motivo = '';

  try {
    const corpo  = req.body || {};
    const claims = Array.isArray(corpo.claims) ? corpo.claims : [];

    const tenants = valoresDoClaim(claims, CLAIM_TENANT);
    const email   = (primeiroPorPrioridade(claims, CLAIM_EMAIL) || corpo.userDetails || '')
                      .trim().toLowerCase();

    if (tenants.length > 1) {
      // Mais de um tenant no mesmo token não é cenário legítimo. Fecha e grita.
      motivo = `ambíguo: ${tenants.length} claims de tenant distintos`;
      context.log.error('papeis: ' + motivo);
    } else if (tenants.length === 1 && tenants[0].toLowerCase() === TENANT_GRID) {
      if (ehConvidado(claims)) {
        // Convidado B2B no tenant da Grid não é da Grid. Cai para a regra de
        // cliente: se estiver cadastrado, entra como cliente; senão, nada.
        const c = await clientesDoEmail(email);
        if (c.length === 1 && PAPEIS_CLIENTE.has(c[0].papel)) {
          papeis = [c[0].papel];
          motivo = 'convidado B2B, cadastrado como cliente';
        } else {
          motivo = 'convidado B2B sem cadastro de cliente';
        }
      } else {
        // Todo o tenant da Grid recebe `admin` — decisão do Fillipe, 19/08/2026.
        // Inclui as quatro abas internas (Religamentos, Em Verificação,
        // Sugestões IA, Gestão MPAS). Não há mais distinção admin/equipe para
        // quem é da Grid: a variável PAPEL_ADMINS deixou de ser lida e foi
        // apagada do SWA, para não ficar configuração morta sugerindo controle
        // que não existe.
        //
        // `equipe` continua definido nas rotas e no painel, e continua sendo o
        // papel certo para quem só consulta. Hoje ninguém o recebe.
        papeis = ['admin'];
        motivo = 'tenant Grid';
      }
    } else if (email) {
      const achados = await clientesDoEmail(email);
      if (achados.length > 1) {
        motivo = `ambíguo: ${email} cadastrado para ${achados.length} clientes`;
        context.log.error('papeis: ' + motivo);
      } else if (achados.length === 1) {
        const { papel } = achados[0];
        if (PAPEIS_CLIENTE.has(papel)) {
          papeis = [papel];
          motivo = 'cadastro de cliente';
        } else {
          // Erro de digitação no nome da variável. O papel "existiria" e o
          // painel não o reconheceria — o pior dos dois mundos.
          motivo = `papel "${papel}" desconhecido — cadastro inválido para ${email}`;
          context.log.error('papeis: ' + motivo);
        }
      } else {
        motivo = 'e-mail não cadastrado';
      }
    } else {
      motivo = 'login sem e-mail utilizável';
    }
  } catch (e) {
    // Falha fecha. Conceder por engano não aparece nunca; negar aparece na hora.
    papeis = [];
    motivo = 'erro: ' + (e && e.message);
    context.log.error('papeis: falha ao resolver —', e);
  }

  // O sentinela entra SEMPRE — inclusive quando não há papel. É o único jeito de
  // distinguir, depois, "não cadastrado" de "a função nem rodou".
  const saida = papeis.concat(SENTINELA);
  context.log(`papeis: ${papeis.join(',') || '(nenhum)'} — ${motivo}`);

  context.res = {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    body: { roles: saida }
  };
};
