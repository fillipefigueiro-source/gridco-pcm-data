# -*- coding: utf-8 -*-
"""
Cascata de disponibilidade por região — gerencial.json.

Reproduz o método do one-pager "Disponibilidade por região" (set/2026):
  · cada TAREFA de OS de religamento entra pela janela Data do Incidente
    (event_date) → Data final (final_date; recuo: wo_final_date; aberta: agora);
  · só as horas DIURNAS (6h–18h, hora de Brasília) contam;
  · o peso é o escopo do código do ativo — UFV inteira = 1, cabine = 1/nº de
    cabines, inversor = 1/nº de inversores (nº vem do operacoes.json);
  · disponibilidade = 1 − Σ(horas ponderadas) ÷ (dias × 12 h × usinas em operação).

A separação da cascata é por COMO o evento foi resolvido, não por causa:
  campo        OS "Religamento" (equipe foi até a usina)
  emergencial  "Religamento" com prioridade alta/urgente ou texto "emergenc"
  remoto       OS "Religamento Remoto" (COS)
  queda        texto "queda/falta de energia", "concessionária", "distribuidora"
  programado   texto "programad", "manobra"
O Fracttal não registra causa de perda; isto é regra de texto e tipo, e a
tela diz isso. Validado contra o one-pager na primeira rodada (ver ESTADO.md).

Não chama a API: recebe os eventos que o gerar_engenharia_json.py já coletou
na mesma paginação (uma passada de 6 min, não duas).
"""
from __future__ import annotations

import io
import json
import os
import re
from datetime import datetime, timedelta, timezone

BR = timezone(timedelta(hours=-3))
SAIDA = os.environ.get("GER_SAIDA", "gerencial.json")
OPERACOES = os.environ.get("OPERACOES_ARQ", "operacoes.json")
INICIO_PADRAO = os.environ.get("GER_INICIO", "2025-11-01")
MAX_EVENTOS = 20000

RX_TOKEN = re.compile(r"\b([A-Z]{2,5}\d{2,3})\b")
RX_QUEDA = re.compile(r"queda de energia|falta de energia|concession[aá]ria|distribuidora|rede da (?:cemig|enel|equatorial|copel|celesc|coelba|neoenergia)", re.I)
RX_PROG = re.compile(r"programad|manobra|desligamento programado|janela de manuten", re.I)
RX_EMERG = re.compile(r"emergenc", re.I)
PRIO_ALTA = {"HIGH", "URGENT", "VERY_HIGH", "ALTA", "URGENTE"}


def log(msg, level="INFO"):
    print(f"[{datetime.now():%H:%M:%S}] {level}: {msg}", flush=True)


def _dt(v):
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def horas_diurnas(ini, fim):
    """Horas do intervalo que caem entre 6h e 18h (Brasília)."""
    if not ini or not fim or fim <= ini:
        return 0.0
    a, b = ini.astimezone(BR), fim.astimezone(BR)
    total = 0.0
    dia = a.replace(hour=0, minute=0, second=0, microsecond=0)
    while dia <= b:
        j0 = dia.replace(hour=6)
        j1 = dia.replace(hour=18)
        lo, hi = max(a, j0), min(b, j1)
        if hi > lo:
            total += (hi - lo).total_seconds() / 3600
        dia += timedelta(days=1)
    return total


def carregar_operacoes():
    try:
        with io.open(OPERACOES, encoding="utf-8") as f:
            d = json.load(f)
    except Exception as e:
        log(f"{OPERACOES} indisponível ({e}) — sem universo, sem cascata", "WARN")
        return None, {}
    usinas = [u for u in d.get("usinas", []) if u.get("status") == "OPERAÇÃO"]
    idx = {}
    for i, u in enumerate(usinas):
        cod = str(u.get("codigo") or "")
        tok = cod.split("-")[-1].strip().upper() if "-" in cod else cod.strip().upper()
        if tok:
            idx[tok] = i
        idx["nome:" + _norm(u["usina"])] = i
    return usinas, idx


def _norm(s):
    s = str(s or "").lower()
    s = re.sub(r"[áàãâ]", "a", s); s = re.sub(r"[éê]", "e", s); s = re.sub(r"[í]", "i", s)
    s = re.sub(r"[óôõ]", "o", s); s = re.sub(r"[ú]", "u", s); s = re.sub(r"ç", "c", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def casar_usina(ev, idx):
    """Índice da usina em operação: pelo token do código do ativo, depois pelo nome."""
    for tok in RX_TOKEN.findall(str(ev.get("cod") or "").upper()):
        if tok in idx:
            return idx[tok]
    full = str(ev.get("usinaFull") or "")
    partes = [p.strip() for p in full.split(" - ")]
    nome = partes[1] if len(partes) >= 2 else full
    k = "nome:" + _norm(nome)
    if k in idx:
        return idx[k]
    # "Boa Esperança do Sul 1 e 2" vs "Boa Esperança do Sul 1": tenta prefixo
    for kk, i in idx.items():
        if kk.startswith("nome:") and _norm(nome) and (kk[5:].startswith(_norm(nome)) or _norm(nome).startswith(kk[5:])):
            return i
    return None


def peso_e_escopo(cod, u):
    """(peso, escopo, aproximado). Escopo pelo sufixo do código do ativo."""
    c = str(cod or "").upper()
    # o token da usina (EBG100, MRV100) pode vir com prefixo de cliente (THPN-EBG100-INVR2.2):
    # o escopo é o que vem DEPOIS do token
    m = RX_TOKEN.search(c)
    suf = c[m.end():].lstrip("-") if m else ""
    if not suf:
        return 1.0, "usina", False
    if suf.startswith("CAB"):
        n = u.get("nCab") or 0
        return (1.0 / n, "cabine", False) if n else (1.0, "cabine", True)
    if suf.startswith("INV"):
        n = u.get("nInv") or 0
        return (1.0 / n, "inversor", False) if n else (1.0, "inversor", True)
    n = u.get("nInv") or 0
    return (1.0 / n, "outro", True) if n else (1.0, "outro", True)


def categoria(ev):
    """Regra calibrada contra o one-pager de set/2026 (BD Relatório Semanal):
    a coluna que reproduz a divisão é "Tarefa → Classificação 1"
    (tasks_types_description): Religamento / Emergencial / Programada /
    QUEDA DE ENERGIA. Remoto é o tipo principal "Religamento Remoto".
    Resíduo conhecido: o PDF tinha remoto 0,63 pp e programado 0,11 pp por
    ajuste manual; por regra saem ~0,05 e ~0,5. Campo/emergencial/queda batem."""
    tipo = str(ev.get("tipo") or "").lower()
    cls1 = str(ev.get("cls1") or "").strip().lower()
    txt = f"{ev.get('tarefa','')} {ev.get('nota','')}"
    if "remoto" in tipo:
        return "remoto"
    if "queda" in cls1 or RX_QUEDA.search(txt):
        return "queda"
    if cls1.startswith("programad") or RX_PROG.search(txt):
        return "programado"
    if cls1.startswith("emergenc") or "emergencial" in tipo or RX_EMERG.search(txt):
        return "emergencial"
    return "campo"


def gerar(eventos_brutos, agora=None):
    agora = agora or datetime.now(timezone.utc)
    usinas, idx = carregar_operacoes()
    if usinas is None:
        return None
    inicio = datetime.fromisoformat(INICIO_PADRAO).replace(tzinfo=BR)
    eventos = []
    sem_usina = 0
    aprox = 0
    canceladas = 0
    abertas_antigas = 0
    for ev in eventos_brutos:
        ini = _dt(ev.get("ini"))
        if not ini or ini < inicio:
            continue
        # OS cancelada (status 4) ou tarefa cancelada não é parada — como no one-pager
        if ev.get("stWo") == 4 or "cancel" in str(ev.get("st") or "").lower():
            canceladas += 1
            continue
        fim = _dt(ev.get("fim")) or _dt(ev.get("fimWo"))
        aberto = fim is None
        if aberto:
            # sem data final: se é recente, a usina está parada e conta até agora;
            # se é velha, é tarefa esquecida aberta — contaria meses de parada falsa
            if (agora - ini).total_seconds() > 72 * 3600:
                abertas_antigas += 1
                continue
            fim = agora
        i = casar_usina(ev, idx)
        if i is None:
            sem_usina += 1
            continue
        u = usinas[i]
        peso, escopo, ap = peso_e_escopo(ev.get("cod"), u)
        aprox += 1 if ap else 0
        hd = horas_diurnas(ini, fim)
        h24 = max(0.0, (fim - ini).total_seconds() / 3600)
        eventos.append({
            "u": i, "os": str(ev.get("os") or ""), "cat": categoria(ev),
            "ini": ini.astimezone(BR).strftime("%Y-%m-%dT%H:%M"), "fim": fim.astimezone(BR).strftime("%Y-%m-%dT%H:%M"),
            "hDia": round(hd, 3), "h24": round(h24, 3), "peso": round(peso, 4), "escopo": escopo,
            "ativo": str(ev.get("nome") or "")[:50], "cod": str(ev.get("cod") or ""), "aberto": aberto,
        })
    eventos.sort(key=lambda e: e["ini"], reverse=True)
    eventos = eventos[:MAX_EVENTOS]

    # resumo da janela padrão (de INICIO_PADRAO até hoje), para PDF/insights sem JS
    fim_j = agora.astimezone(BR)
    dias = max(1, (fim_j.date() - inicio.date()).days + 1)
    cats = ["campo", "emergencial", "remoto", "queda", "programado"]
    por_u = {}
    for e in eventos:
        d = por_u.setdefault(e["u"], {"rel": 0, "h": 0.0, "hp": 0.0, **{c: 0.0 for c in cats}})
        d["rel"] += 1; d["h"] += e["hDia"]; d["hp"] += e["hDia"] * e["peso"]; d[e["cat"]] += e["hDia"] * e["peso"]
    def bloco(ids):
        n = len(ids)
        den = dias * 12.0 * n if n else 1.0
        hp = sum(por_u.get(i, {}).get("hp", 0.0) for i in ids)
        out = {"usinas": n, "mwp": round(sum(usinas[i].get("mwp") or 0 for i in ids), 1),
               "rel": sum(por_u.get(i, {}).get("rel", 0) for i in ids),
               "h": round(sum(por_u.get(i, {}).get("h", 0.0) for i in ids)),
               "disp": round(100 * (1 - hp / den), 2) if n else None,
               "comRelig": sum(1 for i in ids if i in por_u)}
        for c in cats:
            out[c] = round(100 * sum(por_u.get(i, {}).get(c, 0.0) for i in ids) / den, 2) if n else None
        return out
    regioes = {}
    for i, u in enumerate(usinas):
        regioes.setdefault(u.get("regiao") or "Sem região", []).append(i)
    resumo = {"de": inicio.strftime("%Y-%m-%d"), "ate": fim_j.strftime("%Y-%m-%d"), "dias": dias,
              "portfolio": bloco(list(range(len(usinas)))),
              "regioes": [dict(regiao=r, **bloco(ids)) for r, ids in sorted(regioes.items(), key=lambda kv: (kv[0] == "Sem região", kv[0]))],
              "usinas": [dict(i=i, usina=usinas[i]["usina"], regiao=usinas[i].get("regiao") or "Sem região", cliente=usinas[i].get("cliente"),
                              rel=por_u[i]["rel"], h=round(por_u[i]["h"]), disp=round(100 * (1 - por_u[i]["hp"] / (dias * 12.0)), 2))
                         for i in sorted(por_u, key=lambda i: -por_u[i]["hp"])[:40]]}
    saida = {
        "geradoEm": agora.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "operacoesGeradoEm": (json.load(io.open(OPERACOES, encoding="utf-8")).get("geradoEm") if os.path.exists(OPERACOES) else ""),
        "metodo": {"horas": "diurnas 6h-18h (Brasília)", "peso": "usina=1, cabine=1/nCab, inversor=1/nInv, outro=1/nInv (aproximado)",
                   "janela": "event_date -> final_date (recuo wo_final_date; aberta conta até agora)",
                   "categorias": "por tipo da OS e texto — não é causa"},
        "usinas": [{"usina": u["usina"], "codigo": u.get("codigo"), "cliente": u.get("cliente"), "uf": u.get("uf"),
                    "regiao": u.get("regiao") or "Sem região", "mwp": u.get("mwp"), "nInv": u.get("nInv"), "nCab": u.get("nCab")} for u in usinas],
        "eventos": eventos, "resumo": resumo,
        "avisos": {"eventosSemUsina": sem_usina, "pesoAproximado": aprox, "canceladas": canceladas, "abertasAntigas": abertas_antigas,
                   "usinasSemRegiao": sum(1 for u in usinas if not u.get("regiao")),
                   "usinasSemNInv": sum(1 for u in usinas if not u.get("nInv"))},
    }
    tmp = SAIDA + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, SAIDA)
    p = resumo["portfolio"]
    log(f"{SAIDA}: {len(eventos)} eventos em {p['usinas']} usinas ({p['mwp']} MWp) | {p['rel']} religamentos, "
        f"{p['h']} h diurnas | disp {p['disp']}% | campo {p['campo']} emerg {p['emergencial']} remoto {p['remoto']} "
        f"queda {p['queda']} prog {p['programado']} | sem usina {sem_usina}, peso aprox {aprox} | {os.path.getsize(SAIDA)/1024:.0f} KB")
    return saida
