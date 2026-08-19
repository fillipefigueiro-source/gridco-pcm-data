// Extraído de index.html em 13/08/2026 (Melhoria 0.10, Fase 2).
// Script CLÁSSICO (não-módulo) de propósito: os ~100 onclick inline do HTML
// dependem de escopo global, e strict mode quebraria atribuições legadas.
// A conversão para módulos ES é a Fase 4 do plano (PROPOSTA_Painel_Modular.md).
const CONFIG = {
  // Path relativo (= mesma origem do dashboard, fillipefigueiro-source.github.io)
  // raw.githubusercontent.com pode ser bloqueado por firewall corporativo
  JSON_URL: "banco_dados.json",
  SUGESTOES_URL: "sugestoes.json",
  ETIQUETAS_URL: "etiquetas.json",
  GESTAO_URL: "gestao_pcm.json",
  CONFIAB_URL: "confiabilidade.json",
  // Link p/ abrir a OT no Fracttal. O Fracttal One NÃO tem deep-link por OT
  // (a URL colapsa p/ /tasks/wo). Decisão: abrir o módulo de OS; usuário busca
  // o número (mostrado no card). Suporta {id}/{folio} se um dia houver deep-link.
  GESTAO_WO_URL: "https://one.fracttal.com/tasks/wo",
  SUPERVISORES_URL: "supervisores.json",
  REFRESH_MS: 300000,
  // Painel local (Streamlit) — botão "Aceitar" abre essa URL com ?ss=NUMERO
  PAINEL_LOCAL_URL: "http://localhost:8501",
};
let SUGESTOES_DB=[];
let ETIQUETAS_DB=null;
let SUPERVISORES_DB={porCluster:{},porEquipe:{},lista:[]};

async function sha256(str) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str));
  return Array.from(new Uint8Array(buf)).map(b=>b.toString(16).padStart(2,'0')).join('');
}

const LS  = { P:'gc_p', A:'gc_a', V:'gc_view' };
const lsG = (k,fb) => { try { const v=localStorage.getItem(k); return v?JSON.parse(v):fb; } catch { return fb; } };
const lsS = (k,v)  => { try { localStorage.setItem(k,JSON.stringify(v)); } catch {} };

const DEF_PWDS = JSON.parse(document.getElementById('gc-pwds').textContent);
// Mapa login → nome real do cliente no banco (para logins sem espaço como "gdenergy" → "GD Energy")
const LOGIN_ALIASES = JSON.parse(document.getElementById('gc-aliases')?.textContent || '{}');

// Helper global: escapa HTML (usado em varios geradores de strings)
function fmtMTTR(h){
  // Aceita horas como número (ex: 0.0625) e devolve hh:mm
  if(h==null || isNaN(h)) return '--';
  const totalMin = Math.round(Number(h) * 60);
  const hh = Math.floor(totalMin/60);
  const mm = totalMin % 60;
  return hh + ':' + (mm<10?'0':'') + mm;
}

function esc(s){
  return String(s==null?'':s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

let DB=null, timer=null;
let S = {
  pwds:    DEF_PWDS,
  active:  lsG(LS.A, ''),
  user:    null, isAdmin:false, viewCli:null,
  fEquipe:'', fTipo:'', fUsina:'', fSupervisor:'', fStatus:'', fSS:'', fEtq:'',
  view:    lsG(LS.V, 'semana'), // 'semana' | 'mes'
  topView: (function(){try{return localStorage.getItem('gc_topv')||'semana';}catch(e){return 'semana';}})(),
};

const ADMIN_ID = 'admin';
const HH_DISP  = 44;
const DAYS   = ['Segunda-feira','Ter\u00e7a-feira','Quarta-feira','Quinta-feira','Sexta-feira'];
const DSHORT = {'Segunda-feira':'SEG','Ter\u00e7a-feira':'TER','Quarta-feira':'QUA','Quinta-feira':'QUI','Sexta-feira':'SEX'};
const TC = {'MPM':'#6366f1','MPS':'#0ea5e9','Corretiva':'#e53e3e','OUTRA':'#f59e0b','Zeladoria':'#10b981','MPA':'#f97316','MPM-Mod/Tracker':'#8b5cf6','MPM-Inversor':'#3b82f6'};
const TB = {'MPM':'#f0f0ff','MPS':'#f0f9ff','Corretiva':'#fff5f5','OUTRA':'#fffbeb','Zeladoria':'#f0fdf4','MPA':'#fff7ed','MPM-Mod/Tracker':'#faf5ff','MPM-Inversor':'#eff6ff'};
const TK = {'MPM':'tMPM','MPS':'tMPS','Corretiva':'tCorr','OUTRA':'tOUT','Zeladoria':'tZel','MPA':'tMPA','MPM-Mod/Tracker':'tMod','MPM-Inversor':'tInv'};
const TL = {'MPM':'Prev. Mensal','MPS':'Prev. Semestral','Corretiva':'Corretiva','OUTRA':'Outra','Zeladoria':'Zeladoria','MPA':'Prev. Anual','MPM-Mod/Tracker':'Mod/Tracker','MPM-Inversor':'Inversor'};
const TD = {'MPM':'Manut. Preventiva Mensal','MPS':'Manut. Preventiva Semestral','Corretiva':'Ordem Corretiva','OUTRA':'Atividade especial','Zeladoria':'Zeladoria','MPA':'Manut. Preventiva Anual','MPM-Mod/Tracker':'Prev. Mod./Trackers','MPM-Inversor':'Prev. de Inversores'};
const MESES = ['Janeiro','Fevereiro','Mar\u00e7o','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
const MESES_S = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];

// ── LOAD DB ──────────────────────────────────────────────────────────────────
async function loadDB(silent=false) {
  if (!silent) setStatus('Buscando dados...','loading');
  try {
    const res = await fetch(CONFIG.JSON_URL+'?t='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(10000)});
    if (!res.ok) throw new Error('HTTP '+res.status);
    const data = await res.json();
    // Passwords come from index.html only — ignore pwds from JSON
    // if (data.pwds) { S.pwds=Object.assign({},data.pwds,lsG(LS.P,{})); lsS(LS.P,S.pwds); }
    DB=data;
    if (!S.active&&data.semana_ativa) S.active=data.semana_ativa;
    statusHeartbeat();                      // 0.4: idade real do dado, n\u00e3o hora do fetch
    if(!window._hbTimer) window._hbTimer=setInterval(statusHeartbeat,60000);
    return true;
  } catch(err) {
    if (!silent) setStatus('\u26a0 Falha: '+err.message,'warn');
    return false;
  }
}

async function loadSugestoes(){
  try{
    const res=await fetch(CONFIG.SUGESTOES_URL+'?t='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(10000)});
    if(!res.ok){SUGESTOES_DB=[]; return false;}
    SUGESTOES_DB=await res.json();
    if(!Array.isArray(SUGESTOES_DB)) SUGESTOES_DB=SUGESTOES_DB.sugestoes||SUGESTOES_DB.data||[];
    return true;
  }catch(e){
    SUGESTOES_DB=[];
    return false;
  }
}
async function loadSupervisores(){
  // FIX #159: carrega mapa cluster -> supervisor (gerado por gerar_supervisores_json.py)
  try{
    const res=await fetch(CONFIG.SUPERVISORES_URL+'?t='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(10000)});
    if(!res.ok){SUPERVISORES_DB={porCluster:{},porEquipe:{},lista:[]}; return false;}
    const j=await res.json();
    SUPERVISORES_DB={porCluster:j.porCluster||{}, porEquipe:j.porEquipe||{}, lista:j.lista||[]};
    return true;
  }catch(e){
    SUPERVISORES_DB={porCluster:{},porEquipe:{},lista:[]};
    return false;
  }
}
function setStatus(msg,type) {
  const el=document.getElementById('refresh-status'); if(!el) return;
  const cols={loading:'#A9DB21',ok:'#22c55e',warn:'#f59e0b',err:'#ef4444'};
  el.innerHTML='<span style="color:'+(cols[type]||cols.ok)+'">'+msg+'</span>';
}
// ---- Heartbeat do robô (0.4) ----
// A barra verde mostrava a hora do FETCH do navegador — parecia fresco mesmo
// com o dado 2h velho. Agora mostra a idade do geradoEm do banco_dados.json.
// Régua medida no robô real: intervalo mediano 54 min, máximo observado 140.
function statusHeartbeat(){
  const g=DB&&DB.geradoEm?new Date(DB.geradoEm):null;
  if(!g||isNaN(g)){setStatus('✓ Atualizado às '+new Date().toLocaleTimeString('pt-BR'),'ok');return;}
  const min=Math.max(0,Math.round((Date.now()-g.getTime())/60000));
  const idade=min<60?min+' min':Math.floor(min/60)+'h'+String(min%60).padStart(2,'0');
  const hora=g.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});
  if(min>240)setStatus('⚠ Dados de '+hora+' · há '+idade+' — robô parado? Verifique o Actions','err');
  else if(min>120)setStatus('⚠ Dados de '+hora+' · há '+idade+' — acima do normal (~1h)','warn');
  else setStatus('✓ Dados de '+hora+' · há '+idade,'ok');
}
function startTimer() {
  if(timer) clearInterval(timer);
  timer=setInterval(async()=>{ const ok=await loadDB(true); await loadSugestoes(); await loadSupervisores(); if(S.topView==='gestaoPcm'){await loadGestao();await loadConfiab();} if(ok&&S.user){buildWeekChips();render();renderSugestoes();if(S.topView==='gestaoPcm')renderGestao();} },CONFIG.REFRESH_MS);
  const el=document.getElementById('refresh-badge'); if(el) el.textContent='Auto-refresh '+Math.round(CONFIG.REFRESH_MS/60000)+'min';
}

// Botao "Atualizar agora" — chama loadDB, loadSugestoes e atualiza UI
async function manualRefresh(){
  setStatus('Atualizando...','loading');
  const ok = await loadDB();
  await loadSugestoes();
  await loadSupervisores();
  if(typeof loadEtiquetas==='function') await loadEtiquetas();
  if(typeof loadGestao==='function') await loadGestao();
  if(typeof loadConfiab==='function') await loadConfiab();
  // Gestão MPAS: o mpas.json tem fonte própria (Gerencial no OneDrive, via
  // botão "Atualizar Gestão MPAS" do PCM_Painel) e não vinha aqui — quem
  // clicava em "Atualizar agora" nesta aba não recebia nada de novo.
  if(typeof initMpas==='function' && MP) { try{ await initMpas(true); }catch(e){} }
  if(ok && S.user){
    buildWeekChips();
    if(typeof render==='function') render();
    if(typeof renderSugestoes==='function') renderSugestoes();
    if(typeof atualizarContadoresTopNav==='function') atualizarContadoresTopNav();
    if(typeof renderGestao==='function' && S.topView==='gestaoPcm') renderGestao();
  }
}

// ── SCREENS ──────────────────────────────────────────────────────────────────
function show(id){document.querySelectorAll('.scr').forEach(s=>s.classList.remove('on'));document.getElementById(id).classList.add('on');}
function goAdmin(){buildAdmin();show('s-admin');}
function goLogin(){updateLoginWeek();show('s-login');}
function doLogout(){S.user=null;S.isAdmin=false;S.viewCli=null;S.fEquipe='';S.fTipo='';S.fUsina='';S.fSupervisor='';S.fStatus='';S.fOS='';S.fSS='';S.fEtq='';goLogin();}
function updateLoginWeek(){ const w=AW(); document.getElementById('l-week').textContent=w?.label||'Carregando...'; }

// ── ADMIN ─────────────────────────────────────────────────────────────────────
function buildAdmin() {
  if(!DB) return;
  document.getElementById('src-box').innerHTML='<span class="src-ok">\u2713 '+CONFIG.JSON_URL+'</span>';
  const semanas=[...(DB.semanas||[])].sort((a,b)=>b.num-a.num);
  document.getElementById('wt').innerHTML=semanas.length?semanas.map(w=>{
    const isA=w.week===S.active,n=w.rows?.length||0,cl=new Set(w.rows?.map(r=>r.cliente)||[]).size;
    return '<div class="wt-row'+(isA?' active':'')+'" onclick="setAW(\''+esc(w.week)+'\')">'
      +'<div class="wt-num">'+w.week+'</div>'
      +'<div style="flex:1"><div class="wt-lbl">'+(w.label||w.week)+'</div>'
      +'<div class="wt-meta">'+n+' tarefas \u00b7 '+cl+' clientes</div></div>'
      +(isA?'<div class="wt-badge">Ativa</div>':'')+'</div>';
  }).join(''):'<div class="wt-empty">Nenhuma semana.</div>';
  const aw=AW();
  const clientes=aw?[...new Set(aw.rows.map(r=>r.cliente))].filter(Boolean).sort():[];
  document.getElementById('cli-list').innerHTML=clientes.map(c=>{
    const hasPwd=!!S.pwds[c.toLowerCase()],n=aw?.rows.filter(r=>r.cliente===c).length||0;
    return '<div class="cli-row"><div><div class="cli-name">'+c+'</div><div class="cli-meta">'+n+' tarefas</div></div>'
      +'<div class="'+(hasPwd?'cli-ok':'cli-warn')+'">'+(hasPwd?'\u2713 Senha ativa':'\u26a0 Sem senha')+'</div></div>';
  }).join('');
}
function setAW(wk){S.active=wk;lsS(LS.A,wk);buildAdmin();toast('Semana ativa: '+wk);}
function saveAdminGo(){lsS(LS.A,S.active);toast('Salvo!');setTimeout(goLogin,600);}

// ── DATA ─────────────────────────────────────────────────────────────────────
const AW=()=>DB?.semanas?.find(w=>w.week===S.active)||DB?.semanas?.[DB.semanas.length-1]||null;
// Comparação de cliente case-insensitive (grafias divergem entre fontes: Semp/SEMP etc.)
const _cliEq=(a,b)=>(a||'').toLowerCase()===(b||'').toLowerCase();
const allRows=()=>{
  const w=AW(); if(!w) return [];
  if(S.isAdmin) return S.viewCli?w.rows.filter(r=>r.cliente===S.viewCli):w.rows;
  return w.rows.filter(r=>_cliEq(r.cliente,S.user));
};
const allRowsAllWeeks=()=>{
  if(!DB?.semanas) return [];
  const rows=[];
  DB.semanas.forEach(w=>{
    const wr=S.isAdmin?(S.viewCli?w.rows.filter(r=>r.cliente===S.viewCli):w.rows):w.rows.filter(r=>_cliEq(r.cliente,S.user));
    rows.push(...wr);
  });
  return rows;
};
const AC=()=>allRows();  // escopo por cliente/semana; filtros agora são multi-seleção em GD()
// Helper #160: extrai descriptions da etiqueta (vem como JSON-string do Fracttal)
const _etqDesc=v=>{
  if(!v) return '';
  const s=String(v).trim();
  if(!s || s==='nan') return '';
  try{
    const j=JSON.parse(s);
    if(Array.isArray(j)) return j.map(o=>(o&&o.description)||'').filter(Boolean).join(' | ');
    if(j&&j.description) return j.description;
  }catch(e){}
  return s;
};
// ── Multi-seleção dos filtros (Programação Semanal) — reusa CSS .gp-ms ──────
const SEM_MS={cliente:{lbl:'Todos'},usina:{lbl:'Todas'},cluster:{lbl:'Todas'},resp:{lbl:'Todos'},respos:{lbl:'Todos'},tipo:{lbl:'Todos'},etq:{lbl:'Todas'},estado:{lbl:'Todos'}};
const SEM_SEL={cliente:new Set(),usina:new Set(),cluster:new Set(),resp:new Set(),respos:new Set(),tipo:new Set(),etq:new Set(),estado:new Set()};
function _semVal(r,key){
  // 'respos' = a PESSOA dona da OS no Fracttal (r.resp_os, 13/08/2026);
  // 'resp' continua sendo o Responsável O&M (contato da usina, via AUXILIAR)
  if(key==='respos')return r.resp_os?[String(r.resp_os)]:[];
  if(key==='etq'){const e=_etqDesc(r.etiquetas);return e?[e]:[];}
  if(key==='estado')return [estadoTarefaInfo(r).l];
  const v=r[key==='resp'?'responsavel':key];return v?[String(v)]:[];
}
function semMsOptions(key){
  const byLk=new Map();   // grafias divergem no Fracttal (ex.: "PA NORTE 01" vs "PA Norte 01")
  allRows().forEach(r=>_semVal(r,key).forEach(v=>{if(v){const s=String(v),lk=s.toLowerCase();
    let m=byLk.get(lk);if(!m){m=new Map();byLk.set(lk,m);} m.set(s,(m.get(s)||0)+1);}}));
  const canon=new Map();
  byLk.forEach((m,lk)=>{let best=null,bn=-1;m.forEach((n,s)=>{if(n>bn){bn=n;best=s;}});canon.set(lk,best);});
  const validLk=new Set(canon.keys());
  [...SEM_SEL[key]].forEach(v=>{if(!validLk.has(String(v).toLowerCase()))SEM_SEL[key].delete(v);});
  return [...canon.values()].sort((a,b)=>a.localeCompare(b,'pt-BR'));
}
function semMsLabel(key){const s=SEM_SEL[key],el=document.getElementById('sm-ms-lbl-'+key);if(!el)return;if(s.size===0){el.textContent=SEM_MS[key].lbl;el.classList.remove('sel');}else if(s.size===1){el.textContent=[...s][0];el.classList.add('sel');}else{el.textContent=s.size+' selecionados';el.classList.add('sel');}}
function semBuildPop(key){const pop=document.getElementById('sm-ms-pop-'+key);if(!pop)return;const opts=semMsOptions(key);let h='<div class="gp-ms-top"><input class="gp-ms-search" placeholder="buscar…" oninput="semMsSearch(\''+key+'\',this.value)"><div class="gp-ms-acts"><a onclick="semMsAll(\''+key+'\')">Todos</a><a onclick="semMsNone(\''+key+'\')">Limpar</a></div></div><div class="gp-ms-opts">';h+=opts.map(v=>{const e=esc(v);return '<label class="gp-ms-opt"><input type="checkbox"'+(SEM_SEL[key].has(v)?' checked':'')+' value="'+e+'" onchange="semMsCheck(\''+key+'\',this)"><span>'+e+'</span></label>';}).join('')||'<div class="gp-ms-empty">—</div>';pop.innerHTML=h+'</div>';}
function semPopulateFilters(){Object.keys(SEM_MS).forEach(k=>{semBuildPop(k);semMsLabel(k);});}
function semMsToggle(key){const box=document.getElementById('sm-ms-'+key),open=box.classList.contains('open');document.querySelectorAll('.gp-ms.open').forEach(b=>b.classList.remove('open'));if(!open){semBuildPop(key);box.classList.add('open');}}
function semMsCheck(key,cb){if(cb.checked)SEM_SEL[key].add(cb.value);else SEM_SEL[key].delete(cb.value);semMsLabel(key);render();updateFCount();}
function semMsAll(key){semMsOptions(key).forEach(v=>SEM_SEL[key].add(v));semBuildPop(key);semMsLabel(key);render();updateFCount();}
function semMsNone(key){SEM_SEL[key].clear();semBuildPop(key);semMsLabel(key);render();updateFCount();}
function semMsSearch(key,q){q=(q||'').toLowerCase();document.querySelectorAll('#sm-ms-pop-'+key+' .gp-ms-opt').forEach(l=>{l.style.display=l.textContent.toLowerCase().indexOf(q)>=0?'':'none';});}
function onDataChange(){S.fDIni=document.getElementById('f-dini').value;S.fDFim=document.getElementById('f-dfim').value;render();updateFCount();}
const GD=()=>{const Q=SEM_SEL;
  const _L=s=>new Set([...s].map(x=>String(x).toLowerCase())),_in=(set,v)=>set.has(String(v||'').toLowerCase());
  const Lcli=_L(Q.cliente),Lusi=_L(Q.usina),Lclu=_L(Q.cluster),Lres=_L(Q.resp),Lros=_L(Q.respos),Ltip=_L(Q.tipo),Lest=_L(Q.estado),Letq=_L(Q.etq);
  return allRows().filter(r=>{
  if(Q.cliente.size&&!_in(Lcli,r.cliente))return false;
  if(Q.usina.size&&!_in(Lusi,r.usina))return false;
  if(Q.cluster.size&&!_in(Lclu,r.cluster))return false;
  if(Q.resp.size&&!_in(Lres,r.responsavel))return false;
  if(Q.respos.size&&!_in(Lros,r.resp_os))return false;
  if(Q.tipo.size&&!_in(Ltip,r.tipo))return false;
  if(Q.estado.size&&!_in(Lest,estadoTarefaInfo(r).l))return false;
  if(Q.etq.size){const e=_etqDesc(r.etiquetas);if(!e||!_in(Letq,e))return false;}
  if(S.fOS&&String(r.os_id||'').indexOf(S.fOS)<0)return false;
  if(S.fSS&&String(r.solic_orig||'').indexOf(S.fSS)<0)return false;
  const dp=(r.dataProgramada||'').slice(0,10);
  if(S.fDIni&&(!dp||dp<S.fDIni))return false;
  if(S.fDFim&&(!dp||dp>S.fDFim))return false;
  return true;
});};
const isExec=r=>r.status_bd&&/(execu|progresso|andamento)/i.test(r.status_bd)&&!/verifica/i.test(r.status_bd);
const isNova=r=>r.nova_os&&r.nova_os.toString().trim()!==''&&r.nova_os.toString().toLowerCase()!=='não'&&r.nova_os.toString().toLowerCase()!=='nao';
const isFinalizada=r=>{const s=(r.status_bd||r.status||'').toString().toLowerCase();return s.includes('finaliz')||s.includes('conclu');};
// Resolve nome do supervisor tentando múltiplos campos possíveis na JSON
const getSupervisor=r=>{
  // Tenta campos diretos na row primeiro
  const direto=(r.responsavel||r.supervisor||r['Responsável']||r['Responsavel']||r.responsavel_om||r.resp||r.responsable||'').toString().trim();
  if(direto) return direto;
  const c=(r.cluster||'').toString().trim();
  if(!c||!SUPERVISORES_DB) return '';
  // Tenta porEquipe primeiro (chave completa: "SP Leste 05") — match exato
  if(SUPERVISORES_DB.porEquipe&&SUPERVISORES_DB.porEquipe[c]) return SUPERVISORES_DB.porEquipe[c];
  // Fallback: porCluster (chave curta: "SP Leste")
  if(SUPERVISORES_DB.porCluster&&SUPERVISORES_DB.porCluster[c]) return SUPERVISORES_DB.porCluster[c];
  return '';
};
const statusKey=r=>{
  // FIX #158: Status PAI tem prioridade se for "Em Verificação"
  // (kanban deve refletir mesmo status do modal — sem divergência)
  const sp=(r.statusPai||'').toString().toLowerCase();
  if(sp.includes('verifica')) return 'verif';
  const s=(r.status_bd||r.status||'').toString().toLowerCase();
  if(s.includes('verifica')) return 'verif';
  if(isExec(r)) return 'exec';
  if(s.includes('finaliz')||s.includes('conclu')) return 'fin';
  if(s.includes('pausad')) return 'pau';
  if(s.includes('iniciada')||s.includes('iniciado')||s==='não iniciada'||s==='nao iniciada') return 'ni';
  return 'ni';
};
const statusLabel=k=>({exec:'Em Processo',fin:'Finalizada',ni:'Não Iniciada',pau:'Pausada',verif:'Em Verificação'})[k]||'--';
const statusColor=k=>({exec:'#8a4cf9',fin:'#a9db21',ni:'#9ca3af',pau:'#f59e0b',verif:'#3b82f6'})[k]||'#9ca3af';
// ── Estado da TAREFA (puro) vs Status da OS — sempre separados (diretriz do PCM)
// Estado da Tarefa: badge principal do card. NÃO usa statusPai.
function estadoTarefaInfo(r){
  const s=(r.status_bd||r.status||'').toString().toLowerCase();
  if(s.includes('finaliz')||s.includes('conclu')) return {k:'finalizada',l:'Finalizada'};
  if(s.includes('pausad')) return {k:'pausada',l:'Pausada'};
  if(s.includes('progress')||s.includes('execu')||s.includes('andamento')) return {k:'emProgresso',l:'Em progresso'};
  return {k:'naoIniciada',l:'Não Iniciada'};
}
// Status da OS (statusPai): selo separado. Retorna null se vazio.
function statusOsInfo(r){
  const sp=(r.statusPai||'').toString().toLowerCase();
  if(sp.includes('verifica')) return {k:'verificacao',l:'Verificação'};
  if(sp.includes('finaliz'))  return {k:'finalizada',l:'Finalizados'};
  if(sp.includes('process'))  return {k:'emProgresso',l:'Em processo'};
  return null;
}
function taxaFinalizacaoPreventiva(rows, cat){
  const subset=rows.filter(r=>r.tipo&&(r.tipo===cat||r.tipo.startsWith(cat+'-')));
  if(!subset.length) return {tx:0, total:0, fin:0};
  const fin=subset.filter(isFinalizada).length;
  return {tx:Math.round(fin/subset.length*100), total:subset.length, fin:fin};
}

// ── LOGIN ─────────────────────────────────────────────────────────────────────
async function doLogin() {
  const c=document.getElementById('inp-c').value.trim();
  const s=document.getElementById('inp-s').value;
  const err=document.getElementById('l-err');
  if(!c||!s){err.style.display='block';err.textContent='Preencha usu\u00e1rio e senha.';return;}
  // Se DB ainda nao carregou, tenta carregar agora (espera ate 10s)
  if(!DB){
    err.style.display='block';err.textContent='Carregando dados... aguarde.';
    await loadDB();
    if(!DB){err.textContent='Falha ao carregar. Tente novamente.';return;}
    err.style.display='none';
  }
  const key=c.toLowerCase(),exp=S.pwds[key]||'';
  if(!exp){err.style.display='block';err.textContent='Usu\u00e1rio n\u00e3o encontrado.';return;}
  const h=await sha256(s);
  if(h!==exp){err.style.display='block';err.textContent='Senha incorreta.';return;}
  err.style.display='none';
  S.isAdmin=key===ADMIN_ID; S.fEquipe=''; S.fTipo=''; S.fUsina=''; S.fSupervisor=''; S.fStatus=''; S.viewCli=null;
  // Guarda a senha do admin s\u00f3 na SESS\u00c3O, para a aba Gest\u00e3o MPAS decifrar o
  // mpas.json sem pedir de novo. Nunca vai para localStorage nem para o servidor.
  if(S.isAdmin){ try{ sessionStorage.setItem('gc_mp_k', s); }catch(e){} }
  if(S.isAdmin){S.user='Admin';launch('Grid Co. \u2014 Todos os Clientes',true);}
  else {
    const aliasName=LOGIN_ALIASES[key]||null;
    // Cliente cadastrado (senha correta) SEMPRE acessa, mesmo sem obra na semana atual.
    // Procura o nome can\u00f4nico em QUALQUER semana; sen\u00e3o usa o alias ou o nome digitado.
    const allCli=[...new Set((DB.semanas||[]).flatMap(w=>(w.rows||[]).map(r=>r.cliente)))].filter(Boolean);
    let found=aliasName
      ? (allCli.find(x=>x===aliasName)||aliasName)
      : (allCli.find(x=>x.toLowerCase()===key)||null);
    if(!found) found=aliasName||(c.charAt(0).toUpperCase()+c.slice(1));
    S.user=found; launch(found,false);
  }
}

function launch(label,isAdmin) {
  const w=AW();
  document.getElementById('ab-client').textContent=label;
  document.getElementById('ab-week').textContent=w?.label||'--';
  document.getElementById('ph-c').textContent=label;
  document.getElementById('ph-w').textContent=(w?.label||'--')+' \u00b7 Programa\u00e7\u00e3o O&M Grid Co.';
  const sw=document.getElementById('admin-sel-wrap');
  if(isAdmin){
    sw.style.display='flex';
    const rows=AW()?.rows||[];
    const cls=[...new Set(rows.map(r=>r.cliente))].filter(Boolean).sort();
    const sel=document.getElementById('admin-client-sel');
    sel.innerHTML='<option value="">Todos os clientes</option>'+cls.map(c=>{const e=String(c||'').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');return '<option value="'+e+'">'+e+'</option>';}).join('');
    sel.value=S.viewCli||'';
  } else sw.style.display='none';
  // Task #130: esconder abas restritas pra não-admin
  const adminOnly = ['religamentos','emVerificacao','sugestoesIA','gestaoMpas'];
  adminOnly.forEach(slug=>{
    const btn = document.querySelector('.tip-tab[data-topv="'+slug+'"]');
    if(btn) btn.style.display = isAdmin ? '' : 'none';
  });
  // Se user não-admin estava em aba restrita, volta pra Programação Semanal
  let _voltouAba=false;
  if(!isAdmin && adminOnly.indexOf(S.topView)>=0){
    S.topView = 'semana';
    try{localStorage.setItem('gc_topv','semana');}catch(e){}
    _voltouAba=true;   // só trocar a variável não esconde a tela restrita
  }
  show('s-briefing');
  if(_voltouAba && typeof setTopView==='function') setTopView('semana');
  buildWeekChips(); buildFilters(); render();
  // Auto-refresh a cada CONFIG.REFRESH_MS (5 min) - dispara depois do login
  startTimer();
}
function onAdminClientChange(){
  S.viewCli=document.getElementById('admin-client-sel').value||null;
  S.fEquipe='';S.fTipo='';S.fUsina='';S.fSupervisor='';S.fStatus='';S.fOS='';
  const lbl=S.viewCli||'Todos os Clientes';
  document.getElementById('ab-client').textContent='Admin \u2014 '+lbl;
  document.getElementById('ph-c').textContent='Grid Co. \u2014 '+lbl;
  buildWeekChips();buildFilters();render();
}

// ── WEEK CHIPS ────────────────────────────────────────────────────────────────
function buildWeekChips() {
  if(!DB?.semanas) return;
  const semanas=[...DB.semanas].sort((a,b)=>b.num-a.num);
  document.getElementById('week-chips').innerHTML=semanas.map(w=>{
    const isA=w.week===S.active;
    const n=w.rows?.length||0;
    return '<div class="week-chip'+(isA?' on':'')+'" onclick="selectWeek(\''+String(w.week).replace(/'/g,"\\'")+'\')">'
      +'<span>'+w.week+'</span>'
      +'<span class="week-chip-lbl">'+n+' OS</span>'
      +'</div>';
  }).join('');
}
function selectWeek(wk) {
  S.active=wk; lsS(LS.A,wk);
  S.fEquipe='';S.fTipo='';S.fUsina='';
  buildWeekChips();buildFilters();render();
  const w=AW();
  document.getElementById('ab-week').textContent=w?.label||'--';
  document.getElementById('ph-w').textContent=(w?.label||'--')+' \u00b7 Programa\u00e7\u00e3o O&M Grid Co.';
}

// ── VIEW TABS ─────────────────────────────────────────────────────────────────
function setView(v) {
  // Visao Mes removida - sempre semanal
  S.view='semana'; lsS(LS.V,'semana');
}

// ── FILTERS ───────────────────────────────────────────────────────────────────
function buildFilters() {
  semPopulateFilters();   // multi-seleção (Cliente/Usina/Cluster/Responsável/Tipo/Etiqueta/Estado)
  const fSS=document.getElementById('f-ss');if(fSS)fSS.value=S.fSS||'';
  const fOS=document.getElementById('f-os');if(fOS)fOS.value=S.fOS||'';
  const fdi=document.getElementById('f-dini');if(fdi)fdi.value=S.fDIni||'';
  const fdf=document.getElementById('f-dfim');if(fdf)fdf.value=S.fDFim||'';
}
function onOSChange(){S.fOS=document.getElementById('f-os').value.trim();render();updateFCount();}
function onSSChange(){S.fSS=document.getElementById('f-ss').value.trim();render();updateFCount();}
function onEtqChange(){S.fEtq=document.getElementById('f-etq').value;render();updateFCount();}
function buildTipoChips(){}   // chips de Tipo removidos (virou multi-seleção)
function setTipo(t){SEM_SEL.tipo.clear();if(t)SEM_SEL.tipo.add(t);semMsLabel('tipo');render();updateFCount();}
function resetFilters(){
  Object.keys(SEM_SEL).forEach(k=>SEM_SEL[k].clear());
  S.fOS='';S.fSS='';S.fDIni='';S.fDFim='';
  ['f-os','f-ss','f-dini','f-dfim'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});
  semPopulateFilters();render();updateFCount();
}
function updateFCount(){const el=document.getElementById('f-count');if(!el)return;const anyMs=Object.values(SEM_SEL).some(s=>s.size);const active=anyMs||S.fOS||S.fSS||S.fDIni||S.fDFim;el.style.display=active?'inline-flex':'none';if(active)el.textContent=GD().length+' de '+allRows().length+' OS';}

// ── RENDER ────────────────────────────────────────────────────────────────────
function render(){const d=GD();renderKPIs(d);renderIns(d);renderCal(d);renderPendentes();renderBottom(d);renderSugestoes();}
function togPend(){const w=document.getElementById('pend-wrap');if(w)w.classList.toggle('open');}

// ===== REPROGRAMAÇÃO RÁPIDA =====================================================
// Monta linhas no formato de Observacoes_Semana.txt a partir dos pendentes.
// O painel NÃO altera a programação: gera o texto para colar no PCM_Painel
// (aba "Observações" = próxima semana | "Semana Atual" = semana em andamento).
const RP_KEY='gc_reprog_v1';
let RP=[];                                  // [{os,tarefa,tipo,dia,turno}]
try{RP=JSON.parse(localStorage.getItem(RP_KEY)||'[]');}catch(e){RP=[];}
// Reprogramar é ação de PCM. Cliente enxerga a lista de pendentes (só as dele),
// mas NÃO vê os controles nem a fila — quem decide a programação é a Grid Co.
Object.defineProperty(window,'RP_OK',{get:()=>!!(typeof S!=='undefined'&&S.isAdmin)});
const RP_SIGLAS=['MPA','MPS','MPT','MPM','MPQ','HANDOVER'];
function rpSave(){try{localStorage.setItem(RP_KEY,JSON.stringify(RP));}catch(e){}}
function rpKey(os,tar){return String(os)+'||'+String(tar||'');}
function rpIdx(os,tar){return RP.findIndex(r=>rpKey(r.os,r.tarefa)===rpKey(os,tar));}

// Modo A (bloco por sigla) precisa de "só:" p/ isolar a tarefa; Modo B usa o nome.
function rpSigla(tipo){
  const t=String(tipo||'').toUpperCase().replace(/-.*$/,'').trim();
  return RP_SIGLAS.indexOf(t)>=0 ? (t==='HANDOVER'?'Handover':t) : null;
}
// "[Grid Co.] - MPA - Caixa d'água" -> "Caixa d'água" | "Handover – Inversores" -> "Inversores"
function rpChave(tarefa){
  let s=String(tarefa||'').split(/\s[-–]\s/).pop().trim();
  s=s.split(',')[0].split(';')[0].trim();     // vírgula/; quebrariam o parser
  return s;
}
function rpLinha(r){
  const tur=r.turno||'';
  // "não" = tira a OS da semana (vale nas duas abas; sempre a OS inteira)
  if(r.dia==='não') return r.os+'; não';
  // OS inteira (tarefa vazia) → "OS; dia" ou "OS; dia; ; turno" (tarefas=None no motor)
  if(!r.tarefa) return tur ? (r.os+'; '+r.dia+'; ; '+tur) : (r.os+'; '+r.dia);
  const sig=rpSigla(r.tipo);
  if(sig){
    const ch=rpChave(r.tarefa);
    return [r.os, r.dia, sig, tur, ch?('só: '+ch):''].filter((v,i)=>i<3||v).join('; ');
  }
  const nome=String(r.tarefa||'').split(',')[0].split(';')[0].trim();
  return [r.os, r.dia, nome, tur].filter((v,i)=>i<3||v).join('; ');
}
// Tirar a OS da semana — gera "OS; não". Sempre a OS INTEIRA: a gramática do
// "não" não aceita filtro por tarefa (para tirar só uma parte, use "sem:").
function rpTirar(os_id,n_tarefas){
  if(!RP_OK)return;
  const n=n_tarefas||1;
  if(!confirm('Tirar a OS #'+os_id+' da programação desta semana?'
      +(n>1?('\n\nIsso remove as '+n+' tarefas dela.'):'')))return;
  const i=rpIdx(os_id,'');
  if(i>=0)RP.splice(i,1);
  RP.push({os:String(os_id),tarefa:'',tipo:'',dia:'não',turno:''});
  rpSave();
  toast('✕ OS #'+os_id+' será tirada da semana · '+RP.length+' na fila');
  const st=document.getElementById('rpm-status');
  if(st)st.innerHTML='<b>'+RP.length+'</b> na fila — linha: <code>'+esc(os_id+'; não')+'</code>';
  renderPendentes();
}
// Reprogramar a partir do modal da OS (serve p/ qualquer OS já programada)
function rpAddModal(os_id){
  if(!RP_OK)return;
  const dia=document.getElementById('rpm-dia').value;
  const turno=document.getElementById('rpm-turno').value;
  const alvo=document.getElementById('rpm-alvo');
  if(!dia){toast('Escolha o dia primeiro');return;}
  const tarefa=(alvo&&alvo.value)||'';        // '' = OS inteira
  // atenção: com 1 tarefa o alvo é <input hidden> (não tem selectedOptions)
  const opt=(alvo&&alvo.selectedOptions)?alvo.selectedOptions[0]:null;
  const tipo=(opt&&opt.dataset&&opt.dataset.tipo)||(alvo&&alvo.dataset&&alvo.dataset.tipo)||'';
  const i=rpIdx(os_id,tarefa);
  if(i>=0)RP.splice(i,1);
  RP.push({os:String(os_id),tarefa:tarefa,tipo:tipo,dia:dia,turno:turno});
  rpSave();
  toast('✓ '+(tarefa?'Tarefa':'OS #'+os_id)+' → '+dia+(turno?' ('+turno+')':'')+' · '+RP.length+' na fila');
  const st=document.getElementById('rpm-status');
  if(st)st.innerHTML='<b>'+RP.length+'</b> na fila — linha: <code>'+esc(rpLinha(RP[RP.length-1]))+'</code>';
  renderPendentes();
}
function rpToggle(ev,os,tarefa,tipo){
  ev.stopPropagation();
  if(!RP_OK)return;                          // guarda: só PCM/admin reprograma
  const row=ev.target.closest('.pend-row');
  const dia=row.querySelector('.rp-dia').value;
  const turno=row.querySelector('.rp-turno').value;
  const i=rpIdx(os,tarefa);
  if(i>=0){RP.splice(i,1);} else {
    if(!dia){toast('Escolha o dia primeiro');return;}
    RP.push({os:String(os),tarefa:tarefa,tipo:tipo,dia:dia,turno:turno});
  }
  rpSave();renderPendentes();
}
function rpTexto(){
  // agrupa por OS mantendo a ordem de inclusão
  return RP.map(rpLinha).join('\n');
}
function rpCopiar(){
  if(!RP_OK)return;
  const txt=rpTexto();
  if(!txt){toast('Nenhuma reprogramação na fila');return;}
  const done=()=>toast('✓ '+RP.length+' linha(s) copiada(s) — cole no PCM_Painel');
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(txt).then(done).catch(()=>{rpFallback(txt);});
  } else rpFallback(txt);
}
function rpFallback(txt){
  const ta=document.createElement('textarea');ta.value=txt;ta.style.position='fixed';ta.style.opacity='0';
  document.body.appendChild(ta);ta.select();
  try{document.execCommand('copy');toast('✓ Copiado');}catch(e){toast('Selecione e copie o texto abaixo');}
  document.body.removeChild(ta);
}
// ===== GESTÃO MPAS ============================================================
// Dados de MPA/MPS (planilha Gerencial + Fracttal). O mpas.json fica CIFRADO no
// repositório (que é público): sem a senha de admin, o arquivo é ilegível.
const MP_URL='mpas.json';
let MP_PACK=null, MP=null;                       // pacote cifrado / dados abertos
const MP_F={concluidas:false};                    // só o checkbox continua simples
// multi-seleção (mesmo componente .gp-ms da Gestão PCM)
const MP_MS={cluster:{f:'cluster',lbl:'Todos'},usina:{f:'usina_curta',lbl:'Todas'},
  tipo:{f:'tipo',lbl:'Todos'},cliente:{f:'cliente',lbl:'Todos'},
  situacao:{f:'_sit',lbl:'Todas'},prioridade:{f:'prioridade',lbl:'Todas'}};
const MP_SEL={cluster:new Set(),usina:new Set(),tipo:new Set(),cliente:new Set(),
  situacao:new Set(),prioridade:new Set()};
const MP_D={de:'',ate:'',pre:''};                 // filtro de data prevista (aaaa-mm-dd)
// 19/08/2026 — filtro por AÇÃO NECESSÁRIA. A aba era organizada por Equipe
// Cluster (a chave de quem executa) e nem o gerente operacional nem o
// financeiro achavam o que era deles. Este filtro é a porta de entrada nova:
// '' = tudo | 'bloq' travada por compra | 'atraso' | 'prox' vence em 30d | 'ok'.
// Entra no mpFilt(), então a árvore, o Gantt e a planilha geral já o respeitam.
let MP_ACAO='';
const MP_ACAO_LBL={bloq:'Travadas por compra',atraso:'Atrasadas',
                   prox:'Vencem em 30 dias',ok:'Concluídas'};
const MP_SITS=['Concluída','Em andamento','Não iniciada','Atrasada'];
const MP_MESES=['janeiro','fevereiro','março','abril','maio','junho','julho',
                'agosto','setembro','outubro','novembro','dezembro'];
const MP_DESDE='2026-01-01';

async function mpCarregarPack(forcar){
  // MP_PACK é cache de sessão: sem o `forcar`, "Atualizar agora" devolvia o
  // MESMO objeto já em memória e o mpas.json novo nunca chegava à tela.
  if(forcar) MP_PACK=null;
  if(MP_PACK)return MP_PACK;
  const r=await fetch(MP_URL+'?t='+Date.now(),{cache:'no-store'});
  if(!r.ok)throw new Error('mpas.json não encontrado');
  MP_PACK=await r.json();
  return MP_PACK;
}
// AES-GCM + PBKDF2 — espelha o gerar_mpas_json.py
async function mpDecifrar(pack,senha){
  const b64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
  const km=await crypto.subtle.importKey('raw',new TextEncoder().encode(senha),'PBKDF2',false,['deriveKey']);
  const key=await crypto.subtle.deriveKey(
    {name:'PBKDF2',salt:b64(pack.salt),iterations:pack.iter,hash:'SHA-256'},
    km,{name:'AES-GCM',length:256},false,['decrypt']);
  const plain=await crypto.subtle.decrypt({name:'AES-GCM',iv:b64(pack.iv)},key,b64(pack.ct));
  return JSON.parse(new TextDecoder().decode(plain));
}
async function mpAbrir(){
  const inp=document.getElementById('mp-pwd'), err=document.getElementById('mp-err');
  const senha=(inp&&inp.value||'').trim();
  if(!senha){err.textContent='Digite a senha.';return;}
  err.textContent='Abrindo…';
  try{
    const pack=await mpCarregarPack();
    MP=await mpDecifrar(pack,senha);
    try{sessionStorage.setItem('gc_mp_k',senha);}catch(e){}   // sessão only
    err.textContent='';
    renderMpas();
  }catch(e){ err.textContent='Senha incorreta (ou arquivo indisponível).'; }
}
// ---- helpers de situação (mesma regra do site MPAS) ----
const mpBd=r=>{const o=String(r.os||'').trim();return (o&&MP&&MP.bd&&MP.bd[o])?MP.bd[o]:null;};
function mpSit(r){
  const b=mpBd(r), hoje=new Date().toISOString().slice(0,10);
  let k=null;
  if(b&&b.sit) k=b.sit;
  else{
    const st=(r.status||'').toLowerCase();
    k = st.startsWith('finaliz')?'Concluída' : st.startsWith('em execu')?'Em andamento':'Não iniciada';
  }
  if(k!=='Concluída'&&r.prevista&&r.prevista<hoje) k='Atrasada';
  const cls={'Concluída':'green','Em andamento':'blue','Não iniciada':'amber','Atrasada':'red'}[k]||'gray';
  return {k,cls};
}
// Clusters cujo kit de equipamento ainda não foi comprado e cuja âncora já
// venceu: as MPAs deles não têm como ser executadas. Memoizado por geradoEm.
let _MP_TRAV=null,_MP_TRAV_G=null;
function mpTrav(){
  const g=(MP&&MP.geradoEm)||'';
  if(_MP_TRAV&&_MP_TRAV_G===g)return _MP_TRAV;
  const out={},hoje=new Date().toISOString().slice(0,10);
  ((MP&&MP.compras&&MP.compras.clusters)||[]).forEach(c=>{
    if(c.ancora&&c.ancora<hoje)out[c.cluster]=c;});
  _MP_TRAV_G=g;_MP_TRAV=out;return out;
}
// A categoria é EXCLUSIVA e a ordem importa: uma MPA atrasada num cluster sem
// kit é 'bloq', não 'atraso' — cobrar execução dela seria cobrar o impossível.
function mpCat(r){
  const k=mpSit(r).k;
  if(k==='Concluída')return 'ok';
  if(r.tipo==='MPA'&&mpTrav()[r.cluster])return 'bloq';
  if(k==='Atrasada')return 'atraso';
  const hoje=new Date().toISOString().slice(0,10);
  const d=new Date();d.setDate(d.getDate()+30);
  const lim=d.toISOString().slice(0,10);
  if(r.prevista&&r.prevista>=hoje&&r.prevista<=lim)return 'prox';
  return 'futuro';
}
const mpBateAcao=r=>!MP_ACAO||mpCat(r)===MP_ACAO;
function mpAcaoSet(cat){
  MP_ACAO=(MP_ACAO===cat)?'':cat;
  // "Concluídas" precisa do checkbox ligado, senão o recorte volta vazio
  if(MP_ACAO==='ok')MP_F.concluidas=true;
  const cb=document.getElementById('mp-f-conc');if(cb)cb.checked=MP_F.concluidas;
  renderMpas();
}
// valor do registro para um campo do filtro ('_sit' é calculado)
const mpCampo=(r,f)=>f==='_sit'?mpSit(r).k:(r[f]||'');
// vazio = todos; comparação case-insensitive (o Fracttal varia a grafia)
function mpBate(r,key){
  const s=MP_SEL[key];
  if(!s||!s.size)return true;
  const v=String(mpCampo(r,MP_MS[key].f)||'').toLowerCase();
  for(const x of s){if(String(x).toLowerCase()===v)return true;}
  return false;
}
// data prevista: intervalo (ISO aaaa-mm-dd, comparação de string funciona)
function mpBateData(r){
  const {de,ate}=MP_D; if(!de&&!ate)return true;
  const p=r.prevista||''; if(!p)return false;
  if(de&&p<de)return false;
  if(ate&&p>ate)return false;
  return true;
}
const mpVisBase=r=>['cluster','usina','tipo','cliente','prioridade'].every(k=>mpBate(r,k))&&mpBateData(r);
const mpFilt=()=>(MP?MP.manut:[]).filter(r=>mpVisBase(r)&&mpBate(r,'situacao')&&mpBateAcao(r));

// ---- componente multi-seleção (reusa o CSS .gp-ms) ----
function mpMsOptions(key){
  const f=MP_MS[key].f, byLk=new Map();
  (MP?MP.manut:[]).forEach(r=>{
    const v=mpCampo(r,f); if(!v)return;
    const s=String(v), lk=s.toLowerCase();
    let m=byLk.get(lk); if(!m){m=new Map();byLk.set(lk,m);}
    m.set(s,(m.get(s)||0)+1);
  });
  const canon=new Map();     // mantém a grafia mais frequente
  byLk.forEach((m,lk)=>{let b=null,bn=-1;m.forEach((n,s)=>{if(n>bn){bn=n;b=s;}});canon.set(lk,b);});
  const ok=new Set(canon.keys());
  [...MP_SEL[key]].forEach(v=>{if(!ok.has(String(v).toLowerCase()))MP_SEL[key].delete(v);});
  return [...canon.values()].sort((a,b)=>a.localeCompare(b,'pt-BR'));
}
function mpMsLabel(key){
  const s=MP_SEL[key], el=document.getElementById('mp-ms-lbl-'+key); if(!el)return;
  if(s.size===0){el.textContent=MP_MS[key].lbl;el.classList.remove('sel');}
  else if(s.size===1){el.textContent=[...s][0];el.classList.add('sel');}
  else{el.textContent=s.size+' selecionados';el.classList.add('sel');}
}
function mpBuildPop(key){
  const pop=document.getElementById('mp-ms-pop-'+key); if(!pop)return;
  const opts=mpMsOptions(key);
  let h='<div class="gp-ms-top"><input class="gp-ms-search" placeholder="buscar…" oninput="mpMsSearch(\''+key+'\',this.value)">'
    +'<div class="gp-ms-acts"><a onclick="mpMsAll(\''+key+'\')">Todos</a><a onclick="mpMsNone(\''+key+'\')">Limpar</a></div></div><div class="gp-ms-opts">';
  h+=opts.map(v=>{const e=esc(v);return '<label class="gp-ms-opt"><input type="checkbox"'
    +(MP_SEL[key].has(v)?' checked':'')+' value="'+e+'" onchange="mpMsCheck(\''+key+'\',this)"><span>'+e+'</span></label>';})
    .join('')||'<div class="gp-ms-empty">—</div>';
  pop.innerHTML=h+'</div>';
}
function mpMsToggle(key){
  const box=document.getElementById('mp-ms-'+key), open=box.classList.contains('open');
  document.querySelectorAll('.gp-ms.open').forEach(b=>b.classList.remove('open'));
  if(!open){mpBuildPop(key);box.classList.add('open');}
}
function mpMsCheck(key,cb){cb.checked?MP_SEL[key].add(cb.value):MP_SEL[key].delete(cb.value);mpMsLabel(key);renderMpas();}
function mpMsAll(key){mpMsOptions(key).forEach(v=>MP_SEL[key].add(v));mpBuildPop(key);mpMsLabel(key);renderMpas();}
function mpMsNone(key){MP_SEL[key].clear();mpBuildPop(key);mpMsLabel(key);renderMpas();}
function mpMsSearch(key,q){q=(q||'').toLowerCase();
  document.querySelectorAll('#mp-ms-pop-'+key+' .gp-ms-opt').forEach(l=>{
    l.style.display=l.textContent.toLowerCase().indexOf(q)>=0?'':'none';});}
const mpTipoCls=t=>t==='MPA'?'mpa':t==='MPS'?'mps':'';

function mpKpis(){
  const base=(MP?MP.manut:[]).filter(mpVisBase), c={};
  MP_SITS.forEach(s=>c[s]=0);
  base.forEach(r=>{const k=mpSit(r).k;c[k]=(c[k]||0)+1;});
  const cards=[
    {l:'Total filtrado',v:mpFilt().length,f:'MPAs e MPSs',c:'#191528',s:null},
    {l:'Concluídas',v:c['Concluída'],f:'clique para filtrar',c:'#15803D',s:'Concluída'},
    {l:'Em andamento',v:c['Em andamento'],f:'clique para filtrar',c:'#1D4ED8',s:'Em andamento'},
    {l:'Não iniciadas',v:c['Não iniciada'],f:'clique para filtrar',c:'#92400E',s:'Não iniciada'},
    {l:'Atrasadas',v:c['Atrasada'],f:'clique para filtrar',c:'#B91C1C',s:'Atrasada'}];
  const box=document.getElementById('mp-kpis');
  box.innerHTML=cards.map(k=>'<div class="calkpi'+((k.s&&MP_SEL.situacao.has(k.s))?' sel':'')+'" data-sit="'+(k.s||'')+'">'
    +'<div class="top" style="background:'+k.c+'"></div><div class="klabel">'+k.l+'</div>'
    +'<div class="kvalue" style="color:'+k.c+'">'+k.v+'</div><div class="kfoot">'+k.f+'</div></div>').join('');
  box.querySelectorAll('.calkpi').forEach(el=>el.onclick=()=>{
    const s=el.dataset.sit; if(!s)return;
    // o card liga/desliga a situação no multi-seleção (os dois ficam em sincronia)
    MP_SEL.situacao.has(s)?MP_SEL.situacao.delete(s):MP_SEL.situacao.add(s);
    mpBuildPop('situacao'); mpMsLabel('situacao'); renderMpas();
  });
  // KPIs do cabeçalho
  const set=(id,v)=>{const e=document.getElementById(id);if(e)e.textContent=v;};
  set('mp-k-tot',base.length); set('mp-k-and',c['Em andamento']||0); set('mp-k-atr',c['Atrasada']||0);
  const t=document.getElementById('tcnt-gestaoMpas'); if(t)t.textContent=base.length;
}
function mpFiltros(){
  const box=document.getElementById('mp-filtros');
  // só remonta a casca uma vez; depois é só repopular (senão o popup fecha ao clicar)
  if(!box.dataset.built){
    const ms=(k,rot)=>'<div class="gp-fg"><label>'+rot+'</label>'
      +'<div class="gp-ms" id="mp-ms-'+k+'"><button type="button" class="gp-ms-btn" onclick="mpMsToggle(\''+k+'\')">'
      +'<span class="gp-ms-lbl" id="mp-ms-lbl-'+k+'">'+MP_MS[k].lbl+'</span><span class="gp-ms-cv">▾</span></button>'
      +'<div class="gp-ms-pop" id="mp-ms-pop-'+k+'"></div></div></div>';
    const pre=(k,r)=>'<button type="button" id="mp-pre-'+k+'" onclick="mpPreset(\''+k+'\')">'+r+'</button>';
    box.innerHTML= '<div class="mp-grid">'
      + ms('cluster','Equipe Cluster')+ms('usina','Usina')
      + ms('tipo','Tipo de manutenção')+ms('cliente','Cliente')
      + ms('situacao','Situação')+ms('prioridade','Prioridade')
      + '</div><div class="mp-linha2">'
      + '<div class="gp-fg mp-per"><label>Data prevista</label><div class="mp-drow">'
      + '<input type="date" id="mp-d-de" onchange="mpData(\'de\',this.value)" title="a partir de">'
      + '<span class="mp-ate">até</span>'
      + '<input type="date" id="mp-d-ate" onchange="mpData(\'ate\',this.value)" title="até">'
      + '<span class="mp-pre">'+pre('mes','Este mês')+pre('tri','Próx. 3 meses')
      + pre('ano','Este ano')+pre('venc','Já venceu')+'</span></div></div>'
      + '<div class="mp-acoes">'
      + '<label class="mp-cbx"><input type="checkbox" id="mp-f-conc"'+(MP_F.concluidas?' checked':'')
      + ' onchange="MP_F.concluidas=this.checked;renderMpas()"> mostrar concluídas</label>'
      + '<button class="rp-btn sec" onclick="mpLimpar()">↺ Limpar filtros</button></div></div>';
    box.dataset.built='1';
  }
  Object.keys(MP_MS).forEach(k=>{mpMsLabel(k);});
  mpDataUI();
}
// ---- período (data prevista) ----
const mpISO=d=>d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
function mpData(campo,v){MP_D[campo]=v||'';MP_D.pre='';mpDataUI();renderMpas();}
function mpPreset(k){
  if(MP_D.pre===k){MP_D.de='';MP_D.ate='';MP_D.pre='';}
  else{
    const h=new Date(); h.setHours(0,0,0,0);
    if(k==='mes'){MP_D.de=mpISO(new Date(h.getFullYear(),h.getMonth(),1));
                  MP_D.ate=mpISO(new Date(h.getFullYear(),h.getMonth()+1,0));}
    else if(k==='tri'){MP_D.de=mpISO(h);MP_D.ate=mpISO(new Date(h.getFullYear(),h.getMonth()+3,h.getDate()));}
    else if(k==='ano'){MP_D.de=h.getFullYear()+'-01-01';MP_D.ate=h.getFullYear()+'-12-31';}
    else if(k==='venc'){MP_D.de='';MP_D.ate=mpISO(new Date(h.getTime()-864e5));}
    MP_D.pre=k;
  }
  mpDataUI(); renderMpas();
}
function mpDataUI(){
  const de=document.getElementById('mp-d-de'), at=document.getElementById('mp-d-ate');
  if(!de)return;
  de.value=MP_D.de; at.value=MP_D.ate;
  de.classList.toggle('on',!!MP_D.de); at.classList.toggle('on',!!MP_D.ate);
  ['mes','tri','ano','venc'].forEach(k=>{const b=document.getElementById('mp-pre-'+k);
    if(b)b.classList.toggle('on',MP_D.pre===k);});
}
function mpLimpar(){
  Object.keys(MP_SEL).forEach(k=>MP_SEL[k].clear());
  MP_F.concluidas=false; MP_D.de='';MP_D.ate='';MP_D.pre=''; MP_ACAO='';
  const cb=document.getElementById('mp-f-conc'); if(cb)cb.checked=false;
  Object.keys(MP_MS).forEach(k=>{mpBuildPop(k);mpMsLabel(k);});
  mpDataUI(); renderMpas();
}
function mpChips(){
  const out=[];
  if(MP_ACAO)out.push('<span class="mp-chip" onclick="mpAcaoSet(&quot;'+MP_ACAO+'&quot;)">'
    +esc(MP_ACAO_LBL[MP_ACAO]||MP_ACAO)+' ✕</span>');
  if(MP_D.de||MP_D.ate){
    const br=s=>s?s.split('-').reverse().join('/'):'';
    const rot=MP_D.de&&MP_D.ate?br(MP_D.de)+' a '+br(MP_D.ate)
             :MP_D.de?'a partir de '+br(MP_D.de):'até '+br(MP_D.ate);
    out.push('<span class="mp-chip" onclick="mpData(\'de\',\'\');mpData(\'ate\',\'\')">📅 '+rot+' ✕</span>');
  }
  Object.keys(MP_MS).forEach(k=>MP_SEL[k].forEach(v=>{
    out.push('<span class="mp-chip" onclick="mpTiraChip(\''+k+'\',\''+esc(String(v)).replace(/'/g,"\\'")+'\')">'
      +esc(v)+' ✕</span>');
  }));
  document.getElementById('mp-chips').innerHTML=out.join('');
}
function mpTiraChip(k,v){MP_SEL[k].delete(v);mpBuildPop(k);mpMsLabel(k);renderMpas();}
// ---- árvore Cluster ▸ Usina ▸ Tipo (mesma navegação da Gestão PCM) ----
let MP_TIP=[];                                    // listas por nó de tipo (lazy)
function mpTog(el){el.parentElement.classList.toggle('gp-open');}
function mpTogTip(el,idx){
  const wrap=el.parentElement, body=wrap.querySelector('.gp-tip-b');
  wrap.classList.toggle('gp-open');
  if(body.dataset.filled==='1')return;
  body.innerHTML=mpTabela(MP_TIP[idx]||[]);
  body.dataset.filled='1';
  body.querySelectorAll('tr[data-k]').forEach(tr=>tr.onclick=()=>mpModal(tr.dataset.k));
}
function mpTabela(list){
  if(!list.length)return '<div class="gp-nores">—</div>';
  const nl=s=>esc(String(s||'')).replace(/\r?\n/g,'<br>');
  const linhas=list.map(r=>{
    const s=mpSit(r), x=mpBd(r);
    return '<tr data-k="'+esc((r.os||'')+'|'+r.usina+'|'+r.tipo+'|'+r.prevista)+'">'
      +'<td class="mp-os">'+(r.os?('#'+esc(r.os)):'—')+'</td>'
      +'<td><span class="spill '+s.cls+'">'+s.k+'</span>'
        +(x?' <span class="bdtag">'+x.fin+'/'+x.total+'</span>':'')+'</td>'
      +'<td class="mp-dt">'+(r.prevista?esc(mpDataBR(r.prevista)):'—')+'</td>'
      +'<td class="mp-eq">'+(r.equipe?nl(r.equipe):'—')+'</td>'
      +'<td class="mp-ap">'+(r.apoio?nl(r.apoio):'—')+'</td>'
      // 19/08: o MOTIVO vem das colunas de pendência da planilha (equipamento
      // faltante, compra, desligamento perdido). A "Observação" conta a
      // história; esta coluna diz a causa. Texto completo no title.
      +(typeof mpMotivo==='function'
        ? (()=>{const m=mpMotivo(r);
            return '<td class="mp-mot"'+(m.det?' title="'+esc(m.det)+'"':'')+'>'
                 +(m.txt?'⚠ '+esc(m.txt):'—')+'</td>';})()
        : '')
      +'<td class="mp-ob">'+(r.obs?nl(r.obs):'—')+'</td></tr>';
  }).join('');
  return '<div class="mp-tblwrap"><table class="mp-tbl"><thead><tr>'
    +'<th>OS ID</th><th>Situação</th><th>Data Prevista</th>'
    +'<th>Equipe</th><th>Apoio na equipe</th>'
    +(typeof mpMotivo==='function'?'<th>Por que está parado</th>':'')
    +'<th>Observação</th>'
    +'</tr></thead><tbody>'+linhas+'</tbody></table></div>';
}
const mpDataBR=iso=>{const p=String(iso||'').split('-');return p.length===3?(p[2]+'/'+p[1]+'/'+p[0]):iso;};

// ---- Frentes de compra de equipamento (aba "Compra Equip MPA 2026") ----
// O Excel manda nas quantidades e abatimentos (julgamento do PCM); a âncora,
// o prazo e a frente são recalculados no gerador a partir das datas reais.
let MP_CMP_ABERTO=false;
const mpBRL=v=>'R$ '+(Math.round(v||0)).toLocaleString('pt-BR');
const mpDia=s=>s?s.split('-').reverse().join('/'):'—';
function mpDias(iso){
  if(!iso)return null;
  const h=new Date(); h.setHours(0,0,0,0);
  return Math.round((new Date(iso+'T00:00:00')-h)/864e5);
}
function mpCompras(){
  const box=document.getElementById('mp-compras');
  if(!box)return;
  const C=MP&&MP.compras;
  if(!C||!C.clusters||!C.clusters.length){box.innerHTML='';return;}
  const hojeISO=new Date().toISOString().slice(0,10);
  // agrupa por frente, somando valor, clusters e MPAs destravadas
  const fr={};
  C.clusters.forEach(c=>{
    const f=fr[c.frente]=fr[c.frente]||{n:0,A:0,B:0,mpas:0,venc:0,prazo:null,cls:[]};
    f.n++; f.A+=c.valorA||0; f.B+=c.valorB||0; f.mpas+=c.mpas||0; f.cls.push(c.cluster);
    if(c.ancora&&c.ancora<hojeISO)f.venc++;
    if(c.ancora&&(!f.prazo||c.ancora<f.prazo))f.prazo=c.ancora;
  });
  const ordem=Object.keys(fr).sort();
  const tA=C.clusters.reduce((s,c)=>s+(c.valorA||0),0);
  const tB=C.clusters.reduce((s,c)=>s+(c.valorB||0),0);
  const totMpas=C.clusters.reduce((s,c)=>s+(c.mpas||0),0);
  const cards=ordem.map(k=>{
    const f=fr[k], venc=f.venc>0, d=mpDias(f.prazo);
    const sel=[...MP_SEL.cluster].length&&f.cls.every(c=>MP_SEL.cluster.has(c));
    return '<div class="cmp-card'+(venc?' venc':'')+(sel?' sel':'')+'" onclick="mpFiltrarFrente(\''+esc(k).replace(/'/g,"\\'")+'\')" '
      +'title="clique para ver só os clusters desta frente">'
      +'<div class="top" style="background:'+(venc?'#c0392b':'#1C1F3B')+'"></div>'
      +'<div class="cl">'+esc(k)+'</div>'
      +'<div class="cv"'+(venc?' style="color:#c0392b"':'')+'>'+mpBRL(f.A)+'</div>'
      +'<div class="cs">'+f.n+' cluster'+(f.n>1?'s':'')+' · destrava <b>'+f.mpas+' MPA'+(f.mpas>1?'s':'')+'</b></div>'
      +'<div class="ctag '+(venc?'t-red':'t-gray')+'">'
      +(venc?f.venc+' já vencida'+(f.venc>1?'s':''):'')
      +(venc?' · ':'')+'prazo '+mpDia(f.prazo)
      +(!venc&&d!=null?' · em '+d+' dias':'')+'</div></div>';
  }).join('');
  // ressalvas que fazem do número um piso
  const av=[];
  const pend=C.clusters.filter(c=>c.pendencia).map(c=>c.cluster);
  if(pend.length)av.push('<b>'+pend.length+' cluster(s) sem tensão cadastrada</b> (aterramento zerado): '+pend.join(', '));
  (C.semDimensionamento||[]).forEach(f=>av.push('<b>'+esc(f.cluster)+' sem linha de dimensionamento</b> — MPA em '+mpDia(f.ancora)+' ('+esc(f.usina||'')+')'));
  if(C.semCluster)av.push(C.semCluster+' MPA(s) sem cluster ficaram fora do rateio');
  const custoMpa=totMpas?tA/totMpas:0;
  box.innerHTML=
    '<div class="cmp-cap">Frentes de compra · equipamento para as '+(C.totalMpas||0)+' MPAs de '
    +mpDia(C.janela&&C.janela[0])+' a '+mpDia(C.janela&&C.janela[1])+'</div>'
    +'<div class="cmp-box"><div class="cmp-grid">'+cards+'</div>'
    +'<div class="cmp-tot">'
    +'<div class="tt"><i>Total do plano</i><b>'+mpBRL(tA)+'</b></div>'
    +'<div class="tt"><i>Cenário econômico</i><b>'+mpBRL(tB)+'</b></div>'
    +'<div class="tt"><i>Diferença</i><b style="color:#3f6b12">'+mpBRL(tA-tB)+'</b></div>'
    +'<div class="tt"><i>Custo por MPA viabilizada</i><b>'+mpBRL(custoMpa)+'</b></div>'
    +'<button class="rp-btn sec" style="margin-left:auto" onclick="mpCmpTog()">'
    +(MP_CMP_ABERTO?'▴ ocultar':'▾ ver')+' os '+C.clusters.length+' clusters</button></div>'
    +(av.length?'<div class="cmp-av"><span>⚠</span><div><b>O valor é piso, não teto.</b> '+av.join(' · ')+'</div></div>':'')
    +(MP_CMP_ABERTO?mpCmpTabela(C,hojeISO):'')
    +'</div>';
}
// Composição do valor por cluster (14/08/2026): o financeiro precisa saber o
// QUE está sendo comprado, não só o total. Os itens já vinham no mpas.json
// (qtd por equipamento + aterramento) e as premissas trazem o preço unitário;
// aqui eles viram uma linha expansível sob o cluster.
const CMP_ITENS = [
  ['megometro',     'Megômetro 5 kV'],
  ['microhmimetro', 'Microhmímetro 10 kV'],
  ['terrometro',    'Terrômetro'],
  ['chave_impacto', 'Chave de impacto + bateria + carregador'],
  ['lanterna',      'Lanterna refletora à bateria'],
];
let MP_CMP_LINHA = null;                    // cluster com a composição aberta

function mpCmpPreco(rotulo){
  const P = (MP && MP.compras && MP.compras.premissas) || [];
  const p = P.find(x => String(x.item || '').toLowerCase().startsWith(rotulo.toLowerCase().slice(0, 14)));
  return p ? p.valor : 0;
}

function mpCmpComposicao(c){
  const linhas = [];
  let somaA = 0;
  CMP_ITENS.forEach(([k, rot]) => {
    const q = Number((c.qtd || {})[k] || 0);
    if (!q) return;
    const unit = mpCmpPreco(rot), tot = q * unit;
    somaA += tot;
    linhas.push([rot, q, unit, tot]);
  });
  if (c.aterramento) {
    somaA += c.aterramento;
    const faixa = (c.faixa && c.faixa !== 'PENDENTE') ? ' (' + c.faixa + ')' : '';
    linhas.push(['Aterramento temporário' + faixa, 1, c.aterramento, c.aterramento]);
  }
  let h = '<div class="cmp-comp"><div class="cmp-comp-t">Composição do Cenário A &mdash; '
        + esc(c.cluster) + '</div><table class="cmp-comp-tbl"><thead><tr>'
        + '<th>Item</th><th style="text-align:center">Qtd</th>'
        + '<th style="text-align:right">Unitário</th><th style="text-align:right">Total</th></tr></thead><tbody>';
  linhas.forEach(([rot, q, u, t]) => {
    h += '<tr><td>' + esc(rot) + '</td><td style="text-align:center">' + q + '</td>'
       + '<td style="text-align:right">' + mpBRL(u) + '</td>'
       + '<td style="text-align:right"><b>' + mpBRL(t) + '</b></td></tr>';
  });
  if (!linhas.length)
    h += '<tr><td colspan="4" style="color:#8a8a94">Sem itens dimensionados para este cluster.</td></tr>';
  h += '</tbody><tfoot><tr><td colspan="3" style="text-align:right">Cenário A</td>'
     + '<td style="text-align:right"><b>' + mpBRL(c.valorA) + '</b></td></tr>'
     + '<tr><td colspan="3" style="text-align:right">Cenário B (alternativa mais econômica)</td>'
     + '<td style="text-align:right"><b>' + mpBRL(c.valorB) + '</b></td></tr></tfoot></table>';
  // divergência entre a soma dos itens e o total da planilha: mostra, não esconde
  if (Math.abs(somaA - (c.valorA || 0)) > 1)
    h += '<div class="cmp-comp-av">A soma dos itens (' + mpBRL(somaA) + ') difere do valor da planilha ('
       + mpBRL(c.valorA) + '). Conferir a linha do cluster na aba Compra Equip MPA 2026.</div>';
  if (c.obs) h += '<div class="cmp-comp-obs">' + esc(c.obs) + '</div>';
  const mpas = c.mpas || 0;
  h += '<div class="cmp-comp-obs">Destrava <b>' + mpas + '</b> MPA(s)'
     + (c.ancoraUsina ? ' &middot; âncora: ' + esc(c.ancoraUsina) : '')
     + (mpas ? ' &middot; custo por MPA: <b>' + mpBRL((c.valorA || 0) / mpas) + '</b>' : '') + '</div>';
  return h + '</div>';
}

function mpCmpLinha(cl){
  MP_CMP_LINHA = (MP_CMP_LINHA === cl) ? null : cl;
  mpCompras();
}

function mpCmpTabela(C,hojeISO){
  const l=C.clusters.slice().sort((a,b)=>String(a.ancora||'9').localeCompare(String(b.ancora||'9')));
  let h='<div style="overflow-x:auto"><table class="cmp-tbl"><thead><tr>'
    +'<th></th><th>Cluster</th><th>Cliente</th><th>Âncora</th><th>MPAs</th>'
    +'<th style="text-align:right">Cenário A</th><th style="text-align:right">Cenário B</th><th>Situação</th></tr></thead><tbody>';
  l.forEach(c=>{
    const venc=c.ancora&&c.ancora<hojeISO, d=mpDias(c.ancora);
    const st=venc?'<span class="cmp-pill p-red">vencida há '+Math.abs(d)+'d</span>'
      :c.pendencia?'<span class="cmp-pill p-amb">tensão pendente</span>'
      :'<span class="cmp-pill p-ok">em '+d+' dias</span>';
    const aberto = (MP_CMP_LINHA === c.cluster);
    h+='<tr class="cmp-row'+(aberto?' on':'')+'" onclick="mpCmpLinha(&quot;'+esc(c.cluster)+'&quot;)" '
      +'title="Ver o que compõe o valor">'
      +'<td class="cmp-cv">'+(aberto?'&#9662;':'&#9656;')+'</td>'
      +'<td><b>'+esc(c.cluster)+'</b></td><td>'+esc(c.cliente||'')+'</td><td>'+mpDia(c.ancora)+'</td>'
      +'<td>'+(c.mpas||0)+'</td><td style="text-align:right">'+mpBRL(c.valorA)+'</td>'
      +'<td style="text-align:right">'+mpBRL(c.valorB)+'</td><td>'+st+'</td></tr>';
    if(aberto) h+='<tr class="cmp-comp-row"><td colspan="8">'+mpCmpComposicao(c)+'</td></tr>';
  });
  return h+'</tbody></table></div>';
}
function mpCmpTog(){MP_CMP_ABERTO=!MP_CMP_ABERTO;mpCompras();}
function mpFiltrarFrente(f){
  const C=MP&&MP.compras; if(!C)return;
  const alvo=C.clusters.filter(c=>c.frente===f).map(c=>c.cluster);
  const jaEsta=alvo.length&&alvo.every(c=>MP_SEL.cluster.has(c))&&MP_SEL.cluster.size===alvo.length;
  MP_SEL.cluster.clear();
  if(!jaEsta)alvo.forEach(c=>MP_SEL.cluster.add(c));
  mpBuildPop('cluster'); mpMsLabel('cluster'); renderMpas();
}

function renderMpas(){
  if(!MP)return;
  document.getElementById('mp-lock').style.display='none';
  document.getElementById('mp-body').style.display='';
  mpFiltros(); mpChips(); mpKpis(); mpCompras();
  if(typeof mpAcao==='function'){try{mpAcao();}catch(e){console.warn('painel de ação:',e);}}
  const mostrarConc=MP_F.concluidas||MP_SEL.situacao.has('Concluída')||MP_ACAO==='ok';
  const rows=mpFilt().filter(r=>mostrarConc||mpSit(r).k!=='Concluída');
  document.getElementById('mp-hint').textContent=
    (mostrarConc?'Todas as manutenções':'Não finalizadas')
    +' · agrupadas por Equipe Cluster ▸ Usina ▸ Tipo · clique numa linha para ver as tarefas do Fracttal';
  // monta a árvore
  const tree={};
  rows.forEach(r=>{
    const cl=r.cluster||'(sem cluster)', us=r.usina_curta||r.usina||'(sem usina)', tp=r.tipo||'—';
    const C=tree[cl]=tree[cl]||{usinas:{},n:0};
    const U=C.usinas[us]=C.usinas[us]||{tipos:{},n:0};
    (U.tipos[tp]=U.tipos[tp]||[]).push(r);
    C.n++; U.n++;
  });
  MP_TIP=[];
  const box=document.getElementById('mp-tree');
  // "(sem cluster)" vai para o fim — é pendência de cadastro, não um cluster real
  const semC='(sem cluster)';
  const keys=Object.keys(tree).sort((a,b)=>
    (a===semC)-(b===semC) || a.localeCompare(b,'pt-BR'));
  if(!keys.length){ box.innerHTML='<div class="calempty">Nenhuma manutenção com os filtros atuais.</div>'; }
  else{
    const atr=l=>l.filter(r=>mpSit(r).k==='Atrasada').length;
    const chip=n=>n>0?' <span class="gp-badge-t" style="background:#d94f3d;color:#fff">⏱ '+n+'</span>':'';
    box.innerHTML=keys.map(cl=>{
      const C=tree[cl];
      const nAtrC=Object.values(C.usinas).flatMap(u=>Object.values(u.tipos)).flat().filter(r=>mpSit(r).k==='Atrasada').length;
      let h='<div class="gp-cli"><div class="gp-cli-h" onclick="mpTog(this)"><span class="nm">'+esc(cl)
        +'</span><span style="display:flex;align-items:center;gap:8px"><span class="gp-badge">'+C.n+'</span>'
        +chip(nAtrC)+'<span class="gp-chev">▾</span></span></div><div class="gp-cli-b">';
      Object.keys(C.usinas).sort((a,b)=>a.localeCompare(b,'pt-BR')).forEach(us=>{
        const U=C.usinas[us];
        const nAtrU=Object.values(U.tipos).flat().filter(r=>mpSit(r).k==='Atrasada').length;
        h+='<div class="gp-usi"><div class="gp-usi-h" onclick="mpTog(this)"><span class="nm">'+esc(us)
          +'</span><span style="display:flex;align-items:center;gap:8px"><span class="gp-badge-d">'+U.n+'</span>'
          +chip(nAtrU)+'<span class="gp-chev-s">▾</span></span></div><div class="gp-usi-b">';
        Object.keys(U.tipos).sort().forEach(tp=>{
          const list=U.tipos[tp].slice().sort((a,b)=>String(a.prevista||'').localeCompare(String(b.prevista||'')));
          const idx=MP_TIP.push(list)-1;
          h+='<div class="gp-tip"><div class="gp-tip-h" onclick="mpTogTip(this,'+idx+')">'
            +'<span class="nm"><span class="ttag '+mpTipoCls(tp)+'">'+esc(tp)+'</span></span>'
            +'<span style="display:flex;align-items:center;gap:6px"><span class="gp-badge-t">'+list.length+'</span>'
            +chip(atr(list))+'<span class="gp-chev-s">▾</span></span></div>'
            +'<div class="gp-tip-b" data-filled="0"></div></div>';
        });
        h+='</div></div>';
      });
      return h+'</div></div>';
    }).join('');
  }
  const nBD=MP.bd?Object.keys(MP.bd).length:0;
  document.getElementById('mp-foot').textContent=
    MP.manut.length+' manutenções da aba "MPAS" (Gerencial - PCM_2026_R00.xlsx) · '
    +nBD+' OS cruzadas com o Fracttal · dados de '+(MP.geradoEm||'—');
  const sub=document.getElementById('mp-sub');
  // idade do dado MPAS: o topo do painel mostra a idade do banco_dados.json,
  // que é outro arquivo e outro robô — aqui o número é o desta aba.
  if(sub){
    let idade='';
    const g=MP.geradoEm?new Date(MP.geradoEm):null;
    if(g&&!isNaN(g)){
      const min=Math.round((Date.now()-g.getTime())/60000);
      const txt=min<60?min+' min':(min<1440?Math.round(min/60)+' h':Math.round(min/1440)+' dia(s)');
      const cor=min>2880?'#b91c1c':(min>1440?'#8a5a08':'#5E8C1A');
      idade=' · <b style="color:'+cor+'">dados de '+g.toLocaleString('pt-BR',
              {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})+
            ' (há '+txt+')</b>';
      if(min>1440) idade+=' <span style="color:#8a5a08">— atualize em PCM_Painel &rarr; Utilitários</span>';
    }
    sub.innerHTML='MPA e MPS por Equipe Cluster · planilha Gerencial + API Fracttal'+idade;
  }
}
function mpModal(key){
  const [os,usina,tipo,prev]=String(key).split('|');
  const r=(MP.manut||[]).find(x=>String(x.os||'')===os&&x.usina===usina&&x.tipo===tipo&&x.prevista===prev);
  if(!r)return;
  const b=mpBd(r), s=mpSit(r);
  const linha=(l,v)=>v?('<div class="mrow"><span class="mk">'+l+'</span><span class="mv">'+esc(String(v))+'</span></div>'):'';
  let h='<div class="mtop2"><button class="mtop2-close" onclick="closeMod()">✕</button>'
   +'<div class="mtop2-row"><span class="mtop2-os">'+(r.os?('OS #'+esc(r.os)):'sem OS')+'</span>'
   +'<span class="spill '+s.cls+'">'+s.k+'</span></div>'
   +'<div class="mtop2-title">'+esc(r.usina)+'</div>'
   +'<div class="mtop2-sub">'+esc([r.cliente,r.cluster,r.tipo].filter(Boolean).join(' · '))+'</div></div>';
  h+='<div class="msec"><div class="msec-t">📅 Datas</div>'
   + linha('Prevista',r.prevista)+linha('Início',r.inicio)+linha('Término',r.termino)
   + linha('Ciclo',r.ciclo)+linha('Prioridade',r.prioridade)+'</div>';
  h+='<div class="msec"><div class="msec-t">👥 Equipe</div>'
   + linha('Supervisor',r.supervisor)+linha('Apoio',r.apoio)
   + linha('Status da OS (planilha)',r.status)+linha('Relatório',r.relatorio)+'</div>';
  if(r.hectare||r.modulos)
    h+='<div class="msec"><div class="msec-t">🔆 Usina</div>'
     + linha('Hectares',r.hectare)+linha('Módulos',r.modulos)
     + linha('Trafos a óleo',r.trafos_oleo)+linha('Análise de óleo',r.oleo)+'</div>';
  if(b&&b.tasks&&b.tasks.length){
    h+='<div class="msec"><div class="msec-t">🔧 Tarefas no Fracttal ('+b.fin+'/'+b.total+')</div>';
    h+='<div class="mtasks">'+b.tasks.map(t=>{
      const e=(t.estado||'').toLowerCase();
      const cl=e.startsWith('finaliz')?'green':(e==='em progresso'||e==='pausado')?'blue':'amber';
      return '<div class="mtask"><span class="spill '+cl+'">'+esc(t.estado||'—')+'</span> '+esc(t.tarefa||'')+'</div>';
    }).join('')+'</div></div>';
  }
  if(r.obs)h+='<div class="msec"><div class="msec-t">📝 Observação</div><div class="mtarefa">'+esc(r.obs)+'</div></div>';
  const mb=document.querySelector('#modal .mbox');
  if(mb){mb.innerHTML=h;document.getElementById('modal').classList.add('open');}
}
async function initMpas(forcar){
  const lock=document.getElementById('mp-lock'), body=document.getElementById('mp-body');
  // forcar=true vem do "Atualizar agora": sem isso o MPAS ficava preso ao
  // primeiro carregamento da sessão e só um F5 trazia o mpas.json novo.
  if(forcar) MP=null;
  if(MP){renderMpas();return;}
  try{
    const pack=await mpCarregarPack(forcar);
    if(!pack.cifrado){ MP=pack; renderMpas(); return; }        // arquivo em claro
    const s=sessionStorage.getItem('gc_mp_k');                 // já abriu nesta sessão?
    if(s){ try{ MP=await mpDecifrar(pack,s); renderMpas(); return; }catch(e){} }
    lock.style.display=''; body.style.display='none';
    const sub=document.getElementById('mp-sub');
    if(sub)sub.textContent=(pack.itens||0)+' manutenções · conteúdo protegido';
  }catch(e){
    lock.style.display='none'; body.style.display='';
    document.getElementById('mp-grid').innerHTML=
      '<div class="calempty" style="grid-column:1/-1">Não foi possível carregar o mpas.json.<br>'
      +'Gere com <code>py -3 gerar_mpas_json.py</code> e publique.</div>';
  }
}

// toast() era chamado em vários pontos (setAW, saveAdminGo, reprogramação) mas
// nunca chegou a ser definido — as chamadas quebravam silenciosamente.
function toast(msg,ms){
  let t=document.getElementById('gc-toast');
  if(!t){ t=document.createElement('div'); t.id='gc-toast'; document.body.appendChild(t); }
  t.textContent=String(msg||'');
  t.classList.add('on');
  clearTimeout(t._h);
  t._h=setTimeout(()=>t.classList.remove('on'), ms||2600);
}

// Barra fixa da fila — vive FORA da seção de pendentes (que é sanfona e fica
// no fim da página), senão quem insere pelo modal do calendário não a encontra.
function rpDock(){
  let d=document.getElementById('rp-dock');
  // só na aba Programação Semanal — nas outras (Gestão PCM, etc.) a fila atrapalha
  const naSemana=(typeof S==='undefined')||!S.topView||S.topView==='semana';
  if(!RP_OK||!RP.length||!naSemana){ if(d)d.remove(); return; }
  if(!d){ d=document.createElement('div'); d.id='rp-dock'; document.body.appendChild(d); }
  const aberto=d.classList.contains('open');
  d.className=aberto?'open':'';
  d.innerHTML='<div class="rp-dock-h">'
    +'<span class="rp-dock-t">📋 '+RP.length+' reprogramação(ões) na fila</span>'
    +'<button class="rp-btn sec" onclick="rpVer()">'+(aberto?'Ocultar':'Ver linhas')+'</button>'
    +'<button class="rp-btn" onclick="rpCopiar()">Copiar tudo</button>'
    +'<button class="rp-btn sec" onclick="rpLimpar()">Limpar</button>'
    +'</div><div class="rp-prev">'+esc(rpTexto())+'</div>';
}
function rpVer(){
  const d=document.getElementById('rp-dock');
  if(d){ d.classList.toggle('open'); rpDock(); }
}
function rpLimpar(){
  if(!RP_OK)return;
  if(!RP.length)return;
  if(!confirm('Limpar as '+RP.length+' reprogramações da fila?'))return;
  RP=[];rpSave();renderPendentes();
}
// ---- M3: alerta do dia (13:30/16:45) + captura de motivo — só admin ----
const MOTIVOS_FIXOS=['Emergencial furou a fila','Aguarda peça/material','Chuva/clima',
  'Acesso à usina negado','Equipe incompleta','Serviço maior que o estimado','Deslocamento','Outro'];
let MV={};                                  // {os: motivo} escolhidos nesta sessão
function mvLinhas(){
  const A=DB&&DB.alertas, out=[];
  Object.keys(MV).forEach(os=>{
    const it=(A&&A.itens||[]).find(i=>String(i.os)===String(os));
    out.push('# motivo OS '+os+(it?' ('+it.equipe+')':'')+': '+MV[os]);
  });
  return out;
}
function mvSet(os,v){
  if(v==='Outro'){
    const t=prompt('Descreva o motivo (curto):','');
    if(!t){return;}
    v='Outro: '+t.slice(0,60);
  }
  if(v)MV[os]=v; else delete MV[os];
  renderAlertas();
}
function mvCopiar(){
  const ls=mvLinhas();
  if(!ls.length){toast('Nenhum motivo selecionado');return;}
  navigator.clipboard.writeText(ls.join('\n')).then(()=>toast(ls.length+' motivo(s) copiados — cole nas Observações da Semana Atual (PCM_Painel)'));
}
function renderAlertas(){
  let box=document.getElementById('alerta-dia-box');
  if(!box){
    const p=document.getElementById('pendentes');
    if(!p)return;
    box=document.createElement('div');box.id='alerta-dia-box';
    p.parentNode.insertBefore(box,document.getElementById('qualidade-box')||p);
  }
  const A=DB&&DB.alertas;
  const hojeISO=new Date().toISOString().slice(0,10);
  if(!S.isAdmin||!A||A.data!==hojeISO||!A.janela||!(A.itens||[]).length){box.innerHTML='';return;}
  const cor=A.janela==='16:45'?'#b91c1c':'#8a5a08';
  const fundo=A.janela==='16:45'?'#fef2f2':'#fffaf0';
  const borda=A.janela==='16:45'?'#f0b9b0':'#f0dcae';
  const porEq={};(A.itens||[]).forEach(i=>{(porEq[i.equipe]=porEq[i.equipe]||[]).push(i);});
  const linhas=Object.keys(porEq).sort().map(eq=>{
    const its=porEq[eq].map(i=>{
      const sel='<select class="mv-sel" onchange="mvSet(\''+esc(String(i.os))+'\',this.value)">'
        +'<option value="">motivo…</option>'
        +MOTIVOS_FIXOS.map(m=>'<option'+(MV[i.os]===m?' selected':'')+'>'+esc(m)+'</option>').join('')
        +(MV[i.os]&&MV[i.os].indexOf('Outro: ')===0?'<option selected>'+esc(MV[i.os])+'</option>':'')
        +'</select>';
      return '<div class="al-i"><b>OS '+esc(String(i.os))+'</b> · '+esc((i.usina||'').split(' - ').slice(-2).join(' - '))
        +' · '+esc(i.tarefa||'')+' <span class="al-h">'+esc(i.h_ini||'')+'–'+esc(i.h_fim||'')
        +' · '+esc(i.estado||'')+'</span> '+sel+'</div>';
    }).join('');
    return '<div class="al-eq">'+esc(eq)+' — '+porEq[eq].length+' em risco</div>'+its;
  }).join('');
  // Pareto dos motivos já capturados (linhas "# motivo ..." das observações)
  let pareto='';
  const ms=DB.motivos||[];
  if(ms.length){
    const c={};ms.forEach(m=>{const k=(m.motivo||'').indexOf('Outro:')===0?'Outro':(m.motivo||'');c[k]=(c[k]||0)+1;});
    const tot=ms.length,ord=Object.entries(c).sort((a,b)=>b[1]-a[1]).slice(0,8);
    pareto='<div class="al-pareto"><b>Pareto de causas ('+tot+' motivos na semana):</b> '
      +ord.map(([k,n])=>esc(k)+' <b>'+n+'</b>').join(' · ')+'</div>';
  }
  box.innerHTML='<div class="al-box" style="background:'+fundo+';border-color:'+borda+'">'
    +'<div class="al-h1" style="color:'+cor+'">'+(A.janela==='16:45'?'🔴':'🟡')+' Alerta '+A.janela
    +' — '+(A.itens||[]).length+' tarefa(s) do dia não fechadas'
    +'<span class="al-ad">aderência até agora: '+A.fechadas+' de '+A.doDia+'</span></div>'
    +linhas
    +'<div class="al-foot"><button class="rp-btn" onclick="mvCopiar()">📋 Copiar '+(mvLinhas().length||'')+' motivo(s)</button>'
    +'<span class="al-dica">cole nas Observações da Semana Atual — sem motivo até 23:59, rola como "não informado"</span></div>'
    +pareto+'</div>';
}

// ---- Portão de qualidade (0.7): avisos de cadastro da geração — só admin ----
function renderQualidade(){
  let box=document.getElementById('qualidade-box');
  if(!box){
    const p=document.getElementById('pendentes');
    if(!p)return;
    box=document.createElement('div');box.id='qualidade-box';
    p.parentNode.insertBefore(box,p);
  }
  const w=AW(),q=(S.isAdmin&&w&&Array.isArray(w.qualidade))?w.qualidade:[];
  if(!q.length){box.innerHTML='';return;}
  const rem=q.filter(x=>x.tipo==='REMOVIDA'),av=q.filter(x=>x.tipo==='AVISO');
  box.innerHTML='<div class="qual-box"><div class="qual-h" onclick="this.parentNode.classList.toggle(\'open\')">'
    +'<span>🧹 Qualidade do cadastro — '
    +(rem.length?rem.length+' linha(s) de teste removida(s)':'')
    +(rem.length&&av.length?' · ':'')
    +(av.length?av.length+' aviso(s)':'')
    +'</span><span class="gp-chev">▾</span></div><div class="qual-b">'
    +q.map(x=>'<div class="qual-i"><b class="'+(x.tipo==='REMOVIDA'?'q-rem':'q-av')+'">'+esc(x.tipo)+'</b> '
      +'<b>'+esc(x.item)+'</b> — '+esc(x.detalhe)+(x.acao?' <i>('+esc(x.acao)+')</i>':'')+'</div>').join('')
    +'</div></div>';
}
function renderPendentes(){
  renderAlertas();
  renderQualidade();
  const box=document.getElementById('pendentes');if(!box)return;
  const w=AW();let pend=(w&&Array.isArray(w.pendentes))?w.pendentes.slice():[];
  if(!S.isAdmin&&S.user)pend=pend.filter(p=>_cliEq(p.cliente,S.user));
  else if(S.viewCli)pend=pend.filter(p=>_cliEq(p.cliente,S.viewCli));
  // mesmos filtros multi-seleção do calendário (case-insensitive)
  const Q=SEM_SEL,_L=s=>new Set([...s].map(x=>String(x).toLowerCase())),_in=(set,v)=>set.has(String(v||'').toLowerCase());
  const Lcli=_L(Q.cliente),Lusi=_L(Q.usina),Lclu=_L(Q.cluster),Ltip=_L(Q.tipo);
  pend=pend.filter(p=>{
    if(Q.cliente.size&&!_in(Lcli,p.cliente))return false;
    if(Q.usina.size&&!_in(Lusi,p.usina))return false;
    if(Q.cluster.size&&!_in(Lclu,p.cluster))return false;
    if(Q.tipo.size&&!_in(Ltip,p.tipo))return false;
    if(S.fOS&&String(p.os_id||'').indexOf(S.fOS)<0)return false;
    return true;
  });
  if(!pend.length){box.innerHTML='';rpDock();return;}   // fila continua visível no dock
  const wasOpen=(document.getElementById('pend-wrap')||{}).classList&&document.getElementById('pend-wrap').classList.contains('open');
  const byU={};pend.forEach(p=>{(byU[p.usina]=byU[p.usina]||[]).push(p);});
  let inner='';
  Object.keys(byU).sort((a,b)=>a.localeCompare(b,'pt-BR')).forEach(u=>{
    const sh=u.split(' - ').slice(-2).join(' - ')||u;
    inner+='<div class="pend-usi"><div class="pend-usi-h">'+esc(sh)+'<span class="pend-cnt">'+byU[u].length+'</span></div>';
    byU[u].forEach(p=>{
      const _t=(p.tarefa||'').replace(/'/g,"\\'"), _ti=(p.tipo||'').replace(/'/g,"\\'");
      const ix=rpIdx(p.os_id,p.tarefa), on=RP_OK&&ix>=0, cur=on?RP[ix]:null;
      const dias=[['','dia…'],['seg','seg'],['ter','ter'],['qua','qua'],['qui','qui'],['sex','sex']];
      const turnos=[['','turno…'],['manhã','manhã'],['tarde','tarde'],['noite','noite']];
      const sel=(cls,opts,val)=>'<select class="'+cls+'" onclick="event.stopPropagation()">'
        +opts.map(o=>'<option value="'+o[0]+'"'+((val||'')===o[0]?' selected':'')+'>'+o[1]+'</option>').join('')+'</select>';
      // Reprogramar é ação de PCM: só admin vê os controles (cliente vê a lista, sem editar)
      const ctrl = RP_OK ? ('<span class="rp-box" onclick="event.stopPropagation()">'
        +sel('rp-dia',dias,cur&&cur.dia)+sel('rp-turno',turnos,cur&&cur.turno)
        +'<button class="rp-add'+(on?' on':'')+'" onclick="rpToggle(event,\''+esc(p.os_id)+'\',\''+esc(_t)+'\',\''+esc(_ti)+'\')">'
        +(on?'✓ na fila':'+ Inserir')+'</button></span>') : '';
      inner+='<div class="pend-row'+(RP_OK?'':' no-rp')+(on?' rp-on':'')+'" onclick="openMod(\''+esc(u)+'\',\'\',\''+esc(p.os_id)+'\')">'
      +'<span class="pend-os">#'+esc(p.os_id)+'</span><span class="pend-tar">'+esc(p.tarefa||'—')+'</span>'
      +'<span class="pend-tipo">'+esc(p.tipo||'')+'</span><span class="pend-mot">'+esc(p.motivo||'')+'</span>'
      +ctrl+'</div>';});
    inner+='</div>';
  });
  // dica de onde colar (a fila em si vive no dock fixo — ver rpDock)
  let rpBar='';
  if(RP_OK&&RP.length){
    rpBar='<div class="rp-bar"><span class="rp-bar-t">📋 '+RP.length+' na fila — use a barra verde no rodapé para copiar</span>'
      +'<span class="pend-desc" style="width:100%">Cole no <b>PCM_Painel</b> → aba <b>Observações</b> (próxima semana) ou <b>Semana Atual</b> (semana em andamento), e gere a programação.</span></div>';
  }
  box.innerHTML='<div class="pend-wrap'+(wasOpen?' open':'')+'" id="pend-wrap">'
    +'<div class="pend-master-h" onclick="togPend()"><div><div class="pend-ttl">&#9203; N&atilde;o couberam na semana <span class="pend-badge">'+pend.length+'</span></div>'
    +'<div class="pend-desc">'+(RP_OK
        ?'OS planejadas que estouraram a capacidade do dia — escolha dia/turno e clique <b>+ Inserir</b> para montar as observações.'
        :'OS planejadas que não couberam na capacidade da semana — serão reprogramadas pela equipe de PCM da Grid Co.')+'</div></div>'
    +'<span class="pend-chev">&#9662;</span></div><div class="pend-body">'+rpBar+inner+'</div></div>';
  rpDock();
}

// === SUGESTOES PCM ===
const SUG_KEY='gc_sug_state';
function lerSugState(){try{return JSON.parse(localStorage.getItem(SUG_KEY)||'{}');}catch(e){return {};}}
function salvarSugState(s){try{localStorage.setItem(SUG_KEY,JSON.stringify(s));}catch(e){}}
function setSugAcao(num,acao){const s=lerSugState();s[num]={acao:acao,ts:new Date().toISOString()};salvarSugState(s);renderSugestoes();}
function sugCriticidadeClass(c){const x=(c||'').toLowerCase();if(x.includes('muito'))return'sug-crit-muito';if(x.includes('alto'))return'sug-crit-alto';if(x.includes('m\u00e9dio')||x.includes('medio'))return'sug-crit-medio';return'sug-crit-baixo';}
function renderSugestoes(){
  // Solicitações IA aparecem APENAS na aba dedicada "Sugestões IA".
  // Independente de semana (SUGESTOES_DB já é semana-independente).
  if(S.topView && S.topView !== 'sugestoesIA'){ document.querySelectorAll('#sug-card').forEach(el=>el.style.display='none'); return; }
  document.querySelectorAll('#sug-card').forEach(el=>el.style.display='');
  const body=document.getElementById('sug-body');
  const cnt=document.getElementById('sug-cnt');
  const ts=document.getElementById('sug-ts');
  if(!body) return;
  const state=lerSugState();
  const lista=(SUGESTOES_DB||[]).filter(s=>{
    // 1) Sem OS criada
    const osCriada=String(s['OS Criada no Sistema']||s.os_criada||'').trim();
    if(osCriada) return false;
    // 2) Status no PCM ≠ OS criada / Cancelada / Não mais Aberta
    const st=String(s['Status no PCM']||s.status||'').toLowerCase();
    if(st.indexOf('os criada')>=0) return false;
    if(st.indexOf('não mais aberta')>=0||st.indexOf('nao mais aberta')>=0) return false;
    if(st.indexOf('cancelad')>=0) return false;
    if(st.indexOf('rejeitad')>=0) return false;
    return true;
  });
  if(!lista.length){
    body.innerHTML='<div class="sug-empty">Nenhuma solicita\u00e7\u00e3o pendente de an\u00e1lise no momento.</div>';
    if(cnt) cnt.textContent='0 pendentes';
    if(ts) ts.textContent='Atualizado: '+new Date().toLocaleTimeString('pt-BR');
    return;
  }
  // Ordena por score desc
  lista.sort((a,b)=>{const sa=Number(a.score||a.Score||0),sb=Number(b.score||b.Score||0);return sb-sa;});
  const nPend=lista.filter(s=>!state[s['N\u00ba Solicita\u00e7\u00e3o']||s.numero]).length;
  if(cnt) cnt.textContent=nPend+' pendente'+(nPend!==1?'s':'')+' de '+lista.length;
  const tcnt=document.getElementById('tcnt-sugestoesIA');if(tcnt) tcnt.textContent=nPend;
  if(ts) ts.textContent='Atualizado: '+new Date().toLocaleTimeString('pt-BR');
  const html=lista.map(s=>{
    const num=s['N\u00ba Solicita\u00e7\u00e3o']||s.numero||'';
    const desc=s['Descri\u00e7\u00e3o']||s.descricao||'(sem descri\u00e7\u00e3o)';
    const ativo=s.Ativo||s.ativo||'';
    const crit=s.Criticidade||s.criticidade||'';
    const urg=(s['Urgente?']||s.urgente||'')==='Sim'?'<span class="sug-meta-pill sug-crit-muito">URGENTE</span>':'';
    const rpn=s.RPN||s.rpn||'';
    const score=s.Score||s.score||'';
    const equipe=s.Equipe||s.equipe||'';
    const dia=s['Dia Sugerido']||s.dia_sugerido||'';
    const hora=s['Hora In\u00edcio Sugerida']||s.hora_inicio_sugerida||'';
    const dur=s['Dura\u00e7\u00e3o (h)']||s.duracao||'';
    const status=s['Status no PCM']||s.status||'';
    const acao=(state[num]||{}).acao;
    const cls=acao==='aceita'?'aceita':(acao==='rejeitada'?'rejeitada':'');
    const scoreCls=Number(score)>=150?'high':'';
    let actions='';
    if(acao==='aceita'){
      actions='<div class="sug-actions-aceita">\u2713 Aceita</div>'+
              '<button class="sug-btn sug-btn-os" onclick="abrirPainelLocal(\''+num+'\')" title="Abre o painel local Streamlit pra criar a OS no Fracttal">\u{1F4E4} Abrir no Painel</button>'+
              '<button class="sug-btn sug-btn-no" onclick="setSugAcao(\''+num+'\',null)" title="Voltar pra pendente (cancela o aceite)" style="margin-left:4px">\u21a9 Reverter</button>';
    }else if(acao==='rejeitada'){
      actions='<button class="sug-btn sug-btn-no" onclick="setSugAcao(\''+num+'\',null)">Reverter</button>';
    }else{
      actions='<button class="sug-btn sug-btn-ok" onclick="aceitarEAbrirPainel(\''+num+'\')" title="Aceita e abre o painel local pra criar OS no Fracttal">Aceitar \u{1F4E4}</button><button class="sug-btn sug-btn-no" onclick="setSugAcao(\''+num+'\',\'rejeitada\')">Rejeitar</button>';
    }
    return '<div class="sug-row '+cls+'">'+
      '<div class="sug-num">#'+num+'</div>'+
      '<div><div class="sug-desc">'+desc+'</div><div style="color:#888;font-size:10px;margin-top:2px">'+ativo+'</div></div>'+
      '<div><span class="sug-meta-pill '+sugCriticidadeClass(crit)+'">'+(crit||'-')+'</span>'+urg+'</div>'+
      '<div class="sug-score '+scoreCls+'">'+score+'<br><span style="font-size:9px;color:#888;font-weight:400">RPN '+rpn+'</span></div>'+
      '<div class="sug-ai"><b>'+equipe+'</b><br>'+dia+' '+hora+'<br><span style="font-size:9px;color:#666">'+dur+'h \u00b7 '+status+'</span></div>'+
      '<div class="sug-actions">'+actions+'</div>'+
      '</div>';
  }).join('');
  body.innerHTML=html;
}
function abrirPainelLocal(num){
  // Abre o painel desktop local (Streamlit) em nova aba, pr\u00e9-selecionando a SS
  const url = CONFIG.PAINEL_LOCAL_URL + '/?ss=' + encodeURIComponent(num);
  const w = window.open(url, 'painel_pcm');
  if(!w){ alert('Pop-up bloqueado. Permita pop-ups para '+location.host+' e tente novamente.'); return; }
  // Detecta se o painel n\u00e3o est\u00e1 rodando (conex\u00e3o recusada \u2192 carrega p\u00e1gina de erro do navegador)
  setTimeout(function(){
    try{
      if(w && w.closed){ return; }
      // Heur\u00edstica: depois de 1.5s, se o location ainda n\u00e3o respondeu, mostra dica
      // (n\u00e3o d\u00e1 pra ler w.location por cross-origin, ent\u00e3o s\u00f3 avisamos preventivamente)
    }catch(e){}
  }, 1500);
}
// Compatibilidade c/ chamadas antigas (caso alguma fique no DOM por cache)
function abrirInstruOS(num){ return abrirPainelLocal(num); }

function aceitarEAbrirPainel(num){
  // 1) Marca como aceita no estado local
  setSugAcao(num, 'aceita');
  // 2) Abre o painel local pr\u00e9-selecionando a SS
  abrirPainelLocal(num);
}


// ── TIPOLOGIA ─────────────────────────────────────────────────────────────────
const TIP_SLUG_MAP={
  religamentos:{label:'Religamentos',icon:'⚡',color:'#f59e0b'},
  chamadosGarantia:{label:'Chamados em Garantia',icon:'\u{1F6E1}',color:'#ef4444'},
  performance:{label:'Performance',icon:'\u{1F4C8}',color:'#8b5cf6'},
  engenharia:{label:'Engenharia',icon:'⚙',color:'#3b82f6'}
};
const TOPV_KEY='gc_topv';
function tipCritClass(c){const x=(c||'').toLowerCase();if(x.indexOf('muito')>=0)return'kc-muito';if(x.indexOf('alt')>=0)return'kc-alta';if(x.indexOf('med')>=0)return'kc-media';return'kc-baixa';}
function tipNumOSs(){if(!ETIQUETAS_DB||!ETIQUETAS_DB.tipologias)return{};const o={};Object.keys(TIP_SLUG_MAP).forEach(k=>{o[k]=ETIQUETAS_DB.tipologias[k]?ETIQUETAS_DB.tipologias[k].total||0:0;});return o;}
async function loadEtiquetas(){
  try{
    const res=await fetch(CONFIG.ETIQUETAS_URL,{cache:'no-store'});
    if(!res.ok){ETIQUETAS_DB=null;return false;}
    ETIQUETAS_DB=await res.json();
    return true;
  }catch(e){ETIQUETAS_DB=null;return false;}
}
function setTopView(v){
  if(v==='manutencoesPreventivas') v='gestaoPcm';  // slug antigo -> nova aba Gestão PCM
  S.topView=v;
  try{localStorage.setItem(TOPV_KEY,v);}catch(e){}
  // tabs
  document.querySelectorAll('.tip-tab').forEach(b=>{b.classList.toggle('on',b.dataset.topv===v);});
  // semana view = mostra blocos atuais; tipologia = esconde e mostra s-tipologias
  const semBlocks=['week-chips-wrap','krow','irow','exec-panel','sug-card','filter-wrap','bottom-grid','wk-row','exec-detail-row','reprog-row','hh-row'];
  const isSem=(v==='semana');
  // procura por id, className ou tag — abordagem simplificada: cria lista de seletores
  // Lista de seletores das seções da view "semana"
  const selsSemana=['.week-chips-wrap','.krow','.irow','#exec-panel','.filter-wrap','.bottom-grid','#wk-tab','#view-semana','.cal','.mcal','.mes-wrap','#exec-detail','.exec-detail','.reprog-card','.hh-card'];
  // O #sug-card é tratado separado pois ele só aparece na aba "sugestoesIA"
  const isSugIA=(v==='sugestoesIA');
  // Se for tipologia ou sugestoesIA: esconde TUDO da semana
  selsSemana.forEach(sel=>{document.querySelectorAll(sel).forEach(el=>{el.style.display=isSem?'':'none';});});
  // O sug-card só visível na aba sugestoesIA
  document.querySelectorAll('#sug-card').forEach(el=>{el.style.display=isSugIA?'':'none';});
  // s-verificacao só visível na aba emVerificacao
  const isVerif=(v==='emVerificacao');
  const verifScreen=document.getElementById('s-verificacao');
  if(verifScreen){verifScreen.classList.toggle('on',isVerif);verifScreen.style.display=isVerif?'block':'none';}
  if(isVerif){renderVerificacao();}
  // s-gestaopcm só visível na aba gestaoPcm (via API Fracttal)
  const isGestao=(v==='gestaoPcm');
  const gestaoScreen=document.getElementById('s-gestaopcm');
  if(gestaoScreen){gestaoScreen.classList.toggle('on',isGestao);gestaoScreen.style.display=isGestao?'block':'none';}
  // Gestão MPAS — só admin (o conteúdo ainda vai cifrado; ver initMpas)
  const isMpas=(v==='gestaoMpas');
  const mpasScreen=document.getElementById('s-gestaompas');
  if(mpasScreen){mpasScreen.classList.toggle('on',isMpas);mpasScreen.style.display=isMpas?'block':'none';}
  if(isMpas && typeof initMpas==='function') initMpas();
  const tipScreen=document.getElementById('s-tipologias');
  if(tipScreen){const showKanban=(!isSem && !isSugIA && !isVerif && !isGestao && !isMpas);tipScreen.classList.toggle('on',showKanban);tipScreen.style.display=showKanban?'block':'none';}
  if(isGestao){
    if(!GESTAO_DB){Promise.all([loadGestao(),loadConfiab()]).then(()=>renderGestao());} else {if(!CONFIAB_DB)loadConfiab().then(()=>renderConfiab());renderGestao();}
  } else if(!isSem){renderTipologiaAtual();}
  if(typeof rpDock==='function') rpDock();   // a fila só vive na aba Programação Semanal
}
function atualizarContadoresTopNav(){
  const n=tipNumOSs();
  Object.keys(n).forEach(k=>{const el=document.getElementById('tcnt-'+k);if(el)el.textContent=n[k];});
}
// Task #133: badge da aba ativa recalcula com filtros
function atualizarBadgeAba(slug, n){
  const el=document.getElementById('tcnt-'+slug);
  if(el) el.textContent=n;
}
function setTipMode(modo){
  S.tipMode = (modo==='historico'?'historico':'abertas');
  renderTipologiaAtual();
}

function renderTipologiaAtual(){
  if(!S.topView||S.topView==='semana')return;
  const slug=S.topView;
  const meta=TIP_SLUG_MAP[slug];
  if(!meta||!ETIQUETAS_DB||!ETIQUETAS_DB.tipologias||!ETIQUETAS_DB.tipologias[slug]){
    ['naoiniciada','emProgresso','pausada'].forEach(c=>{document.getElementById('kan-body-'+c).innerHTML='<div class="kan-empty">Sem dados.</div>';document.getElementById('kc-'+c).textContent='0';});
    document.getElementById('tip-header-title').textContent=meta?meta.label:'--';
    document.getElementById('tip-header-sub').textContent='Aguardando JSON';
    return;
  }
  const data=ETIQUETAS_DB.tipologias[slug];
  // Header
  const ic=document.getElementById('tip-header-icon');ic.style.background=meta.color;ic.textContent=meta.icon;
  document.getElementById('tip-header-title').textContent=data.label||meta.label;
  document.getElementById('tip-header-sub').textContent='Atualizado: '+new Date(ETIQUETAS_DB.geradoEm||Date.now()).toLocaleString('pt-BR');
  // KPIs do header (versão compacta) + Toggle Em Aberto / Histórico
  if(!S.tipMode) S.tipMode = 'abertas';
  const kp=document.getElementById('tip-kpis');
  const nAbertas = (data.kpis?.emAberto)||data.total||0;
  const nHist = data.historicoTotal || (data.ossHistorico||[]).length || 0;
  kp.innerHTML=[
    '<div class="tip-kpi"><div class="tip-kpi-v">'+nAbertas+'</div><div class="tip-kpi-l">Em Aberto</div></div>',
    '<div class="tip-kpi danger"><div class="tip-kpi-v">'+(data.atrasadas||0)+'</div><div class="tip-kpi-l">Atrasadas</div></div>',
    // Toggle Em Aberto / Histórico
    '<div class="tip-toggle">'
      +'<button class="tip-tg-btn'+(S.tipMode==='abertas'?' on':'')+'" onclick="setTipMode(\'abertas\')">📋 Em Aberto <span class="tip-tg-n">'+nAbertas+'</span></button>'
      +'<button class="tip-tg-btn'+(S.tipMode==='historico'?' on':'')+'" onclick="setTipMode(\'historico\')">📚 Histórico <span class="tip-tg-n">'+nHist+'</span></button>'
    +'</div>'
  ].join('');
  // RESUMO EXECUTIVO movido pra DEPOIS do filt (task #122/136)
  // UNE: em aberto + histórico (ignora o toggle pro cálculo do filtro de período)
  const oss = [].concat(data.oss||[]).concat(data.ossHistorico||[]);
  // Filtros simplificados (task #136): Período + OS#
  const fPer=document.getElementById('tip-f-periodo')?.value||'30';
  const fOS=(document.getElementById('tip-f-os')?.value||'').trim();
  const fDi=document.getElementById('tip-f-dini')?.value||'';
  const fDf=document.getElementById('tip-f-dfim')?.value||'';
  // Calcula range do período (opção C: usa dataFinal se finalizada, senão dataCriacao)
  let dIni=null, dFim=null;
  const hojeY=new Date(); hojeY.setHours(23,59,59,999);
  if(fPer==='7'||fPer==='30'||fPer==='90'){
    dFim=hojeY;
    dIni=new Date(hojeY); dIni.setDate(dIni.getDate()-parseInt(fPer,10)); dIni.setHours(0,0,0,0);
  } else if(fPer==='ano'){
    dFim=hojeY;
    dIni=new Date(hojeY.getFullYear(),0,1);
  } else if(fPer==='custom'){
    if(fDi){dIni=new Date(fDi+'T00:00:00');}
    if(fDf){dFim=new Date(fDf+'T23:59:59');}
  }
  const filt=oss.filter(o=>{
    // Filtro OS#: busca parcial
    if(fOS && String(o.osId||'').indexOf(fOS)<0) return false;
    // Filtro Período (opção C): dataFinal se finalizada, senão dataCriacao
    if(dIni || dFim){
      const isFinaliz=(o.status||'').toLowerCase().indexOf('finaliz')>=0
                  ||(o.status||'').toLowerCase().indexOf('conclu')>=0;
      const refStr = (isFinaliz && o.dataFinal) ? o.dataFinal : o.dataCriacao;
      if(!refStr) return false;
      const ref=new Date(refStr);
      if(isNaN(ref)) return false;
      if(dIni && ref<dIni) return false;
      if(dFim && ref>dFim) return false;
    }
    return true;
  });
  // Resumo executivo recebe filt
  const filtroAtivo = !!(fOS || dIni || dFim);
  renderExecResumo(data, slug, filt, filtroAtivo);
  // Task #133: badge da aba mostra contagem filtrada
  atualizarBadgeAba(slug, filt.length);
  // Distribui por coluna
  const byCol={naoiniciada:[],emProgresso:[],pausada:[]};
  filt.forEach(o=>{
    const st=(o.status||'').toLowerCase();
    if(st.indexOf('iniciada')>=0||st.indexOf('nao iniciada')>=0||st.indexOf('não iniciada')>=0)byCol.naoiniciada.push(o);
    else if(st.indexOf('progresso')>=0||st.indexOf('execu')>=0||st.indexOf('andamento')>=0)byCol.emProgresso.push(o);
    else if(st.indexOf('paus')>=0)byCol.pausada.push(o);
    else byCol.naoiniciada.push(o);
  });
  // Renderiza cada coluna
  Object.keys(byCol).forEach(col=>{
    const list=byCol[col];
    document.getElementById('kc-'+col).textContent=list.length;
    const body=document.getElementById('kan-body-'+col);
    if(!list.length){body.innerHTML='<div class="kan-empty">Nenhuma OS</div>';return;}
    body.innerHTML=list.map(o=>{
      const cls=o.atrasada?' atrasada':'';
      const dataAtraso=o.atrasada?' atraso':'';
      const linkH=o.linkFracttal?'<a class="kan-card-link" href="'+o.linkFracttal+'" target="_blank" rel="noopener" onclick="event.stopPropagation()">Fracttal &rarr;</a>':'';
            const stKey2=col==='naoiniciada'?'naoIniciada':col==='emProgresso'?'emProgresso':col==='pausada'?'pausada':'naoIniciada';
      const urg2=(o.criticidade||'').toLowerCase().indexOf('muito')>=0?'<span class="urg" style="margin-left:6px">URG</span>':'';
      return '<div class="kan-card'+cls+'" data-status="'+stKey2+'" style="cursor:pointer" onclick="openMod(\''+'\',\''+'\',\''+esc(o.osId)+'\')">'+
        '<div class="kan-card-top"><span class="kan-card-os">#'+(o.osId||'--')+'</span>'+
        '<span class="kan-card-crit '+tipCritClass(o.criticidade)+'">'+(o.criticidade||'--')+'</span></div>'+
        '<div class="kan-card-ativo">'+(o.ativo||'(sem ativo)')+'</div>'+
        '<div class="kan-card-meta"><span><span class="kan-card-meta-l">Equipe:</span> '+(o.equipe||'--')+'</span>'+
        '<span><span class="kan-card-meta-l">Resp.:</span> '+(o.responsavel||'--')+'</span></div>'+
        '<div class="kan-card-bottom"><span class="kan-card-data'+dataAtraso+'">'+(o.dataProgramada||'--')+(o.atrasada?' (atrasada)':'')+'</span>'+linkH+'</div>'+
        '</div>';
    }).join('');
  });
  atualizarContadoresTopNav();
}




function limparFiltrosTip(){
  ['tip-f-os','tip-f-dini','tip-f-dfim'].forEach(id=>{
    const el=document.getElementById(id); if(el) el.value='';
  });
  const sel=document.getElementById('tip-f-periodo'); if(sel) sel.value='30';
  const cw=document.getElementById('tip-f-periodo-custom'); if(cw) cw.style.display='none';
  renderTipologiaAtual();
}
function onPeriodoChange(){
  const v=document.getElementById('tip-f-periodo').value;
  const cw=document.getElementById('tip-f-periodo-custom');
  if(cw) cw.style.display = v==='custom' ? '' : 'none';
  renderTipologiaAtual();
}

function recalcKPIsDoFiltro(filt){
  const hoje=new Date();
  const d7=new Date(hoje); d7.setDate(d7.getDate()-7);
  const d30=new Date(hoje); d30.setDate(d30.getDate()-30);
  const dow=(hoje.getDay()+6)%7;
  const semIni=new Date(hoje); semIni.setDate(semIni.getDate()-dow); semIni.setHours(0,0,0,0);
  const semFim=new Date(semIni); semFim.setDate(semFim.getDate()+7);
  let t=0,a=0,at=0,c30=0,c7=0,nS=0;
  filt.forEach(o=>{
    t++;
    const st=(o.status||'').toLowerCase();
    const fin=st.indexOf('finaliz')>=0||st.indexOf('conclu')>=0;
    if(!fin) a++;
    if(o.atrasada) at++;
    if(fin && o.dataFinal){
      const df=new Date(o.dataFinal);
      if(df>=d30) c30++;
      if(df>=d7) c7++;
    }
    if(o.dataProgramada){
      const dp=new Date(o.dataProgramada);
      if(dp>=semIni && dp<semFim) nS++;
    }
  });
  return {total:t,emAberto:a,atrasadas:at,concluidas30d:c30,concluidas7d:c7,naSemanaCorrente:nS};
}
function renderExecResumo(data, slug, filt, filtroAtivo){
  const exec=document.getElementById('tip-exec');
  if(!exec) return;
  const k = (filtroAtivo && filt) ? recalcKPIsDoFiltro(filt) : (data.kpis||{});
  const mttr=data.mttr||{};
  const tend=data.tendencia4Semanas||[];
  let ofens = data.topOfensores||{};
  if(filtroAtivo && filt){
    const byEq=new Map(), byResp=new Map();
    filt.forEach(o=>{
      if(o.equipe) byEq.set(o.equipe,(byEq.get(o.equipe)||0)+1);
      if(o.responsavel) byResp.set(o.responsavel,(byResp.get(o.responsavel)||0)+1);
    });
    const top=m=>[...m.entries()].sort((a,b)=>b[1]-a[1]).slice(0,5).map(([nome,total])=>({nome,total}));
    ofens={clusters:top(byEq), responsaveis:top(byResp)};
  }
  // Linha 1: 6 KPIs
  let html='<div class="tip-exec-row">'
    +'<div class="tip-exec-kpi"><div class="tip-exec-kpi-v">'+(k.total||0)+'</div><div class="tip-exec-kpi-l">Total</div></div>'
    +'<div class="tip-exec-kpi info"><div class="tip-exec-kpi-v">'+(k.emAberto||0)+'</div><div class="tip-exec-kpi-l">Em Aberto</div></div>'
    +'<div class="tip-exec-kpi danger"><div class="tip-exec-kpi-v">'+(k.atrasadas||0)+'</div><div class="tip-exec-kpi-l">Atrasadas</div></div>'
    +'<div class="tip-exec-kpi success"><div class="tip-exec-kpi-v">'+(k.concluidas30d||0)+'</div><div class="tip-exec-kpi-l">Concl. 30d</div></div>'
    +'<div class="tip-exec-kpi success"><div class="tip-exec-kpi-v">'+(k.concluidas7d||0)+'</div><div class="tip-exec-kpi-l">Concl. 7d</div></div>'
    +'<div class="tip-exec-kpi warn"><div class="tip-exec-kpi-v">'+(k.naSemanaCorrente||0)+'</div><div class="tip-exec-kpi-l">Semana</div></div>'
    +'</div>';
  // Linha 2: MTTR + Tendência
  html+='<div class="tip-exec-mid">'
    +'<div class="tip-exec-block">'
    +'<div class="tip-exec-block-t">MTTR (Tempo médio de resolução)</div>'
    +'<div class="tip-exec-mttr"><div class="tip-exec-mttr-v">'+(mttr.label||'--')+'</div>'
    +'<div class="tip-exec-mttr-s">amostra: '+(mttr.amostra||0)+' OSs concluídas/30d</div></div>'
    +'</div>'
    +'<div class="tip-exec-block">'
    +'<div class="tip-exec-block-t">Tendência últimas 4 semanas</div>'
    +renderTrendBars(tend)
    +'</div>'
    +'</div>';
  // Linha 3: Top ofensores
  html+='<div class="tip-exec-ofens">'
    +'<div>'
    +'<div class="tip-exec-ofens-t">🏭 Top 5 Clusters / Equipes</div>'
    +renderOfensTab(ofens.clusters||[])
    +'</div>'
    +'<div>'
    +'<div class="tip-exec-ofens-t">👤 Top 5 Responsáveis</div>'
    +renderOfensTab(ofens.responsaveis||[])
    +'</div>'
    +'</div>';
  // Linha 4: Modalidade (só pra religamentos)
  if(slug==='religamentos' && data.subClassificacao){
    const sc=data.subClassificacao;
    const alertCls=sc.alerta?' alert':'';
    const icone=sc.alerta?'⚠':'✓';
    html+='<div class="tip-modalidade'+alertCls+'">'
      +'<div class="tip-modalidade-ico">'+icone+'</div>'
      +'<div>'
      +'<div class="tip-modalidade-title">Modalidade do Religamento</div>'
      +'<div class="tip-modalidade-sub">'
      +(sc.alerta?'⚠ '+sc.localEmAberto+' religamento(s) LOCAL em aberto — ofensor':'Sem religamentos locais pendentes')
      +'</div>'
      +'</div>'
      +'<div class="tip-modalidade-stat remoto"><div class="tip-modalidade-stat-v">'+(sc.remoto||0)+'</div><div class="tip-modalidade-stat-l">Remoto (Total)</div></div>'
      +'<div class="tip-modalidade-stat local"><div class="tip-modalidade-stat-v">'+(sc.local||0)+'</div><div class="tip-modalidade-stat-l">Local (Total)</div></div>'
      +'<div class="tip-modalidade-stat pct"><div class="tip-modalidade-stat-v">'+(sc.pctRemoto||0)+'%</div><div class="tip-modalidade-stat-l">Remoto</div></div>'
      +'</div>';
    // Task #123: Ranking de demora (abertura + fechamento) + abridores
    const rd = data.rankingDemora;
    if(rd){
      html += renderRankingDemora(rd);
    }
    // Task #124: Ranking de UFVs (calc no frontend a partir de filt)
    if(filt && filt.length){
      html += renderRankingUFVs(filt);
    }
    // Task #126: Heatmap dia × hora
    if(filt && filt.length){
      html += renderHeatmapReligamentos(filt);
    }
    // Task #125: Visão gerencial supervisor
    if(filt && filt.length){
      html += renderVisaoGerencialReligamento(filt, data);
    }
    // Task #127: Aba Nobreaks dentro de religamentos
    html += renderControleNobreaks();
  }
  exec.innerHTML=html;
}

function renderControleNobreaks(){
  // Busca todas as OSs no DB que tenham "nobreak" na tarefa
  const todasOSs = [];
  if(ETIQUETAS_DB && ETIQUETAS_DB.ossPublicas){
    ETIQUETAS_DB.ossPublicas.forEach(o=>todasOSs.push(o));
  }
  if(ETIQUETAS_DB && ETIQUETAS_DB.ossHistorico){
    ETIQUETAS_DB.ossHistorico.forEach(o=>todasOSs.push(o));
  }
  const nobreaks = todasOSs.filter(o=>{
    const t = (o.tarefa||'').toLowerCase();
    return t.indexOf('nobreak')>=0 || t.indexOf('no-break')>=0 || t.indexOf('no break')>=0;
  });
  if(!nobreaks.length) return '';
  // Agrupa por UFV (ativo)
  const byUFV = new Map();
  nobreaks.forEach(o=>{
    const ufv = ((o.ativo||'').split('{')[0]||'').trim() || '(sem ativo)';
    if(!byUFV.has(ufv)) byUFV.set(ufv,{ufv,total:0,emAberto:0,finalizadas:0,ultima:''});
    const e = byUFV.get(ufv);
    e.total++;
    const st = (o.status||'').toLowerCase();
    if(st.indexOf('finaliz')>=0 || st.indexOf('conclu')>=0) e.finalizadas++;
    else e.emAberto++;
    const df = o.dataFinal || o.dataCriacao;
    if(df && df > e.ultima) e.ultima = df;
  });
  const rank = [...byUFV.values()].sort((a,b)=>b.total-a.total).slice(0,15);
  const totalNb = nobreaks.length;
  const totalAberto = nobreaks.filter(o=>{
    const s=(o.status||'').toLowerCase();
    return !(s.indexOf('finaliz')>=0 || s.indexOf('conclu')>=0);
  }).length;
  let h = '<div style="margin-top:14px;background:#fff;border:2px solid #f59e0b;border-radius:10px;padding:14px 16px">'
    +'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">'
    +'<div><div style="font-size:10px;color:var(--ink3);text-transform:uppercase;letter-spacing:.5px;font-weight:700">🔋 Controle de Nobreaks</div>'
    +'<div style="font-size:13px;font-weight:800;color:#191528;margin-top:2px">Manutenções e falhas (Nobreaks → previne religamentos)</div></div>'
    +'<div style="display:flex;gap:10px"><div style="text-align:center"><div style="font-size:18px;font-weight:800;color:#f59e0b">'+totalNb+'</div><div style="font-size:9px;color:var(--ink3);text-transform:uppercase">Total</div></div>'
    +'<div style="text-align:center"><div style="font-size:18px;font-weight:800;color:#dc2626">'+totalAberto+'</div><div style="font-size:9px;color:var(--ink3);text-transform:uppercase">Em Aberto</div></div></div>'
    +'</div>'
    +'<table style="width:100%;border-collapse:collapse;font-size:11px;margin-top:6px">'
    +'<thead><tr style="background:#fef3c7;color:#92400e;font-weight:700;text-align:left"><th style="padding:6px 8px">UFV</th><th style="padding:6px 8px;text-align:right">Total</th><th style="padding:6px 8px;text-align:right">Em Aberto</th><th style="padding:6px 8px;text-align:right">Finalizadas</th><th style="padding:6px 8px">Última</th></tr></thead><tbody>';
  rank.forEach(r=>{
    h+='<tr style="border-top:1px solid var(--line)"><td style="padding:6px 8px;color:#191528;font-weight:600">'+esc(r.ufv)+'</td>'
      +'<td style="padding:6px 8px;text-align:right;color:#191528;font-weight:700">'+r.total+'</td>'
      +'<td style="padding:6px 8px;text-align:right;color:'+(r.emAberto>0?'#dc2626':'#16a34a')+';font-weight:700">'+r.emAberto+'</td>'
      +'<td style="padding:6px 8px;text-align:right;color:#16a34a;font-weight:700">'+r.finalizadas+'</td>'
      +'<td style="padding:6px 8px;color:var(--ink2);font-size:10px">'+(r.ultima?r.ultima.slice(0,10):'--')+'</td></tr>';
  });
  h+='</tbody></table></div>';
  return h;
}

function renderVisaoGerencialReligamento(filt, data){
  // KPIs gerenciais a partir do filt
  const totalReligamentos = filt.length;
  const rem = filt.filter(o=>o.modalidade==='remoto').length;
  const loc = filt.filter(o=>o.modalidade==='local').length;
  const finalizadas = filt.filter(o=>{
    const s=(o.status||'').toLowerCase();
    return s.indexOf('finaliz')>=0 || s.indexOf('conclu')>=0;
  });
  const emAberto = filt.length - finalizadas.length;
  const atrasadas = filt.filter(o=>o.atrasada).length;
  // SLA: % finalizadas em < 24h (abrir+fechar)
  const comTempo = finalizadas.filter(o=>typeof o.horasAteAbrir==='number' && typeof o.horasAteFechar==='number');
  const dentroSLA = comTempo.filter(o=>(o.horasAteAbrir + o.horasAteFechar) < 24).length;
  const pctSLA = comTempo.length ? Math.round(dentroSLA/comTempo.length*100) : 0;
  // MTTR médio (resolução total)
  const mttrH = comTempo.length ? Math.round(comTempo.reduce((a,o)=>a+o.horasAteAbrir+o.horasAteFechar,0)/comTempo.length*10)/10 : 0;
  // Alerta crítico: > 30% local em aberto ou SLA < 70%
  const pctLocal = totalReligamentos>0 ? Math.round(loc/totalReligamentos*100) : 0;
  const alertaCritico = (pctLocal > 30) || (pctSLA < 70 && comTempo.length >= 5);
  // Top equipe ofensora
  const eq = new Map();
  filt.forEach(o=>{ if(o.equipe) eq.set(o.equipe,(eq.get(o.equipe)||0)+1); });
  const topEq = [...eq.entries()].sort((a,b)=>b[1]-a[1])[0];
  let cor = alertaCritico ? '#dc2626' : (pctSLA>=85?'#10b981':'#f59e0b');
  let icone = alertaCritico ? '⚠️' : (pctSLA>=85?'✓':'⏳');
  let label = alertaCritico ? 'ATENÇÃO REQUERIDA' : (pctSLA>=85?'PROCESSO SAUDÁVEL':'EM EQUILÍBRIO');
  return '<div style="margin-top:14px;background:linear-gradient(90deg,'+cor+'20,#fff);border-left:4px solid '+cor+';border-radius:10px;padding:14px 16px">'
    +'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">'
    +'<div><div style="font-size:10px;color:var(--ink3);text-transform:uppercase;letter-spacing:.5px;font-weight:700">📊 Visão Gerencial — Religamentos</div>'
    +'<div style="font-size:14px;font-weight:800;color:'+cor+';margin-top:2px">'+icone+' '+label+'</div></div>'
    +'<div style="font-size:10px;color:var(--ink3);text-align:right">Análise sobre '+filt.length+' OSs filtradas</div></div>'
    +'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:10px">'
    +'<div style="background:#fff;border:1px solid var(--line);border-radius:8px;padding:9px 10px"><div style="font-size:9.5px;color:var(--ink3);text-transform:uppercase;font-weight:700">MTTR Médio</div><div style="font-size:18px;font-weight:800;color:#191528;margin-top:2px">'+mttrH+'h</div><div style="font-size:9px;color:var(--ink3);margin-top:2px">amostra: '+comTempo.length+'</div></div>'
    +'<div style="background:#fff;border:1px solid var(--line);border-radius:8px;padding:9px 10px"><div style="font-size:9.5px;color:var(--ink3);text-transform:uppercase;font-weight:700">SLA &lt; 24h</div><div style="font-size:18px;font-weight:800;color:'+(pctSLA>=85?'#16a34a':pctSLA>=70?'#f59e0b':'#dc2626')+';margin-top:2px">'+pctSLA+'%</div><div style="font-size:9px;color:var(--ink3);margin-top:2px">'+dentroSLA+' de '+comTempo.length+'</div></div>'
    +'<div style="background:#fff;border:1px solid var(--line);border-radius:8px;padding:9px 10px"><div style="font-size:9.5px;color:var(--ink3);text-transform:uppercase;font-weight:700">% Local</div><div style="font-size:18px;font-weight:800;color:'+(pctLocal>30?'#dc2626':'#191528')+';margin-top:2px">'+pctLocal+'%</div><div style="font-size:9px;color:var(--ink3);margin-top:2px">'+loc+' OSs locais</div></div>'
    +'<div style="background:#fff;border:1px solid var(--line);border-radius:8px;padding:9px 10px"><div style="font-size:9.5px;color:var(--ink3);text-transform:uppercase;font-weight:700">Em aberto</div><div style="font-size:18px;font-weight:800;color:'+(atrasadas>0?'#dc2626':'#191528')+';margin-top:2px">'+emAberto+'</div><div style="font-size:9px;color:var(--ink3);margin-top:2px">'+atrasadas+' atrasadas</div></div>'
    +'</div>'
    +(topEq?'<div style="font-size:11px;color:var(--ink2);background:#fff;border:1px solid var(--line);border-radius:8px;padding:8px 12px"><strong>Maior ofensor:</strong> '+esc(topEq[0])+' ('+topEq[1]+' religamentos)</div>':'')
    +'</div>';
}

function renderHeatmapReligamentos(filt){
  const dias=['Dom','Seg','Ter','Qua','Qui','Sex','Sáb'];
  const mkMat=()=>{const m=[];for(let i=0;i<7;i++){m.push(new Array(24).fill(0));}return m;};
  const matR=mkMat(), matL=mkMat();
  filt.forEach(o=>{
    const ds=o.dataInicial||o.dataCriacao;
    if(!ds) return;
    const d=new Date(ds);
    if(isNaN(d)) return;
    const dow=d.getDay(), h=d.getHours();
    if(o.modalidade==='remoto') matR[dow][h]++;
    else matL[dow][h]++;
  });
  const maxR=Math.max(...matR.flat(),1);
  const maxL=Math.max(...matL.flat(),1);
  const cell=(v,max,color)=>{
    const op=v?(0.15+0.85*v/max):0;
    return '<td style="background:rgba('+color+','+op.toFixed(2)+');color:'+(v?'#191528':'#cbd5e1')+';font-weight:'+(v?'700':'400')+';text-align:center;width:14px;height:16px;font-size:9px" title="'+v+' OS">'+(v||'')+'</td>';
  };
  const mkTbl=(mat,max,color,titulo)=>{
    let h='<div style="flex:1"><div style="font-size:11px;font-weight:700;color:var(--ink);margin-bottom:4px">'+titulo+'</div>'
      +'<table style="border-collapse:collapse;font-size:9px"><thead><tr><th></th>';
    for(let hr=0;hr<24;hr++){ h+='<th style="font-size:8px;color:var(--ink3);width:14px;text-align:center">'+(hr%6===0?hr:'')+'</th>'; }
    h+='</tr></thead><tbody>';
    for(let dw=0;dw<7;dw++){
      h+='<tr><td style="font-size:9px;color:var(--ink2);padding-right:4px;font-weight:600">'+dias[dw]+'</td>';
      for(let hr=0;hr<24;hr++){ h+=cell(mat[dw][hr],max,color); }
      h+='</tr>';
    }
    h+='</tbody></table></div>';
    return h;
  };
  return '<div style="margin-top:14px"><div class="tip-rank-t" style="display:block">🕒 Heatmap dia × hora</div>'
    +'<div style="display:flex;gap:18px;margin-top:8px;overflow-x:auto">'
    +mkTbl(matR,maxR,'22,163,74','Remoto')+mkTbl(matL,maxL,'220,38,38','Local')
    +'</div></div>';
}

function renderRankingUFVs(filt){
  const uR=new Map(), uL=new Map();
  filt.forEach(o=>{
    const ufv=((o.ativo||'').split('{')[0]||'').trim();
    if(!ufv) return;
    if(o.modalidade==='remoto') uR.set(ufv,(uR.get(ufv)||0)+1);
    else uL.set(ufv,(uL.get(ufv)||0)+1);
  });
  const all=new Set([...uR.keys(),...uL.keys()]);
  const rank=[...all].map(u=>({ufv:u,remoto:uR.get(u)||0,local:uL.get(u)||0,total:(uR.get(u)||0)+(uL.get(u)||0)})).sort((a,b)=>b.total-a.total).slice(0,10);
  if(!rank.length) return '';
  let h='<div style="margin-top:14px"><div class="tip-rank-t" style="display:block">🏭 Ranking UFVs com religamentos (Top 10)</div>'
    +'<table style="width:100%;border-collapse:collapse;font-size:11px;margin-top:6px">'
    +'<thead><tr style="background:#f9fafb;color:var(--ink2);font-weight:700;text-align:left"><th style="padding:6px 8px">UFV</th><th style="padding:6px 8px;text-align:right">Remoto</th><th style="padding:6px 8px;text-align:right">Local</th><th style="padding:6px 8px;text-align:right">Total</th></tr></thead><tbody>';
  rank.forEach(r=>{
    h+='<tr style="border-top:1px solid var(--line)"><td style="padding:6px 8px;color:#191528;font-weight:600">'+esc(r.ufv)+'</td>'
      +'<td style="padding:6px 8px;text-align:right;color:#16a34a;font-weight:700">'+r.remoto+'</td>'
      +'<td style="padding:6px 8px;text-align:right;color:#dc2626;font-weight:700">'+r.local+'</td>'
      +'<td style="padding:6px 8px;text-align:right;color:#191528;font-weight:800">'+r.total+'</td></tr>';
  });
  h+='</tbody></table></div>';
  return h;
}

function renderRankingDemora(rd){
  const rowH = (o, lbl) => '<div class="tip-rank-row"><span class="tip-rank-os">#'+esc(o.osId||'--')+'</span>'
      +'<span class="tip-rank-ativo" title="'+esc(o.ativo||'')+'">'+esc(o.ativo||'(sem ativo)')+'</span>'
      +'<span class="tip-rank-h">'+(o.horas||0).toFixed(1)+'h</span></div>';
  const topAb = (rd.topAbrir||[]).slice(0,5);
  const topFc = (rd.topFechar||[]).slice(0,5);
  let html = '<div class="tip-rank">';
  html += '<div class="tip-rank-block">'
    +'<div class="tip-rank-t">⏱ Top 5 demora abertura'
    +'<span class="tip-rank-t-med">média '+(rd.medHorasAbrir||0).toFixed(1)+'h · n='+(rd.amostraAbrir||0)+'</span></div>'
    +(topAb.length ? topAb.map(o=>rowH(o)).join('') : '<div style="font-size:10.5px;color:var(--ink3);padding:8px 0">Sem dados</div>')
    +'</div>';
  html += '<div class="tip-rank-block">'
    +'<div class="tip-rank-t">⚙ Top 5 demora fechamento'
    +'<span class="tip-rank-t-med">média '+(rd.medHorasFechar||0).toFixed(1)+'h · n='+(rd.amostraFechar||0)+'</span></div>'
    +(topFc.length ? topFc.map(o=>rowH(o)).join('') : '<div style="font-size:10.5px;color:var(--ink3);padding:8px 0">Sem dados</div>')
    +'</div>';
  html += '</div>';
  // Top abridores
  const ab = rd.topAbridores||[];
  if(ab.length){
    html += '<div style="margin-top:10px"><div class="tip-rank-t" style="display:block">👤 Top abridores (criaram OS de religamento)</div>'
      +'<div class="tip-abri">'+ab.map(a=>'<span class="tip-abri-chip">'+esc(a.nome||'--')+'<span class="tip-abri-chip-n">'+a.total+'</span></span>').join('')+'</div></div>';
  }
  return html;
}

function renderTrendBars(tend){
  if(!tend||!tend.length) return '<div class="tip-exec-trend"><div style="color:var(--ink3);font-size:10px;padding:10px">Sem dados de tendência</div></div>';
  const max=Math.max(...tend.flatMap(t=>[t.criadas||0,t.finalizadas||0]),1);
  let html='<div class="tip-exec-trend">';
  tend.forEach(t=>{
    const hC=Math.round((t.criadas||0)/max*48);
    const hF=Math.round((t.finalizadas||0)/max*48);
    html+='<div class="tip-exec-trend-col">'
      +'<div class="tip-exec-trend-bars">'
      +'<div class="tip-exec-trend-bar cri" style="height:'+hC+'px" title="Criadas: '+(t.criadas||0)+'"></div>'
      +'<div class="tip-exec-trend-bar fin" style="height:'+hF+'px" title="Finalizadas: '+(t.finalizadas||0)+'"></div>'
      +'</div>'
      +'<div class="tip-exec-trend-lbl">'+(t.semana||'')+'</div>'
      +'</div>';
  });
  html+='</div>';
  html+='<div class="tip-exec-trend-leg"><span><span class="ldot" style="background:#3b82f6"></span>Criadas</span><span><span class="ldot" style="background:#10b981"></span>Finalizadas</span></div>';
  return html;
}

function renderOfensTab(arr){
  if(!arr||!arr.length) return '<div style="font-size:10px;color:var(--ink3);padding:8px">Sem dados</div>';
  let html='<div class="ofens-hdr"><div>Nome</div><div class="ofens-hdr-r">Total</div><div class="ofens-hdr-r">Aberto</div></div>';
  arr.forEach(o=>{
    const ab=o.emAberto||0;
    html+='<div class="ofens-row">'
      +'<div class="ofens-row-nome" title="'+esc(o.nome)+'">'+o.nome+'</div>'
      +'<div class="ofens-row-tot">'+(o.total||0)+'</div>'
      +'<div class="ofens-row-ab'+(ab===0?' zero':'')+'">'+ab+'</div>'
      +'</div>';
  });
  return html;
}

// ── EM VERIFICAÇÃO ────────────────────────────────────────────────────────────
function renderVerificacao(){
  const data=(ETIQUETAS_DB||{}).verificacao||{};
  document.getElementById('verif-total').textContent=data.total||0;
  document.getElementById('verif-atrasadas').textContent=data.atrasadas||0;
  document.getElementById('verif-sub').textContent='Atualizado: '+new Date(ETIQUETAS_DB?.geradoEm||Date.now()).toLocaleString('pt-BR');
  const tcnt=document.getElementById('tcnt-emVerificacao');if(tcnt) tcnt.textContent=data.total||0;
  const oss=data.oss||[];
  // Popula filtros
  const sups=[...new Set(oss.map(o=>o.supervisor||o.responsavel).filter(Boolean))].sort();
  const selSup=document.getElementById('verif-f-sup');
  const supAtual=selSup.value;
  selSup.innerHTML='<option value="">Todos</option>'+sups.map(s=>'<option value="'+esc(s)+'"'+(s===supAtual?' selected':'')+'>'+s+'</option>').join('');
  const eqs=[...new Set(oss.map(o=>o.equipe).filter(Boolean))].sort();
  const selEq=document.getElementById('verif-f-eq');
  const eqAtual=selEq.value;
  selEq.innerHTML='<option value="">Todas</option>'+eqs.map(e=>'<option value="'+esc(e)+'"'+(e===eqAtual?' selected':'')+'>'+e+'</option>').join('');
  // Filtra
  const fSup=selSup.value,fEq=selEq.value;
  const filt=oss.filter(o=>{
    if(fSup && (o.supervisor||o.responsavel)!==fSup) return false;
    if(fEq && o.equipe!==fEq) return false;
    return true;
  });
  // Conta agrupamentos filtrados
  const eqCount={},respCount={};
  filt.forEach(o=>{
    const e=(o.equipe||'(sem equipe)').trim()||'(sem equipe)';
    const r=(o.responsavel||'(sem responsável)').trim()||'(sem responsável)';
    eqCount[e]=(eqCount[e]||0)+1;
    respCount[r]=(respCount[r]||0)+1;
  });
  function renderBars(targetId, counts){
    const arr=Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,8);
    if(!arr.length){document.getElementById(targetId).innerHTML='<div class="verif-empty">Nenhuma OS</div>';return;}
    const max=arr[0][1];
    document.getElementById(targetId).innerHTML=arr.map(([k,n])=>{
      const pct=Math.round(n/max*100);
      return '<div class="verif-bar-row"><div class="verif-bar-lbl" title="'+esc(k)+'">'+k+'</div>'
        +'<div class="verif-bar-track"><div class="verif-bar-fill" style="width:'+pct+'%"></div></div>'
        +'<div class="verif-bar-val">'+n+'</div></div>';
    }).join('');
  }
  renderBars('verif-bars-eq', eqCount);
  renderBars('verif-bars-resp', respCount);
  // Lista
  document.getElementById('verif-list-t').textContent='Lista de OSs ('+filt.length+')';
  const body=document.getElementById('verif-list-body');
  if(!filt.length){body.innerHTML='<div class="verif-empty">Nenhuma OS no filtro selecionado.</div>';return;}
  body.innerHTML=filt.map(o=>{
    const cls=o.atrasada?' atrasada':'';
    const linkH=o.linkFracttal?'<a href="'+o.linkFracttal+'" target="_blank" rel="noopener" style="font-size:10px;font-weight:700;color:var(--gd);text-decoration:none;padding:2px 8px;border-radius:4px;background:#f0fdf4;border:1px solid #a9db21">Fracttal &rarr;</a>':'';
    return '<div class="verif-row'+cls+'" style="cursor:pointer" onclick="openMod(\'\',\'\',\''+esc(o.osId)+'\')">'
      +'<div class="verif-row-os">#'+(o.osId||'--')+'</div>'
      +'<div class="verif-row-ativo">'+(o.ativo||'(sem ativo)')+'<div class="verif-row-sub">Equipe: '+(o.equipe||'--')+'</div></div>'
      +'<div class="verif-row-meta"><b>Resp.:</b> '+(o.responsavel||'--')+'</div>'
      +'<div class="verif-row-data'+(o.atrasada?' atraso':'')+'">'+(o.dataProgramada||'--')+(o.atrasada?' (atrasada)':'')+'</div>'
      +'<div>'+linkH+'</div>'
      +'</div>';
  }).join('');
}

// ── GRÁFICO STATUS (Aba Programação Semanal) ─────────────────────────────────
const STATUS_CORES={
  'Não Iniciada':'#94a3b8','Nao Iniciada':'#94a3b8','Naoiniciada':'#94a3b8',
  'Em progresso':'#3b82f6','Em Progresso':'#3b82f6','progresso':'#3b82f6',
  'Verificação':'#f59e0b','Verificacao':'#f59e0b','verifica':'#f59e0b',
  'pausado':'#fbbf24','Pausada':'#fbbf24',
  'Finalizada':'#10b981','Concluída':'#10b981','Concluida':'#10b981','Concluído':'#10b981',
  'Outros':'#cbd5e1'
};
function statusCanonico(s){
  // FIX #157: fallback "Não Iniciada" (não "Outros") + reconhecer "Em processo" do Fracttal
  const x=(s||'').toString().toLowerCase().trim();
  if(!x) return 'Não Iniciada';
  if(x.indexOf('verifica')>=0) return 'Verificação';
  if(x.indexOf('paus')>=0) return 'Pausada';
  if(x.indexOf('progresso')>=0||x.indexOf('andamento')>=0||x.indexOf('execu')>=0||x.indexOf('processo')>=0) return 'Em progresso';
  if(x.indexOf('iniciada')>=0||x.indexOf('iniciado')>=0||x.indexOf('aberta')>=0) return 'Não Iniciada';
  if(x.indexOf('finaliz')>=0||x.indexOf('conclu')>=0) return 'Finalizada';
  return 'Não Iniciada';
}
function renderStatusChart(d){
  const counts={};
  d.forEach(r=>{
    const c=statusCanonico(r.status_bd||r.status);
    counts[c]=(counts[c]||0)+1;
  });
  const ordem=['Não Iniciada','Em progresso','Verificação','Pausada','Finalizada','Outros'];
  const entries=ordem.filter(s=>counts[s]).map(s=>[s,counts[s]]);
  const total=entries.reduce((a,b)=>a+b[1],0);
  const body=document.getElementById('status-chart-body');
  if(!body) return;
  if(!total){body.innerHTML='<div class="verif-empty">Sem dados de status nesta semana.</div>';return;}
  // SVG donut
  const RAD=42,CX=50,CY=50;
  const PERIM=2*Math.PI*RAD;
  let off=0;
  const segs=entries.map(([name,n])=>{
    const pct=n/total;
    const dash=pct*PERIM;
    const color=STATUS_CORES[name]||'#cbd5e1';
    const seg='<circle cx="'+CX+'" cy="'+CY+'" r="'+RAD+'" fill="none" stroke="'+color+'" stroke-width="14" stroke-dasharray="'+dash.toFixed(2)+' '+PERIM.toFixed(2)+'" stroke-dashoffset="-'+off.toFixed(2)+'"></circle>';
    off+=dash;
    return seg;
  }).join('');
  const legenda=entries.map(([name,n])=>{
    const color=STATUS_CORES[name]||'#cbd5e1';
    const pct=Math.round(n/total*100);
    return '<div class="status-leg-row">'
      +'<div class="status-leg-dot" style="background:'+color+'"></div>'
      +'<div class="status-leg-name">'+name+'</div>'
      +'<div class="status-leg-n">'+n+'</div>'
      +'<div class="status-leg-pct">'+pct+'%</div>'
      +'</div>';
  }).join('');
  body.innerHTML='<div class="status-chart">'
    +'<div class="status-donut">'
    +  '<svg viewBox="0 0 100 100">'+segs+'</svg>'
    +  '<div class="status-donut-center"><div class="status-donut-tot">'+total+'</div><div class="status-donut-lbl">OSs</div></div>'
    +'</div>'
    +'<div class="status-leg">'+legenda+'</div>'
    +'</div>';
}

function renderKPIs(d){
  const base=allRows(),w=AW(),nn=d.length||1;
  const h=d.reduce((a,b)=>a+(b.duracao||0),0);
  const u=new Set(d.map(r=>r.usina)).size,cl=new Set(d.map(r=>r.cluster)).size;
  const corr=d.filter(r=>r.tipo==='Corretiva').length;
  const rep=d.filter(r=>r.reprog==='Sim').length;
  const prev=d.filter(r=>['MPM','MPS','MPA','MPM-Mod/Tracker','MPM-Inversor'].includes(r.tipo)).length;
  const pend=Object.entries(w?.resumo||{}).filter(([k])=>base.some(r=>r.cluster===k)).reduce((a,[,v])=>a+(v.pend||0),0);
  const exec=d.filter(isExec).length;
  const novas=d.filter(isNova).length;
  const hh=h.toFixed(0);
  // Taxa de finalizacao por categoria preventiva (MPA semestral, MPS, MPM)
  const txMPM=taxaFinalizacaoPreventiva(d,'MPM');
  const txMPS=taxaFinalizacaoPreventiva(d,'MPS');
  const txMPA=taxaFinalizacaoPreventiva(d,'MPA');
  document.getElementById('krow').innerHTML=[
    ['--green', d.length,'OS programadas',h.toFixed(0)+'h de campo','g'],
    ['--green', u,'Usinas',cl+' equipe'+(cl!==1?'s':''),'g'],
    ['--danger', corr,'Corretivas',corr===0?'Portf\u00f3lio saud\u00e1vel':(corr/nn*100).toFixed(0)+'% do total',corr>0?'d':'g'],
    ['--warn', rep,'Reprogramadas',(rep/nn*100).toFixed(0)+'% das OS',rep/nn>.4?'w':''],
    ['--danger', pend,'Pendentes','sem equipe alocada',pend>0?'d':''],
    ['--exec', exec,'Em Execu\u00e7\u00e3o','OS em andamento agora','p'],
    // Taxa finalizacao preventivas - 3 cards (verde/amarelo/vermelho conforme %)
    ['--green', txMPA.tx+'%','Taxa Final. MPA',txMPA.fin+' de '+txMPA.total+' OS',txMPA.total===0?'':(txMPA.tx>=80?'g':txMPA.tx>=50?'w':'d')],
    ['--green', txMPS.tx+'%','Taxa Final. MPS',txMPS.fin+' de '+txMPS.total+' OS',txMPS.total===0?'':(txMPS.tx>=80?'g':txMPS.tx>=50?'w':'d')],
    ['--green', txMPM.tx+'%','Taxa Final. MPM',txMPM.fin+' de '+txMPM.total+' OS',txMPM.total===0?'':(txMPM.tx>=80?'g':txMPM.tx>=50?'w':'d')],
    // OS NAO Programadas - DESTAQUE com warning
    ['--danger', '\u26A0 '+novas,'OS N\u00c3O Programadas',novas>0?'Inseridas durante a semana':'Programa\u00e7\u00e3o respeitada',novas>0?'d':'g'],
    ['--green', hh+'h','HH Utilizada','horas de campo','g'],
  ].map(([col,val,lbl,sub,cls])=>
    '<div class="kpi"><div class="kpi-top" style="background:var('+col+')"></div>'
    +'<div class="kpi-body"><div class="kv '+cls+'">'+val+'</div><div class="kl">'+lbl+'</div><div class="ks">'+sub+'</div></div></div>'
  ).join('');
}

function renderIns(d){
  const n=d.length||1,corr=d.filter(r=>r.tipo==='Corretiva').length;
  const prev=d.filter(r=>['MPM','MPS','MPA','MPM-Mod/Tracker','MPM-Inversor'].includes(r.tipo)).length;
  const rep=d.filter(r=>r.reprog==='Sim').length,v3=d.filter(r=>r.vezes>=3).length;
  const h=d.filter(r=>!r.foraDoPlano).reduce((a,b)=>a+(b.duracao||0),0);
  const novas=d.filter(isNova).length;
  const exec=d.filter(isExec).length;
  const dc={}; DAYS.forEach(x=>dc[x]=d.filter(r=>r.dia===x).length);
  const pk=Object.entries(dc).sort((a,b)=>b[1]-a[1])[0]||['--',0];
  const w=AW(),resumo=w?.resumo||{};
  const equipes=[...new Set(d.map(r=>r.cluster))];
  const totalDisp=equipes.length*HH_DISP,totalUtil=h;
  const utilPct=totalDisp?Math.round(totalUtil/totalDisp*100):0;
  const overloaded=equipes.filter(cl=>(resumo[cl]?.hh_util||0)>HH_DISP);
  const planRows=d.filter(r=>!r.foraDoPlano),planFin=planRows.filter(isFinalizada).length;
  const ader=planRows.length?Math.round(planFin/planRows.length*100):0;
  const foraTot=d.filter(r=>r.foraDoPlano).length;
  document.getElementById('irow').innerHTML=[
    {cls:ader>=80?'ok':ader>=50?'w':'d',ico:'&#128203;',val:ader+'%',lbl:'Ader\u00eancia ao plano',desc:planFin+' de '+planRows.length+' tarefas do plano feitas'+(foraTot?' \u00b7 <strong>'+foraTot+' fora do plano</strong>':'')},
    {cls:corr===0?'ok':corr/n>.15?'d':'w',ico:'&#128295;',val:(prev/n*100).toFixed(0)+'%',lbl:'Preventivas',desc:corr===0?'Portf\u00f3lio saud\u00e1vel.':corr+' corretiva'+(corr>1?'s':'')+' ('+(corr/n*100).toFixed(0)+'%).'},
    {cls:rep===0?'ok':rep/n>.6?'d':'w',ico:'&#128260;',val:(rep/n*100).toFixed(0)+'%',lbl:'Reprogramadas',desc:rep===0?'Todas OS novas.':rep+' postergadas'+(v3?', '+v3+' na 3\u00aa+ tentativa':'')+'.'},
    {cls:utilPct>100?'d':utilPct<50?'w':'ok',ico:'&#9202;',val:utilPct+'%',lbl:'Hora Homem',desc:h.toFixed(0)+'h de '+totalDisp+'h.'+(overloaded.length?' '+overloaded.length+' equipe'+(overloaded.length>1?'s':'')+' sobrecarregada'+(overloaded.length>1?'s':'')+'!':'')},
    {cls:exec>0?'exec':'ok',ico:'&#9889;',val:exec,lbl:'Em Execu\u00e7\u00e3o',desc:exec>0?exec+' OS em andamento agora.':'Nenhuma OS em execu\u00e7\u00e3o.'},
    {cls:novas>0?'d':'ok',ico:novas>0?'&#9888;':'&#128196;',val:novas,lbl:novas>0?'\u26a0 OS N\u00c3O Programadas':'OS N\u00e3o Programadas',desc:novas>0?'<strong>'+novas+' OS</strong> inseridas SEM planejamento pr\u00e9vio. Investigar origem.':'Programa\u00e7\u00e3o respeitada.'},
  ].map(i=>'<div class="ins '+i.cls+'"><div class="ins-ico">'+i.ico+'</div><div class="ins-val">'+i.val+'</div><div class="ins-lbl">'+i.lbl+'</div><div class="ins-desc">'+i.desc+'</div></div>').join('');
}

// ── OS EM EXECUÇÃO ────────────────────────────────────────────────────────────
function renderExec(d){
  const execRows=d.filter(isExec);
  const cnt=document.getElementById('exec-cnt');
  if(cnt) cnt.textContent=execRows.length+' em andamento';
  const body=document.getElementById('exec-body');
  if(!body) return;
  if(!execRows.length){
    body.innerHTML='<div class="exec-empty">&#10003; Nenhuma OS em execu\u00e7\u00e3o no momento.</div>';
    return;
  }
  // Calcula tempo decorrido (em h) desde h_ini hoje
  const agora=new Date();
  function critPill(c){const x=(c||'').toLowerCase();if(x.indexOf('muito')>=0)return'<span class="exec-row-pill kc-muito">'+(c||'Muito alta')+'</span>';if(x.indexOf('alt')>=0)return'<span class="exec-row-pill kc-alta">'+(c||'Alta')+'</span>';if(x.indexOf('med')>=0)return'<span class="exec-row-pill kc-media">'+(c||'M\u00e9dia')+'</span>';if(x.indexOf('baix')>=0)return'<span class="exec-row-pill kc-baixa">'+(c||'Baixa')+'</span>';return'';}
  function decorrido(hIni){if(!hIni)return'';const m=String(hIni).match(/(\d{1,2}):(\d{2})/);if(!m)return'';const ini=parseInt(m[1])*60+parseInt(m[2]);const nowM=agora.getHours()*60+agora.getMinutes();const diff=nowM-ini;if(diff<0)return'';const h=Math.floor(diff/60),mi=diff%60;const cls=diff>=480?'veryLong':diff>=240?'long':'';return'<div class="exec-row-decorrido '+cls+'">'+(h?h+'h':'')+(mi?(h?' ':'')+mi+'m':'')+' decorridas</div>';}
  body.innerHTML=execRows.map(r=>{
    const sh=r.usina?r.usina.split(' - ').slice(-2).join(' - '):'';
    const hora=r.h_ini&&r.h_fim?r.h_ini+' \u2013 '+r.h_fim:r.h_ini||'';
    const resp=getSupervisor(r)||r.responsavel||'';
    const crit=r.criticidade||r['Criticidade']||'';
    const status=r.status_bd||r.status||'';
    const stC=statusCanonico(r.status_bd||r.status||'');
    const stKey=stC==='Não Iniciada'?'naoIniciada':stC==='Em progresso'?'emProgresso':stC==='Verificação'?'verificacao':stC==='Pausada'?'pausada':stC==='Finalizada'?'finalizada':'naoIniciada';
    const urgente=(crit||'').toLowerCase().indexOf('muito')>=0;
    return '<div class="exec-row" data-status="'+stKey+'" onclick="openMod(\''+esc(r.usina)+'\',\''+esc(r.dia)+'\',\''+esc(r.os_id)+'\')">'
      +'<div class="exec-row-l">'
      +  '<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px"><div class="exec-row-os">OS #'+r.os_id+'</div>'+(urgente?'<span class="urg">URGENTE</span>':'')+'<span class="stp '+stKey+'"><span class="stp-dot"></span>'+stC+'</span></div>'
      +  '<div class="exec-row-ativo">'+sh+'</div>'
      +  '<div class="exec-row-meta">'
      +    critPill(crit)
      +    '<span><b>Equipe:</b> '+(r.cluster||'--')+'</span>'
      +    (resp?'<span><b>Resp.:</b> '+resp+'</span>':'')
      +    '<span><b>Tipo:</b> '+(r.tipo||'--')+'</span>'
      +    (status?'<span><b>Status:</b> '+status+'</span>':'')
      +  '</div>'
      +'</div>'
      +'<div class="exec-row-time">'
      +  '<div class="exec-row-h">'+hora+'</div>'
      +  '<div class="exec-row-dur">'+(r.duracao||0)+'h previstas</div>'
      +  decorrido(r.h_ini)
      +'</div>'
      +'</div>';
  }).join('');
}

// ── CALENDAR SEMANAL ──────────────────────────────────────────────────────────
function renderCal(d){
  const w=AW(),dt=w?.dates||{seg:0,ter:0,qua:0,qui:0,sex:0};
  const dn=[dt.seg,dt.ter,dt.qua,dt.qui,dt.sex];
  document.getElementById('cal').innerHTML=DAYS.map((day,di)=>{
    const dd=d.filter(r=>r.dia===day),om={};
    dd.forEach(r=>{
      const k=r.os_id+'||'+r.usina;
      if(!om[k])om[k]={os:r.os_id,usina:r.usina,tipo:r.tipo,tasks:[],cluster:r.cluster,h_ini:r.h_ini,h_fim:r.h_fim,dur:0,rep:false,exec:false,nova:false,fora:false};
      om[k].tasks.push(r);om[k].dur+=r.duracao||0;
      if(r.reprog==='Sim')om[k].rep=true;
      if(isExec(r))om[k].exec=true;
      if(isNova(r))om[k].nova=true;
      if(r.foraDoPlano)om[k].fora=true;
      // M1 — rolagem 23:59: '↻ de ...' = rolou de verdade; 'sombra: ...' = só
      // simulação (visível apenas ao admin enquanto a rolagem roda em sombra)
      if(r.rolagem){
        if(r.rolagem.indexOf('sombra')===0){om[k].rolS=r.rolagem;}
        else{om[k].rol=r.rolagem;}
      }
    });
    const gs=Object.values(om).sort((a,b)=>{
      if(a.exec&&!b.exec)return -1;if(b.exec&&!a.exec)return 1;
      if(a.tipo==='Corretiva'&&b.tipo!=='Corretiva')return -1;
      if(b.tipo==='Corretiva'&&a.tipo!=='Corretiva')return 1;
      return (a.h_ini||'').localeCompare(b.h_ini||'');
    });
    // FIX #156: mostrar TODAS as OS — coluna agora é scrollável (.dtasks max-height)
    const vis=gs,ovf=0;
    const nos=new Set(dd.map(r=>r.os_id)).size,hd=dd.filter(r=>!r.foraDoPlano).reduce((a,b)=>a+(b.duracao||0),0);
    const cards=vis.map(g=>{
      const col=TC[g.tipo]||'#999',cls=TK[g.tipo]||'tOUT';
      const ut=[...new Set(g.tasks.map(t=>t.tarefa))];
      const hora=g.h_ini&&g.h_fim?g.h_ini+'\u2013'+g.h_fim:'';
      const dur=g.dur>0?(g.dur===Math.floor(g.dur)?g.dur+'h':g.dur.toFixed(1)+'h'):'';
      const sh=g.usina.split(' - ').slice(-2).join(' - ');
      // ESTADO DA TAREFA (badge principal): mais "avançado" das tasks, SEM statusPai
      const ests=g.tasks.map(estadoTarefaInfo);
      let estK='naoIniciada',estL='Não Iniciada';
      if(ests.some(e=>e.k==='emProgresso')){estK='emProgresso';estL='Em progresso';}
      else if(ests.some(e=>e.k==='pausada')){estK='pausada';estL='Pausada';}
      else if(ests.length&&ests.every(e=>e.k==='finalizada')){estK='finalizada';estL='Finalizada';}
      // STATUS DA OS (selo separado): prioriza Verificação; senão o primeiro não-vazio
      const soss=g.tasks.map(statusOsInfo);
      const sos=soss.find(x=>x&&x.k==='verificacao')||soss.find(Boolean)||null;
      return '<div class="osc '+cls+(g.fora?' fora-plano':'')+'" onclick="openMod(\''+esc(g.usina)+'\',\''+esc(day)+'\',\''+esc(g.os)+'\')">'
        +'<div class="osc-top"><span class="osc-num">OS #'+g.os+'</span>'
        +'<span class="stp '+estK+'"><span class="stp-dot"></span>'+estL+'</span>'
        +(sos?'<span class="osc-osstatus '+sos.k+'" title="Status da OS">'+sos.l+'</span>':'')
        +'<span class="osc-badge" style="background:'+col+'1a;color:'+col+'">'+(TL[g.tipo]||g.tipo)+'</span></div>'
        +'<div class="osc-usina" style="color:'+col+'">'+sh+'</div>'
        +'<div class="osc-tasks">'+ut.join(' \u00b7 ')+'</div>'
        +'<div class="osc-foot">'+(hora?'<span class="osc-time">'+hora+'</span>':'')+(dur?'<span class="osc-dur">'+dur+'</span>':'')
        +(g.fora?'<span class="osc-fora">&#9889; Fora do plano</span>':'')
        +(g.exec?'<span class="osc-exec">&#9889; Em exec.</span>':'')
        +(g.nova?'<span class="osc-nova">&#43; N\u00e3o prog.</span>':'')
        +(g.rep?'<span class="osc-rep">&#8635; Reprog.</span>':'')
        +(g.rol?'<span class="osc-rol'+(/([3-9]|\d\d)ª/.test(g.rol)?' r3':'')+'" title="'+esc(g.rol)+'">&#8635; rolou</span>':'')
        +(g.rolS&&S.isAdmin?'<span class="osc-rolsombra" title="'+esc(g.rolS)+'">&#8635; sombra</span>':'')
        +'<span class="osc-n">'+g.tasks.length+'t</span></div></div>';
    }).join('');
    const ovfBtn=ovf>0?'<div class="more-pill" onclick="openMod(\'\',\''+esc(day)+'\',\'\')">+'+ovf+' OS</div>':'';
    // Contagem por TAREFA (mesma unidade dos KPIs de cima) — soma dos dias = total da semana
    const planT=dd.filter(r=>!r.foraDoPlano), foraT=dd.filter(r=>r.foraDoPlano);
    const feitasN=planT.filter(isFinalizada).length, foraN=foraT.length, foraFeitas=foraT.filter(isFinalizada).length;
    const meta=planT.length+' no plano'
      +(feitasN?' \u00b7 <span class="mfeitas">\u2705'+feitasN+' feitas</span>':'')
      +(foraN?' \u00b7 <span class="mfora">\u26a1'+foraN+' fora do plano'+(foraFeitas?' ('+foraFeitas+' feitas)':'')+'</span>':'')
      +' \u00b7 '+hd.toFixed(0)+'h';
    return '<div class="dcol"><div class="dhdr"><div class="dname">'+DSHORT[day]+'</div>'
      +'<div class="dnum">'+(dn[di]||'')+'</div><div class="dmeta">'+meta+'</div></div>'
      +'<div class="dtasks">'+(dd.length?cards+ovfBtn:'<div class="dempty">Sem atividades</div>')+'</div></div>';
  }).join('');
}

// ── CALENDÁRIO MENSAL ─────────────────────────────────────────────────────────
function renderMonthly(){
  const rows=allRowsAllWeeks();
  if(!rows.length){document.getElementById('mcal-wrap').innerHTML='<div style="text-align:center;padding:40px;color:var(--ink3)">Sem dados para exibir.</div>';return;}

  // Descobrir mês/ano do banco ativo
  const w=AW();
  const ano=w?.dates?.ano||2026;
  const mes=new Date().getMonth(); // mês atual como padrão
  const primeiroDia=new Date(ano,mes,1);
  const ultimoDia=new Date(ano,mes+1,0).getDate();
  const inicioSem=primeiroDia.getDay(); // 0=dom
  const offset=inicioSem===0?6:inicioSem-1; // ajusta para seg=0

  // Mapear OS por dia do mês
  const osPorDia={};
  rows.forEach(r=>{
    if(!r.dia||!r.semana) return;
    // Buscar a semana correspondente
    const sem=DB?.semanas?.find(s=>s.num===r.semana);
    if(!sem) return;
    const dt=sem.dates;
    const diaMap={'Segunda-feira':dt.seg,'Ter\u00e7a-feira':dt.ter,'Quarta-feira':dt.qua,'Quinta-feira':dt.qui,'Sexta-feira':dt.sex};
    const diaNum=diaMap[r.dia];
    if(!diaNum) return;
    // Verificar se esse dia é do mês exibido
    // (simplificado: usa o número do dia diretamente)
    const k=diaNum;
    if(k<1||k>ultimoDia) return;
    if(!osPorDia[k]) osPorDia[k]=[];
    osPorDia[k].push(r);
  });

  const hoje=new Date();
  const hojeDia=hoje.getDate(),hojeMes=hoje.getMonth(),hojeAno=hoje.getFullYear();
  const isHoje=(d)=>d===hojeDia&&mes===hojeMes&&ano===hojeAno;

  let html='<div class="mcal-hdr">'+['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'].map(d=>'<div class="mcal-dname">'+d+'</div>').join('')+'</div>';
  html+='<div class="mcal">';

  // Células vazias antes do dia 1
  for(let i=0;i<offset;i++) html+='<div class="mcal-day empty"></div>';

  // Dias do mês
  for(let d=1;d<=ultimoDia;d++){
    const dayOs=osPorDia[d]||[];
    const isToday=isHoje(d);
    html+='<div class="mcal-day'+(isToday?' today':'')+'"><div class="mcal-day-num">'+d+'</div>';
    const vis=dayOs.slice(0,3);
    const ovf=dayOs.length-3;
    vis.forEach(r=>{
      const col=TC[r.tipo]||'#999';
      const sh=r.usina.split(' - ').slice(-1)[0];
      html+='<div class="mcal-os-pill" style="background:'+col+'20;color:'+col+'" onclick="openMod(\''+esc(r.usina)+'\',\''+esc(r.dia)+'\',\''+esc(r.os_id)+'\')">'+sh+'</div>';
    });
    if(ovf>0) html+='<div class="mcal-more">+'+ovf+' OS</div>';
    html+='</div>';
  }

  // Completar última semana
  const total=offset+ultimoDia;
  const restante=total%7===0?0:7-(total%7);
  for(let i=0;i<restante;i++) html+='<div class="mcal-day empty"></div>';

  html+='</div>';

  const wrap=document.getElementById('mcal-wrap');
  if(wrap){
    document.getElementById('mcal-title').textContent=MESES[mes]+' '+ano;
    wrap.innerHTML=html;
  }
}

// ── BOTTOM ────────────────────────────────────────────────────────────────────
function renderBottom(d){renderUsinaTable(d);renderStats(d);renderHH(d);renderExecDayChart(d);renderStatusChart(d);}
function renderExecDayChart(d){
  const el=document.getElementById('exec-day-chart');
  if(!el) return;
  // Calcula finalizadas vs total por dia
  const stats=DAYS.map(day=>{
    const dd=d.filter(r=>r.dia===day);
    const tot=dd.length;
    const fin=dd.filter(isFinalizada).length;
    return {day:day,short:DSHORT[day]||day.slice(0,3),tot:tot,fin:fin,pct:tot?Math.round(fin/tot*100):0};
  });
  const maxTot=Math.max(1,...stats.map(s=>s.tot));
  const W=520,H=220,P=30,BW=(W-P*2)/stats.length;
  let svg='<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;height:auto" xmlns="http://www.w3.org/2000/svg">';
  // grade
  for(let i=0;i<=4;i++){
    const y=P+(H-P*2)*i/4;
    svg+='<line x1="'+P+'" y1="'+y+'" x2="'+(W-P)+'" y2="'+y+'" stroke="#eee" stroke-width="1"/>';
    svg+='<text x="'+(P-5)+'" y="'+(y+3)+'" font-size="9" text-anchor="end" fill="#888">'+Math.round(maxTot*(1-i/4))+'</text>';
  }
  stats.forEach((s,i)=>{
    const x=P+i*BW+BW*0.1, bw=BW*0.8;
    const hTot=(H-P*2)*s.tot/maxTot, hFin=(H-P*2)*s.fin/maxTot;
    // Barra total (cinza claro)
    svg+='<rect x="'+x+'" y="'+(H-P-hTot)+'" width="'+bw+'" height="'+hTot+'" fill="#e5e7eb" rx="2"/>';
    // Barra finalizadas (verde)
    if(hFin>0) svg+='<rect x="'+x+'" y="'+(H-P-hFin)+'" width="'+bw+'" height="'+hFin+'" fill="#a9db21" rx="2"/>';
    // Labels
    svg+='<text x="'+(x+bw/2)+'" y="'+(H-P-hTot-6)+'" font-size="10" font-weight="700" text-anchor="middle" fill="#333">'+s.fin+'/'+s.tot+'</text>';
    svg+='<text x="'+(x+bw/2)+'" y="'+(H-P+12)+'" font-size="10" font-weight="700" text-anchor="middle" fill="#666">'+s.short+'</text>';
    svg+='<text x="'+(x+bw/2)+'" y="'+(H-P+24)+'" font-size="9" text-anchor="middle" fill="#a9db21">'+s.pct+'%</text>';
  });
  // legenda
  svg+='<rect x="'+P+'" y="6" width="10" height="10" fill="#a9db21" rx="2"/><text x="'+(P+14)+'" y="15" font-size="10" fill="#555">Finalizadas</text>';
  svg+='<rect x="'+(P+85)+'" y="6" width="10" height="10" fill="#e5e7eb" rx="2"/><text x="'+(P+99)+'" y="15" font-size="10" fill="#555">Programadas</text>';
  svg+='</svg>';
  el.innerHTML=svg;
}

function renderUsinaTable(d){
  const baseU=S.fEquipe?allRows().filter(r=>r.cluster===S.fEquipe):AC(),um={};
  baseU.forEach(r=>{if(!um[r.usina])um[r.usina]={cluster:r.cluster,tipos:{},os:new Set(),h:0};
    um[r.usina].tipos[r.tipo]=(um[r.usina].tipos[r.tipo]||0)+1;
    um[r.usina].os.add(r.os_id);um[r.usina].h+=r.duracao||0;});
  const sorted=Object.entries(um).sort((a,b)=>b[1].h-a[1].h);
  const maxH=sorted[0]?.[1]?.h||1;
  document.getElementById('usina-cnt').textContent=sorted.length+' usina'+(sorted.length!==1?'s':'');
  document.getElementById('usina-tbody').innerHTML=sorted.map(([u,info])=>{
    const chips=Object.entries(info.tipos).sort((a,b)=>b[1]-a[1]).map(([t,n])=>
      '<span class="ut-chip" style="background:'+(TB[t]||'#f0f0f0')+';color:'+(TC[t]||'#666')+'">'+(TL[t]||t)+(n>1?' \u00d7'+n:'')+'</span>').join('');
    const h=info.h,dur=h===Math.floor(h)?h+'h':h.toFixed(1)+'h';
    const sh=u.split(' - ').slice(-2).join(' - ');
    return '<tr onclick="filterByUsina(\''+esc(u)+'\')">'
      +'<td style="padding-left:16px"><div class="ut-n">'+sh+'</div><div class="ut-c">'+info.cluster+' \u00b7 '+info.os.size+' OS</div></td>'
      +'<td><div class="ut-chips">'+chips+'</div></td>'
      +'<td><div class="ut-h">'+dur+'</div></td>'
      +'<td><div class="ut-bw"><div class="ut-b" style="width:'+Math.round(info.h/maxH*100)+'%"></div></div></td></tr>';
  }).join('');
}
function filterByUsina(u){const s=SEM_SEL.usina;if(s.has(u))s.delete(u);else s.add(u);semMsLabel('usina');render();updateFCount();if(s.size)toast('Filtrado: '+u.split(' - ').slice(-1)[0]);}

function renderStats(d){
  const n=d.length||1;
  const corr=d.filter(r=>r.tipo==='Corretiva').length;
  const prev=d.filter(r=>['MPM','MPS','MPA','MPM-Mod/Tracker','MPM-Inversor'].includes(r.tipo)).length;
  const v1=d.filter(r=>r.vezes===1).length,v2=d.filter(r=>r.vezes===2).length,v3=d.filter(r=>r.vezes>=3).length;
  const novas=d.filter(isNova).length;
  const pp=Math.round(prev/n*100),cp=Math.round(corr/n*100);
  document.getElementById('stat-grid').innerHTML=
    '<div class="stat-card"><div class="sc-val" style="color:'+(pp>=80?'var(--gd)':'var(--warn)')+'">'+pp+'%</div>'
    +'<div class="sc-lbl">Preventivas</div><div class="sc-sub">'+prev+' de '+n+' OS</div>'
    +'<div class="sc-bar-wrap"><div class="sc-bar-lbl"><span>Prev.</span><span>Corr.</span></div>'
    +'<div class="sc-bar"><div class="sc-fill" style="width:'+pp+'%;background:var(--green)"></div></div></div></div>'
    +'<div class="stat-card"><div class="sc-val" style="color:'+(cp>15?'var(--danger)':cp>5?'var(--warn)':'var(--gd)')+'">'+corr+'</div>'
    +'<div class="sc-lbl">Corretivas</div><div class="sc-sub">'+cp+'% do total</div>'
    +'<div class="sc-bar-wrap"><div class="sc-bar-lbl"><span>Vol.</span><span>'+cp+'%</span></div>'
    +'<div class="sc-bar"><div class="sc-fill" style="width:'+cp+'%;background:'+(cp>15?'var(--danger)':'var(--warn)')+'"></div></div></div></div>';
  document.getElementById('reprog-detail').innerHTML=
    '<div class="reprog-sec-title">Hist\u00f3rico de reprograma\u00e7\u00e3o</div>'
    +[['1\u00aa vez',v1,'#10b981'],['2\u00aa tentativa',v2,'#f59e0b'],['3\u00aa+ tentativa',v3,'#e53e3e']]
    .map(([lbl,val,col])=>'<div class="reprog-row"><div class="reprog-dot" style="background:'+col+'"></div>'
      +'<div class="reprog-lbl">'+lbl+'</div><div class="reprog-n">'+val+'</div>'
      +'<div class="reprog-pct">'+((val/n)*100).toFixed(0)+'%</div></div>').join('')
    +'<div class="reprog-row"><div class="reprog-dot" style="background:#0ea5e9"></div>'
    +'<div class="reprog-lbl">N\u00e3o programadas</div><div class="reprog-n">'+novas+'</div>'
    +'<div class="reprog-pct">'+((novas/n)*100).toFixed(0)+'%</div></div>';
}

function renderHH(d){
  const w=AW();
  // Calcula resumo DINÂMICO a partir do d filtrado (não do w.resumo estático)
  const resumo={};
  d.forEach(r=>{
    const cl=r.cluster||'(sem equipe)';
    if(!resumo[cl]) resumo[cl]={hh_util:0,hh_disp:HH_DISP,pend:0};
    resumo[cl].hh_util += (r.duracao||0);
  });
  // Mescla pendentes do resumo original (que não vem em d)
  const resumoOrig=w?.resumo||{};
  Object.keys(resumo).forEach(cl=>{
    if(resumoOrig[cl]) resumo[cl].pend=resumoOrig[cl].pend||0;
  });
  const equipes=[...new Set(d.map(r=>r.cluster))].sort();
  const totalDisp=equipes.length*HH_DISP,totalUtil=d.reduce((a,b)=>a+(b.duracao||0),0);
  const utilPct=totalDisp?Math.round(totalUtil/totalDisp*100):0;
  const livre=totalDisp-totalUtil,colU=utilPct>100?'var(--danger)':utilPct>80?'var(--warn)':'var(--gd)';
  let html='<div class="hh-summary">'
    +'<div class="hh-sum-card"><div class="hh-sum-val" style="color:'+colU+'">'+totalUtil.toFixed(0)+'h</div><div class="hh-sum-lbl">HH Utilizada</div><div class="hh-sum-sub">'+utilPct+'% da capacidade</div></div>'
    +'<div class="hh-sum-card"><div class="hh-sum-val">'+totalDisp+'h</div><div class="hh-sum-lbl">HH Dispon\u00edvel</div><div class="hh-sum-sub">'+equipes.length+' equipe'+(equipes.length!==1?'s':'')+' \u00d7 '+HH_DISP+'h</div></div>'
    +'<div class="hh-sum-card"><div class="hh-sum-val" style="color:'+(livre<0?'var(--danger)':'var(--ink)')+'">'+Math.abs(livre).toFixed(0)+'h</div><div class="hh-sum-lbl">'+(livre<0?'Hora Extra':'Hora Livre')+'</div><div class="hh-sum-sub">'+(livre<0?'Excedida':'N\u00e3o alocada')+'</div></div>'
    +'</div><div class="hh-sec-title">Por equipe</div>';
  if(!equipes.length){
    html+='<div class="hh-empty-msg">Nenhuma equipe com OS programada nesta semana.</div>';
  } else {
    html+='<div class="hh-grid">';
    equipes.sort((a,b)=>((resumo[b]?.hh_util||0)-(resumo[a]?.hh_util||0))).forEach(cl=>{
      const r=resumo[cl]||{hh_util:0,hh_disp:HH_DISP};
      const pct=Math.min(100,Math.round(r.hh_util/r.hh_disp*100));
      const colHH=pct>100?'var(--danger)':pct>80?'var(--warn)':'var(--gd)';
      const pctCls=pct>100?'sni':pct>80?'sni':'sep2';
      html+='<div class="hh-row">'
        +'<div class="hh-lbl" title="'+cl+'">'+cl+'</div>'
        +'<div class="hh-track"><div class="hh-fill" style="width:'+pct+'%;background:'+colHH+'"></div></div>'
        +'<div class="hh-vals">'+r.hh_util.toFixed(0)+'h/'+r.hh_disp+'h<span class="hh-pct-tag '+pctCls+'" style="color:'+colHH+'">'+pct+'%</span></div>'
        +'</div>';
    });
    html+='</div>';
  }
  document.getElementById('hh-body').innerHTML=html;
}


// ── MODAL DE DETALHES DA OS ────────────────────────────────────────────────────
function openMod(usina, dia, os_id){
  // Acha a OS no DB pela os_id
  let osRow = null;
  let osLista = [];
  if(DB && DB.semanas){
    const w = AW() || DB.semanas[DB.semanas.length-1];
    if(w && w.rows){
      if(os_id){
        osLista = w.rows.filter(r => String(r.os_id) === String(os_id));
        // O card do dia é POR TAREFA: uma OS partida aparece em vários dias com
        // tarefas diferentes. Sem filtrar pelo dia clicado, o modal mostrava a
        // PRIMEIRA tarefa da OS na semana — ou seja, quase sempre a de outro
        // dia, e o técnico não sabia o que fazer naquele dia.
        const _doDia = dia ? osLista.filter(r => String(r.dia||'').indexOf(dia) >= 0) : [];
        osRow = _doDia[0] || osLista[0] || null;
        if(_doDia.length){ osRow = Object.assign({}, osRow, {_tarefasDoDia:_doDia, _diaClicado:dia}); }
      } else if(usina && dia){
        osLista = w.rows.filter(r => r.usina===usina && (r.dia||'').indexOf(dia)>=0);
        osRow = osLista[0] || null;
      } else if(dia){
        osLista = w.rows.filter(r => (r.dia||'').indexOf(dia)>=0);
        osRow = osLista[0] || null;
      }
    }
  }
  if(!osRow && os_id && ETIQUETAS_DB && ETIQUETAS_DB.tipologias){
    // Procura nas listas em aberto OU histórico (toggle Em Aberto / Histórico)
    for(const slug in ETIQUETAS_DB.tipologias){
      const tp = ETIQUETAS_DB.tipologias[slug];
      const o = (tp.oss||[]).find(x=>String(x.osId)===String(os_id))
             || (tp.ossHistorico||[]).find(x=>String(x.osId)===String(os_id));
      if(o){
        osRow = {os_id:o.osId, usina:o.ativo, cluster:o.equipe, responsavel:o.responsavel, status_bd:o.status, criticidade:o.criticidade, dia:o.dataProgramada, dataProgramada:o.dataProgramada, tarefa:o.tarefa, linkFracttal:o.linkFracttal, modalidade:o.modalidade, dataCriacao:o.dataCriacao, dataFinal:o.dataFinal};
        break;
      }
    }
  }
  // Task #134: enriquece osRow do PCM com dataCriacao/dataFinal/criadoPor/horasAteFechar das etiquetas
  if(osRow && os_id && ETIQUETAS_DB && ETIQUETAS_DB.tipologias){
    for(const slug in ETIQUETAS_DB.tipologias){
      const tp = ETIQUETAS_DB.tipologias[slug];
      const o = (tp.oss||[]).find(x=>String(x.osId)===String(os_id))
             || (tp.ossHistorico||[]).find(x=>String(x.osId)===String(os_id));
      if(o){
        ['dataCriacao','dataProgramada','dataFinal','dataInicial','criadoPor',
         'horasAteAbrir','horasAteFechar','modalidade'].forEach(k=>{
          if(!osRow[k] && o[k]!=null) osRow[k] = o[k];
        });
        break;
      }
    }
  }
  // ENRIQUECIMENTO: quando osRow veio das etiquetas/verificação (poucos campos),
  // procura a MESMA OS no banco_dados.json pra trazer MTTR/relatório/timeline/outras tarefas
  if(osRow && os_id && DB && DB.semanas){
    for(const w of DB.semanas){
      const matches = (w.rows||[]).filter(r => String(r.os_id) === String(os_id));
      if(matches.length){
        // Pega o primeiro pra dados gerais; lista pra "outras tarefas"
        const fromBD = matches[0];
        ['relatorio','historico','mttr_s','mttr_h','tempo_total_s','pausado_s',
         'duracao','h_ini','h_fim','reprog','vezes','nova_os','codigo','etiquetas',
         'cluster','responsavel','tarefa'].forEach(k=>{
          if(!osRow[k] && fromBD[k]!=null) osRow[k] = fromBD[k];
        });
        if(matches.length > 1) osLista = matches;
        // não deixa o enriquecimento trocar a tarefa do dia pela primeira da OS
        if(osRow._tarefasDoDia && osRow._tarefasDoDia.length) osRow.tarefa = osRow._tarefasDoDia[0].tarefa;
        break;
      }
    }
  }
  if(!osRow && ETIQUETAS_DB && ETIQUETAS_DB.verificacao && ETIQUETAS_DB.verificacao.oss){
    const o = ETIQUETAS_DB.verificacao.oss.find(x=>String(x.osId)===String(os_id));
    if(o) osRow = {os_id:o.osId, usina:o.ativo, cluster:o.equipe, responsavel:o.responsavel, status_bd:o.status, criticidade:o.criticidade, dia:o.dataProgramada, linkFracttal:o.linkFracttal};
  }
  const mbox = document.querySelector('#modal .mbox');
  if(!osRow){
    mbox.innerHTML = '<div class="mtop2"><button class="mtop2-close" onclick="closeMod()">✕</button><div class="mtop2-title">OS não encontrada</div><div class="mtop2-sub">'+(os_id?('#'+os_id):dia||'')+'</div></div><div class="msec" style="text-align:center;color:var(--ink3);padding:30px">Não foi possível carregar os detalhes desta OS.</div>';
    document.getElementById('modal').classList.add('open');
    return;
  }
  const _esc = s => String(s==null?'':s).replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const stCanon = statusCanonico(osRow.status_bd || osRow.status || 'naoIniciada');
  const stKey = stCanon === 'Não Iniciada'?'naoIniciada':stCanon==='Em progresso'?'emProgresso':stCanon==='Verificação'?'verificacao':stCanon==='Pausada'?'pausada':stCanon==='Finalizada'?'finalizada':'naoIniciada';
  const stLabel = stCanon==='Verificação'?'⚠ Em Verificação':stCanon;
  const crit = (osRow.criticidade||'').toLowerCase();
  const critKey = crit.indexOf('muito')>=0?'crit-muito':crit.indexOf('alt')>=0?'crit-alta':crit.indexOf('med')>=0?'crit-media':crit?'crit-baixa':'';
  const isUrgente = crit.indexOf('muito')>=0 || /urgente/i.test(osRow.urgente||'');
  // Datas
  const hoje = new Date(); hoje.setHours(0,0,0,0);
  function parseDt(s){
    if(!s) return null;
    s = String(s).trim();
    // 1. ISO completa "2026-05-28T20:44:50.049389+00:00" → parse direto
    if(/^\d{4}-\d{2}-\d{2}T/.test(s)){
      let str = s;
      // Trunca microsegundos pra 3 dígitos (alguns browsers falham com 6)
      str = str.replace(/(\.\d{3})\d+/, '$1');
      // Se não tem timezone, adiciona Z (assume UTC)
      if(!/[Z+-]\d{2}:?\d{2}$|Z$/.test(str)) str += 'Z';
      const d = new Date(str);
      if(!isNaN(d)) return d;
      // Fallback: extrai só a parte da data
      const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
      if(m) return new Date(parseInt(m[1]), parseInt(m[2])-1, parseInt(m[3]));
    }
    // 2. YYYY-MM-DD
    const m2 = s.match(/(\d{4})-(\d{2})-(\d{2})/);
    if(m2) return new Date(m2[1]+'-'+m2[2]+'-'+m2[3]);
    // 3. DD/MM (assume ano atual)
    const m = s.match(/(\d{1,2})\/(\d{1,2})/);
    if(m){
      const d = new Date();
      d.setMonth(parseInt(m[2])-1);
      d.setDate(parseInt(m[1]));
      d.setHours(0,0,0,0);
      return d;
    }
    return null;
  }
  const dCria = parseDt(osRow.dataCriacao||osRow.data_criacao);
  const dProg = parseDt(osRow.dataProgramada||osRow.data_prog||osRow.dia);
  const dFim = parseDt(osRow.dataFinal||osRow.data_final);
  // FIX #143: Modal mostra status PAI se "Em Verificação" (OS pai aguarda aprovação)
  // mas mantém card kanban com status da subtarefa
  const statusPaiRaw = (osRow.statusPai||'').toString().toLowerCase();
  const statusRaw = (osRow.status_bd||osRow.status||'').toString().toLowerCase();
  // Se OS pai está em Verificação, modal mostra "Em Verificação" SEMPRE
  if(statusPaiRaw.indexOf('verifica')>=0){
    osRow.status_bd = 'Em Verificação';
  } else if((statusRaw.indexOf('finaliz')>=0||statusRaw.indexOf('conclu')>=0) && !dFim){
    // Heurística fallback: "Finalizada" sem dataFinal → "Em Verificação"
    osRow.status_bd = 'Em Verificação';
  }
  const dProgClass = dProg && dProg < hoje && !dFim ? 'atraso' : (dFim ? 'ok' : '');
  function fmtDt(d){if(!d)return '--'; return ('0'+d.getDate()).slice(-2)+'/'+('0'+(d.getMonth()+1)).slice(-2);}
  function fmtDtH(d){
    if(!d) return '--';
    const dd = ('0'+d.getDate()).slice(-2);
    const mm = ('0'+(d.getMonth()+1)).slice(-2);
    const hh = ('0'+d.getHours()).slice(-2);
    const mn = ('0'+d.getMinutes()).slice(-2);
    // Se hora=00:00 não mostra (provavelmente date-only)
    if(hh==='00' && mn==='00') return dd+'/'+mm;
    return dd+'/'+mm+' às '+hh+':'+mn;
  }
  let html = '';
  html += '<div class="mtop2">';
  html += '  <button class="mtop2-close" onclick="closeMod()">✕</button>';
  html += '  <div class="mtop2-row"><span class="mtop2-os">OS #'+(osRow.os_id||'--')+'</span><span class="mtop2-status '+stKey+'">'+stLabel+'</span></div>';
  html += '  <div class="mtop2-title">'+_esc(osRow.usina||'(sem ativo)')+'</div>';
  html += '  <div class="mtop2-sub">'+_esc([osRow.cluster, osRow.responsavel].filter(Boolean).join(' · '))+'</div>';
  html += '</div>';
  // SEÇÃO 1: O que fazer
  html += '<div class="msec"><div class="msec-t">📋 O que fazer</div>';
  const _td = osRow._tarefasDoDia || [];
  if(_td.length){
    const _dl = String(osRow._diaClicado||'').split(' [')[0];
    html += '  <div class="mdia-lbl">'+_esc(_dl)+' &middot; '+_td.length+' tarefa(s) neste dia</div>';
    html += _td.slice().sort((x,y)=>String(x.h_ini||'').localeCompare(String(y.h_ini||'')))
      .map(t => '<div class="mtarefa mtarefa-dia">'
        + (t.h_ini ? '<span class="mtarefa-h">'+_esc(t.h_ini)+(t.h_fim?'–'+_esc(t.h_fim):'')+'</span>' : '')
        + _esc(t.tarefa||'(sem descrição)') + '</div>').join('');
    // as demais tarefas da MESMA OS ficam como contexto, sem confundir com o dia
    const _outras = (osLista||[]).filter(r => _td.indexOf(r) < 0);
    if(_outras.length){
      const _po = {};
      _outras.forEach(r => { const d = String(r.dia||'').split(' [')[0]; (_po[d] = _po[d] || []).push(r); });
      html += '<div class="mdia-out"><b>Mesma OS em outros dias:</b> '
        + Object.keys(_po).map(d => _esc(d)+' ('+_po[d].length+')').join(' &middot; ') + '</div>';
    }
  } else {
    html += '  <div class="mtarefa">'+_esc(osRow.tarefa||osRow.usina||'(sem descrição da tarefa)')+'</div>';
  }
  html += '  <div class="mpills">';
  if(isUrgente) html += '<span class="mpill crit-muito">⚠ URGENTE</span>';
  if(critKey) html += '<span class="mpill '+critKey+'">'+_esc(osRow.criticidade||'')+'</span>';
  if(osRow.tipo) html += '<span class="mpill tipo">'+_esc(osRow.tipo)+'</span>';
  if(osRow.modalidade) html += '<span class="mpill modalidade-'+osRow.modalidade+'">'+osRow.modalidade.toUpperCase()+'</span>';
  html += '  </div>';
  html += '</div>';
  // SEÇÃO 2 removida — Datas agora ficam na timeline (task #146)
  let mttrLabel = '';
  if(osRow.mttr_h!=null && Number(osRow.mttr_h)>0){
    mttrLabel = fmtMTTR(osRow.mttr_h);
  } else if(osRow.horasAteFechar!=null && Number(osRow.horasAteFechar)>0){
    mttrLabel = fmtMTTR(osRow.horasAteFechar);
  }
  // SEÇÃO 2.5: Relatório de execução (subtarefa preenchida pelo executor)
  if(osRow.relatorio && String(osRow.relatorio).trim()){
    const rel = String(osRow.relatorio);
    const longo = rel.length > 300;
    html += '<div class="msec"><div class="msec-t">📝 Relatório de execução'+(osRow.responsavel?(' — '+_esc(osRow.responsavel)):'')+'</div>';
    html += '  <div class="mreport"><div class="mreport-c'+(longo?'':' open')+'" id="mrc">'+_esc(rel)+'</div>';
    if(longo) html += '<button class="mreport-btn" onclick="(function(b){var c=document.getElementById(\'mrc\');c.classList.toggle(\'open\');b.textContent=c.classList.contains(\'open\')?\'Ver menos ↑\':\'Ver mais ↓\';})(this)">Ver mais ↓</button>';
    html += '  </div>';
    html += '</div>';
  }
  // SEÇÃO 2.55: MTTR destacado (se disponível)
  if(osRow.mttr_s && osRow.mttr_s > 0){
    function _fmtDurH(s){s=parseInt(s)||0;if(!s)return '0min';const d=Math.floor(s/86400),h=Math.floor((s%86400)/3600),m=Math.floor((s%3600)/60);if(d)return d+'d'+(h?(' '+h+'h'):'');if(h)return h+'h'+(m?(' '+m+'min'):'');return m+'min';}
    const mttrTxt = _fmtDurH(osRow.mttr_s);
    const totalTxt = _fmtDurH(osRow.tempo_total_s);
    const pausTxt = _fmtDurH(osRow.pausado_s);
    html += '<div class="msec"><div class="msec-t">⏱ MTTR (tempo real de reparo)</div>';
    html += '  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:6px">';
    html += '    <div style="background:#dcfce7;border-radius:8px;padding:10px;text-align:center"><div style="font-size:10px;color:#166534;font-weight:600;text-transform:uppercase;letter-spacing:.5px">MTTR Real</div><div style="font-size:18px;font-weight:700;color:#15803d;margin-top:2px">'+mttrTxt+'</div></div>';
    html += '    <div style="background:#fef3c7;border-radius:8px;padding:10px;text-align:center"><div style="font-size:10px;color:#854f0b;font-weight:600;text-transform:uppercase;letter-spacing:.5px">Em Pausa</div><div style="font-size:18px;font-weight:700;color:#a16207;margin-top:2px">'+pausTxt+'</div></div>';
    html += '    <div style="background:#f1f5f9;border-radius:8px;padding:10px;text-align:center"><div style="font-size:10px;color:#475569;font-weight:600;text-transform:uppercase;letter-spacing:.5px">Decorrido</div><div style="font-size:18px;font-weight:700;color:#334155;margin-top:2px">'+totalTxt+'</div></div>';
    html += '  </div>';
    html += '</div>';
  }
  // SEÇÃO 2.6: Timeline de execução (histórico IN_PROGRESS / PAUSED)
  if(Array.isArray(osRow.historico) && osRow.historico.length){
    function _fmtDtHora(s){if(!s)return '--';try{const d=new Date(s);if(isNaN(d))return String(s).substring(5,16);return ('0'+d.getDate()).slice(-2)+'/'+('0'+(d.getMonth()+1)).slice(-2)+' '+('0'+d.getHours()).slice(-2)+':'+('0'+d.getMinutes()).slice(-2);}catch(e){return String(s).substring(5,16);}}
    function _fmtDurTL(s){s=parseInt(s)||0;if(!s)return '0min';const d=Math.floor(s/86400),h=Math.floor((s%86400)/3600),m=Math.floor((s%3600)/60);if(d)return d+'d'+(h?(' '+h+'h'):'');if(h)return h+'h'+(m?(' '+m+'min'):'');return m+'min';}
    // Mapeia tipo IN_PROGRESS/PAUSED/END_TASK → classe visual + ícone
    function _mapaTipo(tipo){
      const t=(tipo||'').toUpperCase();
      if(t.indexOf('PROGRESS')>=0 || t.indexOf('RUN')>=0) return {cls:'run', icone:'▶', label:'Em progresso'};
      if(t.indexOf('PAUSED')>=0 || t.indexOf('PAUSA')>=0) return {cls:'pau', icone:'⏸', label:'Pausada'};
      if(t.indexOf('END')>=0 || t.indexOf('FIM')>=0) return {cls:'fim', icone:'✔', label:'Concluída'};
      return {cls:'fim', icone:'•', label:tipo||'Ação'};
    }
    let totalRun=0, totalPau=0;
    osRow.historico.forEach(a=>{
      const t=(a.tipo||'').toUpperCase();
      if(t.indexOf('PROGRESS')>=0 || t.indexOf('RUN')>=0) totalRun += (parseInt(a.seg)||0);
      else if(t.indexOf('PAUSED')>=0) totalPau += (parseInt(a.seg)||0);
    });
    html += '<div class="msec"><div class="msec-t" style="display:flex;justify-content:space-between;align-items:center">🕐 Timeline de execução';
    if(mttrLabel) html += '<span style="background:#dcfce7;color:#166534;font-size:10.5px;font-weight:700;padding:3px 9px;border-radius:8px;letter-spacing:.3px">⏱ MTTR ' + mttrLabel + '</span>';
    html += '</div>';
    html += '  <div class="mtl-resumo"><b>'+_fmtDurTL(totalRun)+'</b> ativos · <b>'+_fmtDurTL(totalPau)+'</b> em pausas · <b>'+osRow.historico.length+'</b> evento'+(osRow.historico.length!==1?'s':'')+'</div>';
    html += '  <div class="mtimeline">';
    osRow.historico.forEach(a=>{
      const mp=_mapaTipo(a.tipo);
      html += '<div class="mtl-item">';
      html += '  <div class="mtl-dot '+mp.cls+'"></div>';
      html += '  <div class="mtl-t '+mp.cls+'">'+mp.icone+' '+mp.label+'</div>';
      html += '  <div class="mtl-d">'+_fmtDtHora(a.ini)+' → '+_fmtDtHora(a.fim)+' · <b>'+_fmtDurTL(a.seg)+'</b>'+(a.usuario?(' · '+_esc(a.usuario)):'')+'</div>';
      if(a.motivo) html += '  <div class="mtl-m">↳ '+_esc(a.motivo)+'</div>';
      html += '</div>';
    });
    html += '  </div>';
    html += '</div>';
  } else {
    // Task #146: Timeline visual a partir das datas básicas (criada/programada/iniciada/finalizada)
    const dIni = parseDt(osRow.dataInicial||osRow.data_inicial);
    const eventos = [];
    // Ordem semântica fixa (task #150) — independe da data
    if(dCria) eventos.push({d:dCria, label:'Criada', icone:'➕', cls:'run', ord:1});
    if(dProg) eventos.push({d:dProg, label:'Programada', icone:'📅', cls:'run', ord:2});
    if(dIni)  eventos.push({d:dIni,  label:'Iniciada',   icone:'▶', cls:'run', ord:3});
    if(osRow.statusPai && /verifica/i.test(osRow.statusPai) && !dFim){
      eventos.push({d:new Date(), label:'Em Verificação', icone:'⏳', cls:'pau', pendente:true, ord:4});
    }
    if(dFim)  eventos.push({d:dFim,  label:'Finalizada', icone:'✔', cls:'fim', ord:5});
    if(eventos.length){
      eventos.sort((a,b)=>a.ord-b.ord);
      function _fmtDur(ms){
        const s=Math.floor(ms/1000); if(s<60)return s+'s';
        const m=Math.floor(s/60); if(m<60)return m+'min';
        const h=Math.floor(m/60); if(h<24)return h+'h '+(m%60)+'min';
        return Math.floor(h/24)+'d '+(h%24)+'h';
      }
      function _fmtIso(d){
        if(!d) return '';
        return ('0'+d.getDate()).slice(-2)+'/'+('0'+(d.getMonth()+1)).slice(-2)+' '+('0'+d.getHours()).slice(-2)+':'+('0'+d.getMinutes()).slice(-2);
      }
      html += '<div class="msec"><div class="msec-t" style="display:flex;justify-content:space-between;align-items:center">🕐 Linha do tempo';
      if(mttrLabel) html += '<span style="background:#dcfce7;color:#166534;font-size:10.5px;font-weight:700;padding:3px 9px;border-radius:8px;letter-spacing:.3px">⏱ MTTR ' + mttrLabel + '</span>';
      html += '</div>';
      html += '  <div class="mtimeline">';
      eventos.forEach((e,i)=>{
        const delta = i>0 ? ' <span style="color:#94a3b8">(+'+_fmtDur(e.d - eventos[i-1].d)+')</span>' : '';
        html += '<div class="mtl-item">';
        html += '  <div class="mtl-dot '+e.cls+'"></div>';
        html += '  <div class="mtl-t '+e.cls+'">'+e.icone+' '+e.label+(e.pendente?' (aguardando)':'')+'</div>';
        html += '  <div class="mtl-d">'+_fmtIso(e.d)+delta+'</div>';
        html += '</div>';
      });
      html += '  </div>';
      html += '</div>';
    }
  }
  // SEÇÃO 3: Detalhes operacionais
  html += '<div class="msec"><div class="msec-t">⚙ Detalhes operacionais</div>';
  html += '  <div class="mgrid">';
  if(osRow.h_ini) html += '<div class="mkv"><span class="mkv-k">Início Previsto</span><span class="mkv-v">'+_esc(osRow.h_ini)+'</span></div>';
  if(osRow.h_fim) html += '<div class="mkv"><span class="mkv-k">Fim Previsto</span><span class="mkv-v">'+_esc(osRow.h_fim)+'</span></div>';
  if(osRow.duracao) html += '<div class="mkv"><span class="mkv-k">Duração</span><span class="mkv-v">'+osRow.duracao+'h</span></div>';
  if(osRow.completed_pct!=null || osRow.completed_percentage!=null) html += '<div class="mkv"><span class="mkv-k">% Concluída</span><span class="mkv-v">'+(osRow.completed_pct||osRow.completed_percentage||0)+'%</span></div>';
  if(osRow.reprog) html += '<div class="mkv"><span class="mkv-k">Reprogramada</span><span class="mkv-v">'+_esc(osRow.reprog)+'</span></div>';
  if(osRow.nova_os) html += '<div class="mkv"><span class="mkv-k">Nova OS</span><span class="mkv-v">'+_esc(osRow.nova_os)+'</span></div>';
  if(osRow.codigo) html += '<div class="mkv"><span class="mkv-k">Código</span><span class="mkv-v">'+_esc(osRow.codigo)+'</span></div>';
  if(osRow.etiquetas) html += '<div class="mkv"><span class="mkv-k">Etiquetas</span><span class="mkv-v">'+_esc(osRow.etiquetas)+'</span></div>';
  html += '  </div>';
  html += '</div>';
  // Outras tarefas da mesma OS
  if(osLista && osLista.length > 1){
    html += '<div class="msec"><div class="msec-t">Outras tarefas desta OS</div>';
    osLista.forEach(o=>{
      if(o===osRow) return;
      const stat=(o.status_bd||o.status||'')||'';
      const stClass=stat.toLowerCase().indexOf('finaliz')>=0?'#16a34a':stat.toLowerCase().indexOf('progress')>=0?'#3b82f6':stat.toLowerCase().indexOf('paus')>=0?'#f59e0b':'#94a3b8';
      html += '<div style="font-size:10.5px;padding:6px 0;color:#475569;display:flex;justify-content:space-between;gap:8px;border-bottom:1px dashed #e5e7eb">'
        + '<span><b>'+_esc(o.h_ini||'')+'</b> · '+_esc((o.tarefa||'').substring(0,80))+'</span>'
        + '<span style="white-space:nowrap"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:'+stClass+';margin-right:4px"></span>'+_esc(stat||'--')+' · ('+(o.duracao||0)+'h)</span>'
        + '</div>';
    });
    html += '</div>';
  }
  // --- Reprogramar (somente PCM/admin) — vale p/ OS já programada ---
  if(RP_OK && osRow.os_id){
    const _oid=String(osRow.os_id);
    const _tks=(osLista&&osLista.length?osLista:[osRow]);
    const _dias=[['','dia…'],['seg','seg'],['ter','ter'],['qua','qua'],['qui','qui'],['sex','sex']];
    const _tur=[['','turno…'],['manhã','manhã'],['tarde','tarde'],['noite','noite']];
    const _op=(o)=>o.map(x=>'<option value="'+x[0]+'">'+x[1]+'</option>').join('');
    html += '<div class="msec"><div class="msec-t">🔄 Reprogramar</div>';
    html += '<div class="rpm-box">';
    if(_tks.length>1){
      html += '<select id="rpm-alvo"><option value="" data-tipo="">A OS inteira ('+_tks.length+' tarefas)</option>'
           + _tks.map(t=>'<option value="'+_esc(String(t.tarefa||'').replace(/"/g,'&quot;'))+'" data-tipo="'+_esc(t.tipo||'')+'">'
             + _esc(String(t.tarefa||'').slice(0,52))+'</option>').join('') + '</select>';
    } else {
      html += '<input type="hidden" id="rpm-alvo" value="">';
    }
    html += '<select id="rpm-dia">'+_op(_dias)+'</select>'
         +  '<select id="rpm-turno">'+_op(_tur)+'</select>'
         +  '<button class="rp-add" onclick="rpAddModal(\''+_esc(_oid)+'\')">+ Inserir</button>'
         +  '<button class="rp-out" onclick="rpTirar(\''+_esc(_oid)+'\','+_tks.length+')">✕ Tirar da semana</button>';
    html += '</div><div class="rpm-status" id="rpm-status">Escolha o dia e clique <b>+ Inserir</b> para mover, '
         +  'ou <b>✕ Tirar da semana</b> para remover a OS. A linha entra na fila — copie na barra verde do rodapé '
         +  'e cole no PCM_Painel.</div></div>';
  }
  // Ações
  const link = osRow.linkFracttal || (osRow.os_id ? ('https://app.fracttal.com/oneview/general/items?folio='+osRow.os_id) : '');
  if(link){
    html += '<div class="mactions"><a href="'+link+'" target="_blank" rel="noopener" class="mbtn mbtn-prim" style="text-decoration:none">🔗 Abrir no Fracttal</a></div>';
  }
  mbox.innerHTML = html;
  document.getElementById('modal').classList.add('open');
}

function closeMod(){
  document.getElementById('modal').classList.remove('open');
}

document.addEventListener('keydown', e=>{
  if(e.key==='Escape') closeMod();
});

// ── GESTÃO PCM (via API Fracttal — gestao_pcm.json) ───────────────────────────
let GESTAO_DB=null;
const GP={};            // estado dos filtros/dados renderizados
let GP_TIP_DATA=[];     // tarefas por nó de tipo (lazy render)

async function loadGestao(){
  try{
    const res=await fetch(CONFIG.GESTAO_URL,{cache:'no-store'});
    if(!res.ok){GESTAO_DB=null;return false;}
    GESTAO_DB=await res.json();
    return true;
  }catch(e){GESTAO_DB=null;return false;}
}
function gpEsc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function gpFmtData(iso){if(!iso)return '—';const p=String(iso).split('-');return p.length===3?p[2]+'/'+p[1]+'/'+p[0]:iso;}
function gpWoUrl(t){const tpl=CONFIG.GESTAO_WO_URL||'';if(!tpl)return t.url||'';
  return tpl.replace('{id}',t.idWO!=null?t.idWO:'').replace('{folio}',t.os!=null?t.os:'');}
function gpTipoClass(t){const x=(t||'').toLowerCase();
  if(x.indexOf('emergencial')>=0)return 't-emergencial';
  if(x.indexOf('corretiva')>=0)return 't-corretiva';
  if(x.indexOf('preventiva')>=0)return 't-preventiva';
  if(x.indexOf('handover')>=0)return 't-handover';
  if(x.indexOf('religa')>=0)return 't-religamento';
  if(x.indexOf('inspe')>=0)return 't-inspecao';
  if(x.indexOf('predit')>=0)return 't-preditiva';
  if(x.indexOf('admin')>=0)return 't-administrativa';
  return 't-outra';}
function gpEstadoPill(e){const x=(e||'').toLowerCase();
  let c='gp-e-ni';
  if(x.indexOf('progress')>=0)c='gp-e-em';
  else if(x.indexOf('paus')>=0)c='gp-e-pau';
  else if(x.indexOf('finaliz')>=0)c='gp-e-fin';
  return '<span class="gp-pill '+c+'">'+gpEsc(e||'—')+'</span>';}
function gpDiasCell(t){
  if(!t.aberta||t.dias==null||t.dias<0)return '<span class="gp-dias ok">—</span>';
  const cls=t.dias>(GESTAO_DB.diasAlerta||10)?'red':(t.dias>=5?'amber':'ok');
  return '<span class="gp-dias '+cls+'">'+t.dias+'d</span>';}
// respeita o escopo: não-admin vê só o próprio cliente
function gpScopedTarefas(){
  const all=(GESTAO_DB&&GESTAO_DB.tarefas)||[];
  // esconde tarefas sem Classificação 1 (ativos "TESTE"/não classificados)
  let arr=all.filter(t=>t.usina && t.usina!=='(sem usina)' && t.cliente && t.cliente!=='(sem cliente)' && (t.cliente||'').toLowerCase()!=='usina teste');
  if(S.isAdmin||!S.user)return arr;
  return arr.filter(t=>_cliEq(t.cliente,S.user));
}
// ── Filtros multi-seleção (checkboxes) ────────────────────────────────────
// key -> {f: campo da tarefa, lbl: rótulo "vazio"}
const GP_MS={cliente:{f:'cliente',lbl:'Todos'},usina:{f:'usina',lbl:'Todas'},
  cluster:{f:'cluster',lbl:'Todos'},resp:{f:'responsavel',lbl:'Todos'},
  tipo:{f:'tipo',lbl:'Todos'},etq:{f:'etiquetas',lbl:'Todas'},estado:{f:'estado',lbl:'Todos'}};
const GP_SEL={cliente:new Set(),usina:new Set(),cluster:new Set(),resp:new Set(),tipo:new Set(),etq:new Set(),estado:new Set()};
function gpMsOptions(key){
  const fld=GP_MS[key].f, byLk=new Map();   // lowercase -> Map(grafia->contagem)
  gpScopedTarefas().forEach(t=>{const v=t[fld];
    (Array.isArray(v)?v:[v]).forEach(x=>{if(x){const s=String(x),lk=s.toLowerCase();
      let m=byLk.get(lk);if(!m){m=new Map();byLk.set(lk,m);} m.set(s,(m.get(s)||0)+1);}});});
  // dedupe case-insensitive: mantém a grafia MAIS FREQUENTE (ex.: PA Norte 01 vs PA NORTE 01)
  const canon=new Map();
  byLk.forEach((m,lk)=>{let best=null,bn=-1;m.forEach((n,s)=>{if(n>bn){bn=n;best=s;}});canon.set(lk,best);});
  const validLk=new Set(canon.keys());
  [...GP_SEL[key]].forEach(v=>{if(!validLk.has(String(v).toLowerCase()))GP_SEL[key].delete(v);});
  return [...canon.values()].sort((a,b)=>a.localeCompare(b,'pt-BR'));
}
function gpMsLabel(key){
  const s=GP_SEL[key],el=document.getElementById('gp-ms-lbl-'+key);if(!el)return;
  if(s.size===0){el.textContent=GP_MS[key].lbl;el.classList.remove('sel');}
  else if(s.size===1){el.textContent=[...s][0];el.classList.add('sel');}
  else{el.textContent=s.size+' selecionados';el.classList.add('sel');}
}
function gpBuildPop(key){
  const pop=document.getElementById('gp-ms-pop-'+key);if(!pop)return;
  const opts=gpMsOptions(key);
  let h='<div class="gp-ms-top"><input class="gp-ms-search" placeholder="buscar…" oninput="gpMsSearch(\''+key+'\',this.value)">'
      +'<div class="gp-ms-acts"><a onclick="gpMsAll(\''+key+'\')">Todos</a><a onclick="gpMsNone(\''+key+'\')">Limpar</a></div></div><div class="gp-ms-opts">';
  h+=opts.map(v=>{const e=gpEsc(v);return '<label class="gp-ms-opt"><input type="checkbox"'+(GP_SEL[key].has(v)?' checked':'')+' value="'+e+'" onchange="gpMsCheck(\''+key+'\',this)"><span>'+e+'</span></label>';}).join('')||'<div class="gp-ms-empty">—</div>';
  return pop.innerHTML=h+'</div>';
}
function gpPopulateFilters(){Object.keys(GP_MS).forEach(k=>{gpBuildPop(k);gpMsLabel(k);});}
function gpMsToggle(key){
  const box=document.getElementById('gp-ms-'+key),open=box.classList.contains('open');
  document.querySelectorAll('.gp-ms.open').forEach(b=>b.classList.remove('open'));
  if(!open){gpBuildPop(key);box.classList.add('open');}
}
function gpMsCheck(key,cb){if(cb.checked)GP_SEL[key].add(cb.value);else GP_SEL[key].delete(cb.value);gpMsLabel(key);renderGestao(false);}
function gpMsAll(key){gpMsOptions(key).forEach(v=>GP_SEL[key].add(v));gpBuildPop(key);gpMsLabel(key);renderGestao(false);}
function gpMsNone(key){GP_SEL[key].clear();gpBuildPop(key);gpMsLabel(key);renderGestao(false);}
function gpMsSearch(key,q){q=(q||'').toLowerCase();document.querySelectorAll('#gp-ms-pop-'+key+' .gp-ms-opt').forEach(l=>{l.style.display=l.textContent.toLowerCase().indexOf(q)>=0?'':'none';});}
document.addEventListener('click',e=>{if(!e.target.closest('.gp-ms'))document.querySelectorAll('.gp-ms.open').forEach(b=>b.classList.remove('open'));});
function gpVal(id){const el=document.getElementById(id);return el?el.value.trim():'';}
function gpFilteredTarefas(){
  const S1=GP_SEL,fOS=gpVal('gp-f-os').toLowerCase(),fSS=gpVal('gp-f-ss').toLowerCase(),
        pIni=gpVal('gp-f-pini'),pFim=gpVal('gp-f-pfim'),pMod=gpVal('gp-f-pmodo')||'qq';
  // Período: a tarefa entra se QUALQUER uma das datas (programada, início ou
  // final) cair na faixa. O seletor "considerar" restringe a uma delas quando
  // a pergunta é específica (ex.: "o que FINALIZEI em julho").
  const _d=v=>v?String(v).slice(0,10):'';
  const _dentro=v=>{const d=_d(v); if(!d)return false;
    if(pIni&&d<pIni)return false; if(pFim&&d>pFim)return false; return true;};
  const noPeriodo=t=>{
    if(!pIni&&!pFim)return true;
    if(pMod==='prog')return _dentro(t.dataProg);
    if(pMod==='ini') return _dentro(t.dataInicio);
    if(pMod==='fim') return _dentro(t.dataFinal);
    return _dentro(t.dataProg)||_dentro(t.dataInicio)||_dentro(t.dataFinal);
  };
  // Matches case-insensitive (grafias divergem no Fracttal: "PA NORTE 01" vs "PA Norte 01")
  const _L=s=>new Set([...s].map(x=>String(x).toLowerCase())), _in=(set,v)=>set.has(String(v||'').toLowerCase());
  const Lcli=_L(S1.cliente),Lusi=_L(S1.usina),Lclu=_L(S1.cluster),Lres=_L(S1.resp),Ltip=_L(S1.tipo),Lest=_L(S1.estado),Letq=_L(S1.etq);
  return gpScopedTarefas().filter(t=>{
    if(S1.cliente.size&&!_in(Lcli,t.cliente))return false;
    if(S1.usina.size&&!_in(Lusi,t.usina))return false;
    if(S1.cluster.size&&!_in(Lclu,t.cluster))return false;
    if(S1.resp.size&&!_in(Lres,t.responsavel))return false;
    if(S1.tipo.size&&!_in(Ltip,t.tipo))return false;
    if(S1.estado.size&&!_in(Lest,t.estado))return false;
    if(S1.etq.size&&!(t.etiquetas||[]).some(e=>_in(Letq,e)))return false;
    if(fOS&&String(t.os).toLowerCase().indexOf(fOS)<0)return false;
    if(fSS&&String(t.ss).toLowerCase().indexOf(fSS)<0)return false;
    if(!noPeriodo(t))return false;
    return true;
  });
}
// Tarefa "não finalizada no período": OS já finalizada, mas a tarefa ficou
// com estado em aberto (Não Iniciada / Em progresso / Pausada).
function gpNaoFin(t){ return t.osStatus==='Finalizados' && t.aberta; }
// Monta a árvore Cliente ▸ Usina ▸ Tipo (reutilizável p/ árvore principal e p/
// o dropdown "Não Finalizadas no Período"). Empilha as listas em GP_TIP_DATA.
function gpTreeHTML(arr, autoOpen){
  const tree={};
  arr.forEach(t=>{
    (((tree[t.cliente]=tree[t.cliente]||{usinas:{},n:0}).usinas[t.usina]=tree[t.cliente].usinas[t.usina]||{tipos:{},n:0}).tipos[t.tipo]=tree[t.cliente].usinas[t.usina].tipos[t.tipo]||[]).push(t);
    tree[t.cliente].n++;tree[t.cliente].usinas[t.usina].n++;
  });
  const cntAtr=(list)=>list.filter(t=>t.atrasado).length;
  const chipAtr=(k)=>k>0?' <span class="gp-badge-t" style="background:#d94f3d;color:#fff">⏱ '+k+'</span>':'';
  let html='';
  Object.keys(tree).sort((a,b)=>a.localeCompare(b,'pt-BR')).forEach(cli=>{
    const C=tree[cli];
    html+='<div class="gp-cli'+(autoOpen?' gp-open':'')+'"><div class="gp-cli-h" onclick="gpTog(this)"><span class="nm">'+gpEsc(cli)+'</span><span style="display:flex;align-items:center;gap:8px"><span class="gp-badge">'+C.n+'</span><span class="gp-chev">▾</span></span></div><div class="gp-cli-b">';
    Object.keys(C.usinas).sort((a,b)=>a.localeCompare(b,'pt-BR')).forEach(usi=>{
      const U=C.usinas[usi];
      html+='<div class="gp-usi'+(autoOpen?' gp-open':'')+'"><div class="gp-usi-h" onclick="gpTog(this)"><span class="nm">'+gpEsc(usi)+'</span><span style="display:flex;align-items:center;gap:8px"><span class="gp-badge-d">'+U.n+'</span><span class="gp-chev-s">▾</span></span></div><div class="gp-usi-b">';
      Object.keys(U.tipos).sort((a,b)=>a.localeCompare(b,'pt-BR')).forEach(tp=>{
        const list=U.tipos[tp].slice().sort((a,b)=>{const da=(a.aberta&&a.dias!=null)?a.dias:-1e9,db=(b.aberta&&b.dias!=null)?b.dias:-1e9;return db-da;});
        const idx=GP_TIP_DATA.push(list)-1;
        html+='<div class="gp-tip '+gpTipoClass(tp)+(autoOpen?' gp-open':'')+'"><div class="gp-tip-h" onclick="gpTogTip(this,'+idx+')"><span class="nm">'+gpEsc(tp)+'</span><span style="display:flex;align-items:center;gap:6px"><span class="gp-badge-t">'+list.length+'</span>'+chipAtr(cntAtr(list))+'<span class="gp-chev-s">▾</span></span></div><div class="gp-tip-b" data-filled="0" data-idx="'+idx+'"></div></div>';
      });
      html+='</div></div>';
    });
    html+='</div></div>';
  });
  return html;
}
function renderGestao(rebuildFilters){
  const box=document.getElementById('gp-tree');
  if(!box)return;
  if(!GESTAO_DB){box.innerHTML='<div class="gp-nores">Não foi possível carregar gestao_pcm.json.</div>';
    document.getElementById('gp-sub').textContent='Falha ao carregar';return;}
  if(rebuildFilters!==false)gpPopulateFilters();else Object.keys(GP_MS).forEach(gpMsLabel);
  document.getElementById('gp-sub').textContent='Atualizado: '+new Date(GESTAO_DB.geradoEm||Date.now()).toLocaleString('pt-BR')+' · corte '+gpFmtData(GESTAO_DB.corteData)+' · fonte: API Fracttal';
  const all=gpFilteredTarefas();
  const nf=all.filter(gpNaoFin);                 // não finalizadas no período (à parte)
  const arr=all.filter(t=>!gpNaoFin(t));         // árvore principal
  const ab=arr.filter(t=>t.aberta), atr=ab.filter(t=>t.atrasado);
  // Finalizadas = Estado da Tarefa 'Finalizada' (aberta=false no gerador).
  // Vale a identidade: Visíveis = Finalizadas + Em aberto.
  const fin=arr.length-ab.length;
  document.getElementById('gp-k-vis').textContent=arr.length;
  document.getElementById('gp-k-ab').textContent=ab.length;
  document.getElementById('gp-k-atr').textContent=atr.length;
  const _fin=document.getElementById('gp-k-fin');
  if(_fin){
    _fin.textContent=fin;
    const pct=arr.length?Math.round(fin/arr.length*100):0;
    document.getElementById('gp-kpi-fin').title=
      'Estado da Tarefa = Finalizada · '+pct+'% do que está visível'
      +(nf.length?' (as '+nf.length+' de "Não Finalizadas no Período" ficam fora desta conta)':'');
  }
  const badge=document.getElementById('tcnt-gestaoPcm');if(badge)badge.textContent=ab.length;
  // Sincroniza visual do modo "só atrasadas"
  const _tg=document.getElementById('gp-atr-toggle');if(_tg)_tg.classList.toggle('on',!!GP.soAtrasadas);
  const _kp=document.getElementById('gp-kpi-atr');if(_kp)_kp.classList.toggle('active',!!GP.soAtrasadas);
  renderConfiab();   // dropdown de confiabilidade (independente do modo da árvore)
  renderMttrCluster();   // dropdown de MTTR por equipe cluster
  // Modo "só atrasadas": lista plana ordenada por dias em aberto (mais velhas no topo)
  if(GP.soAtrasadas){box.innerHTML=gpFlatHTML(atr);return;}
  if(!all.length){box.innerHTML='<div class="gp-nores">Nenhuma tarefa para os filtros selecionados.</div>';return;}
  GP_TIP_DATA=[];
  let html='';
  // Dropdown separado: "Não Finalizadas no Período"
  if(nf.length){
    html+='<div class="gp-nf"><div class="gp-nf-h" onclick="gpTog(this)"><span class="nm">&#9888;&#65039; Não Finalizadas no Per&iacute;odo</span>'
      +'<span style="display:flex;align-items:center;gap:8px"><span class="gp-nf-badge">'+nf.length+'</span><span class="gp-chev">▾</span></span></div>'
      +'<div class="gp-nf-b">'+gpTreeHTML(nf,false)+'</div></div>';
  }
  // Árvore principal
  const mainHtml=gpTreeHTML(arr, arr.length<=60);
  html+= mainHtml || (nf.length? '<div class="gp-nores" style="padding:18px">Sem tarefas na visão principal (só há não finalizadas no período).</div>' : '');
  box.innerHTML=html;
  box.querySelectorAll('.gp-tip.gp-open>.gp-tip-b').forEach(el=>gpFillTable(el));
}
// ── CONFIABILIDADE (MTBF/MTTR/Disponibilidade por ativo) ─────────────────────
let CONFIAB_DB=null;
async function loadConfiab(){
  try{const r=await fetch(CONFIG.CONFIAB_URL,{cache:'no-store'});
    if(!r.ok){CONFIAB_DB=null;return false;}CONFIAB_DB=await r.json();return true;
  }catch(e){CONFIAB_DB=null;return false;}
}
function cfNum(v,dec){return v==null?'—':Number(v).toLocaleString('pt-BR',{minimumFractionDigits:dec||0,maximumFractionDigits:dec||0});}
function cfDispCls(d){if(d==null)return 'cf-na';const p=d*100;return p>=95?'hi':(p>=90?'mid':'lo');}
function cfDispTxt(d){return d==null?'—':(d*100).toFixed(2)+'%';}
function cfChips(u){
  const lo=cfDispCls(u.disp)==='lo';
  return '<span class="cf-chip cf-mtbf"><span class="k">MTBF</span>'+cfNum(u.mtbf,0)+'h</span>'
    +'<span class="cf-chip cf-mttr"><span class="k">MTTR</span>'+cfNum(u.mttr,2)+'h</span>'
    +'<span class="cf-chip cf-disp'+(lo?' warn':'')+'"><span class="k">Disp</span>'+cfDispTxt(u.disp)+'</span>';
}
function cfTaskRows(a){
  if(!a.tarefas||!a.tarefas.length)return '<div class="cf-tk-row cf-na">Sem tarefas.</div>';
  return a.tarefas.map(t=>
    '<div class="cf-tk-row"><span class="os">#'+gpEsc(t.os)+'</span><span class="cf-tk">'+gpEsc(t.tarefa||'—')+'</span>'
    +'<span>'+gpEsc(t.tipo||'—')+'</span><span>'+gpFmtData(t.inicio)+'</span><span>'+gpFmtData(t.fim)+'</span>'
    +'<span class="hh">'+(t.horas==null?'—':String(t.horas).replace('.',',')+'h')+'</span></div>').join('');
}
function cfUsiHTML(u){
  const rows=(u.ativos||[]).map(a=>{
    const main='<tr class="cf-a-row" onclick="cfTogAtivo(this)"><td><span class="cf-a-cv">&#9656;</span>'
      +gpEsc(a.ativo)+'</td><td>'+cfNum(a.mtbf,0)+'</td><td>'+cfNum(a.mttr,2)+'</td>'
      +'<td class="cf-d '+cfDispCls(a.disp)+'">'+(a.disp==null?'<span class="cf-na">—</span>':cfDispTxt(a.disp))+'</td>'
      +'<td>'+a.n+'</td></tr>';
    const det='<tr class="cf-a-det"><td colspan="5"><div class="cf-a-det-in"><div class="cf-tk-list">'
      +'<div class="cf-tk-hd"><span>OS</span><span>Tarefa</span><span>Tipo</span>'
      +'<span>Início</span><span>Fim</span><span class="hh">Horas</span></div>'
      +cfTaskRows(a)+'</div></div></td></tr>';
    return main+det;
  }).join('');
  return '<div class="cf-usi"><div class="cf-usi-h" onclick="cfTogUsi(this)">'
    +'<span class="nm">'+gpEsc(u.usina)+'</span>'
    +'<span class="cf-metrics">'+cfChips(u)+'<span class="cf-chev-s">&#9662;</span></span></div>'
    +'<div class="cf-usi-b"><table class="cf-tbl"><thead><tr><th>Ativo</th><th>MTBF (h)</th>'
    +'<th>MTTR (h)</th><th>Disp. Inerente</th><th>Falhas</th></tr></thead><tbody>'+rows+'</tbody></table></div></div>';
}
function cfTogAtivo(tr){
  const det=tr.nextElementSibling;
  if(det&&det.classList.contains('cf-a-det')){tr.classList.toggle('open');det.classList.toggle('open');}
}
function renderConfiab(){
  const box=document.getElementById('gp-confiab');if(!box)return;
  if(!CONFIAB_DB||!CONFIAB_DB.clientes){box.innerHTML='';return;}
  let cls=CONFIAB_DB.clientes.slice();
  // Comparação case-insensitive: a grafia do cliente diverge entre fontes
  // (Gestão usa "Greenyellow/RenoGrid/Semp", AUXILIAR usa "GreenYellow/Renogrid/SEMP").
  const _selCli=new Set([...GP_SEL.cliente].map(x=>x.toLowerCase()));
  if(!S.isAdmin&&S.user)cls=cls.filter(c=>(c.cliente||'').toLowerCase()===S.user.toLowerCase());
  if(GP_SEL.cliente.size)cls=cls.filter(c=>_selCli.has((c.cliente||'').toLowerCase()));
  const wasOpen=(document.getElementById('cf-master')||{}).classList&&document.getElementById('cf-master').classList.contains('open');
  let inner='';
  cls.sort((a,b)=>a.cliente.localeCompare(b.cliente,'pt-BR')).forEach(c=>{
    let usinas=(c.usinas||[]).slice();
    if(GP_SEL.usina.size)usinas=usinas.filter(u=>GP_SEL.usina.has(u.usina));
    if(!usinas.length)return;
    usinas.sort((a,b)=>a.usina.localeCompare(b.usina,'pt-BR'));
    const totFalhas=usinas.reduce((s,u)=>s+(u.n||0),0);
    const usiHtml=usinas.map(cfUsiHTML).join('');
    inner+='<div class="cf-cli"><div class="cf-cli-h" onclick="cfTogCli(this)">'
      +'<span class="cnm">'+gpEsc(c.cliente)+'</span>'
      +'<span class="cf-metrics"><span class="cf-chip cf-count">'+usinas.length+' usinas</span>'
      +'<span class="cf-chip cf-count">'+totFalhas.toLocaleString('pt-BR')+' falhas</span>'
      +'<span class="cf-chev-s">&#9662;</span></span></div>'
      +'<div class="cf-cli-b">'+usiHtml+'</div></div>';
  });
  if(!inner){box.innerHTML='';return;}
  const upd=CONFIAB_DB.geradoEm?new Date(CONFIAB_DB.geradoEm).toLocaleString('pt-BR'):'';
  box.innerHTML='<div class="cf-wrap"><div class="cf-master'+(wasOpen?' open':'')+'" id="cf-master">'
    +'<div class="cf-master-h" onclick="cfTogMaster()"><div><div class="ttl">&#128202; Confiabilidade por ativo</div>'
    +'<div class="desc">MTBF &middot; MTTR &middot; Disponibilidade Inerente &mdash; por tarefa &middot; base: '+(CONFIAB_DB.tiposFalha||[]).join(', ')+' &middot; atualizado '+upd+'</div></div>'
    +'<span class="cf-chev">&#9662;</span></div><div class="cf-master-b">'+inner+'</div></div></div>';
}
function cfTogMaster(){const m=document.getElementById('cf-master');if(m)m.classList.toggle('open');}
function cfTogCli(h){h.parentElement.classList.toggle('open');}
function cfTogUsi(h){h.parentElement.classList.toggle('open');}

// ── MTTR por Equipe Cluster ──────────────────────────────────────────────────
function cfMttrCls(m){if(m==null)return 'cf-na';return m<=24?'hi':(m<=72?'mid':'lo');}
function renderMttrCluster(){
  const box=document.getElementById('gp-mttr-cluster');if(!box)return;
  if(!CONFIAB_DB||!CONFIAB_DB.clusters){box.innerHTML='';return;}
  let cs=CONFIAB_DB.clusters.slice();
  const _selCli=new Set([...GP_SEL.cliente].map(x=>x.toLowerCase()));   // grafia diverge entre fontes
  const _selClu=new Set([...GP_SEL.cluster].map(x=>x.toLowerCase()));
  if(!S.isAdmin&&S.user)cs=cs.filter(c=>(c.cliente||'').toLowerCase()===S.user.toLowerCase());
  if(GP_SEL.cliente.size)cs=cs.filter(c=>_selCli.has((c.cliente||'').toLowerCase()));
  if(GP_SEL.cluster.size)cs=cs.filter(c=>_selClu.has((c.cluster||'').toLowerCase()));
  const wasOpen=(document.getElementById('mc-master')||{}).classList&&document.getElementById('mc-master').classList.contains('open');
  let inner='';
  cs.forEach(c=>{
    const rows=(c.usinas||[]).map(u=>
      '<div class="mc-row"><span class="cf-tk">'+gpEsc(u.usina)+'</span>'
      +'<span class="cf-d '+cfMttrCls(u.mttr)+'">'+(u.mttr==null?'—':cfNum(u.mttr,2)+'h')+'</span>'
      +'<span class="hh">'+u.n+'</span></div>').join('');
    inner+='<div class="cf-usi"><div class="cf-usi-h" onclick="cfTogUsi(this)">'
      +'<span class="nm">'+gpEsc(c.cluster)+'<span class="cli">'+gpEsc(c.cliente)+'</span></span>'
      +'<span class="cf-metrics"><span class="cf-chip cf-mttr"><span class="k">MTTR</span>'+(c.mttr==null?'—':cfNum(c.mttr,2)+'h')+'</span>'
      +'<span class="cf-chip cf-count">'+(c.n||0).toLocaleString('pt-BR')+' falhas</span>'
      +'<span class="cf-chev-s">&#9662;</span></span></div>'
      +'<div class="cf-usi-b"><div class="mc-list"><div class="mc-hd"><span>Usina</span><span>MTTR</span>'
      +'<span class="hh">Falhas</span></div>'+rows+'</div></div></div>';
  });
  if(!inner){box.innerHTML='';return;}
  const upd=CONFIAB_DB.geradoEm?new Date(CONFIAB_DB.geradoEm).toLocaleString('pt-BR'):'';
  box.innerHTML='<div class="cf-wrap"><div class="cf-master'+(wasOpen?' open':'')+'" id="mc-master">'
    +'<div class="cf-master-h" onclick="mcTogMaster()"><div><div class="ttl">&#128295; Tempo médio de reparo por Equipe Cluster</div>'
    +'<div class="desc">MTTR por cluster (equipe) &mdash; piores no topo &middot; por tarefa &middot; verde &le;24h, amarelo &le;72h, vermelho &gt;72h &middot; atualizado '+upd+'</div></div>'
    +'<span class="cf-chev">&#9662;</span></div><div class="cf-master-b">'+inner+'</div></div></div>';
}
function mcTogMaster(){const m=document.getElementById('mc-master');if(m)m.classList.toggle('open');}

// Lista plana das atrasadas, ordenada por dias em aberto (mais velhas no topo).
function gpFlatHTML(list){
  const lim=(GESTAO_DB&&GESTAO_DB.diasAlerta)||10;
  const arr=list.slice().sort((a,b)=>((b.dias||0)-(a.dias||0)));
  if(!arr.length)return '<div class="gp-nores" style="padding:22px">&#127881; Nenhuma tarefa atrasada nos filtros atuais.</div>';
  let h='<div class="gp-flat-hd">&#9201; Atrasadas <span class="cnt">'+arr.length+'</span>'
      +'<span class="hint">ordenadas por tempo em aberto &middot; vermelho = mais de '+lim+' dias</span></div>';
  h+='<table class="gp-flat"><thead><tr><th>Dias</th><th>OS</th><th>Cliente</th><th>Usina</th>'
     +'<th>Tarefa</th><th>Tipo</th><th>Estado</th><th>Data Prog.</th></tr></thead><tbody>';
  arr.forEach(t=>{
    const d=(t.dias!=null?t.dias:0);
    const cls=d>lim?'red':(d>=5?'amber':'');
    const crit=d>lim?' class="crit"':'';
    const _u=gpWoUrl(t);
    const tar=_u?('<a href="'+gpEsc(_u)+'" target="_blank" rel="noopener" title="Abrir no Fracttal">'+gpEsc(t.tarefa||'—')+'</a>'):gpEsc(t.tarefa||'—');
    h+='<tr'+crit+'><td class="dd '+cls+'">'+d+'d</td><td class="os">#'+gpEsc(t.os)+'</td>'
      +'<td>'+gpEsc(t.cliente)+'</td><td>'+gpEsc(t.usina)+'</td><td>'+tar+'</td>'
      +'<td>'+gpEsc(t.tipo||'—')+'</td><td>'+gpEstadoPill(t.estado)+'</td>'
      +'<td class="gp-data">'+gpFmtData(t.dataProg)+'</td></tr>';
  });
  return h+'</tbody></table>';
}
function gpToggleAtrasadas(){GP.soAtrasadas=!GP.soAtrasadas;renderGestao(false);}
function gpTableHTML(list){
  let h='<table class="gp-tbl"><thead><tr><th>OS ID</th><th>Tarefa</th><th>Estado</th><th>Etiquetas</th><th>Data Prog.</th><th>Data Final</th><th>Dias</th></tr></thead><tbody>';
  list.forEach(t=>{
    const etq=(t.etiquetas||[]).slice(0,3).map(e=>'<span class="gp-etq">'+gpEsc(e)+'</span>').join('')+((t.etiquetas||[]).length>3?'<span class="gp-etq">+'+((t.etiquetas.length-3))+'</span>':'');
    const _u=gpWoUrl(t);
    const tarefa=_u?('<a href="'+gpEsc(_u)+'" target="_blank" rel="noopener" title="Abrir no Fracttal">'+gpEsc(t.tarefa||'—')+'</a>'):gpEsc(t.tarefa||'—');
    h+='<tr><td><span class="gp-os">#'+gpEsc(t.os)+'</span></td><td class="gp-tarefa">'+tarefa+'</td><td>'+gpEstadoPill(t.estado)+'</td><td><div class="gp-etqs">'+(etq||'<span class="gp-data">—</span>')+'</div></td><td class="gp-data">'+gpFmtData(t.dataProg)+'</td><td class="gp-data">'+gpFmtData(t.dataFinal)+'</td><td>'+gpDiasCell(t)+'</td></tr>';
  });
  return h+'</tbody></table>';
}
function gpFillTable(bodyEl){
  if(!bodyEl||bodyEl.getAttribute('data-filled')==='1')return;
  const idx=parseInt(bodyEl.getAttribute('data-idx'),10);
  bodyEl.innerHTML=gpTableHTML(GP_TIP_DATA[idx]||[]);
  bodyEl.setAttribute('data-filled','1');
}
function gpTog(h){h.parentElement.classList.toggle('gp-open');}
function gpTogTip(h,idx){
  const blk=h.parentElement;const willOpen=!blk.classList.contains('gp-open');
  blk.classList.toggle('gp-open');
  if(willOpen)gpFillTable(blk.querySelector('.gp-tip-b'));
}
function gpOnFilter(){renderGestao();}
function gpClear(){GP.soAtrasadas=false;Object.keys(GP_SEL).forEach(k=>GP_SEL[k].clear());['gp-f-os','gp-f-ss','gp-f-pini','gp-f-pfim'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});const md=document.getElementById('gp-f-pmodo');if(md)md.value='qq';renderGestao(true);}

// FIX #159: carrega supervisores.json no boot
loadSupervisores().then(()=>{ if(typeof buildFilters==='function' && S.user) buildFilters(); });
Promise.all([loadGestao(),loadConfiab()]).then(()=>{ if(S.user && S.topView==='gestaoPcm') renderGestao(); });
