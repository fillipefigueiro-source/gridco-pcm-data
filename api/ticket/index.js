// Tickets e relatórios do módulo Confiabilidade — persistência no repositório.
//
// Por que aqui e não em localStorage: o ticket é de quem assume, e quem assume
// não é quem abriu. Estado que vive no navegador de uma pessoa não é gestão.
// Por que no repositório e não no Blob (como os acessos): decisão do PCM em
// 03/09/2026 — o histórico de commits vira a trilha de auditoria de graça.
//
// Arquivo: engenharia/tickets.json — numa SUBPASTA de propósito. O deploy do
// SWA dispara em "*.json" da raiz; um commit por clique redeployaria o painel
// inteiro a cada ticket assumido.
//
// Token: o mesmo GITHUB_DISPATCH_TOKEN do /api/acordar. repository_dispatch já
// exige escrita em conteúdo, então o token serve. Se um dia trocarem por um
// token só de dispatch, o PUT devolve 403 e a tela avisa — não falha calado.
//
// Concorrência: cada escrita é ler → aplicar a operação → gravar com o sha
// lido. Dois engenheiros ao mesmo tempo: o segundo leva 409, relê e reaplica.
// Por isso o painel manda OPERAÇÕES (um ticket, um relatório), nunca o estado
// inteiro — mandar tudo faria o último a salvar apagar o que o outro fez.

const REPO = process.env.GITHUB_REPO || 'fillipefigueiro-source/gridco-pcm-data';
const ARQ = process.env.TICKETS_ARQUIVO || 'engenharia/tickets.json';
const RAMO = process.env.TICKETS_RAMO || 'main';
const MAX_CORPO = 200 * 1024;
const TENTATIVAS = 4;

function principalDe(req) {
  try {
    const h = req.headers['x-ms-client-principal'];
    if (!h) return null;
    return JSON.parse(Buffer.from(h, 'base64').toString('utf8'));
  } catch (e) {
    return null;
  }
}

// Texto que vai para o arquivo E para o log: sem controle, tamanho limitado.
const limpar = (v, n) => String(v == null ? '' : v).replace(/[\r\n\t]+/g, ' ').slice(0, n || 200);

function cabecalhos(tok) {
  return {
    'Authorization': 'Bearer ' + tok,
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'gridco-pcm-painel',
  };
}

async function ler(tok) {
  const r = await fetch('https://api.github.com/repos/' + REPO + '/contents/' + ARQ + '?ref=' + RAMO,
    { headers: cabecalhos(tok) });
  if (r.status === 404) return { estado: { versao: 1, tickets: [], relatorios: [] }, sha: null };
  if (!r.ok) throw new Error('GitHub leu ' + r.status);
  const j = await r.json();
  const txt = Buffer.from(j.content || '', 'base64').toString('utf8');
  let estado;
  try { estado = JSON.parse(txt); } catch (e) { estado = { versao: 1, tickets: [], relatorios: [] }; }
  estado.tickets = Array.isArray(estado.tickets) ? estado.tickets : [];
  estado.relatorios = Array.isArray(estado.relatorios) ? estado.relatorios : [];
  return { estado, sha: j.sha };
}

async function gravar(tok, estado, sha, mensagem, quem) {
  const corpo = {
    message: mensagem,
    content: Buffer.from(JSON.stringify(estado, null, 1), 'utf8').toString('base64'),
    branch: RAMO,
    committer: { name: 'pcm-painel', email: 'pcm-painel@users.noreply.github.com' },
  };
  if (sha) corpo.sha = sha;
  const r = await fetch('https://api.github.com/repos/' + REPO + '/contents/' + ARQ, {
    method: 'PUT', headers: Object.assign({ 'Content-Type': 'application/json' }, cabecalhos(tok)),
    body: JSON.stringify(corpo),
  });
  return r;
}

// Normaliza um ticket vindo do painel: só os campos que existem, tamanhos
// limitados. O `a` (objeto do ativo) nunca entra — vai só o código.
function normalizarTicket(t) {
  if (!t || typeof t !== 'object') return null;
  const ETAPAS = ['detectado', 'notificado', 'analise', 'acao', 'verificado'];
  return {
    id: limpar(t.id, 12),
    cod: limpar(t.cod, 40),
    etapa: ETAPAS.includes(t.etapa) ? t.etapa : 'detectado',
    resp: limpar(t.resp, 60) || '—',
    prazo: limpar(t.prazo, 10),
    nota: limpar(t.nota, 2000),
    reinc: Math.max(0, Math.min(99, parseInt(t.reinc, 10) || 0)),
    abertoEm: limpar(t.abertoEm, 25),
    assumidoEm: t.assumidoEm ? limpar(t.assumidoEm, 25) : null,
    atualizadoEm: new Date().toISOString(),
    hist: (Array.isArray(t.hist) ? t.hist : []).slice(-60).map(h => ({
      q: limpar(h.q, 60), t: limpar(h.t, 60), d: limpar(h.d, 25) })),
  };
}

function normalizarRelatorio(r) {
  if (!r || typeof r !== 'object') return null;
  return {
    n: limpar(r.n, 20), tipo: limpar(r.tipo, 20), rev: limpar(r.rev, 6),
    cod: limpar(r.cod, 40), data: limpar(r.data, 10), autor: limpar(r.autor, 80),
    rpn: r.rpn == null ? null : (parseInt(r.rpn, 10) || null),
    st: limpar(r.st, 20) || 'emitido',
    emitidoEm: new Date().toISOString(),
    campos: (Array.isArray(r.campos) ? r.campos : []).slice(0, 80).map(c => limpar(c, 600)),
  };
}

function proximoId(tickets) {
  const n = tickets.reduce((m, t) => Math.max(m, parseInt(String(t.id).slice(3), 10) || 0), 100) + 1;
  return 'TK-' + String(n).padStart(4, '0');
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
  // Só admin e equipe. O cliente não vê o processo — vê o resultado.
  if (!papeis.includes('admin') && !papeis.includes('equipe')) {
    return responder(403, { erro: 'sem acesso a tickets' });
  }
  const quem = limpar((p && p.userDetails) || '', 80);

  const tok = process.env.GITHUB_DISPATCH_TOKEN;
  if (!tok) {
    context.log.error('ticket: GITHUB_DISPATCH_TOKEN não configurado');
    return responder(500, { erro: 'o token do GitHub não está configurado no SWA' });
  }

  try {
    if (req.method === 'GET') {
      const { estado } = await ler(tok);
      return responder(200, estado);
    }
    if (req.method !== 'POST') return responder(405, { erro: 'método' });

    const bruto = typeof req.body === 'string' ? req.body : JSON.stringify(req.body || {});
    if (bruto.length > MAX_CORPO) return responder(413, { erro: 'corpo grande demais' });
    const op = typeof req.body === 'string' ? JSON.parse(req.body) : (req.body || {});

    let resultado = null;
    for (let tent = 1; tent <= TENTATIVAS; tent++) {
      const { estado, sha } = await ler(tok);
      let mensagem;

      if (op.op === 'ticket') {
        const t = normalizarTicket(op.ticket);
        if (!t || !t.cod) return responder(400, { erro: 'ticket sem código de ativo' });
        if (!t.id || t.id === 'novo') t.id = proximoId(estado.tickets);
        const i = estado.tickets.findIndex(x => x.id === t.id);
        if (i >= 0) {
          // conserva o que o painel não manda (abertoEm original)
          t.abertoEm = t.abertoEm || estado.tickets[i].abertoEm;
          estado.tickets[i] = t;
        } else {
          t.abertoEm = t.abertoEm || new Date().toISOString();
          estado.tickets.push(t);
        }
        mensagem = 'pcm: ticket ' + t.id + ' · ' + t.etapa + ' · ' + (t.resp || '—') + ' · por ' + quem;
        resultado = { ticket: t };
      } else if (op.op === 'relatorio') {
        const r = normalizarRelatorio(op.relatorio);
        if (!r || !r.cod || !r.n) return responder(400, { erro: 'relatório sem número ou ativo' });
        if (estado.relatorios.some(x => x.n === r.n)) {
          // número já usado por outro engenheiro no mesmo minuto: renumera
          const pref = r.n.replace(/-\d+$/, '');
          const n = estado.relatorios.filter(x => x.n.startsWith(pref)).length + 1;
          r.n = pref + '-' + String(n).padStart(4, '0');
        }
        estado.relatorios.unshift(r);
        mensagem = 'pcm: ' + r.n + ' emitido · ' + r.cod + ' · por ' + quem;
        resultado = { relatorio: r };
      } else {
        return responder(400, { erro: 'operação desconhecida' });
      }

      estado.versao = 1;
      estado.atualizadoEm = new Date().toISOString();
      estado.atualizadoPor = quem;
      const r = await gravar(tok, estado, sha, mensagem, quem);
      if (r.ok) {
        context.log('ticket: ' + mensagem);
        return responder(200, Object.assign({ ok: true, estado }, resultado));
      }
      if (r.status === 409 || r.status === 422) {
        context.log.warn('ticket: conflito de sha (tentativa ' + tent + ')');
        await new Promise(res => setTimeout(res, 300 * tent));
        continue;
      }
      const t = await r.text().catch(() => '');
      context.log.error('ticket: GitHub respondeu ' + r.status + ': ' + t.slice(0, 200));
      return responder(502, { erro: 'o GitHub recusou a gravação (HTTP ' + r.status + ')' });
    }
    return responder(409, { erro: 'muita gente salvando ao mesmo tempo — tente de novo' });
  } catch (e) {
    context.log.error('ticket: ' + (e && e.message));
    return responder(502, { erro: 'falha ao falar com o GitHub: ' + limpar(e && e.message, 120) });
  }
};
