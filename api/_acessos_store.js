// ============================================================================
// CADASTRO DE ACESSOS DE CLIENTE — leitura e escrita
//
// Guarda o cadastro "e-mail X vê cliente Y" num único JSON no Blob Storage.
// Não fica no repositório: são e-mails de pessoas, e o repositório é público.
//
// Usa o módulo `https` do Node, não `fetch`. É mais código, mas o `fetch` global
// só existe do Node 18 em diante e este arquivo roda no caminho do LOGIN — se o
// runtime for mais antigo, ninguém entra. Não vale a economia de dez linhas.
//
// A URL com o SAS vem da app setting ACESSOS_BLOB_URL. Ela é credencial: não
// aparece em log, não vai para o cliente, não entra no repositório.
// ============================================================================

const https = require('https');
const { URL } = require('url');

// Os 11 papéis que o painel conhece (AUTH_CLI em js/auth.js). Cadastro fora
// desta lista é erro, não papel novo.
const CLIENTES = {
  'cli-2c': '2C',
  'cli-alves-lima': 'Alves Lima',
  'cli-athon': 'Athon',
  'cli-axis': 'Axis',
  'cli-gd-energy': 'GD Energy',
  'cli-greenyellow': 'Greenyellow',
  'cli-renogrid': 'RenoGrid',
  'cli-sal-energia': 'Sal Energia',
  'cli-semp': 'Semp',
  'cli-thopen': 'Thopen',
  'cli-utragaz': 'Utragaz',
};

function pedir(metodo, url, corpo, cabecalhos) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const dados = corpo == null ? null : Buffer.from(corpo, 'utf8');
    const req = https.request({
      method: metodo,
      hostname: u.hostname,
      path: u.pathname + u.search,
      headers: Object.assign(
        { 'x-ms-version': '2021-08-06' },
        dados ? { 'Content-Length': dados.length } : {},
        cabecalhos || {}
      ),
    }, (res) => {
      let txt = '';
      res.setEncoding('utf8');
      res.on('data', (d) => { txt += d; });
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, texto: txt }));
    });
    req.on('error', reject);
    req.setTimeout(10000, () => req.destroy(new Error('timeout no Blob')));
    if (dados) req.write(dados);
    req.end();
  });
}

// A URL vem preferencialmente em BASE64 (ACESSOS_BLOB_URL_B64).
//
// Não é capricho: no Windows o `az` é um .cmd, e o cmd.exe reinterpreta o
// argumento — os `&` que separam os parâmetros do SAS viram separadores de
// comando e o valor chega TRUNCADO no primeiro `&`. Aconteceu em 19/08: a
// gravação "funcionou", devolveu 200, e guardou 89 dos ~230 caracteres.
// O alfabeto do base64 não tem `&`, então o problema some na origem.
//
// ACESSOS_BLOB_URL em texto puro continua aceita, para quem gravar pelo portal.
function urlDoBlob() {
  const b64 = process.env.ACESSOS_BLOB_URL_B64;
  if (b64) {
    const u = Buffer.from(String(b64).trim(), 'base64').toString('utf8').trim();
    if (!/^https:\/\//.test(u)) throw new Error('ACESSOS_BLOB_URL_B64 não decodifica para uma URL https');
    return u;
  }
  const u = process.env.ACESSOS_BLOB_URL;
  if (!u) throw new Error('ACESSOS_BLOB_URL_B64 (ou ACESSOS_BLOB_URL) não configurada no SWA');
  // Guarda contra o truncamento acima: SAS sem assinatura não serve para nada,
  // e falhar aqui com o motivo é melhor que um 403 sem explicação no login.
  if (u.includes('?') && !u.includes('sig=')) {
    throw new Error('ACESSOS_BLOB_URL parece truncada (sem sig=) — regrave usando ACESSOS_BLOB_URL_B64');
  }
  return u;
}

// Devolve { acessos: [...], etag } — o etag é usado na escrita para não
// atropelar quem salvou no intervalo.
async function ler() {
  const r = await pedir('GET', urlDoBlob());
  if (r.status === 404) return { acessos: [], etag: null };   // ainda não existe
  if (r.status !== 200) throw new Error('Blob respondeu ' + r.status);
  let d;
  try { d = JSON.parse(r.texto || '{}'); } catch (e) { throw new Error('cadastro corrompido: ' + e.message); }
  return { acessos: Array.isArray(d.acessos) ? d.acessos : [], etag: r.headers.etag || null };
}

// Escreve de volta. Se `etag` vier, exige que o arquivo não tenha mudado desde
// a leitura (If-Match) — duas pessoas cadastrando ao mesmo tempo não se
// sobrescrevem em silêncio. É o mesmo cuidado que o Fabrício pôs na escrita da
// Observação da OS no Fracttal.
async function gravar(acessos, etag) {
  const corpo = JSON.stringify({ acessos, atualizadoEm: new Date().toISOString() }, null, 2);
  const cab = {
    'x-ms-blob-type': 'BlockBlob',
    'Content-Type': 'application/json; charset=utf-8',
  };
  if (etag) cab['If-Match'] = etag;
  const r = await pedir('PUT', urlDoBlob(), corpo, cab);
  if (r.status === 412) throw new Error('CONFLITO: alguém salvou enquanto você editava — recarregue e refaça');
  if (r.status !== 201) throw new Error('Blob recusou a escrita (' + r.status + ')');
  return true;
}

const normalizar = (e) => String(e || '').trim().toLowerCase();

module.exports = { CLIENTES, ler, gravar, normalizar };
