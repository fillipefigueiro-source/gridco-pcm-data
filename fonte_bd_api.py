# -*- coding: utf-8 -*-
"""
fonte_bd_api.py
---------------
Fonte de dados via API Fracttal — substitui a leitura do BD_Relatório Semanal.xlsx
nos scripts de Programação Semanal (programacao_v7, atualizacao_semanal).

Reusa o gerar_bd_via_api (mesmo client OAuth + transformar_wo_para_bd + COLS_BD_SEMANAL),
então o DataFrame devolvido tem EXATAMENTE as mesmas colunas da aba "Semanal" do BD.
Assim a lógica de escalonamento/reprogramação continua idêntica — só a fonte muda.

API:
  df_semanal(ttl_min=None) -> DataFrame das OS/tarefas (colunas do BD "Semanal").
      Cache local .cache_semanal_api.pkl com TTL (env PROG_API_TTL_MIN, default 10 min).
      Estado da Tarefa normalizado (IN_PROGRESS->Em progresso, etc).
  df_auxiliar() -> DataFrame do cadastro (AUXILIAR - FABRICIO.xlsx, aba Operacoes_1):
      UFV, CLIENTE, CLUSTER, RESPONSÁVEL O&M, CAPACIDADE INSTALADA (MWp), Data Mobilização...

NÃO depende de BD_Relatório Semanal.xlsx.
"""
import os
import json
import time
import pickle
import pandas as pd

# Normaliza códigos crus de Estado da Tarefa que o TASK_STATUS_MAP não cobre.
# (a API às vezes devolve IN_PROGRESS em vez de STARTED). NÃO é Status da OS.
_EST_FIX = {"IN_PROGRESS": "Em progresso", "STARTED": "Em progresso",
            "NO_STARTED": "Não Iniciada", "NOT_STARTED": "Não Iniciada",
            "PAUSED": "pausado", "DONE": "Finalizados"}


def _bd():
    import gerar_bd_via_api as bd
    return bd


COORD_CACHE_NOME = "_usinas_coordenadas_cache.json"

# Preenchidos por df_semanal() (Melhoria 0.1, 13/08/2026). Chave = Ativo
# Classificação 1 (nome da usina). NÃO mudar o formato do cache de
# classificação: ele é compartilhado com gerar_gestao_pcm_json (ver proposta §3).
_MAPA_COORD = {}    # {usina: (lat, lon)}
_MAPA_CIDADE = {}   # {usina: cidade}


def _coord_valida(lat, lon):
    """Faixa do território brasileiro. Descarta lixo sem confiar no cadastro."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if -34.0 <= lat <= 6.0 and -74.0 <= lon <= -34.0:
        return (lat, lon)
    return None


def _carregar_coord_cache():
    """Popula os mapas a partir do ARQUIVO de cache, sem TTL de leitura.

    Necessário porque df_semanal() com pickle quente retorna cedo e nunca chama
    _carregar_ativos — sem isto, o deslocamento (0.1) ficava mudo sempre que o
    cache estivesse quente, que é o caso normal. Coordenada de usina não
    apodrece; quem RENOVA o arquivo é a paginação, quando o cache de
    classificação expira (~6 h)."""
    if _MAPA_COORD:
        return
    try:
        with open(os.path.join(_bd().BASE_DIR, COORD_CACHE_NOME),
                  encoding="utf-8") as f:
            cc = json.load(f)
        _MAPA_COORD.update({k: tuple(v) for k, v in cc.get("coords", {}).items()})
        _MAPA_CIDADE.update(cc.get("cidades", {}))
    except Exception:
        pass


def mapa_coordenadas():
    """{usina: (lat, lon)} das usinas com coordenada válida no Fracttal."""
    _carregar_coord_cache()
    return dict(_MAPA_COORD)


def mapa_cidades():
    """{usina: cidade} — Fracttal field_3."""
    _carregar_coord_cache()
    return dict(_MAPA_CIDADE)


def _carregar_ativos(client):
    """Mapa id_item -> (Classificação 1, Classificação 2) ATUAIS do ativo (cadastro).
    A OT guarda a classificação do momento da criação; aqui pegamos a ATUAL (usinas
    mudam de equipe cluster). Mesma lógica/cache do gerar_gestao_pcm_json.py."""
    bd = _bd()
    cache = os.path.join(bd.BASE_DIR, "_ativos_classificacao_cache.json")
    ttl = float(os.environ.get("GESTAO_ATIVOS_TTL_H", "6")) * 3600
    coord_cache = os.path.join(bd.BASE_DIR, COORD_CACHE_NOME)
    _dois_quentes = (
        os.path.exists(cache) and os.path.exists(coord_cache)
        and time.time() - os.path.getmtime(cache) < ttl
        and time.time() - os.path.getmtime(coord_cache) < ttl)
    if _dois_quentes:
        try:
            with open(cache, "r", encoding="utf-8") as f:
                raw = json.load(f)
            with open(coord_cache, "r", encoding="utf-8") as f:
                cc = json.load(f)
            _MAPA_COORD.update({k: tuple(v) for k, v in cc.get("coords", {}).items()})
            _MAPA_CIDADE.update(cc.get("cidades", {}))
            return {int(k): (v[0], v[1]) for k, v in raw.items()}
        except Exception:
            pass
    m = {}
    coords, cidades = {}, {}
    for it in client.paginar("items", page_size=100):
        # ATENÇÃO: page_size=100 é obrigatório (com 200 a API corta a paginação)
        i = it.get("id")
        if i is None:
            continue
        c1 = (it.get("groups_1_description") or "").strip()
        m[int(i)] = (c1, (it.get("groups_2_description") or "").strip())
        if not c1:
            continue
        # Coordenada só existe no ativo de LOCALIZAÇÃO nível usina; os filhos
        # (Cabine, QGBT, Skid) vêm vazios — por isso a chave é a Classificação 1.
        if c1 not in coords:
            xy = _coord_valida(it.get("latitude"), it.get("longitud"))
            if xy:
                coords[c1] = xy
        if c1 not in cidades:
            cid = (it.get("field_3") or "").strip()
            if cid:
                cidades[c1] = cid
    try:
        tmp = cache + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({str(k): [a, b] for k, (a, b) in m.items()}, f,
                      ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, cache)
    except Exception:
        pass
    try:
        tmp2 = coord_cache + ".tmp"
        with open(tmp2, "w", encoding="utf-8") as f:
            json.dump({"coords": {k: list(v) for k, v in coords.items()},
                       "cidades": cidades},
                      f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp2, coord_cache)
    except Exception:
        pass
    _MAPA_COORD.update(coords)
    _MAPA_CIDADE.update(cidades)
    return m


def df_semanal(ttl_min=None):
    """OS/tarefas da API Fracttal, no formato/colunas do BD 'Semanal'. Cache TTL."""
    bd = _bd()
    ttl = (int(os.environ.get("PROG_API_TTL_MIN", "10")) if ttl_min is None else ttl_min) * 60
    cache = os.path.join(bd.BASE_DIR, ".cache_semanal_api.pkl")
    if os.path.exists(cache):
        try:
            if time.time() - os.path.getmtime(cache) < ttl:
                with open(cache, "rb") as f:
                    d = pickle.load(f)
                if d.get("v") == 1:
                    return d["df"].copy()
        except Exception:
            pass
    client = bd.FracttalClient(bd.CLIENT_ID, bd.CLIENT_SECRET, bd.BASE_URL)
    client.autenticar()
    ativos = _carregar_ativos(client)   # id_item -> (Classif 1, Classif 2) ATUAIS
    cols = list(bd.COLS_BD_SEMANAL)
    seen = set()
    rows = []
    for it in client.paginar("work_orders", page_size=100):
        d = bd.transformar_wo_para_bd(it)
        e = d.get("Estado da Tarefa")
        if e in _EST_FIX:
            d["Estado da Tarefa"] = _EST_FIX[e]
        # Classificação 1/2 ATUAL do ativo (cadastro) tem prioridade sobre a histórica
        # da OT — usinas mudam de equipe cluster (corrige usina/cluster/responsável).
        _idit = it.get("id_item")
        _at = ativos.get(int(_idit)) if _idit not in (None, "") else None
        if _at:
            if _at[0]:
                d["Ativo Classificação 1"] = _at[0]
            if _at[1]:
                d["Ativo Classificação 2"] = bd._aplicar_override_cls2(
                    it.get("items_log_description") or "", _at[1])
        wt = d.get("_id_work_orders_tasks")
        key = ("wt", wt) if wt else ("combo", d.get("OSs ID"), d.get("Código"), d.get("Tarefa"))
        if key in seen:
            continue
        seen.add(key)
        rows.append({c: d.get(c) for c in cols})
    df = pd.DataFrame(rows, columns=cols)
    try:
        tmp = cache + ".tmp"
        with open(tmp, "wb") as f:
            pickle.dump({"v": 1, "df": df}, f)
        os.replace(tmp, cache)
    except Exception:
        pass
    return df


def df_auxiliar():
    """Cadastro de usinas do AUXILIAR - FABRICIO.xlsx (aba Operacoes_1)."""
    bd = _bd()
    path = os.environ.get("PROG_AUXILIAR_PATH") or os.path.join(bd.BASE_DIR, "AUXILIAR - FABRICIO.xlsx")
    if not os.path.exists(path):
        return pd.DataFrame()
    for sn in ("Operacoes_1", 0):
        try:
            return pd.read_excel(path, sheet_name=sn)
        except Exception:
            continue
    return pd.DataFrame()
