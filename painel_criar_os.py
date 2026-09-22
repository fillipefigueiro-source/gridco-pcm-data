# -*- coding: utf-8 -*-
"""
painel_criar_os.py — Painel Streamlit local pra criar OS no Fracttal a partir
de Solicitações de Serviço pendentes.

Lê:
- Solicitações pendentes via Fracttal API REST (`requests`)
- Sugestões automáticas do PCM (`Sugestoes_PCM.xlsx`) para pré-preenchimento
- Lista de responsáveis (`personnel`) do Fracttal

Cria OT corretiva via `tasks/noscheduled` (endpoint REST do Fracttal).

Uso:
    streamlit run painel_criar_os.py
ou abrir `iniciar_painel_os.bat`
"""
from __future__ import annotations
import os, sys, json
import datetime as dt
from pathlib import Path
from typing import Optional

import streamlit as st
import pandas as pd

# Reusa o cliente do gerar_bd_via_api
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from gerar_bd_via_api import FracttalClient, CLIENT_ID, CLIENT_SECRET, BASE_URL
except Exception as e:
    st.error(f"Falha ao importar FracttalClient: {e}")
    st.stop()


# ────────────────────────────────────────────────────────────────────
# Configuração
# ────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Grid Co. — Criador de OS",
                   page_icon="🛠", layout="wide")

PASTA = Path(__file__).resolve().parent
SUGESTOES_PATH = PASTA / "Sugestoes_PCM.xlsx"

CRIT_MAP_PT = {"VERY_HIGH": "Muito alta", "HIGH": "Alta",
               "MEDIUM": "Média", "LOW": "Baixa", "VERY_LOW": "Muito baixa"}
CRIT_TO_ID = {"VERY_HIGH": 1, "HIGH": 2, "MEDIUM": 3, "LOW": 4, "VERY_LOW": 5,
              "Muito alta": 1, "Alta": 2, "Média": 3, "Baixa": 4, "Muito baixa": 5}
DIA_TO_OFFSET = {"Segunda-feira": 0, "Terça-feira": 1, "Quarta-feira": 2,
                 "Quinta-feira": 3, "Sexta-feira": 4, "Sábado": 5, "Domingo": 6}


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_client():
    c = FracttalClient(CLIENT_ID, CLIENT_SECRET, BASE_URL)
    c.autenticar()
    return c


@st.cache_data(ttl=300)
def carregar_solicitacoes_pendentes():
    """Lista solicitações abertas (status 1, 2, 7, 8) sem OS criada."""
    client = get_client()
    rows = []
    for item in client.paginar("requests", page_size=100):
        if item.get("id_status") not in (1, 2, 7, 8):
            continue
        wo = item.get("wo_folio")
        if wo and str(wo).strip() not in ("", "0"):
            continue
        rows.append(item)
    return rows


@st.cache_data(ttl=600)
def carregar_sugestoes_pcm():
    """Lê Sugestoes_PCM.xlsx — map num_solicitacao → dict(equipe, dia, hora, dur, score, rpn)."""
    if not SUGESTOES_PATH.exists():
        return {}
    try:
        df = pd.read_excel(SUGESTOES_PATH)
    except Exception:
        return {}
    out = {}
    for _, r in df.iterrows():
        num = r.get("Nº Solicitação")
        if pd.isna(num):
            continue
        out[int(num)] = {
            "equipe": r.get("Equipe") or "",
            "dia": r.get("Dia Sugerido") or "",
            "hora": r.get("Hora Início Sugerida") or "",
            "duracao": r.get("Duração (h)") or 1.0,
            "score": r.get("Score") or 0,
            "rpn": r.get("RPN") or 0,
            "categoria": r.get("Categoria RPN") or "",
            "status_pcm": r.get("Status no PCM") or "",
            "observacao": r.get("Observação") or "",
        }
    return out


@st.cache_data(ttl=600)
def carregar_responsaveis():
    """Lista personnel ativos da empresa."""
    client = get_client()
    rows = []
    try:
        for item in client.paginar("personnel", page_size=100):
            if item.get("active") is False:
                continue
            full_name = (item.get("description") or item.get("full_name")
                         or f"{item.get('first_name','')} {item.get('last_name','')}").strip()
            if not full_name:
                continue
            rows.append({"id": item.get("id"), "nome": full_name})
    except Exception:
        pass
    rows.sort(key=lambda x: x["nome"])
    return rows


def proxima_data_do_dia(nome_dia: str) -> dt.date:
    """Calcula próxima ocorrência do dia da semana (ex: 'Quinta-feira') a partir de hoje."""
    if not nome_dia or nome_dia not in DIA_TO_OFFSET:
        return dt.date.today() + dt.timedelta(days=1)
    alvo = DIA_TO_OFFSET[nome_dia]
    hoje = dt.date.today()
    delta = (alvo - hoje.weekday()) % 7
    if delta == 0:
        delta = 7  # próxima ocorrência se hoje for o mesmo dia
    return hoje + dt.timedelta(days=delta)


def parse_hora(s: str) -> dt.time:
    """'07:30' → time(7,30)."""
    try:
        h, m = str(s).split(":")[:2]
        return dt.time(int(h), int(m))
    except Exception:
        return dt.time(7, 30)


def iso_utc(d: dt.datetime) -> str:
    """ISO 8601 UTC com milisegundos."""
    if d.tzinfo is None:
        # Assume horário local de Brasília (UTC-3)
        d = d.replace(tzinfo=dt.timezone(dt.timedelta(hours=-3)))
    d_utc = d.astimezone(dt.timezone.utc)
    return d_utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d_utc.microsecond // 1000:03d}Z"


def criar_os_fracttal(payload: dict) -> tuple[bool, str]:
    """Chama tasks/noscheduled via cliente Fracttal. Retorna (sucesso, mensagem)."""
    client = get_client()
    try:
        path = client._resolver_path("tasks_noscheduled") if hasattr(client, "_resolver_path") else None
        # Tenta endpoints conhecidos
        candidatos = ["tasks/noscheduled", "tasks_noscheduled"]
        for ep in candidatos:
            try:
                url = client.base_url.rstrip("/") + "/" + ep.lstrip("/")
                resp = client.session.post(url, json=payload,
                                           headers={"Authorization": f"Bearer {client.token}",
                                                    "Content-Type": "application/json"},
                                           timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        d = data.get("data") or {}
                        folio = d.get("wo_folio") or d.get("id_work_order") or "?"
                        return True, f"OT criada! Folio: {folio}"
                    return False, data.get("message", "Erro desconhecido")
            except Exception as e:
                continue
        return False, "Nenhum endpoint funcionou. Validar JWT/permissões."
    except Exception as e:
        return False, f"Exceção: {e}"


# ────────────────────────────────────────────────────────────────────
# UI principal
# ────────────────────────────────────────────────────────────────────
st.title("🛠 Criador de OS — Grid Co.")
st.caption("Cria OT corretiva no Fracttal a partir de Solicitação de Serviço pendente.")

with st.sidebar:
    st.markdown("### Filtros")
    so_urgentes = st.checkbox("Só urgentes", value=False)
    cluster_filter = st.text_input("Cluster contém", value="")
    if st.button("↻ Atualizar dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.markdown("---")
    st.caption(f"Sugestões PCM: `{SUGESTOES_PATH.name}`")
    st.caption("Token Fracttal: lido de `.env`")

# Carrega dados
with st.spinner("Carregando solicitações..."):
    ss_list = carregar_solicitacoes_pendentes()
    sugestoes = carregar_sugestoes_pcm()
    responsaveis = carregar_responsaveis()

if not ss_list:
    st.info("Nenhuma solicitação pendente.")
    st.stop()

# Aplica filtros
ss_filt = []
for ss in ss_list:
    if so_urgentes and not ss.get("is_urgent"):
        continue
    if cluster_filter:
        cluster = (ss.get("groups_2_description") or "").lower()
        if cluster_filter.lower() not in cluster:
            continue
    ss_filt.append(ss)

st.markdown(f"**{len(ss_filt)} solicitações pendentes**")

# Lista de SS pra escolher
opcoes = []
for ss in sorted(ss_filt, key=lambda x: (not x.get("is_urgent"),
                                         {"VERY_HIGH":0,"HIGH":1,"MEDIUM":2,"LOW":3,"VERY_LOW":4}
                                         .get(x.get("priorities_description","MEDIUM"), 5))):
    label = f"#{ss['id_code']} — {(ss.get('description') or '')[:60]}"
    if ss.get("is_urgent"):
        label = "🔴 " + label
    opcoes.append((label, ss))

# Pré-seleção via query param ?ss=NUMERO (vem do dashboard)
default_idx = 0
try:
    qss = st.query_params.get("ss")
    if qss:
        for i, (_, item) in enumerate(opcoes):
            if str(item.get("id_code")) == str(qss):
                default_idx = i
                st.toast(f"📥 Abrindo SS #{qss} (vinda do dashboard)", icon="🔗")
                break
        else:
            st.warning(f"⚠ SS #{qss} não encontrada na lista de pendentes. "
                       "Pode ter sido criada/finalizada — clique em '↻ Atualizar dados'.")
except Exception:
    pass

sel = st.selectbox("Selecione a SS", options=opcoes,
                    format_func=lambda x: x[0], index=default_idx)
if not sel:
    st.stop()

ss_sel = sel[1]
num_ss = int(ss_sel["id_code"])
sug = sugestoes.get(num_ss, {})

# Mostra info da sugestão se houver
if sug:
    st.success(f"✨ Sugestão automática do PCM — Score {sug.get('score')} · "
               f"RPN {sug.get('rpn')} · "
               f"Categoria {sug.get('categoria')} · "
               f"Equipe {sug.get('equipe') or '—'}")
elif sug == {} and num_ss in sugestoes:
    pass
else:
    st.info("⚠ Sem sugestão PCM para esta SS — rode `atualizacao_semanal.py` primeiro.")

# Bloco descrição
st.markdown("#### 📝 Detalhes da SS")
c1, c2 = st.columns([2, 1])
with c1:
    st.text_area("Descrição original", value=ss_sel.get("description") or "",
                 height=80, disabled=True)
with c2:
    st.text_input("Ativo", value=ss_sel.get("items_description") or "", disabled=True)
    st.text_input("Localização",
                  value=ss_sel.get("parent_description") or "", disabled=True)
    st.text_input("Solicitado por", value=ss_sel.get("requested_by") or "",
                  disabled=True)

# Formulário de criação
st.markdown("#### 🛠 Criação da OT")
data_padrao = proxima_data_do_dia(sug.get("dia", "")) if sug.get("dia") else dt.date.today() + dt.timedelta(days=1)
hora_padrao = parse_hora(sug.get("hora", "07:30"))

col1, col2, col3 = st.columns(3)
with col1:
    data_alvo = st.date_input("Data alvo *", value=data_padrao,
                              help="Sugestão do PCM se disponível")
with col2:
    hora_alvo = st.time_input("Hora alvo *", value=hora_padrao)
with col3:
    duracao_h = st.number_input("Duração (h) *",
                                 value=float(sug.get("duracao", 1.0) or 1.0),
                                 min_value=0.25, max_value=24.0, step=0.25)

col4, col5 = st.columns(2)
with col4:
    # Prioridade
    prio_raw = ss_sel.get("priorities_description") or "MEDIUM"
    prio_pt = CRIT_MAP_PT.get(prio_raw, "Média")
    prio_idx = list(CRIT_MAP_PT.values()).index(prio_pt) if prio_pt in CRIT_MAP_PT.values() else 2
    prio_sel = st.selectbox("Prioridade *", list(CRIT_MAP_PT.values()),
                             index=prio_idx)
with col5:
    nomes_resp = [r["nome"] for r in responsaveis]
    resp_sel = st.selectbox("Responsável *", nomes_resp,
                             index=0 if nomes_resp else None)

# Descrição da tarefa
tarefa_desc = st.text_area("Descrição da tarefa *",
                            value=(ss_sel.get("description") or "")[:200],
                            max_chars=200,
                            help="Max 200 chars (limite do Fracttal)")

# Botão criar
st.markdown("---")
col_btn1, col_btn2 = st.columns([3, 1])
with col_btn1:
    if sug.get("equipe"):
        st.caption(f"📋 Equipe sugerida pelo PCM: **{sug['equipe']}** · "
                   f"Slot: **{sug.get('dia','—')} {sug.get('hora','—')}**")
with col_btn2:
    confirmado = st.button("📤 Criar OT no Fracttal",
                            type="primary", use_container_width=True)

if confirmado:
    # Monta payload pra tasks_noscheduled
    id_resp = next((r["id"] for r in responsaveis if r["nome"] == resp_sel), None)
    dt_alvo = dt.datetime.combine(data_alvo, hora_alvo)
    iso_alvo = iso_utc(dt_alvo)
    iso_fim = iso_utc(dt_alvo + dt.timedelta(hours=duracao_h))

    payload = {
        "id_item": ss_sel.get("id_item"),
        "items_description": ss_sel.get("items_description") or "",
        "description": tarefa_desc.strip()[:200],
        "id_task_type_main": 43885,  # Corretiva (descobrir do BD se diferente por empresa)
        "tasks_types_main_description": "Corretiva",
        "event_date": iso_utc(dt.datetime.now()),
        "cal_date_maintenance": iso_alvo,
        "date_maintenance": iso_alvo,
        "initial_date": iso_alvo,
        "final_date": iso_fim,
        "id_priorities": CRIT_TO_ID.get(prio_sel, 3),
        "assigment_date": iso_utc(dt.datetime.now()),
        "id_type_item": 2,  # Equipment
        "path_node": ss_sel.get("parent_description") or "",
        "to_work_order": True,
        "id_request": int(ss_sel.get("id_code")) if ss_sel.get("id_code") else None,
        "duration": int(duracao_h * 3600),
        "array_resources": [],
        "subtasks": [],
        "stop_assets": False,
    }
    if id_resp:
        payload["type_user"] = "HUMAN_RESOURCES"
        payload["id_assigned_user"] = id_resp

    with st.spinner("Criando OT no Fracttal..."):
        ok, msg = criar_os_fracttal(payload)

    if ok:
        st.success(f"✅ {msg}")
        st.balloons()
        st.cache_data.clear()
        st.info("Cache limpo. Recarregue a página pra ver a SS removida da lista.")
    else:
        st.error(f"❌ Falha: {msg}")
        with st.expander("Ver payload enviado (debug)"):
            st.json(payload)
