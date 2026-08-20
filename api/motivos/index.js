// ─────────────────────────────────────────────────────────────────────────────
// /api/motivos — grava o motivo escolhido no painel na Observação da OS
// no Fracttal. Criado em 20/08/2026 (pedido do PCM).
//
// POR QUE UMA FUNÇÃO: o painel é estático. O navegador não pode carregar a
// credencial do Fracttal, então a escrita passa por aqui, onde o segredo fica
// em app setting e a identidade de quem pediu vem assinada pelo Azure.
//
// LINHA GRAVADA (formato definido pelo PCM):
//     [dd/mm/aaaa] - [título da tarefa] - motivo
//
// CONTRATO DA ESCRITA NO FRACTTAL (descoberto por sondagem — ver o .md ao lado):
//     PUT /work_orders/{WO_FOLIO}   {"note": <texto COMPLETO>, "account_code": "02"}
//   · o path é o FOLIO, não o id_work_order
//   · account_code é código de PESSOA (02 = Fabricio); a alteração fica atribuída a ele
//   · valor vazio é recusado ("note is required") — não dá para limpar por aqui
//   · só grava em OS com status 1 (em processo) ou 2 (em revisão)
//
// A escrita SUBSTITUI o campo inteiro: não existe append nativo. Por isso é
// sempre ler → concatenar → gravar, e a leitura é feita IMEDIATAMENTE antes do
// PUT. Se o texto mudou nesse intervalo, aborta em vez de sobrescrever quem
// estava editando no Fracttal — o campo é usado à mão pelo time de campo.
// ─────────────────────────────────────────────────────────────────────────────

const FX_BASE = process.env.FRACTTAL_BASE_URL || 'https://app.fracttal.com/';
const FX_API = process.env.FRACTTAL_API_BASE || 'https://app.fracttal.com/api/';
const ACCOUNT_CODE = process.env.FRACTTAL_ACCOUNT_CODE || '02';
const STATUS_GRAVAVEL = [1, 2];          // em processo / em revisão

let _tok = null, _exp = 0;

async function token() {
  if (_tok && Date.now() < _exp) return _tok;
  const id = process.env.FRACTTAL_CLIENT_ID, sec = process.env.FRACTTAL_CLIENT_SECRET;
  if (!id || !sec) throw new Error('FRACTTAL_CLIENT_ID/SECRET não configurados no SWA');
  const basic = Buffer.from(`${id}:${sec}`).toString('base64');
  const r = await fetch(FX_BASE.replace(/\/$/, '') + '/oauth/token', {
    method: 'POST',
    headers: {
      'Authorization': 'Basic ' + basic,
      'Content-Type': 'application/x-www-form-urlencoded',
      'Accept': 'application/json',
    },
    body: 'grant_type=client_credentials',
  });
  if (!r.ok) throw new Error('falha ao autenticar no Fracttal: HTTP ' + r.status);
  const j = await r.json();
  _tok = j.access_token || j.token;
  _exp = Date.now() + ((j.expires_in || 3600) - 60) * 1000;
  return _tok;
}

async function fx(path, method, body) {
  const t = await token();
  const r = await fetch(FX_API.replace(/\/$/, '') + '/' + path.replace(/^\//, ''), {
    method: method || 'GET',
    headers: {
      'Authorization': 'Bearer ' + t,
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let j;
  try { j = await r.json(); } catch (e) { j = { _texto: await r.text().catch(() => '') }; }
  return { status: r.status, ok: r.ok, body: j };
}

async function lerOS(folio) {
  const r = await fx('work_orders?wo_folio=' + encodeURIComponent(folio) + '&limit=1&page=1');
  if (!r.ok) return null;
  const d = (r.body && r.body.data) || [];
  return d.length ? d[0] : null;
}

function doisDig(n) { return String(n).padStart(2, '0'); }

// A data é a do fuso de Brasília, não a do servidor (que roda em East US 2).
// Sem isso, tudo que fosse gravado depois das 21h daqui sairia com a data do
// dia seguinte — justamente na janela em que o motivo é preenchido.
function hojeBRT() {
  const agora = new Date(Date.now() - 3 * 3600 * 1000);   // BRT = UTC-3, sem horário de verão
  return `${doisDig(agora.getUTCDate())}/${doisDig(agora.getUTCMonth() + 1)}/${agora.getUTCFullYear()}`;
}

function prefixoLinha(tarefa) {
  return `[${hojeBRT()}] - [${String(tarefa || '').trim()}] - `;
}

function montarLinha(tarefa, motivo) {
  return prefixoLinha(tarefa) + String(motivo || '').trim();
}

// Monta a Observação nova ACRESCENTANDO a linha e preservando tudo o que já
// estava lá — inclusive outra linha do mesmo dia para a mesma tarefa.
//
// Isto foi decidido pelo PCM em 20/08 e é uma regra de negócio, não descuido:
// a MESMA tarefa pode não ter sido feita por DOIS motivos no mesmo dia (faltou
// equipamento E choveu). Substituir perderia metade da explicação. A única
// coisa que nunca duplica é a linha idêntica (mesma data, tarefa e motivo) —
// isso é tratado antes de chegar aqui.
//
// O texto escrito à mão pelo time de campo nunca é tocado.
function textoFinal(atual, linha) {
  const base = String(atual || '').replace(/\s+$/, '');
  return base ? base + '\n' + linha : linha;
}

function principalDe(req) {
  try {
    const h = req.headers['x-ms-client-principal'];
    if (!h) return null;
    return JSON.parse(Buffer.from(h, 'base64').toString('utf8'));
  } catch (e) { return null; }
}

// Grava UM motivo. Devolve {os, ok, estado, detalhe}.
async function gravarUm(item, log) {
  const folio = String(item.os || '').trim();
  const tarefa = String(item.tarefa || '').trim();
  const motivo = String(item.motivo || '').trim();
  if (!folio || !tarefa || !motivo) {
    return { os: folio, tarefa, ok: false, estado: 'incompleto',
             detalhe: 'os, tarefa e motivo são obrigatórios' };
  }

  const wo = await lerOS(folio);
  if (!wo) return { os: folio, tarefa, ok: false, estado: 'nao_encontrada',
                    detalhe: 'OS não encontrada no Fracttal' };

  const st = Number(wo.id_status_work_order);
  const atual = wo.note || '';
  const linha = montarLinha(tarefa, motivo);

  // idempotente: reenviar a mesma linha não duplica
  if (atual.indexOf(linha) >= 0) {
    return { os: folio, tarefa, ok: true, estado: 'ja_estava', detalhe: linha };
  }
  if (STATUS_GRAVAVEL.indexOf(st) < 0) {
    return { os: folio, tarefa, ok: false, estado: 'fechada',
             detalhe: `a OS está com status ${st}; o Fracttal só aceita edição em processo ou em revisão` };
  }

  const final = textoFinal(atual, linha);

  // relê imediatamente antes de gravar: janela mínima para não atropelar
  // quem estiver editando a Observação pela tela do Fracttal
  const conf = await lerOS(folio);
  if ((conf && conf.note ? conf.note : '') !== atual) {
    return { os: folio, tarefa, ok: false, estado: 'conflito',
             detalhe: 'a Observação mudou durante a gravação; não sobrescrevi' };
  }

  const put = await fx('work_orders/' + encodeURIComponent(folio), 'PUT',
                       { note: final, account_code: ACCOUNT_CODE });
  if (!put.ok || (put.body && put.body.success === false)) {
    const err = (put.body && put.body.data && put.body.data[0] && put.body.data[0].ERROR)
             || (put.body && put.body.message) || ('HTTP ' + put.status);
    log(`motivos: FALHA os=${folio} — ${err}`);
    return { os: folio, tarefa, ok: false, estado: 'erro_fracttal', detalhe: String(err) };
  }
  log(`motivos: gravado os=${folio} tarefa="${tarefa}"`);
  return { os: folio, tarefa, ok: true, estado: 'gravado', detalhe: linha };
}

module.exports = async function (context, req) {
  const responder = (status, body) => {
    context.res = {
      status,
      headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' },
      body: JSON.stringify(body),
    };
  };
  const log = (m) => { try { context.log(m); } catch (e) {} };

  // O Azure injeta a identidade já validada; o navegador não consegue forjá-la.
  const p = principalDe(req);
  const papeis = ((p && p.userRoles) || []).filter(r => r !== 'anonymous' && r !== 'authenticated');
  if (!p) return responder(401, { erro: 'não autenticado' });
  if (!papeis.includes('admin') && !papeis.includes('equipe')) {
    // cliente NUNCA escreve no Fracttal — a aba nem aparece para ele
    return responder(403, { erro: 'sem permissão para registrar motivo' });
  }

  const corpo = req.body || {};
  const itens = Array.isArray(corpo.itens) ? corpo.itens
              : (corpo.os ? [corpo] : []);
  if (!itens.length) return responder(400, { erro: 'nada para gravar' });
  if (itens.length > 50) return responder(400, { erro: 'no máximo 50 motivos por chamada' });

  const res = [];
  for (const it of itens) {                 // em série: o Fracttal não gosta de rajada
    try {
      res.push(await gravarUm(it, log));
    } catch (e) {
      log('motivos: exceção — ' + (e && e.message));
      res.push({ os: String(it.os || ''), tarefa: String(it.tarefa || ''),
                 ok: false, estado: 'excecao', detalhe: String((e && e.message) || e) });
    }
  }
  const okN = res.filter(r => r.ok).length;
  responder(200, { total: res.length, gravados: okN, falhas: res.length - okN, itens: res });
};
