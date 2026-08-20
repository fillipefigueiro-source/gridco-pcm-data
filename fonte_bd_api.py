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
    # A varredura de items é a outra metade do custo (20.083 ativos ≈ 200 páginas,
    # ~4,6 min em série). Mesmo tratamento: páginas em paralelo, com fallback.
    try:
        _itens = _paginas_rest(client, "items", {}, _total_rest(client, "items"))
    except Exception as _e:
        bd.log("  items em paralelo indisponivel (%s) — varredura em serie" % _e, "WARN")
        _itens = client.paginar("items", page_size=100)
    for it in _itens:
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


# ── Coleta particionada por status (19/08/2026) ─────────────────────────────
# A varredura única de work_orders pagina a conta INTEIRA (28.399 linhas em 19/08,
# ~284 páginas, ~6,5 min em série) a cada execução — e 67% disso são OS concluídas,
# que por definição não mudam mais. No Actions (runner sem estado, ciclo de 15 min)
# isso quase saturava o próprio ciclo.
#
# O desenho: vivo (status 1+2, ~4.300 linhas) sempre fresco, em páginas paralelas;
# histórico (3+4) em cache validado por CONTAGEM — uma OS terminal só muda por
# transição de status, e transição muda a contagem da partição. TTL de 24 h como
# cinto de segurança para o caso raríssimo de transições simultâneas que se
# compensam. Medido em 19/08: os 4 status somam EXATAMENTE o total (28.399 = 2.149
# + 2.166 + 18.940 + 5.144) — e essa soma é conferida a cada coleta: se um dia o
# Fracttal criar um status 5, a conta não fecha e a coleta VOLTA para a varredura
# completa antiga, avisando. Nenhuma inconsistência passa calada.

_HIST_CACHE = ".cache_hist_api.pkl"
_ST_VIVO = (1, 2)     # Em processo, Em verificação
_ST_HIST = (3, 4)     # Concluída, Cancelada

# O Fracttal corta em ~200 requisições/minuto por IP (HTTP 429 "Too many requests
# (200) created from this IP", medido em 19/08/2026 na primeira tentativa de
# paralelismo — a varredura serial antiga nunca chegou perto do teto). O espaçador
# é GLOBAL entre as threads: 0,42 s entre requisições ≈ 143/min, com folga para as
# chamadas de dimensionamento e para outro consumidor eventual no mesmo IP.
import threading as _th
_RITMO_TRAVA = _th.Lock()
_RITMO_ULTIMO = [0.0]


def _ritmo():
    intervalo = float(os.environ.get("PROG_API_INTERVALO_S", "0.42"))
    with _RITMO_TRAVA:
        agora = time.monotonic()
        espera = _RITMO_ULTIMO[0] + intervalo - agora
        if espera > 0:
            time.sleep(espera)
            agora = time.monotonic()
        _RITMO_ULTIMO[0] = agora


def _total_rest(client, path, params=None):
    """O campo `total` do envelope — dimensiona qualquer filtro por 1 requisição.

    Nota: o `total` chega como int em work_orders e como STRING em requests —
    o int() cobre os dois. E o caminho passa pelo _resolver_path do client, como
    o paginar faz: o get cru não resolve, e a conta pode servir o recurso em
    outra base."""
    p = dict(params or {})
    p.update({"limit": 1, "start": 0})
    _ritmo()
    payload = client.get(client._resolver_path(path), params=p)
    try:
        return int(payload.get("total"))
    except (TypeError, ValueError, AttributeError):
        return None


def _paginas_rest(client, path, params, total, workers=5):
    """Todas as linhas de um filtro, com as páginas em PARALELO (+ cauda em série).

    O client não tem trava no refresh do token, então quem chama autentica ANTES —
    o token novo dura a varredura inteira. O `total` pode crescer entre o
    dimensionamento e a leitura: depois do paralelo, segue em série até a página
    vazia, como o paginar antigo fazia."""
    from concurrent.futures import ThreadPoolExecutor

    path = client._resolver_path(path)   # o get cru não resolve; o paginar resolvia

    def _uma(start):
        p = dict(params)
        p.update({"limit": 100, "start": start})
        # O retry interno do client espaça 3 s/6 s — curto demais para o castigo de
        # 1 minuto do 429. Aqui: uma segunda chance depois de esperar a janela.
        payload = None
        for tentativa in (1, 2):
            _ritmo()
            try:
                payload = client.get(path, params=p)
                break
            except Exception as e:
                if tentativa == 1 and ("429" in str(e) or "Too many requests" in str(e)):
                    time.sleep(62)
                    continue
                raise
        return (payload.get("data") if isinstance(payload, dict) else payload) or []

    out = []
    starts = list(range(0, max(int(total or 0), 1), 100))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for parte in ex.map(_uma, starts):
            out.extend(parte)
    start = starts[-1] + 100
    while True:
        parte = _uma(start)
        if not parte:
            break
        out.extend(parte)
        start += 100
    return out


def _hist_ler(totais):
    """O histórico do cache — SE as contagens de 3 e 4 continuam as mesmas."""
    try:
        with open(os.path.join(_bd().BASE_DIR, _HIST_CACHE), "rb") as f:
            d = pickle.load(f)
        ttl_h = float(os.environ.get("PROG_HIST_TTL_H", "24"))
        if (d.get("v") == 1
                and d.get("totais") == {s: totais[s] for s in _ST_HIST}
                and time.time() - float(d.get("ts") or 0) < ttl_h * 3600):
            return d["rows"]
    except Exception:
        pass
    return None


def _hist_gravar(rows, totais):
    # validade por carimbo INTERNO, não por mtime: o actions/cache restaura o
    # arquivo com o mtime da criação, e mtime enganaria o TTL nos dois sentidos
    try:
        cam = os.path.join(_bd().BASE_DIR, _HIST_CACHE)
        with open(cam + ".tmp", "wb") as f:
            pickle.dump({"v": 1, "ts": time.time(),
                         "totais": {s: totais[s] for s in _ST_HIST},
                         "rows": rows}, f, protocol=4)
        os.replace(cam + ".tmp", cam)
    except Exception:
        pass


def _linhas_work_orders(client):
    """As linhas cruas de work_orders — particionadas, com fallback à varredura antiga.

    Devolve LISTA (não generator) de propósito: ou a partição inteira dá certo, ou
    nada dela é usado — um fallback no meio de um generator já consumido duplicaria
    linhas."""
    bd = _bd()
    try:
        tot_geral = _total_rest(client, "work_orders")
        totais = {s: _total_rest(client, "work_orders", {"id_status_work_order": s})
                  for s in _ST_VIVO + _ST_HIST}
        if not tot_geral or any(v is None for v in totais.values()) \
                or sum(totais.values()) != tot_geral:
            raise RuntimeError("particao nao fecha: %s vs total=%s" % (totais, tot_geral))
        vivo = []
        for s in _ST_VIVO:
            vivo.extend(_paginas_rest(client, "work_orders",
                                      {"id_status_work_order": s}, totais[s]))
        hist = _hist_ler(totais)
        origem = "cache"
        if hist is None:
            hist = []
            for s in _ST_HIST:
                hist.extend(_paginas_rest(client, "work_orders",
                                          {"id_status_work_order": s}, totais[s]))
            _hist_gravar(hist, totais)
            origem = "refeito"
        bd.log("  coleta particionada: vivo=%d hist=%d (hist %s)"
               % (len(vivo), len(hist), origem))
        return vivo + hist
    except Exception as e:
        bd.log("  coleta particionada indisponivel (%s) — varredura completa" % e, "WARN")
        return list(client.paginar("work_orders", page_size=100))


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
    for it in _linhas_work_orders(client):
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
