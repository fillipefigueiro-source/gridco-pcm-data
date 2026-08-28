// Detalhe de uma OS, direto do Fracttal, para a gaveta lateral do painel.
//
// Por que existe: o gestao_pcm.json tem 20 mil tarefas e, para caber, guarda só
// o essencial de cada uma. A Observação, quem criou, os ativos envolvidos e a
// trilha de execução (com pausas e motivos) não estão lá e não devem estar —
// engordariam um arquivo que já tem 9,7 MB e que todo mundo baixa. Aqui é sob
// demanda: uma consulta quando o usuário abre a gaveta.
//
// O cliente do Fracttal é cópia do padrão de api/motivos/index.js, validado em
// produção. Aquele arquivo não pode ser alterado, então foi copiado, não
// importado.

const FX_BASE = process.env.FRACTTAL_BASE || 'https://one.fracttal.com';
const FX_API  = process.env.FRACTTAL_API  || 'https://app.fracttal.com/api';

let _tok = null, _exp = 0;

async function token() {
  if (_tok && Date.now() < _exp) return _tok;
  const id = process.env.FRACTTAL_CLIENT_ID, sec = process.env.FRACTTAL_CLIENT_SECRET;
  if (!id || !sec) throw new Error('FRACTTAL_CLIENT_ID/SECRET não configurados no SWA');
  const basic = Buffer.from(id + ':' + sec).toString('base64');
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

async function fx(caminho) {
  const t = await token();
  const r = await fetch(FX_API.replace(/\/$/, '') + '/' + caminho.replace(/^\//, ''), {
    headers: { 'Authorization': 'Bearer ' + t, 'Accept': 'application/json' },
  });
  let j = null;
  try { j = await r.json(); } catch (e) { j = null; }
  return { ok: r.ok, status: r.status, body: j };
}

function principalDe(req) {
  try {
    const h = req.headers['x-ms-client-principal'];
    if (!h) return null;
    return JSON.parse(Buffer.from(h, 'base64').toString('utf8'));
  } catch (e) {
    return null;
  }
}

const STATUS = { 1: 'Em processo', 2: 'Em verificação', 3: 'Finalizada', 4: 'Cancelada' };
const PRIOR  = { 1: 'Muito alta', 2: 'Alta', 3: 'Média', 4: 'Baixa', 5: 'Muito baixa' };
// O Fracttal devolve o estado da tarefa em código (NO_STARTED, IN_PROGRESS…).
// O painel mostra em português em toda parte; traduzir aqui evita que cada tela
// invente a sua tabela.
const ESTADO = {
  NO_STARTED: 'Não Iniciada', NOT_STARTED: 'Não Iniciada',
  IN_PROGRESS: 'Em progresso', PAUSED: 'Pausada',
  DONE: 'Finalizada', STOPPED: 'Parada', CANCELLED: 'Cancelada',
};
const dia = s => (s ? String(s).slice(0, 10) : '');

// O Fracttal devolve o ativo como "Nome   { CODIGO }". Separar deixa a gaveta legível.
function partirAtivo(s) {
  const m = String(s || '').match(/^(.*?)\s*\{\s*([^}]+)\s*\}\s*$/);
  if (m) return { nome: m[1].trim().replace(/\s{2,}/g, ' '), codigo: m[2].trim() };
  return { nome: String(s || '').trim().replace(/\s{2,}/g, ' '), codigo: '' };
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

  // A gaveta vive na Gestão PCM, que é tela de admin (TELAS_ADMIN no novo.html).
  // A trava aqui repete isso no servidor: sem ela bastaria chamar a URL na mão
  // para um cliente ler a operação inteira, OS por OS.
  if (!papeis.includes('admin') && !papeis.includes('equipe')) {
    return responder(403, { erro: 'sem permissão para ver o detalhe da OS' });
  }

  const folio = String((req.query && req.query.folio) || '').trim();
  if (!/^[0-9A-Za-z._-]{1,32}$/.test(folio)) {
    return responder(400, { erro: 'folio inválido' });
  }

  try {
    const wo = await fx('work_orders?wo_folio=' + encodeURIComponent(folio) + '&limit=1&page=1');
    const cab = (wo.ok && wo.body && wo.body.data && wo.body.data[0]) || null;
    if (!cab) return responder(404, { erro: 'OS não encontrada no Fracttal' });

    const idWO = cab.id_work_order || cab.id;

    // As TAREFAS da OS saem do mesmo recurso, mas com o folio no CAMINHO —
    // `work_orders?wo_folio=` (acima) devolve o cabeçalho da OS, `work_orders/{folio}`
    // devolve a lista de tarefas. São formas diferentes do mesmo endpoint; confundir
    // as duas devolve a coisa errada sem erro nenhum.
    //
    // A trilha de execução (início / pausa com motivo / retomada) NÃO entra aqui:
    // `tasks_iterations` é sobre ciclos do plano, não sobre esses eventos, e não
    // achei o caminho público que os sirva. A linha do tempo é montada com as datas
    // que existem. Quando o caminho certo aparecer, é só acrescentar.
    const tk = await fx('work_orders/' + encodeURIComponent(folio) + '?limit=100');

    const tarefas = ((tk.ok && tk.body && tk.body.data) || []).map(t => ({
      tarefa: t.description || t.tasks_description || '',
      estado: ESTADO[t.task_status] || t.task_status || '',
      ativo: partirAtivo(t.items_log_description || t.items_description || ''),
      prog: dia(t.date_maintenance),
      inicio: dia(t.initial_date),
      fim: dia(t.final_date),
      resp: (t.personnel_description || '').trim(),
      tipo: t.tasks_types_description || t.tasks_log_types_description || '',
      prioridade: PRIOR[t.id_priorities] || '',
      duracao: t.tasks_duration || 0,
      duracaoReal: t.real_duration || 0,
      observacao: t.task_note || '',
      etiquetas: Array.isArray(t.labels) ? t.labels.filter(Boolean) : [],
      feita: !!t.done,
    }));
    // Se a consulta de tarefas falhar, a gaveta ainda abre com o cabeçalho: é
    // melhor mostrar metade do que uma tela de erro sobre uma OS que existe.
    const tarefasOk = !!tk.ok;

    // Ativos: o cabeçalho nem sempre traz items_log_descriptions (medido vazio na
    // OS 10345, que tem três ativos). Cada tarefa carrega o seu, então a lista sai
    // dali, sem repetir, e o cabeçalho serve só de reforço.
    const vistos = new Set(), ativos = [];
    const juntar = a => {
      if (!a || (!a.nome && !a.codigo)) return;
      const k = a.codigo || a.nome;
      if (vistos.has(k)) return;
      vistos.add(k); ativos.push(a);
    };
    tarefas.forEach(t => juntar(t.ativo));
    (cab.items_log_descriptions || []).forEach(x => juntar(partirAtivo(x)));

    responder(200, {
      os: folio,
      idWO: idWO,
      status: STATUS[cab.id_status_work_order] || '',
      observacao: cab.note || '',
      pct: typeof cab.completed_percentage === 'number' ? cab.completed_percentage : null,
      criadaPor: cab.created_by || '',
      responsavel: (cab.personnel_description || '').trim(),
      criacao: dia(cab.creation_date),
      programada: dia(cab.date_maintenance || cab.cal_date_maintenance),
      primeiraTarefa: dia(cab.first_date_task),
      fechamento: dia(cab.wo_final_date),
      duracao: cab.duration || 0,
      avaliacao: cab.rating || null,
      ativos: ativos,
      tarefas: tarefas,
      tarefasOk: tarefasOk,
      url: FX_BASE.replace(/\/$/, '') + '/tasks/wo/' + encodeURIComponent(idWO),
    });
  } catch (e) {
    context.log.error('os: ' + (e && e.message));
    responder(502, { erro: 'não foi possível consultar o Fracttal agora' });
  }
};
