# -*- coding: utf-8 -*-
"""
gerar_etiquetas_json.py  (v2 — versão final)
--------------------------------------------
Lê BD_Relatório Semanal.xlsx (aba Semanal) e o arquivo Programação Semana XX.xlsx
e gera etiquetas.json com:
  - KPIs por tipologia (Total / Em aberto / Atrasadas / Concluídas 30d e 7d /
    Na semana corrente)
  - MTTR (Tempo médio de resolução) por tipologia
  - Tendência das últimas 4 semanas (criadas vs finalizadas)
  - Top 5 ofensores: por cluster e por responsável
  - Religamentos sub-classificados em REMOTO vs LOCAL (palavra "remoto" na Tarefa)
  - Seção verificacao: OSs com status contendo "verifica"

Classificação por palavra-chave na coluna "Tarefa":
  Religamento           → religamentos
  MPM/MPS/MPA/MPT/...   → manutencoesPreventivas (ou "preventiva" no texto)
  Garantia / RMA        → chamadosGarantia
  Performance / Análise PR / Soiling / Geração / Perda  → performance
  Engenharia / Estudo / Adequação / Modificação SCADA   → engenharia

Filtros globais:
  - Status != Cancelada (mantém finalizadas pra cálculo de tendência/MTTR)

Saída: etiquetas.json no mesmo diretório.

Uso:
   py -3 gerar_etiquetas_json.py
   py -3 gerar_etiquetas_json.py --dry-run    # imprime JSON, não grava
"""
from __future__ import annotations
import os, sys, json, re, argparse, datetime as dt
from pathlib import Path
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import openpyxl

# ════════════════════════════════════════════════════════════════════
# Configuração
# ════════════════════════════════════════════════════════════════════
META = {
    "religamentos":            {"label": "Religamentos",            "icone": "ti-bolt",          "cor": "#f59e0b"},
    "manutencoesPreventivas":  {"label": "Manutenções Preventivas", "icone": "ti-tool",          "cor": "#10b981"},
    "chamadosGarantia":        {"label": "Chamados em Garantia",    "icone": "ti-shield-check",  "cor": "#ef4444"},
    "performance":             {"label": "Performance",             "icone": "ti-chart-line",    "cor": "#8b5cf6"},
    "engenharia":              {"label": "Engenharia",              "icone": "ti-settings-cog",  "cor": "#3b82f6"},
}

# Regex de classificação por conteúdo da Tarefa (case/accent-insensitive).
# Ordem importa: avaliada de cima pra baixo, primeira que casa ganha.
RULES = [
    ("religamentos",            r"\breligamento|\breligar|\breligando"),
    ("manutencoesPreventivas",  r"\bmpm|\bmps|\bmpa|\bmpt|\bmpq|preventiva|inspecao rotineira"),
    ("chamadosGarantia",        r"\bgarantia\b|\brma\b"),
    ("performance",             r"performance|analise pr|soiling|comparativo geracao|perda|degradacao"),
    ("engenharia",              r"engenharia|estudo|adequacao|modificacao scada|projeto eletrico"),
]

# Sub-classificação dentro de Religamentos
REMOTO_RE = re.compile(r"\bremoto|remota|remotamente|scada|supervisorio|supervisoria", re.IGNORECASE)

STATUS_CANCELADO = ("cancelad",)
STATUS_FINALIZADO = ("finaliz", "conclu")

LINK_FRACTTAL = "https://app.fracttal.com/oneview/general/items/wo/{id}"

# Data de corte: OSs criadas antes desta data são ignoradas no dashboard de
# etiquetas (não relevantes pro fluxo atual de 2026).
DATA_CORTE_MIN = dt.date(2026, 1, 1)


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════
def _log(msg: str):
    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _detectar_pasta() -> Path:
    env = os.getenv("PCM_PROG_DIR")
    if env and Path(env).exists():
        return Path(env)
    here = Path(__file__).resolve().parent
    if (here / "atualizacao_semanal.py").exists():
        return here
    for c in [
        Path.home() / "GRID CO" / "Grid Co. - Gridco" / "4. O&M"
            / "11.Pré-Operação" / "6. PCM" / "09. Programação Semanal",
        Path.home() / "OneDrive - Grid Co" / "4. O&M"
            / "11.Pré-Operação" / "6. PCM" / "09. Programação Semanal",
    ]:
        if c.exists():
            return c
    raise FileNotFoundError("Pasta PCM não encontrada. Defina PCM_PROG_DIR.")


def _norm(s) -> str:
    if not s:
        return ""
    s = str(s).strip().lower()
    repls = {"ã":"a","á":"a","â":"a","à":"a","é":"e","ê":"e","í":"i","ó":"o","ô":"o","ú":"u","ç":"c"}
    for k, v in repls.items():
        s = s.replace(k, v)
    return re.sub(r"\s+", " ", s)


def _classificar_slug(tarefa: str, etiquetas_raw=None) -> str | None:
    """Devolve o slug da tipologia (ou None). Prioriza:
       1. Etiqueta Fracttal (se houver e bater);
       2. Regex no texto da Tarefa."""
    # 1) Etiqueta explícita do Fracttal
    if etiquetas_raw:
        s = str(etiquetas_raw).strip()
        if s.startswith("["):
            try:
                arr = json.loads(s.replace("'", '"'))
                if isinstance(arr, list):
                    for v in arr:
                        v_norm = _norm(v)
                        for slug, meta in META.items():
                            if _norm(meta["label"]) in v_norm or slug in v_norm:
                                return slug
            except Exception:
                pass
    # 2) Regex no texto da Tarefa
    t = _norm(tarefa)
    if not t:
        return None
    for slug, pattern in RULES:
        if re.search(pattern, t):
            return slug
    return None


def _classificar_modalidade(tarefa: str) -> str:
    """Pra Religamentos: 'remoto' ou 'local'."""
    if REMOTO_RE.search(tarefa or ""):
        return "remoto"
    return "local"


def _classificar_status(estado: str) -> str:
    e = (estado or "").lower()
    if any(t in e for t in STATUS_FINALIZADO):
        return "finalizada"
    if "paus" in e:
        return "pausada"
    if "progress" in e or "andamento" in e or "execu" in e:
        return "emProgresso"
    if "verifica" in e:
        return "verificacao"
    return "naoIniciada"


def _is_cancelada(estado: str) -> bool:
    e = (estado or "").lower()
    return any(t in e for t in STATUS_CANCELADO)


def _is_finalizada(estado: str) -> bool:
    return _classificar_status(estado) == "finalizada"


def _is_em_aberto(estado: str) -> bool:
    return _classificar_status(estado) in ("naoIniciada", "emProgresso", "pausada", "verificacao")


def _parse_data(v):
    if v in (None, ""):
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, (int, float)):
        try:
            return (dt.datetime(1899, 12, 30) + dt.timedelta(days=float(v))).date()
        except Exception:
            return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(s[:19], fmt).date()
        except Exception:
            continue
    return None


def _semana_iso_str(d: dt.date | None) -> str:
    if not d:
        return ""
    _, w, _ = d.isocalendar()
    return f"W{w:02d}"


# ════════════════════════════════════════════════════════════════════
# Leitor de BD
# ════════════════════════════════════════════════════════════════════
def ler_bd(xlsx_path: Path) -> tuple[list, int]:
    """Lê OS/tarefas via API Fracttal (fonte_bd_api), exceto canceladas. Devolve lista de dicts.
    Migrado de BD_Relatório Semanal.xlsx → API (sem dependência do xlsx / OneDrive)."""
    try:
        import fonte_bd_api
        df = fonte_bd_api.df_semanal()
        df = df.astype(object).where(df.notna(), None)   # NaN/NaT -> None (igual ao openpyxl)
    except Exception as e:
        _log(f"ERRO ao carregar OS da API: {e}")
        return [], 0

    header = list(df.columns)
    rows_iter = (tuple(x) for x in df.itertuples(index=False, name=None))

    def idx(name):
        try:
            return header.index(name)
        except ValueError:
            return None

    cols = {
        "OSs ID":            idx("OSs ID"),
        "Status":            idx("Status"),
        "Estado da Tarefa":  idx("Estado da Tarefa"),
        "Tarefa":            idx("Tarefa"),
        "Etiquetas":         idx("Etiquetas"),
        "Ativo":             idx("Ativo"),
        "Equipe":            idx("Equipe"),
        "Responsável":       idx("Responsável"),
        "Data Programada":   idx("Data Programada"),
        "Data de criação":   idx("Data de criação") or idx("Data Criada") or idx("Data criação") or idx("Data de Criação da OS"),
        "Data inicial":      idx("Data inicial") or idx("Data Inicial"),
        "Data Final":        idx("Data Final") or idx("Data final") or idx("Data de finalização") or idx("Data de finalização da OS"),
        "Criticidade":       idx("Criticidade"),
        "Criado por":        idx("Criado por") or idx("Criado Por"),
        "id_work_order":     idx("id_work_order") or idx("ID Work Order"),
        "% Concluída":       idx("% Concluída"),
    }

    if cols["Estado da Tarefa"] is None or cols["Tarefa"] is None:
        _log(f"ERRO: colunas obrigatórias ausentes. Header: {header}")
        return [], 0

    out = []
    vistos = set()  # dedupa OSs por osId — BD tem 1 linha por tarefa, queremos 1 entrada por OS
    total = 0
    for r in rows_iter:
        total += 1
        estado = (r[cols["Estado da Tarefa"]] or "").strip() if cols["Estado da Tarefa"] is not None else ""
        if not estado or _is_cancelada(estado):
            continue
        # FIX 2026-06-15 (task #121): também filtra OSs cuja OS PAI está cancelada
        # no Fracttal (ex: OS 7802 cancelada mas Estado da Tarefa ficou "Não Iniciada").
        if cols["Status"] is not None:
            status_os = (r[cols["Status"]] or "").strip()
            if status_os and _is_cancelada(status_os):
                continue
            # Se OS pai = Finalizado mas Estado Tarefa não atualizou, força Finalizada
            # (ex: OS 7862 Religamento finalizada mas Estado ainda "Não Iniciada")
            if status_os and ("finaliz" in status_os.lower() or "conclu" in status_os.lower()):
                estado = "Finalizada"
        # HEURÍSTICA: Em Progresso + 100% concluída = Em Verificação
        if cols["% Concluída"] is not None:
            pct_raw = r[cols["% Concluída"]]
            try:
                pct_val = float(pct_raw) if pct_raw not in (None, "") else 0.0
            except (ValueError, TypeError):
                pct_val = 0.0
            est_lower = estado.lower()
            if ("progress" in est_lower or "execu" in est_lower) and pct_val >= 100:
                estado = "Em Verificação"
        tarefa = (r[cols["Tarefa"]] or "") if cols["Tarefa"] is not None else ""
        if not tarefa:
            continue
        etiq = r[cols["Etiquetas"]] if cols["Etiquetas"] is not None else None
        slug = _classificar_slug(tarefa, etiq)
        if not slug:
            continue

        data_prog = _parse_data(r[cols["Data Programada"]]) if cols["Data Programada"] is not None else None
        data_criacao = _parse_data(r[cols["Data de criação"]]) if cols["Data de criação"] is not None else None
        data_final = _parse_data(r[cols["Data Final"]]) if cols["Data Final"] is not None else None

        # Filtro: ignora OSs criadas antes de DATA_CORTE_MIN (default: 2026-01-01)
        # Sem data de criação? mantém (não dá pra avaliar).
        if data_criacao is not None:
            try:
                d_cri = data_criacao.date() if hasattr(data_criacao, "date") else data_criacao
                if d_cri < DATA_CORTE_MIN:
                    continue
            except Exception:
                pass

        # Task #123: Data inicial e Criado por (responsável pela abertura)
        data_inicial = _parse_data(r[cols["Data inicial"]]) if cols["Data inicial"] is not None else None
        criado_por = (r[cols["Criado por"]] or "") if cols["Criado por"] is not None else ""

        os_id = r[cols["OSs ID"]] if cols["OSs ID"] is not None else None
        id_wo = r[cols["id_work_order"]] if cols["id_work_order"] is not None else None
        link = LINK_FRACTTAL.format(id=id_wo) if id_wo else ""

        item = {
            "osId":           str(os_id) if os_id else "",
            "ativo":          (r[cols["Ativo"]] or "") if cols["Ativo"] is not None else "",
            "equipe":         (r[cols["Equipe"]] or "") if cols["Equipe"] is not None else "",
            "responsavel":    (r[cols["Responsável"]] or "") if cols["Responsável"] is not None else "",
            "criadoPor":      criado_por,
            "supervisor":     (r[cols["Responsável"]] or "") if cols["Responsável"] is not None else "",
            "status":         estado,
            "tarefa":         tarefa,
            "criticidade":    (r[cols["Criticidade"]] or "") if cols["Criticidade"] is not None else "",
            "dataProgramada": data_prog.isoformat() if data_prog else "",
            "dataCriacao":    data_criacao.isoformat() if data_criacao else "",
            "dataInicial":    data_inicial.isoformat() if data_inicial else "",
            "dataFinal":      data_final.isoformat() if data_final else "",
            "linkFracttal":   link,
            "_slug":          slug,
            "_estado":        estado,
            "_data_prog":     data_prog,
            "_data_criacao":  data_criacao,
            "_data_inicial":  data_inicial,
            "_data_final":    data_final,
        }
        # Task #123: calcula horas até abrir (criação→início) e até fechar (início→final)
        try:
            if data_criacao and data_inicial:
                delta_ab = (data_inicial - data_criacao).total_seconds() / 3600.0
                item["horasAteAbrir"] = round(max(0, delta_ab), 1)
            if data_inicial and data_final:
                delta_fc = (data_final - data_inicial).total_seconds() / 3600.0
                item["horasAteFechar"] = round(max(0, delta_fc), 1)
        except Exception:
            pass
        if slug == "religamentos":
            item["modalidade"] = _classificar_modalidade(tarefa)
        # Dedup: só inclui se ainda não vimos esse osId
        os_id_key = item["osId"]
        if os_id_key and os_id_key in vistos:
            continue
        if os_id_key:
            vistos.add(os_id_key)
        out.append(item)

    return out, total


# ════════════════════════════════════════════════════════════════════
# Cálculo de KPIs / agrupamentos por tipologia
# ════════════════════════════════════════════════════════════════════
def calcular_tipologia(slug: str, todas: list, hoje: dt.date) -> dict:
    meta = META[slug]
    itens = [o for o in todas if o["_slug"] == slug]
    d30 = hoje - dt.timedelta(days=30)
    d7  = hoje - dt.timedelta(days=7)

    em_aberto_lst = [o for o in itens if _is_em_aberto(o["_estado"])]
    finaliz_lst   = [o for o in itens if _is_finalizada(o["_estado"])]
    finaliz_30d   = [o for o in finaliz_lst if o["_data_final"] and o["_data_final"] >= d30]
    finaliz_7d    = [o for o in finaliz_lst if o["_data_final"] and o["_data_final"] >= d7]

    # Semana corrente (ISO da segunda)
    mon = hoje - dt.timedelta(days=hoje.weekday())
    sun = mon + dt.timedelta(days=6)
    semana_lst = [o for o in itens if o["_data_prog"] and mon <= o["_data_prog"] <= sun]

    # Atrasadas: em aberto + data prog no passado
    atrasadas = [o for o in em_aberto_lst if o["_data_prog"] and o["_data_prog"] < hoje]

    # MTTR (horas): média de (Data Final − Data Criação) nas últimas 30d finalizadas
    mttr_horas = None
    if finaliz_30d:
        diffs = []
        for o in finaliz_30d:
            if o["_data_criacao"] and o["_data_final"]:
                delta = (o["_data_final"] - o["_data_criacao"]).total_seconds() / 3600.0
                if 0 <= delta <= 24*365:  # sane filter
                    diffs.append(delta)
        if diffs:
            mttr_horas = sum(diffs) / len(diffs)

    mttr_label = ""
    if mttr_horas is not None:
        h = int(mttr_horas)
        m = int(round((mttr_horas - h) * 60))
        if h >= 24:
            d = h // 24
            h2 = h % 24
            mttr_label = f"{d}d {h2}h"
        elif h > 0:
            mttr_label = f"{h}h {m}min"
        else:
            mttr_label = f"{m}min"

    # Tendência 4 semanas (criadas vs finalizadas)
    semanas = []
    for i in range(3, -1, -1):  # W-3 .. W0
        ini = mon - dt.timedelta(days=7 * i)
        fim = ini + dt.timedelta(days=6)
        criadas = sum(1 for o in itens if o["_data_criacao"] and ini <= o["_data_criacao"] <= fim)
        finalizadas = sum(1 for o in itens if o["_data_final"] and ini <= o["_data_final"] <= fim)
        semanas.append({
            "semana": _semana_iso_str(ini),
            "criadas": criadas,
            "finalizadas": finalizadas,
        })

    # Top ofensores
    cl_aberto = Counter()
    rs_aberto = Counter()
    cl_total  = Counter()
    rs_total  = Counter()
    for o in itens:
        eq = (o.get("equipe") or "(sem equipe)").strip() or "(sem equipe)"
        rs = (o.get("responsavel") or "(sem responsável)").strip() or "(sem responsável)"
        cl_total[eq] += 1
        rs_total[rs] += 1
        if _is_em_aberto(o["_estado"]):
            cl_aberto[eq] += 1
            rs_aberto[rs] += 1

    def top5(total_cnt: Counter, aberto_cnt: Counter):
        return [
            {"nome": k, "total": n, "emAberto": aberto_cnt.get(k, 0)}
            for k, n in total_cnt.most_common(5)
        ]

    porStatus = Counter()
    for o in em_aberto_lst:
        porStatus[_classificar_status(o["_estado"])] += 1

    porEquipe = Counter()
    for o in em_aberto_lst:
        porEquipe[(o.get("equipe") or "(sem equipe)").strip() or "(sem equipe)"] += 1

    oss_publico = []
    for o in em_aberto_lst:
        d = {k: v for k, v in o.items() if not k.startswith("_")}
        d["atrasada"] = bool(o["_data_prog"] and o["_data_prog"] < hoje)
        oss_publico.append(d)
    oss_publico.sort(key=lambda x: (not x.get("atrasada"), x.get("dataProgramada") or "9999"))

    # ── HISTÓRICO: OSs FINALIZADAS nos últimos 90 dias ──
    # (Canceladas já foram filtradas em ler_bd — nunca chegam aqui.)
    # Pra dar visão de backlog gerenciado, não só status atual.
    d90 = hoje - dt.timedelta(days=90)
    finaliz_90d = [o for o in itens
                   if o["_data_final"] and o["_data_final"] >= d90]
    historico_publico = []
    for o in finaliz_90d[:150]:  # limita pra não pesar o JSON
        d = {k: v for k, v in o.items() if not k.startswith("_")}
        d["atrasada"] = False
        historico_publico.append(d)
    # Mais recente primeiro
    historico_publico.sort(key=lambda x: x.get("dataFinal") or "0000", reverse=True)

    out = {
        "label": meta["label"],
        "icone": meta["icone"],
        "cor": meta["cor"],
        "kpis": {
            "total":             len(itens),
            "emAberto":          len(em_aberto_lst),
            "atrasadas":         len(atrasadas),
            "concluidas30d":     len(finaliz_30d),
            "concluidas7d":      len(finaliz_7d),
            "naSemanaCorrente":  len(semana_lst),
        },
        "mttr": {
            "horas":   round(mttr_horas, 2) if mttr_horas is not None else None,
            "label":   mttr_label,
            "amostra": len(finaliz_30d),
        },
        "tendencia4Semanas": semanas,
        "topOfensores": {
            "clusters":     top5(cl_total, cl_aberto),
            "responsaveis": top5(rs_total, rs_aberto),
        },
        "total":      len(em_aberto_lst),
        "atrasadas":  len(atrasadas),
        "porStatus":  {k: porStatus.get(k, 0) for k in ("naoIniciada","emProgresso","pausada","verificacao")},
        "porEquipe":  dict(porEquipe),
        "oss":        oss_publico,
        # Histórico de FINALIZADAS dos últimos 90 dias (max 150 itens).
        # Usado pra toggle "Em aberto / Histórico" no frontend.
        "ossHistorico": historico_publico,
        "historicoTotal": len(finaliz_90d),
    }

    if slug == "religamentos":
        rem_total = sum(1 for o in itens if o.get("modalidade") == "remoto")
        loc_total = sum(1 for o in itens if o.get("modalidade") == "local")
        rem_aberto = sum(1 for o in em_aberto_lst if o.get("modalidade") == "remoto")
        loc_aberto = sum(1 for o in em_aberto_lst if o.get("modalidade") == "local")
        clasf = rem_total + loc_total
        out["subClassificacao"] = {
            "remoto":         rem_total,
            "local":          loc_total,
            "remotoEmAberto": rem_aberto,
            "localEmAberto":  loc_aberto,
            "pctRemoto":      int(round(rem_total / clasf * 100)) if clasf else 0,
            "alerta":         loc_aberto > 0,
        }
        # Task #123: Ranking de demora (abertura + fechamento) e abridores
        remotos = [o for o in itens if o.get("modalidade") == "remoto"]
        # Por abridor (criadoPor): conta total
        from collections import Counter as _Cnt
        por_abridor = _Cnt()
        for o in remotos:
            ab = (o.get("criadoPor") or "").strip() or "(sem dado)"
            por_abridor[ab] += 1
        # Top 10 mais demorados pra abrir (horasAteAbrir)
        com_demora_ab = [o for o in remotos if o.get("horasAteAbrir") is not None]
        com_demora_ab.sort(key=lambda x: x.get("horasAteAbrir", 0), reverse=True)
        top_demora_abrir = [{
            "osId":         o.get("osId"),
            "ativo":        o.get("ativo"),
            "criadoPor":    o.get("criadoPor"),
            "responsavel":  o.get("responsavel"),
            "horas":        o.get("horasAteAbrir"),
            "linkFracttal": o.get("linkFracttal"),
        } for o in com_demora_ab[:10]]
        # Top 10 mais demorados pra fechar (horasAteFechar)
        com_demora_fc = [o for o in remotos if o.get("horasAteFechar") is not None]
        com_demora_fc.sort(key=lambda x: x.get("horasAteFechar", 0), reverse=True)
        top_demora_fechar = [{
            "osId":         o.get("osId"),
            "ativo":        o.get("ativo"),
            "criadoPor":    o.get("criadoPor"),
            "responsavel":  o.get("responsavel"),
            "horas":        o.get("horasAteFechar"),
            "linkFracttal": o.get("linkFracttal"),
        } for o in com_demora_fc[:10]]
        # Médias
        med_abrir = round(sum(o["horasAteAbrir"] for o in com_demora_ab) / len(com_demora_ab), 1) if com_demora_ab else 0
        med_fechar = round(sum(o["horasAteFechar"] for o in com_demora_fc) / len(com_demora_fc), 1) if com_demora_fc else 0
        out["rankingDemora"] = {
            "topAbrir":         top_demora_abrir,
            "topFechar":        top_demora_fechar,
            "medHorasAbrir":    med_abrir,
            "medHorasFechar":   med_fechar,
            "amostraAbrir":     len(com_demora_ab),
            "amostraFechar":    len(com_demora_fc),
            "topAbridores":     [{"nome": n, "total": t} for n, t in por_abridor.most_common(10)],
        }

    return out


def montar_verificacao(itens_em_aberto, hoje):
    verif = [o for o in itens_em_aberto if _classificar_status(o["_estado"]) == "verificacao"]
    porEq = Counter()
    porRs = Counter()
    pub = []
    for o in verif:
        eq = (o.get("equipe") or "(sem equipe)").strip() or "(sem equipe)"
        rs = (o.get("responsavel") or "(sem responsável)").strip() or "(sem responsável)"
        porEq[eq] += 1
        porRs[rs] += 1
        d = {k: v for k, v in o.items() if not k.startswith("_")}
        d["atrasada"] = bool(o["_data_prog"] and o["_data_prog"] < hoje)
        pub.append(d)
    pub.sort(key=lambda x: (not x.get("atrasada"), x.get("dataProgramada") or "9999"))
    return {
        "total":          len(verif),
        "atrasadas":      sum(1 for o in pub if o.get("atrasada")),
        "porEquipe":      dict(porEq),
        "porResponsavel": dict(porRs),
        "oss":            pub,
    }


def gerar_payload(bd_path):
    pasta = _detectar_pasta()
    _log(f"Pasta: {pasta}")
    todas, total_lidas = ler_bd(bd_path)
    _log(f"  -> {total_lidas} linhas no BD; {len(todas)} classificadas (nao canceladas)")
    hoje = dt.date.today()
    # Semana corrente (ini = segunda, fim = domingo)
    dow = hoje.weekday()
    ini = hoje - dt.timedelta(days=dow)
    fim = ini + dt.timedelta(days=6)
    tipologias = {}
    for slug in META:
        tipologias[slug] = calcular_tipologia(slug, todas, hoje)
        t = tipologias[slug]
        _log(f"  * {t['label']:30s}: total={t['kpis']['total']} aberto={t['kpis']['emAberto']} atrasadas={t['kpis']['atrasadas']}")
    em_aberto_publicas = [o for o in todas if _is_em_aberto(o["_estado"])]
    oss_publicas = []
    for o in em_aberto_publicas:
        d = {k: v for k, v in o.items() if not k.startswith("_")}
        oss_publicas.append(d)
    d90 = hoje - dt.timedelta(days=90)
    finaliz_90d = [o for o in todas if o["_data_final"] and o["_data_final"] >= d90]
    historico_publico = []
    for o in finaliz_90d[:150]:
        d = {k: v for k, v in o.items() if not k.startswith("_")}
        d["atrasada"] = False
        historico_publico.append(d)
    em_aberto = [o for o in todas if _is_em_aberto(o["_estado"])]
    verificacao = montar_verificacao(em_aberto, hoje)
    _log(f"  -> {verificacao['total']} OSs em verificacao")
    payload = {
        "geradoEm":       dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fonte":          "BD_Relatorio Semanal.xlsx",
        "semana":         f"{ini.isoformat()} .. {fim.isoformat()}",
        "tipologias":     tipologias,
        "ossPublicas":    oss_publicas,
        "ossHistorico":   historico_publico,
        "historicoTotal": len(finaliz_90d),
        "totalGeral":     len(todas),
        "verificacao":    verificacao,
    }
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--bd", default=None)
    args = ap.parse_args()
    pasta = _detectar_pasta()
    bd = Path(args.bd) if args.bd else (pasta / "BD_Relatório Semanal.xlsx")
    if not bd.exists():
        _log(f"[ERROR] BD não encontrado: {bd}")
        sys.exit(1)
    _log(f"Lendo BD: {bd}")
    payload = gerar_payload(bd)
    out = pasta / "etiquetas.json"
    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        _log(f"Gravado: {out}")


if __name__ == "__main__":
    main()
