# -*- coding: utf-8 -*-
"""
gerar_gestao_pcm_json.py
------------------------
Gera `gestao_pcm.json` para a aba "Gestão PCM" do dashboard, puxando as
tarefas DIRETO da API do Fracttal (view tasks.v_works_orders_list_new),
SEM passar pelo BD_Relatório Semanal.xlsx.

Reaproveita o FracttalClient e os mapeamentos do gerar_bd_via_api.py
(mesma autenticação OAuth2, mesma view — paridade garantida com o BD).

Escopo (definido com o PCM em 2026-07):
  - Todas as tarefas com Data Programada >= 2026-01-01
  - Status da OS in (1=Em processo, 2=Em revisão, 3=Finalizada)  → exclui 4=Cancelada
  - Equipe Cluster = Ativo Classificação 2 (já corrigido por override no pipeline)
  - Responsável O&M = join por usina no AUXILIAR (fallback: responsável majoritário
    do cluster; senão "TBD")
  - Aging ("dias em aberto") = hoje - Data Programada, só para tarefas EM ABERTO;
    > 10 dias marca como atrasada (destaque vermelho no frontend)
  - Link da OT = template configurável (default one.fracttal.com/tasks/wo/{folio})

Uso:
    python gerar_gestao_pcm_json.py             # gera gestao_pcm.json
    python gerar_gestao_pcm_json.py --limit 200 # amostra p/ debug
    python gerar_gestao_pcm_json.py --test      # só autentica

Credenciais: .env (FRACTTAL_CLIENT_ID / FRACTTAL_CLIENT_SECRET) — mesmas do BD.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, date

# Reaproveita o cliente e os mapeamentos JÁ PROVADOS do gerador do BD.
# (importar NÃO roda main() — está sob if __name__ == "__main__")
import gerar_bd_via_api as bd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ============================================================
# Config
# ============================================================
CORTE_DATA = os.environ.get("GESTAO_CORTE_DATA", "2026-01-01")   # Data Programada mínima
STATUS_OK = {1, 2, 3}                                            # exclui 4 (cancelada)
# Clientes de teste a NÃO exibir (normalizado: minúsculas, sem acento). Decisão do PCM.
CLIENTES_EXCLUIR = {"usina teste"}
# Link da OT. {id} = id_work_order interno (o folio/número curto NÃO abre no SPA).
WO_URL_TEMPLATE = os.environ.get(
    "GESTAO_WO_URL", "https://one.fracttal.com/tasks/wo/{id}")
DIAS_ALERTA = int(os.environ.get("GESTAO_DIAS_ALERTA", "10"))

BASE_DIR = bd.BASE_DIR
AUXILIAR_PATH = os.environ.get(
    "GESTAO_AUXILIAR_PATH", os.path.join(BASE_DIR, "AUXILIAR - FABRICIO.xlsx"))
OUTPUT_JSON = os.path.join(BASE_DIR, "gestao_pcm.json")
# Cache do mapa de ativos (Classificação 1/2 ATUAL por id_item). Ativos mudam
# raramente, então recarregamos da API só se o cache passou do TTL.
ATIVOS_CACHE = os.path.join(BASE_DIR, "_ativos_classificacao_cache.json")
ATIVOS_TTL_H = float(os.environ.get("GESTAO_ATIVOS_TTL_H", "6"))

log = bd.log


# ============================================================
# Normalização / join com o AUXILIAR
# ============================================================
def _norm(s) -> str:
    if not s:
        return ""
    s = "".join(c for c in unicodedata.normalize("NFD", str(s))
                if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()


def _strip_uf(s: str) -> str:
    return re.sub(r"\s*-\s*[a-z]{2}$", "", s).strip()


def _variantes_usina(usina_full: str) -> set:
    """Chaves candidatas a partir de 'Cliente - Usina N - UF'."""
    base = _strip_uf(_norm(usina_full))          # 'athon - maraba 2'
    out = {base}
    m = re.search(r"(.*?)(\d+)\s*$", base)
    if m:
        pre, num = m.group(1).strip(), m.group(2)
        out.add(f"{pre} {num}00")                # maraba 2 -> maraba 200
        out.add(pre)                              # drop numero -> 'athon - maraba'
    return {k for k in out if k}


def carregar_auxiliar(path: str):
    """Lê o AUXILIAR e devolve (usina_idx, cluster_major).

    usina_idx: chave-usina normalizada -> (cluster, responsavel)
    cluster_major: cluster -> responsavel majoritário (não-vazio, != TBD)
    """
    import openpyxl
    if not os.path.exists(path):
        log(f"AUXILIAR não encontrado: {path} — responsável ficará vazio.", "WARN")
        return {}, {}
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Operacoes_1"]
    usina_idx: dict = {}
    cluster_resp = defaultdict(Counter)
    for r in ws.iter_rows(min_row=2, values_only=True):
        ufv, cliente, cluster, resp, oper = r[0], r[3], r[4], r[5], r[9]
        clu = str(cluster).strip() if cluster else ""
        rsp = str(resp).strip() if resp else ""
        val = (clu, rsp)
        chaves = {_norm(ufv), _strip_uf(_norm(ufv))}
        if cliente and oper:
            chaves.add(_norm(f"{cliente} - {oper}"))
            chaves.add(_strip_uf(_norm(f"{cliente} - {oper}")))
        # também indexa "Nome N00" como "Nome N"
        m = re.search(r"(.*?)(\d)00\s*$", _strip_uf(_norm(ufv)))
        if m:
            chaves.add(f"{m.group(1).strip()} {m.group(2)}")
        for k in chaves:
            if k:
                usina_idx.setdefault(k, val)
        if clu and rsp and rsp.upper() != "TBD":
            cluster_resp[clu][rsp] += 1
    cluster_major = {c: cnt.most_common(1)[0][0] for c, cnt in cluster_resp.items()}
    log(f"AUXILIAR: {len(usina_idx)} chaves de usina, "
        f"{len(cluster_major)} clusters com responsável.")
    return usina_idx, cluster_major


def resolver_responsavel(usina_full: str, cluster: str,
                         usina_idx: dict, cluster_major: dict) -> str:
    if usina_full:
        for k in _variantes_usina(usina_full):
            if k in usina_idx:
                _clu, rsp = usina_idx[k]
                if rsp and rsp.upper() != "TBD":
                    return rsp
    if cluster and cluster in cluster_major:
        return cluster_major[cluster]
    return "TBD"


# ============================================================
# Parsing de campos crus da API
# ============================================================
def _labels_para_lista(labels) -> list:
    """Fracttal 'labels' pode vir como lista de dicts, lista de str, str JSON ou CSV."""
    if not labels:
        return []
    if isinstance(labels, str):
        s = labels.strip()
        if s.startswith("[") or s.startswith("{"):
            try:
                labels = json.loads(s)
            except Exception:
                return [p.strip() for p in s.split(",") if p.strip()]
        else:
            return [p.strip() for p in s.split(",") if p.strip()]
    if isinstance(labels, dict):
        labels = [labels]
    out = []
    for it in labels:
        if isinstance(it, dict):
            v = (it.get("description") or it.get("name")
                 or it.get("label") or it.get("value") or "")
        else:
            v = str(it)
        v = v.strip()
        if v:
            out.append(v)
    return out


def _data_iso(v) -> str:
    """Devolve 'YYYY-MM-DD' (data programada) ou '' ."""
    dt = bd._data_iso_para_naive(v) if hasattr(bd, "_data_iso_para_naive") else None
    if dt is None and v:
        try:
            dt = datetime.fromisoformat(str(v).replace("Z", "").split(".")[0])
        except Exception:
            dt = None
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d")
    if isinstance(dt, date):
        return dt.strftime("%Y-%m-%d")
    return ""


def _cliente_de(usina_full: str) -> str:
    if not usina_full:
        return "(sem cliente)"
    return usina_full.split(" - ")[0].strip() or "(sem cliente)"


# Normaliza estado da tarefa a partir do código CRU da API (task_status) OU do
# rótulo já mapeado pelo bd.TASK_STATUS_MAP. A API às vezes devolve "IN_PROGRESS"
# em vez de "STARTED", então cobrimos ambos.
_ESTADO_CANON = {
    "NO_STARTED": "Não Iniciada", "NOT_STARTED": "Não Iniciada",
    "NOT_INITIATED": "Não Iniciada", "NÃO INICIADA": "Não Iniciada",
    "NAO INICIADA": "Não Iniciada",
    "STARTED": "Em progresso", "IN_PROGRESS": "Em progresso",
    "EM PROGRESSO": "Em progresso",
    "PAUSED": "Pausada", "PAUSADO": "Pausada", "PAUSADA": "Pausada",
    "DONE": "Finalizada", "FINISHED": "Finalizada", "COMPLETED": "Finalizada",
    "FINALIZADOS": "Finalizada", "FINALIZADA": "Finalizada",
}


def normalizar_estado(task_status_raw):
    chave = str(task_status_raw or "").strip().upper()
    lbl = _ESTADO_CANON.get(chave, str(task_status_raw or "").strip() or "Não Iniciada")
    aberta = lbl != "Finalizada"
    return lbl, aberta


# ============================================================
# Mapa de ativos: id_item -> (Classificação 1, Classificação 2) ATUAIS
# A OT guarda a classificação do momento da criação; o usuário quer a ATUAL do
# ativo (usinas mudam de equipe cluster). Fonte de verdade = cadastro do ativo.
# ============================================================
def carregar_ativos(client):
    # Usa cache se estiver dentro do TTL
    try:
        if os.path.exists(ATIVOS_CACHE):
            idade_h = (time.time() - os.path.getmtime(ATIVOS_CACHE)) / 3600
            if idade_h < ATIVOS_TTL_H:
                with open(ATIVOS_CACHE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                m = {int(k): (v[0], v[1]) for k, v in raw.items()}
                log(f"Ativos: {len(m)} do cache ({idade_h:.1f}h atrás).")
                return m
    except Exception as e:
        log(f"Cache de ativos inválido ({e}), recarregando da API.", "WARN")

    log("Ativos: carregando classificação ATUAL da API (/items)...")
    m = {}
    n = 0
    for it in client.paginar("items", page_size=100):
        n += 1
        i = it.get("id")
        if i is None:
            continue
        m[int(i)] = (it.get("groups_1_description") or "",
                     it.get("groups_2_description") or "")
        if n % 4000 == 0:
            log(f"  ... {n} ativos")
    log(f"Ativos: {len(m)} carregados da API.")
    try:
        tmp = ATIVOS_CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({str(k): [a, b] for k, (a, b) in m.items()}, f,
                      ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, ATIVOS_CACHE)
    except Exception as e:
        log(f"Não consegui gravar cache de ativos: {e}", "WARN")
    return m


# ============================================================
# Coleta principal
# ============================================================
def coletar(client, usina_idx, cluster_major, ativos, max_items=None):
    hoje = date.today()
    corte = datetime.fromisoformat(CORTE_DATA).date()
    tarefas = []
    total_bruto = 0
    for row in client.paginar("work_orders", page_size=100, max_items=max_items):
        total_bruto += 1
        if total_bruto % 2000 == 0:
            log(f"  ... {total_bruto} linhas processadas")

        st_wo = row.get("id_status_work_order")
        if st_wo not in STATUS_OK:
            continue

        data_prog = _data_iso(row.get("date_maintenance"))
        if not data_prog or datetime.fromisoformat(data_prog).date() < corte:
            continue

        ativo_nome = row.get("items_log_description") or ""
        # Classificação 1/2 ATUAL do ativo (cadastro) tem prioridade sobre a que
        # a OT gravou na criação — usinas mudam de equipe cluster ao longo do tempo.
        id_item = row.get("id_item")
        at = ativos.get(int(id_item)) if id_item not in (None, "") else None
        usina = (at[0] if at and at[0] else row.get("groups_1_description")) or ""
        cls2_raw = (at[1] if at and at[1] else row.get("groups_2_description")) or ""
        cluster = (bd._aplicar_override_cls2(ativo_nome, cls2_raw)
                   if hasattr(bd, "_aplicar_override_cls2") else cls2_raw)
        # Exclui tarefas sem Classificação 1 (ativos "TESTE"/não classificados —
        # decisão do PCM: não devem aparecer na Gestão PCM).
        if not usina.strip():
            continue
        cliente = _cliente_de(usina)
        if _norm(cliente) in CLIENTES_EXCLUIR:
            continue

        estado, aberta = normalizar_estado(row.get("task_status"))

        dias = None
        atrasado = False
        if aberta and data_prog:
            dias = (hoje - datetime.fromisoformat(data_prog).date()).days
            atrasado = dias > DIAS_ALERTA

        folio = row.get("wo_folio") or row.get("id_work_order") or ""
        responsavel = resolver_responsavel(usina, cluster, usina_idx, cluster_major)

        tarefas.append({
            "os": str(folio),
            "idWO": row.get("id_work_order"),
            "url": WO_URL_TEMPLATE.format(folio=folio, id=row.get("id_work_order")),
            "cliente": cliente,
            "usina": usina or "(sem usina)",
            "cluster": cluster or "(sem cluster)",
            "responsavel": responsavel,
            "tipo": row.get("tasks_log_task_type_main") or "(sem tipo)",
            "tarefa": row.get("description") or "",
            "estado": estado,
            "aberta": aberta,
            # Status da OS (Em processo / Verificação / Finalizados). Usado p/ separar
            # tarefas de OS já finalizada mas com estado em aberto ("não finalizadas
            # no período") num dropdown à parte, fora da árvore/contadores principais.
            "osStatus": bd.STATUS_OS_MAP.get(st_wo, str(st_wo or "")),
            "etiquetas": sorted(_labels_para_lista(row.get("labels"))),
            "ss": str(row.get("id_request") or "").strip(),
            "dataProg": data_prog,
            # Data final = quando a TAREFA foi concluída (Estado da Tarefa,
            # campo API final_date). NÃO é wo_final_date (Status/fim da OS).
            "dataFinal": _data_iso(row.get("final_date")),
            "criacao": _data_iso(row.get("creation_date")),
            "dias": dias,
            "atrasado": atrasado,
        })
    log(f"  -> {total_bruto} linhas brutas | {len(tarefas)} tarefas no escopo")
    return tarefas


def _opts(tarefas, campo):
    vals = set()
    for t in tarefas:
        v = t.get(campo)
        if isinstance(v, list):
            vals.update(v)
        elif v:
            vals.add(v)
    return sorted(vals, key=lambda x: _norm(x))


def montar_json(tarefas):
    # Ordena de forma determinística (a paginação da API pode variar a ordem) —
    # garante que o arquivo e o hash só mudem quando o CONTEÚDO muda de fato.
    tarefas = sorted(tarefas, key=lambda t: json.dumps(t, ensure_ascii=False, sort_keys=True))
    abertas = [t for t in tarefas if t["aberta"]]
    # dataHash = assinatura do conteúdo (tudo menos o timestamp geradoEm).
    # O publisher usa isso p/ NÃO commitar (e não reconstruir o Pages) quando
    # os dados não mudaram — evita churn de rebuild a cada 15 min.
    h = hashlib.sha256()
    h.update(f"{CORTE_DATA}|{DIAS_ALERTA}|".encode("utf-8"))
    for t in tarefas:
        h.update(json.dumps(t, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    data_hash = h.hexdigest()
    return {
        "geradoEm": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "dataHash": data_hash,
        "corteData": CORTE_DATA,
        "diasAlerta": DIAS_ALERTA,
        "totalTarefas": len(tarefas),
        "totalAbertas": len(abertas),
        "totalAtrasadas": sum(1 for t in abertas if t["atrasado"]),
        "filtros": {
            "clientes": _opts(tarefas, "cliente"),
            "usinas": _opts(tarefas, "usina"),
            "clusters": _opts(tarefas, "cluster"),
            "responsaveis": _opts(tarefas, "responsavel"),
            "tipos": _opts(tarefas, "tipo"),
            "etiquetas": _opts(tarefas, "etiquetas"),
            "estados": _opts(tarefas, "estado"),
        },
        "tarefas": tarefas,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()

    log("=" * 70)
    log("GERAR gestao_pcm.json (via API Fracttal — sem BD)")
    log("=" * 70)
    log(f"Corte Data Programada >= {CORTE_DATA} | status in {sorted(STATUS_OK)}")
    log(f"Output: {OUTPUT_JSON}")

    try:
        client = bd.FracttalClient(bd.CLIENT_ID, bd.CLIENT_SECRET, bd.BASE_URL)
        client.autenticar()
    except Exception as e:
        log(f"FALHA na autenticação: {e}", "ERROR")
        return 1
    if args.test:
        log("[--test] Autenticação OK.")
        return 0

    usina_idx, cluster_major = carregar_auxiliar(AUXILIAR_PATH)
    ativos = carregar_ativos(client)

    try:
        tarefas = coletar(client, usina_idx, cluster_major, ativos, max_items=args.limit)
    except Exception as e:
        import traceback
        log(f"FALHA ao coletar: {e}", "ERROR")
        log(traceback.format_exc(), "ERROR")
        return 2

    data = montar_json(tarefas)
    tmp = OUTPUT_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUTPUT_JSON)

    log(f"OK: {data['totalTarefas']} tarefas "
        f"({data['totalAbertas']} abertas, {data['totalAtrasadas']} atrasadas) "
        f"-> {os.path.basename(OUTPUT_JSON)}")
    log("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
