// ─────────────────────────────────────────────────────────────────────────────
// /api/dados — Melhoria 5, FASE 2: filtro por papel NO SERVIDOR (decisão 25)
// Criado em 18/08/2026.
//
// Por que existe: na fase 1 o cliente autentica, mas o banco_dados.json que
// chega ao navegador dele é o arquivo COMPLETO — a visão dele é filtrada só
// na tela. Um usuário curioso abriria o arquivo bruto e leria os outros
// clientes. Esta função devolve a cada papel apenas o que é dele:
//
//   admin / equipe  -> o arquivo completo, como está
//   cli-<cliente>   -> só as linhas daquele cliente; blocos internos
//                      (alertas, qualidade, rolagem, motivos) removidos;
//                      resumo restrito aos clusters que aparecem nas linhas
//   sem papel       -> 403
//
// A identidade vem do cabeçalho x-ms-client-principal, que o PRÓPRIO Azure
// injeta depois de validar a sessão — o navegador não consegue forjá-lo.
//
// O dado é embutido no deploy: o workflow copia o banco_dados.json do
// repositório para api/data/ antes de subir. O robô commita o JSON a cada
// ~54 min e cada push redeploya — a mesma cadência de atualização de hoje.
// ─────────────────────────────────────────────────────────────────────────────
const fs = require('fs');
const path = require('path');

const PAPEL_CLIENTE = {
  'cli-2c': '2C', 'cli-alves-lima': 'Alves Lima', 'cli-athon': 'Athon',
  'cli-axis': 'Axis', 'cli-gd-energy': 'GD Energy', 'cli-greenyellow': 'Greenyellow',
  'cli-renogrid': 'RenoGrid', 'cli-sal-energia': 'Sal Energia', 'cli-semp': 'Semp',
  'cli-thopen': 'Thopen', 'cli-utragaz': 'Utragaz',
};


function principalDe(req) {
  try {
    const h = req.headers['x-ms-client-principal'];
    if (!h) return null;
    return JSON.parse(Buffer.from(h, 'base64').toString('utf8'));
  } catch (e) {
    return null;
  }
}

function carregarBase() {
  const p = path.join(__dirname, '..', 'data', 'banco_dados.json');
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

// ATENÇÃO a quem for manter: a proteção aqui é por LISTA DE PERMISSÃO — só os
// campos explicitamente copiados abaixo saem para o cliente. Não existe (nem
// deve existir) lista de exclusão: blocos internos como alertas, qualidade,
// rolagem e motivos ficam de fora por NÃO estarem nesta lista, e qualquer bloco
// novo do banco_dados.json também fica, por padrão.
// NUNCA troque isto por um spread do objeto base ({...base, rows}) — seria o
// caminho para vazar um bloco novo sem ninguém perceber.
function filtrarParaCliente(base, cliente) {
  const saida = { geradoEm: base.geradoEm, cliente: cliente, semanas: [] };
  for (const w of base.semanas || []) {
    const rows = (w.rows || []).filter(r => String(r.cliente || '') === cliente);
    const clusters = new Set(rows.map(r => r.cluster).filter(Boolean));
    const resumo = {};
    for (const [k, v] of Object.entries(w.resumo || {})) {
      if (clusters.has(k)) resumo[k] = v;
    }
    saida.semanas.push({
      week: w.week, num: w.num, label: w.label, dates: w.dates,
      resumo: resumo, rows: rows,
    });
  }
  return saida;
}

module.exports = async function (context, req) {
  const p = principalDe(req);
  const roles = ((p && p.userRoles) || [])
    .filter(r => r !== 'anonymous' && r !== 'authenticated');

  const resposta = (status, body) => {
    context.res = {
      status: status,
      headers: { 'Content-Type': 'application/json; charset=utf-8',
                 'Cache-Control': 'no-store' },
      body: JSON.stringify(body),
    };
  };

  // registro de acesso: uma linha por carga do painel, para saber quem entrou e
  // quando. Vai para o Application Insights (privado) — nunca para o repositório,
  // que é público.
  const registrar = (forma, extra) => {
    const quem = (p && (p.userDetails || p.userId)) || 'anonimo';
    context.log('acesso: ' + quem + ' | forma=' + forma +
                ' | papeis=' + (roles.join(',') || '-') +
                (extra ? ' | ' + extra : ''));
  };

  if (!p) { registrar('nao-autenticado'); resposta(401, { erro: 'não autenticado' }); return; }

  let base;
  try {
    base = carregarBase();
  } catch (e) {
    registrar('erro-dado');
    resposta(500, { erro: 'dado indisponível no deploy — verifique o passo de cópia no workflow' });
    return;
  }

  if (roles.includes('admin') || roles.includes('equipe')) {
    registrar('completo');
    resposta(200, base);
    return;
  }
  const papelCli = roles.find(r => PAPEL_CLIENTE[r]);
  if (papelCli) {
    registrar('cliente', 'cliente=' + PAPEL_CLIENTE[papelCli]);
    resposta(200, filtrarParaCliente(base, PAPEL_CLIENTE[papelCli]));
    return;
  }
  registrar('sem-papel');
  resposta(403, { erro: 'conta autenticada sem papel neste painel — peça o convite ao PCM' });
};
