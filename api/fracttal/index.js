// ============================================================================
// AMORTECEDOR DO WEBHOOK DO FRACTTAL
//
// O Fracttal chama aqui quando uma tarefa é finalizada (evento WO_TASK_FINISHED,
// via Integrações → conexão HTTP + regra no Dispatcher). Esta função decide se
// vale acordar o robô, e chama o repository_dispatch do GitHub quando vale.
//
// POR QUE EXISTE — o caminho direto seria Fracttal → GitHub, e é armadilha:
// na Semana 34 foram 723 tarefas finalizadas em 5 dias, ~145/dia. A 6 min por
// rodada, isso daria ~14 h de execução por dia. Pior que o cron, que faz ~38.
//
// O que ela faz: agrupa a rajada. No máximo um disparo a cada JANELA_MIN
// minutos — e NENHUM quando não houve mudança, o que o cron não sabe fazer.
//
// Resultado esperado: durante o expediente, latência cai de ~38 min para ~10.
// À noite e no fim de semana, o robô simplesmente não roda.
// ============================================================================

const https = require('https');
const { URL } = require('url');

const JANELA_MIN = 10;      // mínimo entre dois disparos
const REPO = 'fillipefigueiro-source/gridco-pcm-data';
const TIPO = 'fracttal-mudou';   // casa com `types:` no semanal.yml

// ─── Blob: onde guardamos o horário do último disparo ────────────────────────
// Mesmo container do cadastro de acessos, arquivo separado. A URL vem em base64
// pelo mesmo motivo da outra: no Windows o `az` é um .cmd e o cmd.exe corta o
// valor no primeiro `&` do SAS — aconteceu em 19/08, gravou 89 de ~230 chars.
function urlDoBlob() {
  const b64 = process.env.ACESSOS_BLOB_URL_B64;
  if (!b64) throw new Error('ACESSOS_BLOB_URL_B64 não configurada');
  const u = Buffer.from(String(b64).trim(), 'base64').toString('utf8').trim();
  // Mesmo container, outro arquivo.
  return u.replace('/acessos.json?', '/_ultimo_disparo.json?');
}

function pedir(metodo, url, corpo, cabecalhos) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const dados = corpo == null ? null : Buffer.from(corpo, 'utf8');
    const req = https.request({
      method: metodo, hostname: u.hostname, path: u.pathname + u.search,
      headers: Object.assign({}, dados ? { 'Content-Length': dados.length } : {}, cabecalhos || {}),
    }, (res) => {
      let t = '';
      res.setEncoding('utf8');
      res.on('data', (d) => { t += d; });
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, texto: t }));
    });
    req.on('error', reject);
    req.setTimeout(10000, () => req.destroy(new Error('timeout')));
    if (dados) req.write(dados);
    req.end();
  });
}

async function lerUltimo() {
  const r = await pedir('GET', urlDoBlob(), null, { 'x-ms-version': '2021-08-06' });
  if (r.status === 404) return { quando: 0, etag: null };
  if (r.status !== 200) throw new Error('Blob respondeu ' + r.status);
  try {
    const d = JSON.parse(r.texto || '{}');
    return { quando: Number(d.quando) || 0, etag: r.headers.etag || null };
  } catch (e) { return { quando: 0, etag: r.headers.etag || null }; }
}

// Grava com If-Match. Duas chamadas simultâneas do Fracttal leem o mesmo horário
// e ambas decidem disparar; o If-Match faz a segunda perder (412) e desistir.
// Sem isso, uma rajada viraria dois disparos em vez de um.
async function marcarDisparo(etag) {
  const cab = {
    'x-ms-version': '2021-08-06',
    'x-ms-blob-type': 'BlockBlob',
    'Content-Type': 'application/json; charset=utf-8',
  };
  if (etag) cab['If-Match'] = etag; else cab['If-None-Match'] = '*';
  const corpo = JSON.stringify({ quando: Date.now(), em: new Date().toISOString() });
  const r = await pedir('PUT', urlDoBlob(), corpo, cab);
  if (r.status === 412) return false;      // outro ganhou a corrida
  if (r.status !== 201) throw new Error('Blob recusou a escrita (' + r.status + ')');
  return true;
}

async function acordarRobo() {
  const tok = process.env.GITHUB_DISPATCH_TOKEN;
  if (!tok) throw new Error('GITHUB_DISPATCH_TOKEN não configurado');
  const r = await pedir('POST', `https://api.github.com/repos/${REPO}/dispatches`,
    JSON.stringify({ event_type: TIPO }), {
      'Authorization': 'Bearer ' + tok,
      'Accept': 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'Content-Type': 'application/json',
      'User-Agent': 'gridco-pcm-amortecedor',
    });
  // 204 é o sucesso do endpoint dispatches. Qualquer outra coisa é problema, e
  // precisa aparecer: token vencido devolve 401 e falharia calado.
  if (r.status !== 204) throw new Error(`GitHub respondeu ${r.status}: ${r.texto.slice(0, 200)}`);
}

module.exports = async function (context, req) {
  const responder = (status, corpo) => {
    context.res = { status, headers: { 'Content-Type': 'application/json' }, body: corpo };
  };

  // ─── Quem está chamando ───────────────────────────────────────────────────
  // Esta rota é anônima (o Fracttal não faz login), então o segredo compartilhado
  // é a ÚNICA barreira. Comparação de tamanho antes, para não vazar o
  // comprimento por tempo de resposta.
  const esperado = process.env.FRACTTAL_WEBHOOK_SEGREDO || '';
  const veio = String((req.headers && (req.headers['x-gridco-segredo'] || req.headers['X-Gridco-Segredo'])) || '');
  if (!esperado) {
    context.log.error('fracttal: FRACTTAL_WEBHOOK_SEGREDO não configurado — recusando tudo');
    return responder(503, { erro: 'webhook não configurado' });
  }
  if (veio.length !== esperado.length || veio !== esperado) {
    context.log.error('fracttal: segredo inválido');
    return responder(401, { erro: 'não autorizado' });
  }

  try {
    const { quando, etag } = await lerUltimo();
    const decorrido = Date.now() - quando;
    const faltam = JANELA_MIN * 60000 - decorrido;

    if (quando && faltam > 0) {
      // Dentro da janela: nada a fazer. Devolve 200 de propósito — 429 faria o
      // Fracttal tratar como erro e possivelmente desativar a regra.
      const min = Math.ceil(faltam / 60000);
      context.log(`fracttal: agrupado (faltam ~${min} min para a janela)`);
      return responder(200, { ok: true, acao: 'agrupado', faltamMin: min });
    }

    if (!(await marcarDisparo(etag))) {
      context.log('fracttal: outra chamada disparou primeiro');
      return responder(200, { ok: true, acao: 'agrupado', motivo: 'corrida' });
    }

    await acordarRobo();
    context.log('fracttal: robô acordado via repository_dispatch');
    return responder(200, { ok: true, acao: 'disparado' });
  } catch (e) {
    // Erro aparece com o motivo. Webhook que falha calado é a pior combinação:
    // o Fracttal continua chamando, ninguém vê, e o painel fica velho sem sinal.
    context.log.error('fracttal: ' + (e && e.message));
    return responder(500, { erro: String((e && e.message) || e) });
  }
};
