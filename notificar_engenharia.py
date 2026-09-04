# -*- coding: utf-8 -*-
"""
E-mails do módulo Confiabilidade — etapa 3.

Chamado no fim do gerar_engenharia_json.py, com o dado que acabou de ser gerado.
Quatro regras, na ordem em que rodam:

  1. EVENTO NOVO   ativo que acendeu (ou subiu de nível) desde a rodada anterior
                   → engenharia (ENG_EMAIL_PARA). Um e-mail por evento.
  2. RELATÓRIO     FMEA / Causa Raiz emitido no painel e ainda não avisado
                   → engenharia + responsável do cluster. Corpo = a folha em HTML.
                   O PDF sai do painel ("Imprimir / PDF"); aqui vai o conteúdo.
  3. SEM DONO      ticket aberto há 48 h sem ninguém assumir
                   → responsável do cluster + engenharia. Lembra de novo a cada 48 h.
  4. RESUMO        segunda-feira, uma vez na semana → cada responsável recebe
                   os ativos com sinal e os tickets abertos dos clusters dele.

O que impede tempestade: na PRIMEIRA rodada (sem estado gravado) nada é
enviado — só se grava a linha de base. E há um teto por rodada (ENG_EMAIL_MAX).

Estado em engenharia/notificacoes.json — precisa estar no `git add` do
workflow, senão a rodada seguinte não sabe o que já avisou e repete.

Sem SMTP configurado (Secrets SMTP_HOST/USER/PASS), tudo é decidido, logado e
gravado no estado como "não enviado" — não trava o robô, não engana o log.
ENG_EMAIL_DUMP=<pasta> grava cada mensagem como .eml em vez de enviar (teste).
"""
from __future__ import annotations

import json
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from html import escape as h

ESTADO_ARQ = os.environ.get("ENG_NOTIF_ESTADO", os.path.join("engenharia", "notificacoes.json"))
TICKETS_ARQ = os.environ.get("TICKETS_ARQUIVO", os.path.join("engenharia", "tickets.json"))
PAINEL_URL = os.environ.get("PAINEL_URL", "https://pcm.gridco.com.br/novo.html")
MAX_POR_RODADA = int(os.environ.get("ENG_EMAIL_MAX", "20"))
LEMBRETE_H = int(os.environ.get("ENG_LEMBRETE_HORAS", "48"))
NIVEL_ORD = {"monitorar": 1, "atencao": 2, "critico": 3}
ROT = {"critico": "Crítico", "atencao": "Atenção", "monitorar": "Monitorar"}
ETAPAS = {"detectado": "Detectado", "notificado": "Notificado", "analise": "Em análise",
          "acao": "Ação", "verificado": "Verificado"}
BR = timezone(timedelta(hours=-3))


def log(msg, level="INFO"):
    print(f"[{datetime.now():%H:%M:%S}] {level}: {msg}", flush=True)


# ── infraestrutura ────────────────────────────────────────────────────────
def _ler_json(p, padrao):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return padrao


def carregar_estado():
    return _ler_json(ESTADO_ARQ, None)


def gravar_estado(e):
    os.makedirs(os.path.dirname(ESTADO_ARQ) or ".", exist_ok=True)
    tmp = ESTADO_ARQ + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(e, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ESTADO_ARQ)


def mapa_destinatarios():
    """cluster -> 'a@x, b@x'. Secret ALERTA_EMAIL_MAPA manda; recuo é o arquivo."""
    def norm(d):
        out = {}
        for k, v in (d or {}).items():
            if isinstance(v, (list, tuple)):
                v = ", ".join(str(x).strip() for x in v if str(x).strip())
            v = str(v or "").strip()
            if v:
                out[str(k).strip()] = v
        return out
    bruto = os.environ.get("ALERTA_EMAIL_MAPA", "").strip()
    if bruto:
        try:
            m = norm(json.loads(bruto))
            if m:
                return m
        except Exception as e:
            log(f"ALERTA_EMAIL_MAPA inválido ({e}) — usando o arquivo", "WARN")
    return norm(_ler_json("alertas_destinatarios.json", {}).get("mapa"))


class Remetente:
    """Uma conexão por rodada. Sem SMTP: decide, loga, não envia."""

    def __init__(self):
        self.host = os.environ.get("SMTP_HOST", "").strip()
        self.user = os.environ.get("SMTP_USER", "").strip()
        self.pwd = os.environ.get("SMTP_PASS", "").strip()
        self.porta = int(os.environ.get("SMTP_PORT", "587") or 587)
        self.de = os.environ.get("MAIL_FROM", self.user).strip() or "pcm@gridco.com.br"
        self.dump = os.environ.get("ENG_EMAIL_DUMP", "").strip()
        self.configurado = bool(self.host and self.user and self.pwd) or bool(self.dump)
        self.enviados = 0
        self.tentados = 0
        self._smtp = None

    def enviar(self, para, assunto, html):
        dests = sorted({p.strip() for p in str(para or "").split(",") if p.strip()})
        if not dests:
            return False
        self.tentados += 1
        if self.tentados > MAX_POR_RODADA:
            log(f"teto de {MAX_POR_RODADA} e-mails por rodada atingido — '{assunto[:60]}' fica para a próxima", "WARN")
            return False
        msg = MIMEText(f"<div style='font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#191528'>{html}"
                       f"<p style='color:#68667d;font-size:12px;margin-top:18px'>Enviado pela plataforma PCM · "
                       f"<a href='{PAINEL_URL}'>abrir o painel</a>. Responder este e-mail não registra nada — "
                       f"assuma o ticket no painel.</p></div>", "html", "utf-8")
        msg["Subject"] = assunto
        msg["From"] = self.de
        msg["To"] = ", ".join(dests)
        if self.dump:
            os.makedirs(self.dump, exist_ok=True)
            nome = os.path.join(self.dump, f"{self.tentados:03d}_{''.join(c if c.isalnum() else '_' for c in assunto[:50])}.eml")
            with open(nome, "w", encoding="utf-8") as f:
                f.write(msg.as_string())
            self.enviados += 1
            return True
        if not self.configurado:
            log(f"SMTP não configurado — não enviei: '{assunto[:70]}' → {', '.join(dests)}", "WARN")
            return False
        try:
            if self._smtp is None:
                self._smtp = smtplib.SMTP(self.host, self.porta, timeout=60)
                self._smtp.starttls()
                self._smtp.login(self.user, self.pwd)
            self._smtp.sendmail(self.de, dests, msg.as_string())
            self.enviados += 1
            return True
        except Exception as e:
            log(f"falha no envio ({type(e).__name__}: {e}) — '{assunto[:60]}'", "WARN")
            self._smtp = None
            return False

    def fechar(self):
        try:
            if self._smtp:
                self._smtp.quit()
        except Exception:
            pass


# ── pedaços de HTML ───────────────────────────────────────────────────────
def _tab(cabec, linhas):
    th = "".join(f"<th style='text-align:left;padding:5px 8px;border-bottom:1px solid #cbcbdd;font-size:11px;"
                 f"text-transform:uppercase;color:#68667d'>{h(c)}</th>" for c in cabec)
    tr = "".join("<tr>" + "".join(f"<td style='padding:5px 8px;border-bottom:1px solid #e4e4ef'>{c}</td>" for c in l) + "</tr>"
                 for l in linhas)
    return f"<table style='border-collapse:collapse;font-size:13px;width:100%'><tr>{th}</tr>{tr}</table>"


def _pill(nivel):
    cor = {"critico": "#b02525", "atencao": "#a04408", "monitorar": "#5f7f08"}.get(nivel, "#3a3550")
    return f"<b style='color:{cor}'>{h(ROT.get(nivel, nivel))}</b>"


def _ativo_bloco(a):
    conf = ""
    if a.get("mtbf") is not None:
        conf = (f"<tr><td>Confiabilidade</td><td>MTBF {round(a['mtbf'])} h · MTTR {a['mttr']:.1f} h · "
                f"disponibilidade {100 * a['disp']:.1f}%</td></tr>")
    os_ = a.get("os") or []
    ult = (f"<tr><td>Última OS</td><td>#{h(os_[0]['os'])} · {h(os_[0]['t'])} · {h(os_[0]['d'])}</td></tr>") if os_ else ""
    return (f"<table style='font-size:13px;border-collapse:collapse'>"
            f"<tr><td style='padding-right:12px;color:#68667d'>Por quê</td><td>{a['nFalha']} falhas em {a.get('n30', 0)} OS nos últimos 30 dias · "
            f"{a['n7']} nos últimos 7 · P90 da família {h(a['fam'])} é {a['p90']}</td></tr>"
            f"<tr><td style='color:#68667d'>Criticidade</td><td>Classe {h(a['crit'])} (proxy por família)</td></tr>"
            f"{conf}{ult}</table>")


# ── as quatro regras ──────────────────────────────────────────────────────
def eventos_novos(ativos, niveis_antes):
    """Ativo entrou na lista ou subiu de nível. Serviço-como-corretiva não acende."""
    out = []
    for a in ativos:
        if a.get("soServico"):
            continue
        antes = niveis_antes.get(a["cod"])
        if antes is None or NIVEL_ORD.get(a["nivel"], 0) > NIVEL_ORD.get(antes, 0):
            out.append(a)
    return out


def email_evento(rem, a, para):
    assunto = f"[PCM] Evento novo · {ROT[a['nivel']].upper()} · {a['nome'][:40]} · {a['usina']}"
    html = (f"<h2 style='margin:0 0 6px'>{h(a['nome'])} <span style='font-weight:400;color:#68667d'>{h(a['cod'])}</span></h2>"
            f"<p style='margin:0 0 10px'>{h(a['usina'])}{(' · ' + h(a['circuito'])) if a.get('circuito') else ''} — entrou em {_pill(a['nivel'])}.</p>"
            f"{_ativo_bloco(a)}"
            f"<p style='margin-top:12px'>Próximo passo: abrir o ativo no painel → assumir o ticket → emitir FMEA ou Causa Raiz.</p>")
    return rem.enviar(para, assunto, html)


def email_relatorio(rem, r, ativo, para):
    tipo = r.get("tipo", "Relatório")
    assunto = f"[PCM] {r.get('n')} emitido · {tipo} · {(ativo or {}).get('nome', r.get('cod'))[:40]}"
    campos = [c for c in (r.get("campos") or []) if str(c).strip()]
    lista = "".join(f"<li>{h(c)}</li>" for c in campos[:40]) or "<li><i>sem campos preenchidos</i></li>"
    html = (f"<h2 style='margin:0 0 6px'>{h(r.get('n'))} · {h(tipo)} · {h(r.get('rev', 'R00'))}</h2>"
            f"<p style='margin:0 0 10px'>{h((ativo or {}).get('nome', ''))} · {h((ativo or {}).get('usina', ''))} — emitido por {h(r.get('autor', ''))} em {h(r.get('data', ''))}"
            f"{(' · RPN ' + str(r['rpn'])) if r.get('rpn') else ''}.</p>"
            f"<p style='margin:0 0 4px;color:#68667d;font-size:12px'>Campos preenchidos, na ordem da folha:</p><ul style='margin:0;padding-left:18px;font-size:13px'>{lista}</ul>"
            f"<p style='margin-top:12px'>O PDF sai do painel, em Relatórios → abrir → Imprimir / PDF.</p>")
    return rem.enviar(para, assunto, html)


def email_sem_dono(rem, t, ativo, para, horas):
    assunto = f"[PCM] Ticket {t['id']} sem dono há {int(horas)} h · {(ativo or {}).get('nome', t.get('cod'))[:40]}"
    html = (f"<h2 style='margin:0 0 6px'>{h(t['id'])} · {h((ativo or {}).get('nome', t.get('cod')))}</h2>"
            f"<p>{h((ativo or {}).get('usina', ''))} — aberto há <b>{int(horas)} horas</b>, etapa {h(ETAPAS.get(t.get('etapa'), t.get('etapa')))}, "
            f"e ninguém assumiu. Quem assume tira da fila; sem dono o sinal continua acumulando.</p>"
            f"{_ativo_bloco(ativo) if ativo else ''}")
    return rem.enviar(para, assunto, html)


def email_resumo(rem, resp, clusters, ativos, tickets, para):
    n_cr = sum(1 for a in ativos if a["nivel"] == "critico")
    assunto = f"[PCM] Resumo da semana · {len(ativos)} ativos com sinal ({n_cr} críticos) · {len(tickets)} tickets abertos"
    la = _tab(["Nível", "Ativo", "Usina", "Falhas 30 d", "Disp."],
              [[_pill(a["nivel"]), h(a["nome"][:38]), h(a["usina"][:26]), a["nFalha"],
                (f"{100 * a['disp']:.0f}%" if a.get("disp") is not None else "—")]
               for a in ativos[:25]]) if ativos else "<p>Nenhum ativo com sinal nos seus clusters.</p>"
    lt = _tab(["Ticket", "Ativo", "Etapa", "Responsável", "Aberto há"],
              [[h(t["id"]), h((t.get("_ativo") or {}).get("nome", t.get("cod"))[:38]), h(ETAPAS.get(t.get("etapa"), "")),
                h(t.get("resp") or "—"), f"{t.get('_dias', 0)} d"] for t in tickets[:25]]) if tickets else "<p>Nenhum ticket aberto.</p>"
    html = (f"<h2 style='margin:0 0 6px'>Sua semana — {h(resp)}</h2>"
            f"<p style='margin:0 0 10px;color:#68667d'>Clusters: {h(', '.join(sorted(clusters)))}</p>"
            f"<h3 style='margin:12px 0 4px'>Ativos com sinal</h3>{la}"
            f"<h3 style='margin:14px 0 4px'>Tickets abertos</h3>{lt}")
    return rem.enviar(para, assunto, html)


# ── orquestração ──────────────────────────────────────────────────────────
def rodar(dado):
    """dado = o dicionário que virou engenharia.json. Nunca levanta exceção."""
    agora = datetime.now(timezone.utc)
    ativos = [a for a in dado.get("ativos", [])]
    por_cod = {a["cod"]: a for a in ativos}
    estado = carregar_estado()
    primeira = estado is None
    estado = estado or {"niveis": {}, "relatoriosAvisados": [], "lembretes": {}, "resumoSemana": "", "historico": []}
    mapa = mapa_destinatarios()
    eng = os.environ.get("ENG_EMAIL_PARA", "").strip() or os.environ.get("ALERTA_EMAIL_PARA", "").strip()
    rem = Remetente()
    hist = []

    def registrar(tipo, chave, para, ok):
        hist.append({"em": agora.isoformat(timespec="seconds"), "tipo": tipo, "chave": chave,
                     "para": para, "enviado": bool(ok)})

    # 1 — eventos novos
    novos = eventos_novos(ativos, estado.get("niveis", {}))
    if primeira:
        log(f"notificar: primeira rodada — {len(novos)} ativos viram linha de base, nada enviado")
    elif not eng:
        log(f"notificar: {len(novos)} evento(s) novo(s), mas ENG_EMAIL_PARA não está definido — só no painel", "WARN")
    else:
        for a in novos:
            registrar("evento", a["cod"], eng, email_evento(rem, a, eng))
    estado["niveis"] = {a["cod"]: a["nivel"] for a in ativos if not a.get("soServico")}

    # 2 e 3 — dependem do tickets.json (pode não existir ainda)
    tk = _ler_json(TICKETS_ARQ, {}) or {}
    tickets = tk.get("tickets") or []
    relatorios = tk.get("relatorios") or []
    avisados = set(estado.get("relatoriosAvisados", []))
    for r in relatorios:
        n = r.get("n")
        if not n or n in avisados:
            continue
        if primeira:
            avisados.add(n)
            continue
        a = por_cod.get(r.get("cod"))
        para = ", ".join(x for x in [eng, mapa.get((a or {}).get("cluster", ""), "")] if x)
        if para:
            registrar("relatorio", n, para, email_relatorio(rem, r, a, para))
        else:
            log(f"notificar: relatório {n} sem destinatário (ENG_EMAIL_PARA vazio e cluster sem e-mail)", "WARN")
        avisados.add(n)
    estado["relatoriosAvisados"] = sorted(avisados)[-500:]

    lembretes = estado.get("lembretes", {})
    for t in tickets:
        if t.get("etapa") == "verificado" or (t.get("resp") and t.get("resp") != "—"):
            continue
        try:
            aberto = datetime.fromisoformat(str(t.get("abertoEm", "")).replace("Z", "+00:00"))
        except Exception:
            continue
        horas = (agora - aberto).total_seconds() / 3600
        if horas < LEMBRETE_H:
            continue
        ultimo = lembretes.get(t["id"])
        if ultimo:
            try:
                if (agora - datetime.fromisoformat(ultimo)).total_seconds() / 3600 < LEMBRETE_H:
                    continue
            except Exception:
                pass
        if primeira:
            lembretes[t["id"]] = agora.isoformat(timespec="seconds")
            continue
        a = por_cod.get(t.get("cod"))
        para = ", ".join(x for x in [mapa.get((a or {}).get("cluster", ""), ""), eng] if x)
        if para:
            ok = email_sem_dono(rem, t, a, para, horas)
            registrar("sem-dono", t["id"], para, ok)
            lembretes[t["id"]] = agora.isoformat(timespec="seconds")
    estado["lembretes"] = lembretes

    # 4 — resumo semanal, segunda-feira, uma vez por semana ISO
    semana = agora.astimezone(BR).strftime("%G-W%V")
    if agora.astimezone(BR).weekday() == 0 and estado.get("resumoSemana") != semana and not primeira:
        por_resp = {}
        for cl, dest in mapa.items():
            por_resp.setdefault(dest, set()).add(cl)
        for dest, cls in por_resp.items():
            meus = [a for a in ativos if a.get("cluster") in cls and not a.get("soServico")]
            meus_tk = []
            for t in tickets:
                a = por_cod.get(t.get("cod"))
                if t.get("etapa") != "verificado" and a and a.get("cluster") in cls:
                    try:
                        dias = (agora - datetime.fromisoformat(str(t.get("abertoEm", "")).replace("Z", "+00:00"))).days
                    except Exception:
                        dias = 0
                    meus_tk.append(dict(t, _ativo=a, _dias=dias))
            if meus or meus_tk:
                registrar("resumo", dest, dest, email_resumo(rem, dest.split("@")[0].replace(".", " ").title(), cls, meus, meus_tk, dest))
        estado["resumoSemana"] = semana
    elif primeira:
        estado["resumoSemana"] = semana

    rem.fechar()
    estado["historico"] = (estado.get("historico", []) + hist)[-300:]
    estado["ultimaRodada"] = agora.isoformat(timespec="seconds")
    estado["smtpConfigurado"] = rem.configurado
    gravar_estado(estado)
    log(f"notificar: {rem.enviados} enviado(s) de {rem.tentados} · eventos novos {len(novos)} · "
        f"SMTP {'ok' if rem.configurado else 'NÃO configurado'} · estado em {ESTADO_ARQ}")
    return {"enviados": rem.enviados, "tentados": rem.tentados, "eventos": len(novos), "smtp": rem.configurado}


if __name__ == "__main__":
    d = _ler_json(os.environ.get("ENG_SAIDA", "engenharia.json"), None)
    if not d:
        log("engenharia.json não encontrado", "ERRO")
        raise SystemExit(2)
    rodar(d)
