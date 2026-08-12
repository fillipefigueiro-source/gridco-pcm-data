# -*- coding: utf-8 -*-
"""
aprender_duracoes.py — Melhoria 6, nível 1 (duração aprendida)
--------------------------------------------------------------
Lê o tempo de execução REAL das tarefas finalizadas (campo `real_duration` da
API, que o BD expõe como "Tempo de execução") e grava `duracoes_aprendidas.json`
com a duração típica por categoria × usina.

Por que existe: em 31/07/2026 o PCM fez essa análise À MÃO uma vez, sobre 26.267
tarefas, e descobriu que a MPA estava subestimada em 2,6× (1,5 h no motor contra
3,95 h reais). A correção virou constante fixa e GLOBAL — toda MPA vale 4,0 h,
seja em Altair ou em Marabá. Este script troca a constante por medição, mantém
a granularidade e recalcula toda semana.

Decisões aplicadas (pacote de 08/08/2026):
  29 — substitui a estimativa, com piso de n=5 amostras e teto de 2× de variação
       contra a constante do motor (protege de outlier que passou pelo IQR)
  30 — granularidade: categoria × usina  →  categoria × cluster  →  global
  32 — roda na sexta ANTES da geração; grava JSON que o motor lê

Uso:
    py -3 aprender_duracoes.py              # calcula e grava
    py -3 aprender_duracoes.py --dry-run    # só mostra
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
JANELA_DIAS = int(os.environ.get("PCM_APRENDE_JANELA_DIAS", 180))
MIN_AMOSTRAS = int(os.environ.get("PCM_APRENDE_MIN_N", 5))       # decisão 29
TETO_VARIACAO = float(os.environ.get("PCM_APRENDE_TETO", 2.0))   # decisão 29

# Constantes atuais do motor (programacao_v7.estimate_h) — base do teto de 2×
BASE_MOTOR = {"MPM": 1.10, "MPS": 1.30, "MPQ": 0.75, "MPA": 4.0,
              "MPW": 0.75, "HANDOVER": 0.65, "OUTRA": 1.5}


def log(m):
    print(f"[{dt.datetime.now():%H:%M:%S}] {m}", flush=True)


def _pasta_dados():
    p = os.environ.get("PCM_PROG_DIR", "").strip()
    if p and os.path.isdir(p):
        return p
    c = os.path.join(os.path.expanduser("~"), "GRID CO", "GRID CO. - Gridco",
                     "4. O&M", "11.Pré-Operação", "6. PCM", "09. Programação Semanal")
    return c if os.path.isdir(c) else AQUI


def categoria(tarefa):
    t = str(tarefa or "").lower()
    for c in ("mpa", "mps", "mpt", "mpm", "mpq", "mpw"):
        if re.search(rf"\b{c}\b", t):
            return c.upper()
    if "handover" in t:
        return "HANDOVER"
    if "anual" in t:
        return "MPA"
    if "semestral" in t:
        return "MPS"
    if "mensal" in t:
        return "MPM"
    return "OUTRA"


def chave_usina(s):
    """Mesma normalização do motor: tira ' - UF' e converte 100->1."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\s*-\s*[a-z]{2}\s*$", "", s.strip())
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"\b(\d)00\b", r"\1", s)


def iqr_limpo(vals):
    """Remove outliers por IQR — mesmo método que o PCM validou em 31/07."""
    s = pd.Series(vals, dtype="float64")
    if len(s) < 4:
        return s
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    if iqr <= 0:
        return s
    return s[(s >= q1 - 1.5 * iqr) & (s <= q3 + 1.5 * iqr)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    sys.path.insert(0, AQUI)
    import fonte_bd_api

    log("Lendo tarefas do Fracttal...")
    df = fonte_bd_api.df_semanal()
    log(f"  -> {len(df)} linhas")

    d = df[df["Estado da Tarefa"] == "Finalizados"].copy()
    d["_h"] = pd.to_timedelta(d["Tempo de execução"], errors="coerce").dt.total_seconds() / 3600.0
    d["_dt"] = pd.to_datetime(d["Data Programada"], errors="coerce")
    corte = pd.Timestamp("today").normalize() - pd.Timedelta(days=JANELA_DIAS)
    d = d[(d["_dt"] >= corte) & d["_h"].notna()]
    # apontamento de segundos não é execução: descarta < 3 min e > 24 h
    antes = len(d)
    d = d[(d["_h"] >= 0.05) & (d["_h"] <= 24)]
    log(f"  -> {len(d)} finalizadas com tempo real plausível "
        f"({antes - len(d)} descartadas: < 3 min ou > 24 h)")

    d["_cat"] = d["Tarefa"].apply(categoria)
    d["_usina"] = d["Ativo Classificação 1"].fillna(d["Ativo"]).apply(chave_usina)
    d["_cluster"] = d["Ativo Classificação 2"].fillna("").astype(str).str.strip()

    saida = {"geradoEm": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "janelaDias": JANELA_DIAS, "minAmostras": MIN_AMOSTRAS,
             "tetoVariacao": TETO_VARIACAO,
             "porUsina": {}, "porCluster": {}, "global": {}}
    resumo = []

    rejeitados = []

    def medir(g, cat, rotulo):
        """Média após IQR, com os DOIS guarda-corpos da decisão 29:
        piso de amostras e teto de variação contra a constante do motor.

        O teto não é burocracia: a base tem apontamento de segundos (MPA de
        0,07 h = 4 min em Marabá 2, MPS de 0,13 h em Crateús). Aceitar isso
        faria o motor programar 40 MPAs num dia. Fora da faixa -> mantém a
        constante e registra o motivo."""
        v = iqr_limpo(g["_h"].tolist())
        if len(v) < MIN_AMOSTRAS:
            return None, len(v)
        m = round(float(v.mean()), 2)
        base = BASE_MOTOR.get(cat)
        if base:
            razao = m / base
            if razao > TETO_VARIACAO or razao < 1.0 / TETO_VARIACAO:
                rejeitados.append((cat, rotulo, base, m, len(v), razao))
                return None, len(v)
        return m, len(v)

    # nível 3: global por categoria (a base de comparação)
    for cat, g in d.groupby("_cat"):
        m, n = medir(g, cat, "GLOBAL")
        if m is None:
            continue
        base = BASE_MOTOR.get(cat)
        saida["global"][cat] = {"h": m, "n": n}
        if base:
            resumo.append((cat, "GLOBAL", base, m, n, m / base))

    # nível 2: categoria × cluster
    for (cat, cl), g in d.groupby(["_cat", "_cluster"]):
        if not cl:
            continue
        m, n = medir(g, cat, cl)
        if m is not None:
            saida["porCluster"][f"{cat}|{cl}"] = {"h": m, "n": n}

    # nível 1 (mais específico): categoria × usina
    for (cat, us), g in d.groupby(["_cat", "_usina"]):
        if not us:
            continue
        m, n = medir(g, cat, us)
        if m is not None:
            saida["porUsina"][f"{cat}|{us}"] = {"h": m, "n": n}

    log(f"  -> aprendido: {len(saida['porUsina'])} categoria×usina · "
        f"{len(saida['porCluster'])} categoria×cluster · {len(saida['global'])} global")

    print()
    print("  %-10s %-8s %8s %8s %6s %7s" % ("CATEGORIA", "NÍVEL", "MOTOR", "REAL", "n", "razão"))
    for cat, niv, base, m, n, r in sorted(resumo, key=lambda x: -abs(x[5] - 1)):
        marca = "  <-- fora do teto de 2x" if (r > TETO_VARIACAO or r < 1 / TETO_VARIACAO) else ""
        print("  %-10s %-8s %8.2f %8.2f %6d %6.2fx%s" % (cat, niv, base, m, n, r, marca))

    # exemplos de variação entre usinas — o argumento central da M6
    print()
    print("  Variação entre usinas (o que a constante global esconde):")
    for cat in ("MPA", "MPS", "MPM"):
        its = [(k.split("|", 1)[1], v["h"], v["n"])
               for k, v in saida["porUsina"].items() if k.startswith(cat + "|")]
        if len(its) < 3:
            continue
        its.sort(key=lambda x: x[1])
        g = saida["global"].get(cat, {}).get("h")
        print(f"    {cat} (global {g} h): menor {its[0][1]} h ({its[0][0][:22]}, n={its[0][2]}) "
              f"· maior {its[-1][1]} h ({its[-1][0][:22]}, n={its[-1][2]})")

    if rejeitados:
        print()
        print(f"  REJEITADOS pelo teto de {TETO_VARIACAO:.0f}x (mantêm a constante do motor): "
              f"{len(rejeitados)}")
        for cat, rot, base, m, n, r in sorted(rejeitados, key=lambda x: x[5])[:10]:
            print("    %-9s %-24s motor %.2f h  medido %.2f h  (%.2fx, n=%d)"
                  % (cat, str(rot)[:24], base, m, r, n))
        saida["rejeitados"] = [{"cat": c, "escopo": str(r0), "motor": b, "medido": m,
                                "n": n, "razao": round(rz, 2)}
                               for c, r0, b, m, n, rz in rejeitados]

    if a.dry_run:
        print("\n--dry-run: nada gravado.")
        return 0
    destino = os.path.join(_pasta_dados(), "duracoes_aprendidas.json")
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
    log(f"OK: {os.path.basename(destino)} gravado em {_pasta_dados()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
