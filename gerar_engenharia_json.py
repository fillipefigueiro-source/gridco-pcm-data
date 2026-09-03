# -*- coding: utf-8 -*-
"""
Gera o engenharia.json — a base do módulo Confiabilidade do painel.

O que ele produz, por ativo com corretiva na janela (30 dias por padrão):
  · as dimensões do Engenheiro Preventivo que dá para medir hoje:
      A frequência (corretivas na janela), B aceleração (últimos 7 dias),
      D pares (acima do P90 da família). A dimensão C (mesma causa) fica cega
      até a classificação de falha ser preenchida nas OS — hoje ~8%.
  · o nível (crítico / atenção / monitorar) = maior dimensão atingida,
    com a criticidade A subindo um degrau.
  · MTBF / MTTR / disponibilidade do ativo, casados do confiabilidade.json.
  · as OS que pesaram, com o texto da tarefa, tipo (tasks_types_2), a nota do
    técnico e quem pediu — é o que alimenta o pré-preenchimento do FMEA.

Duas decisões que importam:
  1. SERVIÇO NÃO É FALHA. "Limpeza dos sensores", "ensaio nos TCs", "revisão do
     projeto" vêm do Fracttal como Corretiva, mas são serviço. Medido em 03/09/26:
     o ativo mais "crítico" do parque tinha 5 de 5 OS assim. Aqui cada OS recebe
     `servico: true|false` por padrão no texto, e a dimensão A conta só falhas.
     O ativo continua na lista (marcado `soServico`) para a engenharia
     reclassificar — esconder o erro não conserta o cadastro.
  2. A criticidade é PROXY por família até a matriz do cap. 4 ser preenchida.
     O arquivo diz isso (`critProxy: true`), e a tela repete.

Reaproveita o FracttalClient de gerar_bd_via_api.py e os helpers de
gerar_gestao_pcm_json.py. Não altera nenhum dos dois.
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import re
import statistics
import sys
from datetime import datetime, timedelta, timezone

import gerar_bd_via_api as bd
import gerar_gestao_pcm_json as gp

JANELA_DIAS = int(os.environ.get("ENG_JANELA_DIAS", "30"))
SAIDA = os.environ.get("ENG_SAIDA", "engenharia.json")
TIPOS_FALHA = {"corretiva", "corretiva emergencial"}
MAX_OS_POR_ATIVO = 8

# Serviço registrado como corretiva. Casado no texto da tarefa + nota do técnico.
RX_SERVICO = re.compile(
    r"limpeza|ensaio|teste\b|testes\b|revis[ãa]o|readequa|projeto|avcb|ajuste de antena|"
    r"\breset\b|vistoria|inventári|levantamento|instala[çc][ãa]o de|treinamento|acompanhamento",
    re.I)
RX_TESTE = re.compile(r"\bTESTE\b", re.I)
RX_COD = re.compile(r"\{\s*([A-Z0-9][A-Z0-9\-\.]+)\s*\}")

# Criticidade proxy por família: 5 critérios 0–3 multiplicados (cap. 4).
# 0–55 = A · 56–161 = B · 162–243 = C. Vale até a matriz real existir.
CRIT_PROXY = {"Transformador": (1, 1, 2, 1, 1), "Cabine": (1, 2, 2, 1, 1),
              "Inversor": (2, 2, 2, 2, 2), "QGBT": (2, 2, 2, 2, 2),
              "Tracker": (3, 3, 3, 2, 3), "Outros": (2, 3, 3, 2, 3)}


def log(msg, level="INFO"):
    print(f"[{datetime.now():%H:%M:%S}] {level}: {msg}", flush=True)


def familia(cod: str, nome: str) -> str:
    s = f"{cod} {nome}"
    if re.search(r"INV|inversor", s, re.I): return "Inversor"
    if re.search(r"TRK|ETKR|tracker", s, re.I): return "Tracker"
    if re.search(r"CAB|cabine", s, re.I): return "Cabine"
    if re.search(r"TRF|SKID|transformador", s, re.I): return "Transformador"
    if re.search(r"QGBT", s, re.I): return "QGBT"
    return "Outros"


def criticidade(fam: str):
    v = 1
    for x in CRIT_PROXY.get(fam, (2, 2, 2, 2, 2)):
        v *= x
    return v, ("A" if v <= 55 else "B" if v <= 161 else "C")


def _dt(v):
    """creation_date do Fracttal vem ISO com fuso; devolve aware em UTC."""
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _usina_curta(u: str) -> str:
    p = [x.strip() for x in str(u or "").split(" - ")]
    return " - ".join(p[1:]) if len(p) > 1 else str(u or "")


def coletar(client, inicio):
    """Corretivas criadas a partir de `inicio`, agrupadas por código de ativo."""
    por = collections.defaultdict(list)
    bruto = 0
    sem_cod = 0
    for row in client.paginar("work_orders", page_size=100):
        bruto += 1
        if bruto % 4000 == 0:
            log(f"  ... {bruto} linhas")
        tipo = str(row.get("tasks_log_task_type_main") or row.get("tasks_types_main_description") or "").strip().lower()
        if tipo not in TIPOS_FALHA:
            continue
        cr = _dt(row.get("creation_date"))
        if not cr or cr < inicio:
            continue
        nome_raw = str(row.get("items_log_description") or row.get("items_description") or "")
        if RX_TESTE.search(nome_raw):
            continue
        m = RX_COD.search(nome_raw)
        cod = m.group(1) if m else str(row.get("code") or "").strip()
        if not cod:
            sem_cod += 1
            continue
        tarefa = str(row.get("description") or row.get("tasks_description") or "")
        nota = str(row.get("task_note") or "").strip()
        por[cod].append({
            "cod": cod,
            "nome": RX_COD.sub("", nome_raw).strip(),
            "usinaFull": str(row.get("groups_1_description") or row.get("items_log_groups_1_description") or ""),
            "cluster": str(row.get("groups_2_description") or row.get("items_log_groups_2_description") or ""),
            "pai": str(row.get("items_log_parent_description") or ""),
            "cr": cr,
            "os": str(row.get("wo_folio") or row.get("id_work_order") or ""),
            "t": tarefa[:80],
            "tp2": str(row.get("tasks_types_2_description") or ""),
            "nota": nota[:220],
            "quem": str(row.get("requested_by") or row.get("created_by") or "").strip(),
            "prio": str(row.get("priorities_description") or ""),
            "st": str(row.get("task_status") or ""),
            "servico": bool(RX_SERVICO.search(tarefa + " " + nota)),
        })
    log(f"  -> {bruto} linhas brutas | {sum(len(v) for v in por.values())} corretivas na janela | "
        f"{len(por)} ativos | {sem_cod} sem código (descartadas)")
    return por


def carregar_confiabilidade():
    try:
        with open("confiabilidade.json", encoding="utf-8") as f:
            cf = json.load(f)
    except Exception as e:
        log(f"confiabilidade.json indisponível ({e}) — segue sem MTBF/MTTR", "WARN")
        return {}, [], []
    ativos = []
    clientes = []
    usinas = []
    for c in cf.get("clientes", []):
        clientes.append({"cliente": c["cliente"], "mtbf": c.get("mtbf"), "mttr": c.get("mttr"),
                         "disp": c.get("disp"), "n": c.get("n", 0), "usinas": len(c.get("usinas", []))})
        for u in c.get("usinas", []):
            us = u.get("ativos", [])
            usinas.append({"usina": re.sub(r"\s+", " ", u["usina"]).strip(), "cliente": c["cliente"],
                           "mtbf": u.get("mtbf"), "mttr": u.get("mttr"), "disp": u.get("disp"),
                           "n": u.get("n", 0), "ativos": len(us),
                           "abaixo85": sum(1 for a in us if a.get("disp") is not None and a["disp"] < 0.85)})
            for a in us:
                if a.get("ativo"):
                    ativos.append({"ativo": a["ativo"], "mtbf": a.get("mtbf"), "mttr": a.get("mttr"),
                                   "disp": a.get("disp"), "n": a.get("n", 0)})
    clientes.sort(key=lambda x: (x["disp"] is None, x["disp"] or 0))
    usinas.sort(key=lambda x: -x["n"])
    return ativos, clientes, usinas


def casar_conf(nome: str, ativos_conf):
    """Casa por nome (26 primeiros caracteres, sem caixa). O confiabilidade.json
    não guarda o código do ativo — quando guardar, trocar por igualdade."""
    n = nome.lower()
    for a in ativos_conf:
        an = a["ativo"].lower()
        if an[:26] in n or n[:26] in an:
            return a
    return None


def carregar_equipe():
    try:
        with open("alertas_destinatarios.json", encoding="utf-8") as f:
            mapa = json.load(f).get("mapa", {})
    except Exception as e:
        log(f"alertas_destinatarios.json indisponível ({e})", "WARN")
        return []
    por = collections.defaultdict(list)
    for cl, v in mapa.items():
        for e in (v if isinstance(v, list) else [v]):
            por[e].append(cl)
    return [{"email": e, "nome": e.split("@")[0].replace(".", " ").title(), "clusters": len(c)}
            for e, c in por.items()]


def main():
    bd.carregar_env()
    cid = os.environ.get("FRACTTAL_CLIENT_ID") or bd.CLIENT_ID
    csec = os.environ.get("FRACTTAL_CLIENT_SECRET") or bd.CLIENT_SECRET
    if not cid or not csec:
        log("Sem FRACTTAL_CLIENT_ID / SECRET", "ERRO")
        return 2
    client = bd.FracttalClient(cid, csec, bd.BASE_URL)
    if hasattr(client, "autenticar"):
        client.autenticar()

    agora = datetime.now(timezone.utc)
    inicio = agora - timedelta(days=JANELA_DIAS)
    log(f"Corretivas desde {inicio:%d/%m/%Y} ({JANELA_DIAS} dias)...")
    por = coletar(client, inicio)

    ativos_conf, clientes, usinas = carregar_confiabilidade()
    equipe = carregar_equipe()

    # P90 por família, contando SÓ falhas (serviço fora)
    fam_ns = collections.defaultdict(list)
    for cod, rs in por.items():
        nf = sum(1 for r in rs if not r["servico"])
        if nf:
            fam_ns[familia(cod, rs[0]["nome"])].append(nf)
    p90 = {f: sorted(n)[int(round(.9 * (len(n) - 1)))] for f, n in fam_ns.items()}

    lista = []
    crit_dist = collections.Counter()
    for cod, rs in por.items():
        rs.sort(key=lambda r: r["cr"], reverse=True)
        nome = rs[0]["nome"]
        fam = familia(cod, nome)
        cv, cl = criticidade(fam)
        crit_dist[cl] += 1
        falhas = [r for r in rs if not r["servico"]]
        n = len(falhas)
        n7 = sum(1 for r in falhas if (agora - r["cr"]).days <= 7)
        pf = p90.get(fam, 2)
        nivel = ("critico" if (n >= 4 or n7 >= 3) else
                 "atencao" if (n >= 3 or n7 >= 2 or n > pf) else
                 "monitorar" if n >= 2 else None)
        if nivel == "monitorar" and cl == "A":
            nivel = "atencao"
        so_servico = n == 0 and len(rs) >= 2
        if so_servico:
            nivel = "monitorar"       # fica visível para reclassificar, mas não acende
        if not nivel:
            continue
        conf = casar_conf(nome, ativos_conf)
        usina_full = rs[0]["usinaFull"]
        cliente = gp._cliente_de(usina_full) if usina_full else ""
        pai = [s.strip() for s in rs[0]["pai"].split("/") if s.strip()]
        lista.append({
            "cod": cod, "nome": nome[:60], "fam": fam, "crit": cl, "critVal": cv,
            "cliente": cliente, "usina": _usina_curta(usina_full) or (pai[1] if len(pai) > 1 else ""),
            "cluster": rs[0]["cluster"],
            "circuito": " / ".join(pai[2:]) if len(pai) > 2 else "",
            "n30": len(rs), "nFalha": n, "nServico": len(rs) - n, "n7": n7, "p90": pf,
            "nivel": nivel, "soServico": so_servico,
            "mtbf": conf.get("mtbf") if conf else None,
            "mttr": conf.get("mttr") if conf else None,
            "disp": conf.get("disp") if conf else None,
            "os": [{"os": r["os"], "t": r["t"], "tp2": r["tp2"], "nota": r["nota"],
                    "d": r["cr"].astimezone(timezone(timedelta(hours=-3))).strftime("%d/%m %H:%M"),
                    "st": r["st"], "quem": r["quem"], "prio": r["prio"], "servico": r["servico"]}
                   for r in rs[:MAX_OS_POR_ATIVO]],
        })
    ordem = {"critico": 0, "atencao": 1, "monitorar": 2}
    lista.sort(key=lambda a: (ordem[a["nivel"]], a["soServico"], -a["nFalha"], -a["n30"]))

    disp = [a["disp"] for a in ativos_conf if a.get("disp") is not None]
    mt = [a["mtbf"] for a in ativos_conf if a.get("mtbf")]
    tr = [a["mttr"] for a in ativos_conf if a.get("mttr")]
    kpi = {"disp": round(100 * statistics.median(disp), 1) if disp else None,
           "mtbf": round(statistics.median(mt)) if mt else None,
           "mttr": round(statistics.median(tr), 1) if tr else None,
           "abaixo85": sum(1 for x in disp if x < 0.85), "ativosConf": len(disp),
           "corretivas": sum(len(v) for v in por.values()), "ativosCorretiva": len(por),
           "ativosSinal": len(lista),
           "criticos": sum(1 for a in lista if a["nivel"] == "critico")}
    saida = {
        "geradoEm": agora.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "periodo": {"dias": JANELA_DIAS, "de": inicio.strftime("%d/%m/%Y"), "ate": agora.astimezone(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y")},
        "kpi": kpi, "p90": p90, "critDist": dict(crit_dist), "critProxy": True,
        "ativos": lista, "clientes": clientes, "usinas": usinas, "equipe": equipe,
    }
    saida["dataHash"] = hashlib.sha256(json.dumps(
        [(a["cod"], a["nivel"], a["n30"], a["n7"]) for a in lista], sort_keys=True).encode()).hexdigest()
    tmp = SAIDA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, SAIDA)
    log(f"{SAIDA}: {len(lista)} ativos com sinal ({kpi['criticos']} críticos) | "
        f"{kpi['corretivas']} corretivas | {os.path.getsize(SAIDA)/1024:.0f} KB | hash {saida['dataHash'][:8]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
