# -*- coding: utf-8 -*-
"""
Relatório diário de manutenção — PDF por e-mail, uma vez por dia.

Roda como passo do workflow "Atualiza Gestão PCM" (a cada 15 min). Só faz algo
na PRIMEIRA rodada depois das 06:00 (horário de Brasília) de cada dia; nas
demais sai em silêncio. Cobre o dia anterior (dia civil).

Fontes (todas já geradas pelo robô — este script não chama o Fracttal):
  banco_dados.json    programação da semana: programadas × finalizadas do dia
  gestao_pcm.json     OS não programadas criadas no dia, backlog, criadas × finalizadas
  gerencial.json      religamentos do dia e dos 7 anteriores
  engenharia.json     ativos com sinal / críticos no Confiabilidade
  operacoes.json      só para nomes de clusters (opcional)

Saída:
  relatorios/diario/AAAA-MM-DD.html e .pdf   (30 dias guardados)
  relatorios/diario/_estado.json             (qual foi o último dia gerado)
  e-mail com o PDF anexo para RELATORIO_DIARIO_PARA (vários, separados por vírgula)

PDF: Chrome/Chromium headless (no ubuntu do Actions é o `google-chrome` já
instalado; no Windows, o Chrome do usuário). Sem navegador, fica só o HTML.

Sem SMTP (Secrets SMTP_HOST/USER/PASS): gera e grava, avisa no log, não envia.
RELATORIO_DIARIO_DUMP=<pasta> grava o .eml em vez de enviar (teste).

Janela do MEIO-DIA ("Recuperação da tarde"): na primeira rodada depois das 13:00
BRT de dia útil, gera 1 página com o que foi programado para a manhã de HOJE e
ainda não fechou, ordenado por nº de rolagens, com HH pendente × HH já programado
à tarde por supervisor. Sai em relatorios/matinal/ e vai para RELATORIO_MATINAL_PARA
(se vazio, usa RELATORIO_DIARIO_PARA).

Uso manual:
  python relatorio_diario.py                 # regra normal (06:00 e 13:00, uma vez por dia cada)
  python relatorio_diario.py --dia 2026-09-09 --forcar --sem-email              # diário
  python relatorio_diario.py --janela matinal --dia 2026-09-10 --forcar --sem-email
"""
from __future__ import annotations

import argparse
import collections
import glob
import html
import json
import os
import re
import shutil
import smtplib
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

BASE = os.environ.get("PCM_PROG_DIR", os.path.dirname(os.path.abspath(__file__)))
PASTA = os.path.join(BASE, "relatorios", "diario")
ESTADO_ARQ = os.path.join(PASTA, "_estado.json")
PAINEL_URL = os.environ.get("PAINEL_URL", "https://pcm.gridco.com.br/novo.html")
HORA_ENVIO = int(os.environ.get("RELATORIO_DIARIO_HORA", "6"))
GUARDAR_DIAS = int(os.environ.get("RELATORIO_DIARIO_GUARDAR", "30"))
META_ADERENCIA = float(os.environ.get("RELATORIO_DIARIO_META", "85"))
# janela do meio-dia ("Recuperação da tarde")
PASTA_MAT = os.path.join(BASE, "relatorios", "matinal")
ESTADO_MAT = os.path.join(PASTA_MAT, "_estado.json")
HORA_MATINAL = int(os.environ.get("RELATORIO_MATINAL_HORA", "13"))   # quando dispara (BRT)
HORA_CORTE_MANHA = 12                                                 # "manhã" = início programado antes disso
LIN_MATINAL = 12                                                      # linhas da lista de prioridade
BR = timezone(timedelta(hours=-3))
TIPOS_NAO_PROG = ("Corretiva", "Corretiva Emergencial", "Religamento", "Religamento Remoto")
DIAS_PT = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
DIAS_KEY = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
CAT = {"campo": "Em campo", "remoto": "Remoto (COS)", "queda": "Queda de energia",
       "emergencial": "Emergencial", "programado": "Programado"}


def log(msg, level="INFO"):
    print(f"[{datetime.now():%H:%M:%S}] {level}: {msg}", flush=True)


def ler(nome, padrao):
    try:
        with open(os.path.join(BASE, nome), encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"{nome}: não li ({type(e).__name__}) — sigo com o que tenho", "WARN")
        return padrao


h = lambda s: html.escape(str(s if s is not None else ""))
pct = lambda a, b: (100.0 * a / b) if b else 0.0
n = lambda v: f"{int(v):,}".replace(",", ".")
cor = lambda p: "ok" if p >= META_ADERENCIA else "mid" if p >= 70 else "mal"


# ── dados ─────────────────────────────────────────────────────────────────
def semana_do_dia(bd, dia: date):
    alvo = f"{dia.isocalendar()[0]}-W{dia.isocalendar()[1]:02d}"
    for w in bd.get("semanas", []):
        if w.get("week") == alvo:
            return w
    return None


def calcular(dia: date):
    bd = ler("banco_dados.json", {})
    g = ler("gestao_pcm.json", {})
    ger = ler("gerencial.json", {})
    eng = ler("engenharia.json", {})
    D = {"dia": dia.isoformat(), "avisos": []}

    # programação do dia (Programação Semanal)
    w = semana_do_dia(bd, dia)
    nome_dia = DIAS_PT[dia.weekday()]
    rows = []
    if w:
        esperado = dia.strftime("%d/%m")
        if w.get("dates", {}).get(DIAS_KEY[dia.weekday()], esperado) != esperado:
            D["avisos"].append(f"a semana {w['week']} do banco_dados não bate com a data {esperado}")
        rows = [r for r in w.get("rows", []) if str(r.get("dia", "")).lower().startswith(nome_dia[:3].lower())]
    else:
        D["avisos"].append(f"banco_dados.json não tem a semana de {dia:%d/%m} — aderência fica sem dado")
    D["semanaLabel"] = (w or {}).get("label", "") or f"Semana {dia.isocalendar()[1]}"
    D["semanaNum"] = dia.isocalendar()[1]
    fin = lambda r: r.get("status") == "Finalizados"
    andando = lambda r: r.get("status") in ("Em progresso", "pausado")
    D["prog"], D["fin"] = len(rows), sum(1 for r in rows if fin(r))
    D["andamento"] = sum(1 for r in rows if andando(r))
    D["naoIniciada"] = D["prog"] - D["fin"] - D["andamento"]
    D["reprog"] = sum(1 for r in rows if r.get("reprog") == "Sim")

    def bloco(chave):
        o = collections.defaultdict(lambda: [0, 0, 0, 0])
        for r in rows:
            k = chave(r) or "—"
            o[k][0] += 1
            o[k][1] += fin(r)
            o[k][2] += andando(r)
            o[k][3] += r.get("reprog") == "Sim"
        return sorted([(k, *v) for k, v in o.items()], key=lambda x: -x[1])
    D["cli"] = bloco(lambda r: r.get("cliente"))
    D["resp"] = bloco(lambda r: r.get("responsavel"))
    D["naoFeitas"] = [(r.get("os_id"), r.get("tarefa", ""), r.get("cliente"), r.get("cluster"), r.get("status"))
                      for r in rows if not fin(r)]

    # semana até aqui (dias úteis da semana da data)
    D["semana"] = []
    if w:
        for i, d in enumerate(DIAS_PT[:5]):
            rs = [r for r in w.get("rows", []) if r.get("dia") == d]
            D["semana"].append((d[:3], len(rs), sum(1 for r in rs if fin(r)), i > dia.weekday()))

    # não programadas e backlog (Gestão PCM)
    T = g.get("tarefas", [])
    ds = dia.isoformat()
    cri = [t for t in T if (t.get("criacao") or "")[:10] == ds and t.get("tipo") in TIPOS_NAO_PROG]
    D["naoProg"] = {
        "n": len(cri),
        "tipos": collections.Counter(t["tipo"] for t in cri).most_common(),
        "clientes": collections.Counter(t.get("cliente") or "—" for t in cri).most_common(5),
        "lista": [(t.get("os"), t.get("tipo"), t.get("usina"), t.get("tarefa", ""), t.get("cluster")) for t in cri],
    }
    D["criadasTotal"] = sum(1 for t in T if (t.get("criacao") or "")[:10] == ds)
    D["finGestao"] = sum(1 for t in T if (t.get("dataFinal") or "")[:10] == ds)
    D["backlog"] = {"abertas": g.get("totalAbertas", sum(1 for t in T if t.get("aberta"))),
                    "atrasadas": g.get("totalAtrasadas", sum(1 for t in T if t.get("aberta") and t.get("atrasado")))}

    # religamentos (Gerencial)
    U = ger.get("usinas", [])
    ev = ger.get("eventos", [])
    usina = lambda e: U[e["u"]] if isinstance(U, list) and 0 <= e.get("u", -1) < len(U) else {}
    hoje = [e for e in ev if (e.get("ini") or "")[:10] == ds]
    D["relig"] = [(e.get("os"), e.get("cat"), usina(e).get("usina", e.get("ativo", "")), usina(e).get("regiao", ""),
                   e.get("hDia"), e.get("url")) for e in hoje]
    D["relig7"] = [sum(1 for x in ev if (x.get("ini") or "")[:10] == (dia - timedelta(days=i)).isoformat())
                   for i in range(7, 0, -1)]

    # confiabilidade
    D["criticos"] = [(a.get("nome"), a.get("usina"), a.get("nFalha")) for a in eng.get("ativos", []) if a.get("nivel") == "critico"]
    D["sinal"] = (eng.get("kpi") or {}).get("ativosSinal", 0)
    return D


# ── análise (regras fixas, auditáveis) ────────────────────────────────────
def analise(D):
    prog, fin = D["prog"], D["fin"]
    ader = pct(fin, prog)
    np_, relig = D["naoProg"], D["relig"]
    hrel = sum((r[4] or 0) for r in relig)
    med7 = sum(D["relig7"]) / 7
    ins = []
    if prog:
        ins.append(f"<b>Aderência de {ader:.0f}% no dia</b> — {n(fin)} das {n(prog)} OS programadas finalizadas, "
                   f"{'acima' if ader >= META_ADERENCIA else 'abaixo'} da meta de {META_ADERENCIA:.0f}%. "
                   f"{n(D['naoIniciada'])} não iniciadas e {n(D['andamento'])} em andamento passam para hoje.")
    else:
        ins.append("<b>Sem OS programadas para o dia</b> na Programação Semanal — o relatório traz só o que entrou e os religamentos.")
    tipos = " · ".join(f"<b>{n(c)}</b> {h(t)}" for t, c in np_["tipos"]) or "nenhuma"
    if np_["n"]:
        cl = np_["clientes"][0]
        ins.append(f"<b>{n(np_['n'])} OS não programadas entraram</b> ({tipos}). {h(cl[0])} concentra {n(cl[1])} delas. "
                   f"Cada uma compete com a programação de hoje pelo mesmo HH.")
    else:
        ins.append("<b>Nenhuma OS não programada entrou</b> no dia.")
    if relig or med7:
        tom = ("Dia mais calmo que a semana." if len(relig) < med7 * 0.7 else
               "Dia acima do padrão da semana." if len(relig) > med7 * 1.3 else "Dentro do padrão da semana.")
        ins.append(f"<b>Religamentos: {n(len(relig))} no dia</b> ({hrel:.1f} h diurnas de parada), contra média de "
                   f"{med7:.0f}/dia nos 7 dias anteriores. {tom}")
    cl_ok = [(k, p, f) for k, p, f, a, rp in D["cli"] if p >= 10]
    rs_ok = [(k, p, f) for k, p, f, a, rp in D["resp"] if p >= 10 and k != "—"]
    if cl_ok:
        pc = min(cl_ok, key=lambda x: pct(x[2], x[1]))
        frase = f"<b>{h(pc[0])} teve a menor aderência entre os clientes</b> ({pct(pc[2], pc[1]):.0f}% de {n(pc[1])})"
        if rs_ok:
            pr = min(rs_ok, key=lambda x: pct(x[2], x[1]))
            frase += f"; por supervisor, {h(pr[0])} ({pct(pr[2], pr[1]):.0f}% de {n(pr[1])})"
        ins.append(frase + ".")
    saldo = D["criadasTotal"] - D["finGestao"]
    ins.append(f"<b>Backlog segue em {n(D['backlog']['atrasadas'])} tarefas atrasadas</b> de {n(D['backlog']['abertas'])} abertas. "
               f"No dia o Gestão PCM registrou {n(D['criadasTotal'])} tarefas criadas e {n(D['finGestao'])} finalizadas — "
               f"saldo {'+' if saldo > 0 else ''}{n(saldo)}.")
    crit = "; ".join(f"{h(a)} ({h(u)}, {f} falhas)" for a, u, f in D["criticos"][:2])
    ins.append(f"<b>{n(D['sinal'])} ativos com sinal de recorrência</b>, {n(len(D['criticos']))} crítico(s)"
               + (f": {crit}" if crit else "") + ". Estão no módulo Confiabilidade, com ticket.")
    return ins


# ── HTML ──────────────────────────────────────────────────────────────────
def logo_html():
    try:
        with open(os.path.join(BASE, "novo.html"), encoding="utf-8") as f:
            m = re.search(r'<img class="marca-img"[^>]*>', f.read())
        if m:
            return m.group(0).replace("marca-img", "logo")
    except Exception:
        pass
    return '<div class="logo-txt">Grid Co.</div>'


def tabela(linhas, cab, cols, vazio="nada a listar"):
    if not linhas:
        return f'<div class="vazio">{vazio}</div>'
    return ('<table><thead><tr>' + ''.join(f'<th class="{c}">{t}</th>' for t, c in cab) + '</tr></thead><tbody>'
            + ''.join('<tr>' + ''.join(f'<td class="{c}">{v}</td>' for v, c in zip(l, cols)) + '</tr>' for l in linhas)
            + '</tbody></table>')


def montar_html(D, dia: date, gerado: datetime):
    prog, fin, and_, nao = D["prog"], D["fin"], D["andamento"], D["naoIniciada"]
    ader = pct(fin, prog)
    np_, relig = D["naoProg"], D["relig"]
    hrel = sum((r[4] or 0) for r in relig)
    med7 = sum(D["relig7"]) / 7
    ins = analise(D)
    logo = logo_html()
    titulo_dia = f"{DIAS_PT[dia.weekday()]}, {dia:%d/%m/%Y}"

    cli = [(h(k), n(p), n(f), n(a), n(p - f - a), f'<span class="cel {cor(pct(f, p))}">{pct(f, p):.0f}%</span>')
           for k, p, f, a, rp in D["cli"][:8]]
    resp = [(h(k if k != "—" else "sem responsável no BD"), n(p), n(f), n(rp), f'<span class="cel {cor(pct(f, p))}">{pct(f, p):.0f}%</span>')
            for k, p, f, a, rp in D["resp"][:7]]
    tipos_np = " · ".join(f"<b>{n(c)}</b> {h(t)}" for t, c in np_["tipos"]) or "nenhuma no dia"
    usc = lambda u: re.sub(r"^[^-]+ - ", "", (u or "")).rsplit(" - ", 1)[0]
    lista_np = [(f'#{h(o)}', h((t or "").replace("Religamento Remoto", "Relig. remoto")), h(usc(u)[:22]),
                 h(re.sub(r"^\[.*?\]\s*-?\s*", "", ta or "")[:30]), h(c)) for o, t, u, ta, c in np_["lista"][:8]]
    lista_rel = [(f'#{h(o)}', h(CAT.get(c, c)), h((u or "")[:18]) + f' <span class="cinza">· {h(r)}</span>',
                  ("<i>aberta</i>" if hd is None else f"{hd:.1f} h")) for o, c, u, r, hd, url in relig[:8]]
    sem = D["semana"]
    mx = max([p for _, p, _, _ in sem] or [1]) or 1
    barras = "".join(
        f'<div class="bar{" fut" if fut else ""}"><div class="col"><i style="height:{100*p/mx:.0f}%"></i><b style="height:{100*f/mx:.0f}%"></b></div>'
        f'<span>{d}<small>{n(f)}/{n(p)}</small></span></div>' for d, p, f, fut in sem)
    nao_feitas = [(f'#{h(o)}', h(t[:44]), h(c), h(cl), h(st)) for o, t, c, cl, st in D["naoFeitas"][:8]]
    tot_sem = sum(p for _, p, _, _ in sem)
    nota_sem = ""
    if sem and tot_sem:
        d, p, f, _ = max(sem, key=lambda x: x[1])
        if pct(p, tot_sem) >= 35:
            nota_sem = f'<div class="nota">{h(d)} concentra {n(p)} programadas — {pct(p, tot_sem):.0f}% da semana num só dia. Vale nivelar na próxima programação.</div>'
    mais_np = f' <span class="cinza">(+{n(len(np_["lista"]) - 8)} no painel)</span>' if len(np_["lista"]) > 8 else ""
    mais_rel = f' <span class="cinza">(+{n(len(relig) - 8)} no painel)</span>' if len(relig) > 8 else ""
    mais_nf = f' <span class="cinza">(+{n(len(D["naoFeitas"]) - 8)} no painel)</span>' if len(D["naoFeitas"]) > 8 else ""
    saldo = D["criadasTotal"] - D["finGestao"]
    avisos = ("".join(f'<div class="nota aviso">{h(a)}</div>' for a in D["avisos"]))

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Relatório diário de manutenção · {dia:%d/%m/%Y}</title>
<style>
@page{{size:A4;margin:12mm 12mm 14mm}}
*{{box-sizing:border-box}} body{{margin:0;font-family:"Segoe UI",Arial,sans-serif;font-size:9.5pt;color:#191528;line-height:1.3;background:#fff}}
.pg{{page-break-after:always}} .pg:last-child{{page-break-after:auto}}
.top{{display:flex;align-items:flex-start;gap:14px;border-bottom:3px solid #A9DB21;padding-bottom:8px;margin-bottom:10px}}
.top .logo{{height:20px;width:auto;display:block;margin-top:4px}} .logo-txt{{font-weight:800;font-size:14pt;color:#191528}} .top .t{{flex:1}} .top h1{{margin:0;font-size:15pt;font-weight:800;white-space:nowrap}} .top .s{{font-size:9.5pt;color:#68667d}}
.top .d{{text-align:right;font-size:9pt;color:#3a3550}} .top .d b{{display:block;font-size:12pt;color:#191528}}
.kpis{{display:grid;grid-template-columns:repeat(6,1fr);gap:6px;margin:8px 0 10px}}
.kpi{{border:1px solid #e4e4ef;border-left:3px solid #cbcbdd;border-radius:6px;padding:5px 8px}} .kpi.g{{border-left-color:#A9DB21}} .kpi.r{{border-left-color:#c2410c}}
.kpi .v{{font-size:14pt;font-weight:800;line-height:1.05}} .kpi .n{{font-size:8pt;color:#68667d;text-transform:uppercase;letter-spacing:.04em;margin-top:2px}} .kpi .m{{font-size:8pt;color:#68667d}}
.sec{{margin:9px 0 5px;font-size:8.5pt;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:#68667d;display:flex;align-items:center;gap:8px}} .sec::after{{content:"";flex:1;height:1px;background:#e4e4ef}}
table{{width:100%;border-collapse:collapse;font-size:8.6pt}} td,th{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:220px}} th{{text-align:left;font-size:7.5pt;text-transform:uppercase;letter-spacing:.04em;color:#68667d;padding:4px 6px;border-bottom:1px solid #cbcbdd;background:#f6f7fa}}
td{{padding:3px 6px;border-bottom:1px solid #eceef4;vertical-align:top}} .r{{text-align:right}} th.r{{text-align:right}} .mono{{font-family:Consolas,monospace;font-size:9pt}}
.cel{{display:inline-block;min-width:38px;text-align:center;padding:1px 5px;border-radius:4px;font-weight:700}} .cel.ok{{background:#e3f6ea;color:#1f7a4d}} .cel.mid{{background:#fdf0d5;color:#a04408}} .cel.mal{{background:#fde2e2;color:#b02525}}
.g2{{display:grid;grid-template-columns:1.25fr 1fr;gap:12px}} .g2b{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.ins{{margin:0;padding-left:16px}} .ins li{{margin:3px 0;font-size:9.2pt}} .ins b{{color:#191528}}
.chips{{font-size:9.5pt;color:#3a3550;margin:2px 0 6px}} .cinza{{color:#68667d}} .vazio{{color:#68667d;font-size:9pt;padding:6px 2px}}
.bars{{display:flex;gap:10px;align-items:flex-end;height:90px;padding:4px 6px 0}} .bar{{flex:1;display:flex;flex-direction:column;align-items:center;gap:3px;height:100%}} .bar .col{{flex:1;width:100%;display:flex;gap:2px;align-items:flex-end;justify-content:center}}
.bar .col i,.bar .col b{{display:block;width:14px;border-radius:2px 2px 0 0}} .bar .col i{{background:#cbcbdd}} .bar .col b{{background:#191528}} .bar span{{font-size:8.5pt;font-weight:700}} .bar small{{display:block;font-weight:400;color:#68667d;font-size:7.5pt}} .bar.fut{{opacity:.45}}
.nota{{background:#fbfbe8;border-left:3px solid #A9DB21;padding:6px 9px;font-size:9pt;color:#3a3550;margin-top:6px}} .nota.aviso{{background:#fde2e2;border-left-color:#b02525}}
.pe{{margin-top:10px;border-top:1px solid #e4e4ef;padding-top:6px;font-size:7.8pt;color:#68667d;display:flex;justify-content:space-between;gap:10px}}
i{{font-style:normal;color:#b02525;font-weight:700;font-size:8pt}}
</style></head><body>

<div class="pg">
  <div class="top">{logo}<div class="t"><h1>Relatório diário de manutenção</h1><div class="s">Grid Co. · Operação de Ativos · o que aconteceu ontem</div></div>
    <div class="d"><b>{titulo_dia}</b>gerado {gerado:%d/%m} às {gerado:%H:%M} · uso interno (PCM e engenharia)</div></div>
  {avisos}
  <div class="kpis">
    <div class="kpi g"><div class="v">{f"{ader:.0f}%" if prog else "—"}</div><div class="n">Aderência do dia</div><div class="m">{n(fin)} de {n(prog)} programadas</div></div>
    <div class="kpi"><div class="v">{n(nao + and_)}</div><div class="n">Passam para hoje</div><div class="m">{n(nao)} não iniciadas · {n(and_)} em andamento</div></div>
    <div class="kpi r"><div class="v">{n(np_['n'])}</div><div class="n">Não programadas geradas</div><div class="m">corretivas e religamentos</div></div>
    <div class="kpi"><div class="v">{n(len(relig))}</div><div class="n">Religamentos</div><div class="m">{hrel:.1f} h diurnas · média 7 d: {med7:.0f}/dia</div></div>
    <div class="kpi r"><div class="v">{n(D['backlog']['atrasadas'])}</div><div class="n">Backlog atrasado</div><div class="m">de {n(D['backlog']['abertas'])} abertas · saldo do dia {'+' if saldo > 0 else ''}{n(saldo)}</div></div>
    <div class="kpi"><div class="v">{n(D['sinal'])}</div><div class="n">Ativos com sinal</div><div class="m">{n(len(D['criticos']))} crítico(s) no Confiabilidade</div></div>
  </div>

  <div class="sec">Programação do dia — por cliente</div>
  {tabela(cli, [("Cliente",""),("Programadas","r"),("Finalizadas","r"),("Em andamento","r"),("Não iniciadas","r"),("Aderência","r")], ["","r","r","r","r","r"], "sem OS programadas para este dia")}

  <div class="g2">
    <div>
      <div class="sec">Não programadas geradas no dia{mais_np}</div>
      <div class="chips">{tipos_np}</div>
      {tabela(lista_np, [("OS",""),("Tipo",""),("Usina",""),("Tarefa",""),("Cluster","")], ["mono","","","",""], "nenhuma OS não programada criada no dia")}
    </div>
    <div>
      <div class="sec">Religamentos do dia{mais_rel}</div>
      {tabela(lista_rel, [("OS",""),("Como resolveu",""),("Usina · região",""),("Parada","r")], ["mono","","","r"], "nenhum religamento no dia")}
      <div class="nota">Parada = horas diurnas (6h–18h) entre o incidente e o fim da tarefa. "aberta" = ainda sem data final na geração.</div>
    </div>
  </div>

  <div class="sec">Análise gerencial do dia</div>
  <ul class="ins">{''.join(f'<li>{x}</li>' for x in ins)}</ul>
  <div class="pe"><span>Página 1 de 2 · Relatório gerado pela plataforma PCM · pcm.gridco.com.br</span><span>Fontes: Programação Semanal S{D['semanaNum']}, Gestão PCM, Confiabilidade e Gerencial (Fracttal via robô)</span></div>
</div>

<div class="pg">
  <div class="top">{logo}<div class="t"><h1>Detalhe do dia</h1><div class="s">por supervisor, semana até aqui e o que ficou para hoje</div></div><div class="d"><b>{titulo_dia}</b>página 2 de 2</div></div>

  <div class="g2b">
    <div>
      <div class="sec">Por supervisor (Responsável O&amp;M)</div>
      {tabela(resp, [("Supervisor",""),("Prog.","r"),("Final.","r"),("Reprog.","r"),("Aderência","r")], ["","r","r","r","r"], "sem OS programadas para este dia")}
      {'<div class="nota">"sem responsável no BD" são OS cujo cluster não tem Responsável O&amp;M preenchido no BD_Operacoes — cadastro, não execução.</div>' if any(k == "—" for k, *_ in D["resp"]) else ""}
    </div>
    <div>
      <div class="sec">{h(D['semanaLabel'])} — programadas × finalizadas</div>
      <div class="bars">{barras or '<div class="vazio">semana sem programação carregada</div>'}</div>
      {nota_sem}
    </div>
  </div>

  <div class="sec">O que ficou para hoje — programadas do dia não finalizadas ({n(prog - fin)}){mais_nf}</div>
  {tabela(nao_feitas, [("OS",""),("Tarefa",""),("Cliente",""),("Cluster",""),("Estado","")], ["mono","","","",""], "tudo que estava programado foi finalizado")}
  <div class="nota">Lista completa e o motivo de cada rolagem no painel → Semana → filtro "não finalizadas". O cliente não recebe este relatório — ele vê o resultado, não o processo.</div>

  <div class="sec">Ativos críticos no Confiabilidade</div>
  <ul class="ins">{''.join(f"<li><b>{h(a)}</b> — {h(u)} · {f} falhas em 30 dias · ver ticket no painel</li>" for a, u, f in D['criticos']) or '<li>nenhum crítico hoje</li>'}</ul>

  <div class="pe"><span>Página 2 de 2 · Responder este e-mail não registra nada — assuma tickets e justifique rolagens no painel.</span><span>Aderência = finalizadas ÷ programadas do dia. Não programadas = OS criadas no dia dos tipos Corretiva, Corretiva Emergencial, Religamento e Religamento Remoto.</span></div>
</div>
</body></html>"""


# ── PDF ───────────────────────────────────────────────────────────────────
def achar_chrome():
    cand = [os.environ.get("CHROME_BIN", "")]
    cand += [shutil.which(x) for x in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge")]
    cand += [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
             r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
    for c in cand:
        if c and os.path.isfile(c):
            return c
    return None


def html_para_pdf(html_path, pdf_path):
    chrome = achar_chrome()
    if not chrome:
        log("nenhum Chrome/Chromium encontrado — fica só o HTML (defina CHROME_BIN)", "WARN")
        return False
    url = "file:///" + os.path.abspath(html_path).replace("\\", "/")
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
           "--run-all-compositor-stages-before-draw", "--virtual-time-budget=5000",
           f"--print-to-pdf={os.path.abspath(pdf_path)}", url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        log(f"Chrome falhou ({type(e).__name__}: {e})", "WARN")
        return False
    ok = os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 1000
    if not ok:
        log(f"Chrome não gerou o PDF (rc={r.returncode}): {(r.stderr or '')[-400:]}", "WARN")
    return ok


# ── e-mail ────────────────────────────────────────────────────────────────
def enviar_email(assunto, html_resumo, pdf_path, nome_pdf, var_para="RELATORIO_DIARIO_PARA", tag="diario", dia=None):
    para = sorted({p.strip() for p in os.environ.get(var_para, "").split(",") if p.strip()})
    if not para and var_para != "RELATORIO_DIARIO_PARA":
        para = sorted({p.strip() for p in os.environ.get("RELATORIO_DIARIO_PARA", "").split(",") if p.strip()})
    host, user, pwd = (os.environ.get(k, "").strip() for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS"))
    porta = int(os.environ.get("SMTP_PORT", "587") or 587)
    de = os.environ.get("MAIL_FROM", user).strip() or "pcm@gridco.com.br"
    dump = os.environ.get("RELATORIO_DIARIO_DUMP", "").strip()
    if not para:
        log(f"{var_para} vazio — relatório gerado, e-mail não enviado", "WARN")
        return {"enviado": False, "motivo": "sem destinatários"}
    msg = MIMEMultipart("mixed")
    msg["Subject"], msg["From"], msg["To"] = assunto, de, ", ".join(para)
    msg.attach(MIMEText(html_resumo, "html", "utf-8"))
    if pdf_path and os.path.isfile(pdf_path):
        with open(pdf_path, "rb") as f:
            anexo = MIMEApplication(f.read(), _subtype="pdf")
        anexo.add_header("Content-Disposition", "attachment", filename=nome_pdf)
        msg.attach(anexo)
    if dump:
        os.makedirs(dump, exist_ok=True)
        with open(os.path.join(dump, f"relatorio_{tag}_{dia or ''}.eml"), "w", encoding="utf-8") as f:
            f.write(msg.as_string())
        log(f"modo dump: .eml gravado em {dump}")
        return {"enviado": True, "para": len(para), "dump": True}
    if not (host and user and pwd):
        log(f"SMTP não configurado — não enviei para {', '.join(para)}", "WARN")
        return {"enviado": False, "motivo": "SMTP não configurado", "para": len(para)}
    try:
        with smtplib.SMTP(host, porta, timeout=60) as s:
            s.starttls()
            s.login(user, pwd)
            s.sendmail(de, para, msg.as_string())
        log(f"e-mail enviado para {len(para)} destinatário(s)")
        return {"enviado": True, "para": len(para)}
    except Exception as e:
        log(f"falha no envio ({type(e).__name__}: {e})", "WARN")
        return {"enviado": False, "motivo": f"{type(e).__name__}: {e}"[:200], "para": len(para)}


def resumo_email(D, dia: date, ins):
    ader = pct(D["fin"], D["prog"])
    kpis = [(f"{ader:.0f}%" if D["prog"] else "—", f"aderência ({n(D['fin'])} de {n(D['prog'])})"),
            (n(D["naoIniciada"] + D["andamento"]), "passam para hoje"),
            (n(D["naoProg"]["n"]), "não programadas geradas"),
            (n(len(D["relig"])), "religamentos"),
            (n(D["backlog"]["atrasadas"]), "backlog atrasado"),
            (n(D["sinal"]), "ativos com sinal")]
    celulas = "".join(f"<td style='padding:6px 10px;border:1px solid #e4e4ef;text-align:center'><div style='font-size:18px;font-weight:800'>{v}</div>"
                      f"<div style='font-size:11px;color:#68667d'>{r}</div></td>" for v, r in kpis)
    return (f"<div style='font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#191528'>"
            f"<h2 style='margin:0 0 4px'>Relatório diário de manutenção — {DIAS_PT[dia.weekday()]}, {dia:%d/%m/%Y}</h2>"
            f"<p style='margin:0 0 10px;color:#68667d'>O PDF completo vai em anexo (2 páginas).</p>"
            f"<table style='border-collapse:collapse;margin-bottom:12px'><tr>{celulas}</tr></table>"
            f"<ul style='padding-left:18px'>{''.join(f'<li style=margin:4px_0>{x}</li>' for x in ins)}</ul>"
            f"<p style='color:#68667d;font-size:12px;margin-top:18px'>Enviado pela plataforma PCM · <a href='{PAINEL_URL}'>abrir o painel</a>. "
            f"Responder este e-mail não registra nada.</p></div>").replace("margin:4px_0", "'margin:4px 0'")


# ══ JANELA DO MEIO-DIA — "Recuperação da tarde" ═══════════════════════════
# O que foi programado para a MANHÃ de hoje e ainda não fechou, para o time
# tentar recuperar à tarde. Uma página, corte às 13:00 BRT, só dia útil.
def _hora_ini(r):
    """Hora programada de início. 99 quando o campo não é utilizável."""
    v = (r.get("h_ini") or "")[:2]
    return int(v) if v.isdigit() else 99


def _janela_ok(r):
    """Descarta janela impossível (fim depois da meia-noite) da conta de HH."""
    v = (r.get("h_fim") or "")[:2]
    return v.isdigit() and int(v) < 24


def _hh(L):
    return sum(((r.get("duracao") or 0) + (r.get("desloc") or 0)) for r in L if _janela_ok(r))


def calcular_matinal(dia: date):
    bd = ler("banco_dados.json", {})
    g = ler("gestao_pcm.json", {})
    D = {"dia": dia.isoformat(), "avisos": []}
    w = semana_do_dia(bd, dia)
    nome_dia = DIAS_PT[dia.weekday()]
    rows = []
    if w:
        rows = [r for r in w.get("rows", []) if str(r.get("dia", "")).lower().startswith(nome_dia[:3].lower())]
    else:
        D["avisos"].append(f"banco_dados.json não tem a semana de {dia:%d/%m} — sem programação para comparar")
    D["semanaLabel"] = (w or {}).get("label", "") or f"Semana {dia.isocalendar()[1]}"
    D["totalDia"] = len(rows)
    D["manha"] = [r for r in rows if _hora_ini(r) < HORA_CORTE_MANHA]
    D["tarde"] = [r for r in rows if HORA_CORTE_MANHA <= _hora_ini(r) < 24]
    D["fora"] = [r for r in rows if _hora_ini(r) >= 24 or not _janela_ok(r)]
    D["pend"] = [r for r in D["manha"] if r.get("status") != "Finalizados"]
    D["hhPend"], D["hhTarde"] = _hh(D["pend"]), _hh(D["tarde"])

    # uma linha de ação por OS, a que mais rolou primeiro
    grp = {}
    for r in D["pend"]:
        grp.setdefault(r.get("os_id"), []).append(r)
    for L in grp.values():
        L.sort(key=lambda r: r.get("h_ini") or "")
    D["os"] = sorted(grp.items(), key=lambda kv: (-max((r.get("vezes") or 1) for r in kv[1]),
                                                  kv[1][0].get("h_ini") or ""))
    D["reincid"] = sum(1 for _, L in D["os"] if max((r.get("vezes") or 1) for r in L) >= 3)

    D["resp"] = []
    for nome in sorted({(r.get("responsavel") or "—") for r in D["manha"] + D["tarde"]}):
        m = [r for r in D["manha"] if (r.get("responsavel") or "—") == nome]
        p = [r for r in D["pend"] if (r.get("responsavel") or "—") == nome]
        t = [r for r in D["tarde"] if (r.get("responsavel") or "—") == nome]
        D["resp"].append((nome, len(m), len(m) - len(p), len(p), _hh(p), _hh(t)))
    D["resp"].sort(key=lambda x: -x[3])

    ds = dia.isoformat()
    npg = [t for t in g.get("tarefas", []) if (t.get("criacao") or "")[:10] == ds and t.get("tipo") in TIPOS_NAO_PROG]
    D["naoProg"] = {"n": len(npg), "tipos": collections.Counter(t["tipo"] for t in npg).most_common()}
    D["cluster"] = collections.Counter((r.get("cluster") or "—") for r in D["pend"]).most_common(1)
    D["cliente"] = collections.Counter((r.get("cliente") or "—") for r in D["pend"]).most_common(1)
    return D


def analise_matinal(D):
    m, p = len(D["manha"]), len(D["pend"])
    feitas = m - p
    carga = D["hhPend"] + D["hhTarde"]
    ins = []
    if not m:
        return ["<b>Sem tarefas programadas para a manhã de hoje</b> na Programação Semanal — nada a recuperar."]
    ins.append(f"<b>A manhã fechou {pct(feitas, m):.0f}%</b> — {n(feitas)} das {n(m)} tarefas programadas até "
               f"{HORA_CORTE_MANHA:02d}:00 estão finalizadas no Fracttal. Restam <b>{n(p)} tarefas em {n(len(D['os']))} OS</b>, "
               f"somando {D['hhPend']:.0f} h de execução.")
    if p:
        aperto = ("muito acima" if carga > 2 * max(D["hhTarde"], 1) else "acima") if D["hhPend"] > 0 else "dentro"
        ins.append(f"<b>A tarde já tem {n(len(D['tarde']))} tarefas programadas</b> ({D['hhTarde']:.0f} h). Somando o que ficou "
                   f"da manhã, a carga da tarde vai a <b>{carga:.0f} h</b> — {aperto} do que o dia comporta. "
                   f"A lista acima está ordenada por quem rolou mais vezes.")
        if D["reincid"]:
            ins.append(f"<b>{n(D['reincid'])} OS já rolaram 3 vezes ou mais</b> e estão pendentes de novo. São as que devem "
                       f"furar a fila da tarde — cada nova rolagem empurra a OS para a semana seguinte.")
        cli = D["cliente"][0] if D["cliente"] else ("—", 0)
        cl = D["cluster"][0] if D["cluster"] else ("—", 0)
        tipos = " · ".join(f"<b>{n(c)}</b> {h(t)}" for t, c in D["naoProg"]["tipos"]) or "nenhuma"
        ins.append(f"<b>{h(cli[0])} concentra {n(cli[1])} das pendências</b> e o cluster {h(cl[0])} tem {n(cl[1])}. "
                   f"Hoje entraram ainda {n(D['naoProg']['n'])} OS não programadas ({tipos}), que disputam o mesmo HH da tarde.")
        ins.append("<b>Atenção ao apontamento:</b> uma tarefa feita e não fechada no Fracttal aparece aqui como pendente. "
                   "Se a lista tiver OS já executadas, o problema é de fechamento — e resolvê-lo é mais rápido que reprogramar.")
    else:
        ins.append("<b>Nenhuma pendência da manhã</b> — tudo que estava programado até o meio-dia está fechado no Fracttal.")
    return ins


def montar_html_matinal(D, dia: date, gerado: datetime):
    m, p = len(D["manha"]), len(D["pend"])
    carga = D["hhPend"] + D["hhTarde"]
    curto = lambda nm: (nm.split()[0] + " " + nm.split()[-1][:1] + ".") if nm and nm != "—" and len(nm.split()) > 1 else (nm or "—")
    linhas = []
    for os_, L in D["os"][:LIN_MATINAL]:
        r = L[0]
        v = max((x.get("vezes") or 1) for x in L)
        usina = re.sub(r"^[^-]+ - ", "", r.get("usina") or "").rsplit(" - ", 1)[0]
        tarefa = re.sub(r"^\[.*?\]\s*-?\s*", "", r.get("tarefa") or "")
        est = ("pausado" if any(x["status"] == "pausado" for x in L)
               else "em progresso" if any(x["status"] == "Em progresso" for x in L) else "não iniciada")
        linhas.append((f"#{h(os_)}", h(r.get("h_ini")), h(usina[:20]),
                       h(tarefa[:32]) + (f' <span class="cinza">+{len(L)-1}</span>' if len(L) > 1 else ""),
                       h(curto(r.get("responsavel"))), f"{_hh(L):.1f} h",
                       (f'<b class="al">{v}ª</b>' if v >= 3 else f"{v}ª"),
                       f'<span class="est {est.split()[0]}">{est}</span>'))
    resp = [(h(nm if nm != "—" else "sem responsável no BD"), n(qm), n(qf), n(qp), f"{hp:.0f} h", f"{ht:.0f} h",
             f'<span class="cel {"mal" if hp + ht > 40 else "mid" if hp + ht > 25 else "ok"}">{hp + ht:.0f} h</span>')
            for nm, qm, qf, qp, hp, ht in D["resp"][:8]]
    resto = len(D["os"]) - LIN_MATINAL
    aviso = ""
    if D["fora"]:
        ids = ", ".join(sorted({f"#{r['os_id']}" for r in D['fora']})[:6])
        aviso = (f'<div class="nota aviso">{n(len(D["fora"]))} tarefa(s) com janela impossível na programação (fim depois da '
                 f'meia-noite) ficaram fora da conta de HH: {ids}. Vale corrigir a duração no plano.</div>')
    for a in D["avisos"]:
        aviso += f'<div class="nota aviso">{h(a)}</div>'

    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Recuperação da tarde · {dia:%d/%m/%Y}</title>
<style>
@page{{size:A4;margin:10mm 11mm 10mm}}
*{{box-sizing:border-box}} body{{margin:0;font-family:"Segoe UI",Arial,sans-serif;font-size:9.5pt;color:#191528;line-height:1.3;background:#fff}}
.top{{display:flex;align-items:flex-start;gap:14px;border-bottom:3px solid #c2410c;padding-bottom:8px;margin-bottom:9px}}
.top .logo{{height:20px;width:auto;display:block;margin-top:4px}} .logo-txt{{font-weight:800;font-size:14pt}} .top .t{{flex:1}}
.top h1{{margin:0;font-size:15pt;font-weight:800;white-space:nowrap}} .top .s{{font-size:9.5pt;color:#68667d}}
.top .d{{text-align:right;font-size:9pt;color:#3a3550}} .top .d b{{display:block;font-size:12pt;color:#191528}}
.kpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin:8px 0 10px}}
.kpi{{border:1px solid #e4e4ef;border-left:3px solid #cbcbdd;border-radius:6px;padding:5px 8px}} .kpi.g{{border-left-color:#A9DB21}} .kpi.r{{border-left-color:#c2410c}}
.kpi .v{{font-size:14.5pt;font-weight:800;line-height:1.05}} .kpi .n{{font-size:8pt;color:#68667d;text-transform:uppercase;letter-spacing:.04em;margin-top:2px}} .kpi .m{{font-size:8pt;color:#68667d}}
.sec{{margin:8px 0 4px;font-size:8.5pt;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:#68667d;display:flex;align-items:center;gap:8px}} .sec::after{{content:"";flex:1;height:1px;background:#e4e4ef}}
table{{width:100%;border-collapse:collapse;font-size:8.6pt}} td,th{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:230px}}
th{{text-align:left;font-size:7.5pt;text-transform:uppercase;letter-spacing:.04em;color:#68667d;padding:4px 6px;border-bottom:1px solid #cbcbdd;background:#f6f7fa}}
td{{padding:2.6px 6px;border-bottom:1px solid #eceef4;vertical-align:top}} .r{{text-align:right}} th.r{{text-align:right}} .mono{{font-family:Consolas,monospace;font-size:9pt}}
.cel{{display:inline-block;min-width:38px;text-align:center;padding:1px 5px;border-radius:4px;font-weight:700}} .cel.ok{{background:#e3f6ea;color:#1f7a4d}} .cel.mid{{background:#fdf0d5;color:#a04408}} .cel.mal{{background:#fde2e2;color:#b02525}}
.est{{font-size:7.6pt;padding:1px 5px;border-radius:3px;background:#f0f0f6;color:#3a3550}} .est.pausado{{background:#fdf0d5;color:#a04408}} .est.em{{background:#e6efff;color:#1d4ed8}}
.cinza{{color:#68667d}} .al{{color:#b02525}} .vazio{{color:#68667d;font-size:9pt;padding:6px 2px}}
.ins{{margin:0;padding-left:16px}} .ins li{{margin:2px 0;font-size:9pt}}
.nota{{background:#fbfbe8;border-left:3px solid #A9DB21;padding:5px 9px;font-size:8.5pt;color:#3a3550;margin-top:5px}} .nota.aviso{{background:#fdf0d5;border-left-color:#c2410c}}
.pe{{margin-top:9px;border-top:1px solid #e4e4ef;padding-top:6px;font-size:7.8pt;color:#68667d;display:flex;justify-content:space-between;gap:10px}}
</style></head><body>
<div class="top">{logo_html()}<div class="t"><h1>Recuperação da tarde</h1><div class="s">Grid Co. · o programado para a manhã que ainda não fechou</div></div>
  <div class="d"><b>{DIAS_PT[dia.weekday()]}, {dia:%d/%m/%Y}</b>corte às {gerado:%H:%M} · uso interno (PCM, supervisores e engenharia)</div></div>

<div class="kpis">
  <div class="kpi"><div class="v">{n(m)}</div><div class="n">Programadas na manhã</div><div class="m">de {n(D['totalDia'])} no dia todo</div></div>
  <div class="kpi g"><div class="v">{n(m - p)}</div><div class="n">Fechadas</div><div class="m">{pct(m - p, m):.0f}% da manhã</div></div>
  <div class="kpi r"><div class="v">{n(p)}</div><div class="n">Pendentes</div><div class="m">em {n(len(D['os']))} OS · {D['hhPend']:.0f} h</div></div>
  <div class="kpi"><div class="v">{n(len(D['tarde']))}</div><div class="n">Já na tarde</div><div class="m">{D['hhTarde']:.0f} h a partir das {HORA_CORTE_MANHA:02d}:00</div></div>
  <div class="kpi r"><div class="v">{carga:.0f} h</div><div class="n">Carga da tarde</div><div class="m">pendente + programado</div></div>
</div>

<div class="sec">Prioridade de recuperação — OS da manhã ainda abertas</div>
{tabela(linhas, [("OS",""),("Hora",""),("Usina",""),("Tarefa",""),("Responsável",""),("Execução","r"),("Rolagem","r"),("Estado","")], ["mono","mono","","","","r","r",""], "nenhuma pendência da manhã — tudo fechado no Fracttal")}
{f'<div class="nota">Ordenado por número de rolagens: a coluna <b>Rolagem</b> mostra quantas vezes a OS já foi empurrada. As {n(resto)} OS restantes estão no painel → Semana → filtro "não finalizadas". "+N" na tarefa = a OS tem mais tarefas pendentes além da mostrada.</div>' if resto > 0 else ""}

<div class="sec">Onde há espaço na tarde — por supervisor</div>
{tabela(resp, [("Supervisor",""),("Manhã","r"),("Fechou","r"),("Pendente","r"),("HH a recuperar","r"),("HH já na tarde","r"),("Carga da tarde","r")], ["","r","r","r","r","r","r"], "sem programação no dia")}
{aviso}

<div class="sec">Leitura do meio-dia</div>
<ul class="ins">{''.join(f'<li>{x}</li>' for x in analise_matinal(D))}</ul>

<div class="pe"><span>Relatório gerado pela plataforma PCM · pcm.gridco.com.br · o cliente não recebe este relatório</span><span>Manhã = tarefas com início programado antes das {HORA_CORTE_MANHA:02d}:00. Pendente = não finalizada no Fracttal no momento do corte.</span></div>
</body></html>"""


def resumo_email_matinal(D, dia: date):
    m, p = len(D["manha"]), len(D["pend"])
    kpis = [(f"{pct(m - p, m):.0f}%" if m else "—", "fechado na manhã"),
            (n(p), f"pendentes em {n(len(D['os']))} OS"),
            (f"{D['hhPend']:.0f} h", "a recuperar"),
            (f"{D['hhPend'] + D['hhTarde']:.0f} h", "carga da tarde"),
            (n(D["reincid"]), "OS com 3+ rolagens")]
    celulas = "".join(f"<td style='padding:6px 10px;border:1px solid #e4e4ef;text-align:center'><div style='font-size:18px;font-weight:800'>{v}</div>"
                      f"<div style='font-size:11px;color:#68667d'>{r}</div></td>" for v, r in kpis)
    return (f"<div style='font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#191528'>"
            f"<h2 style='margin:0 0 4px'>Recuperação da tarde — {DIAS_PT[dia.weekday()]}, {dia:%d/%m/%Y}</h2>"
            f"<p style='margin:0 0 10px;color:#68667d'>A lista de prioridade vai no PDF em anexo (1 página).</p>"
            f"<table style='border-collapse:collapse;margin-bottom:12px'><tr>{celulas}</tr></table>"
            f"<ul style='padding-left:18px'>{''.join(f'<li style=MG>{x}</li>' for x in analise_matinal(D))}</ul>"
            f"<p style='color:#68667d;font-size:12px;margin-top:18px'>Enviado pela plataforma PCM · <a href='{PAINEL_URL}'>abrir o painel</a>. "
            f"Responder este e-mail não registra nada.</p></div>").replace("style=MG", "style='margin:4px 0'")


def rodar_matinal(dia: date, agora: datetime, sem_email: bool):
    log(f"gerando recuperação da tarde de {DIAS_PT[dia.weekday()]} {dia:%d/%m/%Y}")
    D = calcular_matinal(dia)
    for av in D["avisos"]:
        log(av, "WARN")
    os.makedirs(PASTA_MAT, exist_ok=True)
    html_path = os.path.join(PASTA_MAT, f"{dia:%Y-%m-%d}.html")
    pdf_path = os.path.join(PASTA_MAT, f"{dia:%Y-%m-%d}.pdf")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(montar_html_matinal(D, dia, agora))
    ok_pdf = html_para_pdf(html_path, pdf_path)
    log(f"HTML gravado · PDF {'ok' if ok_pdf else 'NÃO gerado'} · manhã {len(D['manha'])} · "
        f"pendentes {len(D['pend'])} em {len(D['os'])} OS · HH {D['hhPend']:.0f} + {D['hhTarde']:.0f}")
    limpar_antigos(agora.date(), PASTA_MAT)
    envio = {"enviado": False, "motivo": "--sem-email"}
    if not sem_email:
        m, p = len(D["manha"]), len(D["pend"])
        assunto = (f"Recuperação da tarde · {DIAS_PT[dia.weekday()][:3]} {dia:%d/%m} · "
                   + (f"manhã fechou {pct(m - p, m):.0f}%" if m else "sem programação")
                   + f" · {p} pendentes em {len(D['os'])} OS · {D['hhPend']:.0f} h a recuperar")
        envio = enviar_email(assunto, resumo_email_matinal(D, dia), pdf_path if ok_pdf else None,
                             f"Recuperacao_da_Tarde_{dia:%Y-%m-%d}.pdf",
                             var_para="RELATORIO_MATINAL_PARA", tag="matinal", dia=f"{dia:%Y-%m-%d}")
    return {"ultimoDia": dia.isoformat(), "geradoEm": agora.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
            "pdf": ok_pdf, "envio": envio,
            "resumo": {"manha": len(D["manha"]), "pendentes": len(D["pend"]), "os": len(D["os"]),
                       "hhPend": round(D["hhPend"], 1), "hhTarde": round(D["hhTarde"], 1)}}


# ── orquestração ──────────────────────────────────────────────────────────
def limpar_antigos(hoje: date, pasta=None):
    pasta = pasta or PASTA
    corte = hoje - timedelta(days=GUARDAR_DIAS)
    for p in glob.glob(os.path.join(pasta, "20??-??-??.*")):
        try:
            if date.fromisoformat(os.path.basename(p)[:10]) < corte:
                os.remove(p)
                log(f"apagado {os.path.basename(p)} (mais de {GUARDAR_DIAS} dias)")
        except Exception:
            pass


def _ler_estado(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _gravar_estado(p, estado):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=1)


def rodar_diario(dia: date, agora: datetime, sem_email: bool):
    log(f"gerando relatório de {DIAS_PT[dia.weekday()]} {dia:%d/%m/%Y}")
    D = calcular(dia)
    for av in D["avisos"]:
        log(av, "WARN")
    os.makedirs(PASTA, exist_ok=True)
    html_path = os.path.join(PASTA, f"{dia:%Y-%m-%d}.html")
    pdf_path = os.path.join(PASTA, f"{dia:%Y-%m-%d}.pdf")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(montar_html(D, dia, agora))
    ok_pdf = html_para_pdf(html_path, pdf_path)
    log(f"HTML gravado · PDF {'ok' if ok_pdf else 'NÃO gerado'} · prog {D['prog']} fin {D['fin']} · "
        f"não prog {D['naoProg']['n']} · relig {len(D['relig'])}")
    limpar_antigos(agora.date())
    envio = {"enviado": False, "motivo": "--sem-email"}
    if not sem_email:
        ader = pct(D["fin"], D["prog"])
        assunto = (f"Relatório diário de manutenção · {DIAS_PT[dia.weekday()][:3]} {dia:%d/%m} · "
                   + (f"aderência {ader:.0f}%" if D["prog"] else "sem programação")
                   + f" · {D['naoProg']['n']} não programadas · {len(D['relig'])} religamentos")
        envio = enviar_email(assunto, resumo_email(D, dia, analise(D)), pdf_path if ok_pdf else None,
                             f"Relatorio_Diario_Manutencao_{dia:%Y-%m-%d}.pdf", dia=f"{dia:%Y-%m-%d}")
    return {"ultimoDia": dia.isoformat(), "geradoEm": agora.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
            "pdf": ok_pdf, "envio": envio,
            "resumo": {"prog": D["prog"], "fin": D["fin"], "naoProg": D["naoProg"]["n"], "relig": len(D["relig"])}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--janela", choices=["auto", "diario", "matinal"], default="auto",
                    help="auto = decide pelo horário (padrão); diario = só o de ontem; matinal = só o do meio-dia")
    ap.add_argument("--dia", help="AAAA-MM-DD (padrão: ontem no diário, hoje no matinal)")
    ap.add_argument("--forcar", action="store_true", help="gera mesmo fora do horário / já gerado")
    ap.add_argument("--sem-email", action="store_true")
    ap.add_argument("--saida", help="pasta de saída (padrão relatorios/diario e relatorios/matinal)")
    a = ap.parse_args()
    global PASTA, ESTADO_ARQ, PASTA_MAT, ESTADO_MAT
    if a.saida:
        PASTA = a.saida
        ESTADO_ARQ = os.path.join(PASTA, "_estado.json")
        PASTA_MAT = os.path.join(a.saida, "matinal")
        ESTADO_MAT = os.path.join(PASTA_MAT, "_estado.json")

    agora = datetime.now(BR)
    fez = 0

    # ── diário (ontem), primeira rodada após HORA_ENVIO ──
    if a.janela in ("auto", "diario"):
        dia = date.fromisoformat(a.dia) if a.dia else (agora.date() - timedelta(days=1))
        estado = _ler_estado(ESTADO_ARQ)
        if a.forcar or (agora.hour >= HORA_ENVIO and estado.get("ultimoDia") != dia.isoformat()):
            _gravar_estado(ESTADO_ARQ, rodar_diario(dia, agora, a.sem_email))
            fez += 1
        elif a.janela == "diario":
            log(f"diário: {'antes das %02d:00 BRT' % HORA_ENVIO if agora.hour < HORA_ENVIO else 'já gerado hoje'} — nada a fazer")

    # ── meio-dia (hoje), primeira rodada após HORA_MATINAL, só dia útil ──
    if a.janela in ("auto", "matinal"):
        dia = date.fromisoformat(a.dia) if a.dia else agora.date()
        estado = _ler_estado(ESTADO_MAT)
        util = dia.weekday() < 5
        if a.forcar or (util and agora.hour >= HORA_MATINAL and estado.get("ultimoDia") != dia.isoformat()):
            _gravar_estado(ESTADO_MAT, rodar_matinal(dia, agora, a.sem_email))
            fez += 1
        elif a.janela == "matinal":
            log(f"matinal: {'fim de semana' if not util else 'antes das %02d:00 BRT' % HORA_MATINAL if agora.hour < HORA_MATINAL else 'já gerado hoje'} — nada a fazer")

    if not fez and a.janela == "auto":
        log(f"{agora:%H:%M} BRT — nenhuma janela a gerar agora")
    return 0


if __name__ == "__main__":
    sys.exit(main())
