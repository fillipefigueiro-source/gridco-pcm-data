"""
Cadastro Rápido de Usina no Fracttal — Grid Co. O&M / PCM

Gera a árvore de ativos de uma usina inteira a partir do template padrão Grid Co.
(`template_usina_gridco.json`), mostra o preview e publica no Fracttal via API.

Fluxo: preencher → Gerar preview → conferir árvore/validações → Publicar.
Por segurança o modo SIMULAÇÃO vem ligado: nada é escrito no Fracttal até desmarcá-lo.

Credenciais ficam em %APPDATA%\\GridCo\\fracttal.json (fora da pasta compartilhada).
"""

import base64
import csv
import json
import os
import pathlib
import queue
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox, filedialog, scrolledtext

import requests

APP = "Cadastro Rápido de Usina no Fracttal"
VERSAO = "R00"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")


# ====================== Caminhos ======================

def pasta_base():
    """Pasta onde o .exe/.py está (é onde ficam o template e os relatórios)."""
    if getattr(sys, "frozen", False):
        return pathlib.Path(sys.executable).parent
    return pathlib.Path(__file__).resolve().parent


def caminho_template():
    p = pasta_base() / "template_usina_gridco.json"
    if p.exists():
        return p
    embutido = pathlib.Path(getattr(sys, "_MEIPASS", pasta_base())) / "template_usina_gridco.json"
    if embutido.exists():
        return embutido
    raise FileNotFoundError("template_usina_gridco.json não encontrado ao lado do executável.")


def arquivo_credenciais():
    d = pathlib.Path(os.environ.get("APPDATA", pathlib.Path.home())) / "GridCo"
    d.mkdir(parents=True, exist_ok=True)
    return d / "fracttal.json"


def arquivo_ultimo_registro():
    d = pathlib.Path(os.environ.get("APPDATA", pathlib.Path.home())) / "GridCo"
    d.mkdir(parents=True, exist_ok=True)
    return d / "ultimo_registro.json"


def carregar_ultimo_registro():
    f = arquivo_ultimo_registro()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def salvar_ultimo_registro(dados):
    arquivo_ultimo_registro().write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def carregar_credenciais():
    f = arquivo_credenciais()
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    # Fallback para a máquina de desenvolvimento (middleware do App de Campo).
    mw = pasta_base() / "App_Campo" / "middleware" / "local.settings.json"
    if mw.exists():
        v = json.loads(mw.read_text(encoding="utf-8")).get("Values", {})
        if v.get("FRACTTAL_CLIENT_ID"):
            return {"client_id": v["FRACTTAL_CLIENT_ID"], "client_secret": v["FRACTTAL_CLIENT_SECRET"],
                    "base_url": v.get("FRACTTAL_BASE_URL", "https://app.fracttal.com/"),
                    "token_path": v.get("FRACTTAL_TOKEN_PATH", "oauth/token"),
                    "api_base": v.get("FRACTTAL_API_BASE", "https://app.fracttal.com/api/")}
    return {}


# ====================== Cliente Fracttal ======================

class Fracttal:
    def __init__(self, cred):
        self.cred = cred
        self.base = cred.get("base_url", "https://app.fracttal.com/").rstrip("/") + "/"
        self.api = cred.get("api_base", "https://app.fracttal.com/api/").rstrip("/") + "/"
        self.token_path = cred.get("token_path", "oauth/token")
        self._tok = None
        self._exp = 0
        self.evento_parar = threading.Event()  # setado pelo botão "Parar" na interface

    def _checar_parada(self):
        if self.evento_parar.is_set():
            raise InterruptedError("Interrompido pelo usuário")

    def _dormir_interrompivel(self, segundos):
        """Espera em fatias de 1s, checando a parada a cada uma — assim o botão Parar não
        fica preso atrás de uma espera longa de 429 (até 60s)."""
        fim = time.time() + segundos
        while time.time() < fim:
            self._checar_parada()
            time.sleep(min(1, fim - time.time()))
        self._checar_parada()

    def token(self):
        if self._tok and time.time() < self._exp:
            return self._tok
        cid, sec = self.cred.get("client_id"), self.cred.get("client_secret")
        if not cid or not sec:
            raise RuntimeError("Credenciais do Fracttal não configuradas (botão 'Credenciais').")
        basic = base64.b64encode(f"{cid}:{sec}".encode()).decode()
        r = requests.post(self.base + self.token_path,
                          headers={"Authorization": "Basic " + basic, "User-Agent": UA,
                                   "Content-Type": "application/x-www-form-urlencoded"},
                          data={"grant_type": "client_credentials"}, timeout=25)
        if not r.ok:
            raise RuntimeError(f"OAuth Fracttal falhou: HTTP {r.status_code} {r.text[:160]}")
        j = r.json()
        self._tok = j.get("access_token") or j.get("token")
        self._exp = time.time() + int(j.get("expires_in", 3600)) - 60
        return self._tok

    def _h(self):
        return {"Authorization": "Bearer " + self.token(), "User-Agent": UA,
                "Accept": "application/json", "Content-Type": "application/json"}

    def _espera_retry(self, r):
        """429 = limite de requisições por IP: respeita o Retry-After do Fracttal (ou 60s por
        padrão, já que a mensagem deles pede 1 minuto). Erros 5xx (instabilidade pontual do
        servidor) continuam com uma espera curta, não precisam de 1 minuto inteiro."""
        if r.status_code == 429:
            ra = r.headers.get("Retry-After")
            try:
                return max(int(float(ra)), 1) + 2 if ra else 60
            except (TypeError, ValueError):
                return 60
        return None  # sinaliza "usa o backoff padrão" pra quem chamou

    def get(self, path, tentativas=3):
        for i in range(tentativas):
            self._checar_parada()
            r = requests.get(self.api + path, headers=self._h(), timeout=60)
            if r.ok:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504) and i < tentativas - 1:
                self._checar_parada()
                self._dormir_interrompivel(self._espera_retry(r) or 2 * (i + 1))
                continue
            raise RuntimeError(f"GET {path} → HTTP {r.status_code} {r.text[:160]}")

    def post(self, path, body, tentativas=3):
        for i in range(tentativas):
            self._checar_parada()
            r = requests.post(self.api + path, headers=self._h(),
                              data=json.dumps(body, ensure_ascii=False).encode("utf-8"), timeout=60)
            if r.ok:
                try:
                    return r.json()
                except Exception:
                    return {"success": True}
            if r.status_code in (429, 500, 502, 503, 504) and i < tentativas - 1:
                self._checar_parada()
                self._dormir_interrompivel(self._espera_retry(r) or 2 * (i + 1))
                continue
            raise RuntimeError(f"POST {path} → HTTP {r.status_code} {r.text[:200]}")

    def put(self, path, body, tentativas=3):
        for i in range(tentativas):
            self._checar_parada()
            r = requests.put(self.api + path, headers=self._h(),
                             data=json.dumps(body, ensure_ascii=False).encode("utf-8"), timeout=60)
            if r.ok:
                try:
                    return r.json()
                except Exception:
                    return {"success": True}
            if r.status_code in (429, 500, 502, 503, 504) and i < tentativas - 1:
                self._checar_parada()
                self._dormir_interrompivel(self._espera_retry(r) or 2 * (i + 1))
                continue
            raise RuntimeError(f"PUT {path} → HTTP {r.status_code} {r.text[:200]}")

    def vincular_plano(self, item_code, id_tasks_plan, code_user, last_date_maintenance=None):
        """Fase 2: vincula um plano de manutenção a um ativo já criado.
        Endpoint separado do insert — id_group_task não funciona no POST /api/items."""
        if not last_date_maintenance:
            last_date_maintenance = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S+00:00")
        corpo = {"id_tasks_plan": id_tasks_plan, "code_user": code_user,
                 "last_date_maintenance": last_date_maintenance}
        return self.put(f"items_associate_tasks_plan/{item_code}/", corpo)

    def item_por_codigo(self, code):
        j = self.get("items?limit=1&code=" + requests.utils.quote(code))
        d = j.get("data") or []
        return d[0] if d else None

    def localizacoes(self, progresso=None):
        """Todas as localizações (usado p/ achar a raiz do cliente e conferir duplicidade)."""
        out, start = [], 0
        while True:
            j = self.get(f"items?limit=99&start={start}&id_type_item=1")
            d = j.get("data") or []
            out += d
            if progresso:
                progresso(len(out), j.get("total", 0))
            if not d or len(out) >= int(j.get("total", 0)):
                break
            start += len(d)
        return [x for x in out if x.get("id_type_item") == 1]


# ====================== Motor de template ======================

class Gerador:
    # sigla do equipamento -> chave do campo de modelo na tela
    MODELO_POR_SIGLA = {"INVR": "modelo_invr", "TRFR": "modelo_trfr", "RELE": "modelo_rele",
                        "ETKR": "modelo_etkr", "MDFV": "modelo_mdfv"}

    # cliente (normalizado, maiúsculo) -> prefixo extra que entra no código da usina (item 1)
    PREFIXOS_CLIENTE = {"ATHON": "ATHN"}

    def __init__(self, template):
        self.t = template
        self.nos = template["nos"]
        self.planos = template["planos"]

    def gerar(self, p, ligados):
        """p: dicionário de parâmetros da tela. ligados: set de siglas habilitadas."""
        pre = f"{p['sigla']}{p['num']}"                            # prefixo usado pelos FILHOS — nunca leva ATHN
        prefixo_extra = self.PREFIXOS_CLIENTE.get(p["cliente"].strip().upper())
        codigo_usina = f"{prefixo_extra}-{pre}" if prefixo_extra else pre  # só o item 1 leva o prefixo extra
        ativos = []
        inst = {"USINA": [(codigo_usina, "")]}                      # sigla -> [(código, índice)]
        contador = {}

        ativos.append(dict(tipo="L", code=codigo_usina, nome=p["nome_usina"], pai=p["cliente"],
                           plano="USINA", prio=1, nivel=0))

        for no in self.nos:
            sig = no["sig"]
            chave = f"{sig}|{no['nome']}"
            if chave not in ligados:
                continue
            pais = inst.get(no["pai"], [])
            if not pais:
                continue
            criados = []
            for ordem_pai, (pai_code, pai_idx) in enumerate(pais, 1):
                qtd = self._qtd(no.get("qtd", 1), p, ordem_pai)
                inicio = self._inicio(no.get("qtd", 1), p, ordem_pai)
                # Tracker: um conjunto por bloco declarado (ex.: "101,102")
                blocos = [b.strip() for b in str(p.get("bloco", "")).split(",") if b.strip()] or ["100"]
                for j in self._indices(qtd, no, blocos, p.get("trackers_lista"), inicio):
                    if no.get("sub"):                       # Inversor/Disjuntor: {qgbt}.{n}
                        idx = f"{pai_idx}.{j}"
                    elif no.get("bloco"):                   # Tracker: {n}.{bloco} (j já vem pronto)
                        idx = str(j)
                    elif qtd == 1 and pai_idx:              # herda o número do pai
                        idx = str(pai_idx)
                    else:
                        contador[sig] = contador.get(sig, 0) + 1
                        idx = str(contador[sig])
                    sufixo = "" if no.get("num") is False else idx
                    if no.get("cli"):
                        code = f"{pre}-{sig}{sufixo}"
                    elif no.get("pfx"):
                        code = f"{pai_code}-{sig}{sufixo}"
                    else:
                        code = f"{pre}-{sig}{sufixo}"
                    nome = no["nome"].replace("{i}", idx).strip()
                    ativos.append(dict(tipo=no["t"], code=code, nome=nome, pai=pai_code,
                                       plano=no.get("pl"), prio=no.get("pr") or 3,
                                       nivel=0, modelo=p.get(self.MODELO_POR_SIGLA.get(sig, ""), "")))
                    criados.append((code, idx))
            if no["t"] == "L" or no.get("registra_pai"):
                # setdefault+extend (não sobrescreve) — permite duas definições da mesma sigla
                # (ex.: INVR no padrão QGBT e no Ponto de Entrega) alimentarem o mesmo "pai".
                inst.setdefault(sig, []).extend(criados)
        return ativos

    @staticmethod
    def _indices(qtd, no, blocos, lista="", inicio=1):
        """Sequência de índices de um nó.

        Trackers: se a lista do as-built for colada ('1.101,2.101,...'), usa ela verbatim;
        senão gera o produto {linha}×{bloco}, começando em `inicio` (1 por padrão, ou o
        início de um intervalo tipo '6-15' digitado no campo de quantidade).
        """
        if no.get("bloco"):
            itens = [x.strip() for x in str(lista or "").replace(";", ",").split(",") if x.strip()]
            if itens:
                return itens
            return [f"{j}.{b}" for b in blocos for j in range(inicio, inicio + qtd)]
        return list(range(inicio, inicio + qtd))

    @staticmethod
    def _valor_bruto(q, p, ordem_pai=1):
        """Resolve o texto bruto de um campo de quantidade: número fixo, campo da tela,
        ou a fatia certa de uma lista por pai ('4,2,4')."""
        if isinstance(q, int):
            return str(q)
        bruto = str(p.get(q, 0) or 0).strip()
        if "," in bruto:
            partes = [x.strip() for x in bruto.split(",") if x.strip()]
            bruto = partes[ordem_pai - 1] if ordem_pai <= len(partes) else partes[-1]
        return bruto

    @staticmethod
    def _qtd(q, p, ordem_pai=1):
        """Quantidade fixa, parâmetro da tela, lista por pai ('4,2,4' = 4 no 1º QGBT, 2 no
        2º...) ou intervalo ('6-15' = 10 itens, numerados de 6 a 15 — ver _inicio)."""
        bruto = Gerador._valor_bruto(q, p, ordem_pai)
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", bruto)
        if m:
            ini, fim = int(m.group(1)), int(m.group(2))
            return max(0, fim - ini + 1)
        try:
            return max(0, int(float(bruto)))
        except ValueError:
            return 0

    @staticmethod
    def _inicio(q, p, ordem_pai=1):
        """Número inicial da numeração — 1 por padrão, ou o início de um intervalo tipo
        '6-15' digitado no campo de quantidade."""
        bruto = Gerador._valor_bruto(q, p, ordem_pai)
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", bruto)
        return int(m.group(1)) if m else 1

    def validar(self, p, ativos):
        v = []
        codes = [a["code"] for a in ativos]
        dup = sorted({c for c in codes if codes.count(c) > 1})
        v.append(("erro" if dup else "ok",
                  f"{len(dup)} código(s) duplicado(s): {', '.join(dup[:5])}" if dup
                  else "Nenhum código duplicado"))
        longos = [c for c in codes if len(c) > 100]
        v.append(("erro" if longos else "ok",
                  f"{len(longos)} código(s) acima de 100 caracteres" if longos
                  else "Códigos dentro do limite de 100 caracteres"))
        v.append(("erro", "Classificação 1 e 2 são obrigatórias") if not (p["cls1"] and p["cls2"])
                 else ("ok", "Classificação 1 e 2 preenchidas"))
        try:
            la, lo = float(p["lat"]), float(p["lon"])
            ok = -34 <= la <= 6 and -74 <= lo <= -32
        except Exception:
            ok = False
        v.append(("ok", "Coordenadas dentro do Brasil") if ok
                 else ("erro", "Coordenadas inválidas ou fora do Brasil"))
        sem = sum(1 for a in ativos if not a["plano"])
        v.append(("aviso", f"{sem} ativo(s) sem plano de manutenção (segue o padrão atual da base)"))
        return v


# ====================== Interface ======================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP} · {VERSAO}")
        self.geometry("1280x860")
        self.minsize(1100, 720)
        self.template = json.loads(caminho_template().read_text(encoding="utf-8"))
        self.gerador = Gerador(self.template)
        self.fx = Fracttal(carregar_credenciais())
        self.ativos = []
        self.excluidos = set()
        self.raizes = {}
        self.fila = queue.Queue()
        self._montar()
        self._carregar_ultimo_registro_silencioso()
        self.after(120, self._drenar_fila)
        self.gerar_preview()

    # ---------- layout ----------
    def _montar(self):
        top = tk.Frame(self, bg="#191528", height=46)
        top.pack(fill="x")
        tk.Label(top, text="  ⬛ ", bg="#191528", fg="#A9DB21", font=("Segoe UI", 14)).pack(side="left")
        tk.Label(top, text=APP, bg="#191528", fg="white",
                 font=("Segoe UI", 12, "bold")).pack(side="left", pady=10)
        tk.Label(top, text=f"Grid Co. O&M · PCM · template {self.template['versao']}",
                 bg="#191528", fg="#b8b5c9", font=("Segoe UI", 9)).pack(side="left", padx=12)
        ttk.Button(top, text="Credenciais", command=self.dlg_credenciais).pack(side="right", padx=8, pady=8)

        corpo = tk.PanedWindow(self, orient="horizontal", sashwidth=6, bg="#e2e2ee")
        corpo.pack(fill="both", expand=True)

        esq = tk.Frame(corpo, padx=10, pady=10)
        corpo.add(esq, width=440, minsize=380)
        dir_ = tk.Frame(corpo, padx=10, pady=10)
        corpo.add(dir_, minsize=520)

        self._form(esq)
        self._preview(dir_)

    def _campo(self, pai, rot, chave, valor="", largura=28):
        lin = tk.Frame(pai)
        lin.pack(fill="x", pady=2)
        tk.Label(lin, text=rot, width=17, anchor="w", font=("Segoe UI", 8)).pack(side="left")
        e = ttk.Entry(lin, width=largura)
        e.insert(0, valor)
        e.pack(side="left", fill="x", expand=True)
        self.campos[chave] = e
        return e

    def _form(self, pai):
        self.campos = {}
        nb = ttk.Notebook(pai)
        nb.pack(fill="both", expand=True)

        ab1 = tk.Frame(nb, padx=8, pady=8); nb.add(ab1, text="Usina")
        cv1 = tk.Canvas(ab1, highlightthickness=0)
        sb1 = ttk.Scrollbar(ab1, orient="vertical", command=cv1.yview)
        interno1 = tk.Frame(cv1)
        interno1.bind("<Configure>", lambda e: cv1.configure(scrollregion=cv1.bbox("all")))
        cv1.create_window((0, 0), window=interno1, anchor="nw")
        cv1.configure(yscrollcommand=sb1.set)
        cv1.pack(side="left", fill="both", expand=True)
        sb1.pack(side="right", fill="y")

        def _rolar_usina(evento):
            cv1.yview_scroll(int(-1 * (evento.delta / 120)), "units")
        cv1.bind("<Enter>", lambda e: cv1.bind_all("<MouseWheel>", _rolar_usina))
        cv1.bind("<Leave>", lambda e: cv1.unbind_all("<MouseWheel>"))

        ab1 = interno1  # a partir daqui, os widgets da aba Usina vão dentro do frame com scroll
        tk.Label(ab1, text="IDENTIFICAÇÃO", font=("Segoe UI", 8, "bold"), fg="#7a7890").pack(anchor="w")
        self._campo(ab1, "Cliente (prefixo)", "cliente", "2C")
        self._campo(ab1, "Sigla", "sigla", "IPX")
        self._campo(ab1, "Número", "num", "100")
        self._campo(ab1, "Nome da usina", "nome_usina", "Ipixuna do Pará 1")
        self._campo(ab1, "Classificação 1", "cls1", "2C - Ipixuna do Pará 1 - PA")
        self._campo(ab1, "Classificação 2 (cluster)", "cls2", "PA Norte 03")
        tk.Label(ab1, text="LOCALIZAÇÃO", font=("Segoe UI", 8, "bold"), fg="#7a7890").pack(anchor="w", pady=(10, 0))
        self._campo(ab1, "Endereço", "endereco", "Fazenda Santa Cecília S/N")
        self._campo(ab1, "Município", "cidade", "Ipixuna do Pará")
        self._campo(ab1, "UF", "uf", "Pará")
        self._campo(ab1, "País", "pais", "Brasil")
        self._campo(ab1, "Latitude", "lat", "-2.694722")
        self._campo(ab1, "Longitude", "lon", "-47.471203")
        tk.Label(ab1, text="QUANTIDADES", font=("Segoe UI", 8, "bold"), fg="#7a7890").pack(anchor="w", pady=(10, 0))
        self._campo(ab1, "Cabines", "cabines", "1")
        self._campo(ab1, "SKIDs por cabine", "skids", "3")
        self._campo(ab1, "Inversores por QGBT", "inversores", "8")
        self._campo(ab1, "Trackers (por bloco)", "trackers", "180")
        self._campo(ab1, "Blocos (ex.: 101,102)", "bloco", "101")
        self._campo(ab1, "Trackers as-built", "trackers_lista", "")
        self._campo(ab1, "Piranômetros", "piranometros", "3")
        self._campo(ab1, "NCU", "ncu", "1")
        self._campo(ab1, "RSU", "rsu", "1")
        self._campo(ab1, "Estruturas fixas", "fixas", "0")
        self._campo(ab1, "Pontos de entrega", "pontos_entrega", "0")
        self._campo(ab1, "Inversores por Ponto de Entrega", "invr_pecn", "0")
        tk.Label(ab1, text="Quantidades aceitam lista por pai: 'Inversores = 4,2,4' → 4 no 1º QGBT, 2 no 2º, 4 no 3º.\n"
                           "'Trackers as-built': cole a lista do projeto (1.101,2.101,…) e ela manda no lugar do cálculo.",
                 font=("Segoe UI", 7), fg="#7a7890", justify="left", wraplength=380).pack(anchor="w", pady=(6, 0))
        tk.Label(ab1, text="MODELOS DE EQUIPAMENTO", font=("Segoe UI", 8, "bold"), fg="#7a7890").pack(anchor="w", pady=(10, 0))
        self._campo(ab1, "Modelo de inversor", "modelo_invr")
        self._campo(ab1, "Modelo de trafo", "modelo_trfr")
        self._campo(ab1, "Modelo de Relé", "modelo_rele")
        self._campo(ab1, "Modelo de tracker", "modelo_etkr")
        self._campo(ab1, "Modelo de módulo", "modelo_mdfv")
        tk.Label(ab1, text="Opcional — vai para o campo Modelo (field_3) desses equipamentos no Fracttal. "
                           "Em branco, o Fracttal fica sem modelo preenchido (dá pra completar depois manualmente).",
                 font=("Segoe UI", 7), fg="#7a7890", justify="left", wraplength=380).pack(anchor="w", pady=(2, 0))

        ab2 = tk.Frame(nb, padx=8, pady=8); nb.add(ab2, text="Catálogo")
        tk.Label(ab2, text="Desmarque o que a usina não tem. % = presença nas 122 usinas de hoje.",
                 font=("Segoe UI", 8), fg="#7a7890", wraplength=380, justify="left").pack(anchor="w", pady=(0, 6))
        cv = tk.Canvas(ab2, highlightthickness=0)
        sb = ttk.Scrollbar(ab2, orient="vertical", command=cv.yview)
        interno = tk.Frame(cv)
        interno.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window((0, 0), window=interno, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _rolar_catalogo(evento):
            cv.yview_scroll(int(-1 * (evento.delta / 120)), "units")
        cv.bind("<Enter>", lambda e: cv.bind_all("<MouseWheel>", _rolar_catalogo))
        cv.bind("<Leave>", lambda e: cv.unbind_all("<MouseWheel>"))
        self.toggles = {}
        for no in self.template["nos"]:
            ch = f"{no['sig']}|{no['nome']}"
            var = tk.BooleanVar(value=not no.get("opc"))
            self.toggles[ch] = var
            lin = tk.Frame(interno)
            lin.pack(fill="x", anchor="w")
            ttk.Checkbutton(lin, variable=var, command=self.gerar_preview).pack(side="left")
            rot = no["nome"].replace(" {i}", "")
            tk.Label(lin, text=f"{rot}", font=("Segoe UI", 8),
                     width=30, anchor="w").pack(side="left")
            tk.Label(lin, text=f"{no['sig']:6s} {'LOC' if no['t'] == 'L' else 'EQP'} {no.get('pres', 0):3d}%",
                     font=("Consolas", 7), fg="#7a7890").pack(side="left")

        botoes = tk.Frame(pai)
        botoes.pack(fill="x", pady=(8, 0))
        ttk.Button(botoes, text="Gerar preview", command=self.gerar_preview).pack(side="left")
        ttk.Button(botoes, text="💾 Salvar registro", command=self.salvar_registro).pack(side="left", padx=4)
        self.sim = tk.BooleanVar(value=True)
        ttk.Checkbutton(botoes, text="Simulação (não escreve)", variable=self.sim).pack(side="left", padx=8)
        self.btn_pub = ttk.Button(botoes, text="Publicar no Fracttal", command=self.publicar)
        self.btn_pub.pack(side="right")

    def _preview(self, pai):
        kp = tk.Frame(pai)
        kp.pack(fill="x")
        self.kpi = {}
        for chave, rot in [("tot", "ativos"), ("loc", "localizações"), ("eq", "equipamentos"), ("pl", "com plano")]:
            c = tk.Frame(kp, bd=1, relief="solid", padx=12, pady=6)
            c.pack(side="left", padx=(0, 8))
            lb = tk.Label(c, text="0", font=("Segoe UI", 15, "bold"))
            lb.pack()
            tk.Label(c, text=rot, font=("Segoe UI", 7), fg="#7a7890").pack()
            self.kpi[chave] = lb

        nb = ttk.Notebook(pai)
        nb.pack(fill="both", expand=True, pady=8)
        f1 = tk.Frame(nb); nb.add(f1, text="Árvore")
        arv_topo = tk.Frame(f1)
        arv_topo.pack(fill="x")
        ttk.Button(arv_topo, text="Excluir selecionado(s)", command=self.excluir_selecionados).pack(side="left")
        ttk.Button(arv_topo, text="Reincluir selecionado(s)", command=self.reincluir_selecionados).pack(side="left", padx=4)
        ttk.Button(arv_topo, text="Restaurar todos", command=self.restaurar_todos).pack(side="left")
        tk.Label(arv_topo, text="Selecione (clique, Ctrl/Shift p/ vários) e excluia — os filhos do "
                                 "item excluído saem junto.", font=("Segoe UI", 7), fg="#7a7890").pack(side="left", padx=8)
        self.lbl_excluidos = tk.Label(arv_topo, text="", font=("Segoe UI", 7, "bold"), fg="#c0392b")
        self.lbl_excluidos.pack(side="right")
        arv_corpo = tk.Frame(f1)
        arv_corpo.pack(fill="both", expand=True)
        self.arvore = ttk.Treeview(arv_corpo, columns=("nome", "tipo", "plano"), show="tree headings", height=18)
        self.arvore.heading("#0", text="Código")
        self.arvore.column("#0", width=230)
        for c, t, w in [("nome", "Nome", 220), ("tipo", "Tipo", 50), ("plano", "Plano de manutenção", 220)]:
            self.arvore.heading(c, text=t)
            self.arvore.column(c, width=w)
        self.arvore.tag_configure("excluido", foreground="#c0392b")
        sb = ttk.Scrollbar(arv_corpo, orient="vertical", command=self.arvore.yview)
        self.arvore.configure(yscrollcommand=sb.set)
        self.arvore.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        f2 = tk.Frame(nb); nb.add(f2, text="Validações")
        self.val = scrolledtext.ScrolledText(f2, height=10, font=("Consolas", 9), wrap="word")
        self.val.pack(fill="both", expand=True)

        f3 = tk.Frame(nb); nb.add(f3, text="Log de publicação")
        self.log = scrolledtext.ScrolledText(f3, height=10, font=("Consolas", 9), wrap="word")
        self.log.pack(fill="both", expand=True)
        rodape_log = tk.Frame(f3)
        rodape_log.pack(fill="x", pady=(4, 0))
        self.btn_parar = ttk.Button(rodape_log, text="⏹ Parar", command=self.parar, state="disabled")
        self.btn_parar.pack(side="right")

        self.status = tk.Label(pai, text="pronto", anchor="w", font=("Segoe UI", 8), fg="#7a7890")
        self.status.pack(fill="x")

    # ---------- ações ----------
    def parametros(self):
        p = {k: e.get().strip() for k, e in self.campos.items()}
        p["cliente"] = p["cliente"].upper()
        p["sigla"] = p["sigla"].upper()
        return p

    def ligados(self):
        return {k for k, v in self.toggles.items() if v.get()}

    def salvar_registro(self):
        """Salva os campos da tela + as marcações do Catálogo, pra reabrir o app depois
        já preenchido com o último registro feito — não salva nada no Fracttal."""
        dados = {
            "campos": {k: e.get() for k, e in self.campos.items()},
            "toggles": {ch: bool(var.get()) for ch, var in self.toggles.items()},
            "salvo_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            salvar_ultimo_registro(dados)
            self.status.config(text=f"Registro salvo às {datetime.now():%H:%M:%S} "
                                     f"({arquivo_ultimo_registro()})")
            messagebox.showinfo(APP, "Registro salvo. Da próxima vez que abrir o app, "
                                      "os campos e o Catálogo vêm preenchidos com isso.")
        except Exception as e:
            messagebox.showerror(APP, f"Não consegui salvar o registro: {e}")

    def _carregar_ultimo_registro_silencioso(self):
        """Chamado uma vez, na abertura do app — preenche os campos e o Catálogo com o
        último registro salvo, se existir. Não gera preview nem mostra nenhum aviso."""
        dados = carregar_ultimo_registro()
        if not dados:
            return
        for k, v in dados.get("campos", {}).items():
            e = self.campos.get(k)
            if e is not None:
                e.delete(0, "end")
                e.insert(0, v)
        for ch, marcado in dados.get("toggles", {}).items():
            var = self.toggles.get(ch)
            if var is not None:
                var.set(marcado)
        if dados.get("salvo_em"):
            self.status.config(text=f"Último registro carregado (salvo em {dados['salvo_em']})")

    def gerar_preview(self, *_):
        try:
            p = self.parametros()
            self.ativos = self.gerador.gerar(p, self.ligados())
        except Exception as e:
            messagebox.showerror(APP, f"Erro ao gerar: {e}")
            return
        codigos_novos = {a["code"] for a in self.ativos}
        self.excluidos &= codigos_novos  # mantém só exclusões cujo código ainda existe na nova geração
        self.node_por_code = {}         # code -> item id do Treeview
        self.code_por_node = {}         # item id do Treeview -> code

        self.arvore.delete(*self.arvore.get_children())
        agrupados = {}
        for a in self.ativos:
            agrupados.setdefault(a["pai"], []).append(a)

        def inserir(pai_code, no_tk):
            for f in agrupados.get(pai_code, []):
                plano = self.template["planos"].get(f["plano"], ["", ""])[1] if f["plano"] else ""
                n = self.arvore.insert(no_tk, "end", text=f["code"],
                                       values=(f["nome"], "LOC" if f["tipo"] == "L" else "EQP", plano))
                self.node_por_code[f["code"]] = n
                self.code_por_node[n] = f["code"]
                inserir(f["code"], n)

        raiz = self.ativos[0]
        no_raiz = self.arvore.insert("", "end", text=raiz["code"], open=True,
                                     values=(raiz["nome"], "LOC", "USINA GERAL"))
        self.node_por_code[raiz["code"]] = no_raiz
        self.code_por_node[no_raiz] = raiz["code"]
        inserir(raiz["code"], no_raiz)

        for c in self.excluidos:            # reaplica a marcação visual dos que continuam excluídos
            self._repintar(c)

        self._atualizar_kpis_validacoes()
        self.status.config(text=f"preview gerado às {datetime.now():%H:%M:%S}")

    def _atualizar_kpis_validacoes(self):
        """Recalcula KPIs e validações em cima dos ativos EFETIVOS (sem os excluídos).
        Chamado depois de gerar preview e depois de cada exclusão/reinclusão."""
        efetivos = self.ativos_efetivos()
        loc = sum(1 for a in efetivos if a["tipo"] == "L")
        self.kpi["tot"].config(text=str(len(efetivos)))
        self.kpi["loc"].config(text=str(loc))
        self.kpi["eq"].config(text=str(len(efetivos) - loc))
        self.kpi["pl"].config(text=str(sum(1 for a in efetivos if a["plano"])))
        self.lbl_excluidos.config(text=f"{len(self.excluidos)} excluído(s)" if self.excluidos else "")

        self.val.delete("1.0", "end")
        if self.excluidos:
            self.val.insert("end", f"! {len(self.excluidos)} ativo(s) excluído(s) manualmente na árvore "
                                    f"— não entram na publicação.\n")
        for nivel, msg in self.gerador.validar(self.parametros(), efetivos):
            self.val.insert("end", f"{'✓' if nivel == 'ok' else '!' if nivel == 'aviso' else '✕'}  {msg}\n")

    def ativos_efetivos(self):
        """Lista de ativos que serão de fato publicados/exportados — exclui os marcados na árvore."""
        return [a for a in self.ativos if a["code"] not in self.excluidos]

    def _descendentes(self, code):
        """Códigos de todos os descendentes (recursivo) de um ativo, via os nós já criados na árvore."""
        out = []
        node = self.node_por_code.get(code)
        if not node:
            return out
        pilha = list(self.arvore.get_children(node))
        while pilha:
            n = pilha.pop()
            c = self.code_por_node.get(n)
            if c:
                out.append(c)
            pilha.extend(self.arvore.get_children(n))
        return out

    def _repintar(self, code):
        node = self.node_por_code.get(code)
        if node:
            self.arvore.item(node, tags=("excluido",) if code in self.excluidos else ())

    def excluir_selecionados(self):
        sel = self.arvore.selection()
        if not sel:
            return
        raiz_code = self.ativos[0]["code"] if self.ativos else None
        alterados = []
        for node in sel:
            code = self.code_por_node.get(node)
            if not code or code == raiz_code:
                continue
            for c in [code] + self._descendentes(code):
                if c not in self.excluidos:
                    self.excluidos.add(c)
                    alterados.append(c)
        for c in alterados:
            self._repintar(c)
        if alterados:
            self._atualizar_kpis_validacoes()

    def reincluir_selecionados(self):
        sel = self.arvore.selection()
        if not sel:
            return
        alterados = []
        for node in sel:
            code = self.code_por_node.get(node)
            if not code:
                continue
            for c in [code] + self._descendentes(code):
                if c in self.excluidos:
                    self.excluidos.discard(c)
                    alterados.append(c)
        for c in alterados:
            self._repintar(c)
        if alterados:
            self._atualizar_kpis_validacoes()

    def restaurar_todos(self):
        if not self.excluidos:
            return
        for c in list(self.excluidos):
            self.excluidos.discard(c)
            self._repintar(c)
        self._atualizar_kpis_validacoes()

    def exportar_csv(self):
        if not self.ativos:
            return
        p = self.parametros()
        destino = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile=f"preview_{p['cliente']}-{p['sigla']}{p['num']}.csv",
            filetypes=[("CSV", "*.csv")])
        if not destino:
            return
        with open(destino, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["code", "field_1", "id_type_item", "codigo_pai", "id_group_task", "plano",
                        "id_priority", "endereco", "cidade", "uf", "pais", "latitude", "longitude",
                        "classificacao_1", "classificacao_2", "modelo"])
            for a in self.ativos_efetivos():
                w.writerow([a["code"], a["nome"], 1 if a["tipo"] == "L" else 2, a["pai"],
                            pl[0] if pl else "", pl[1] if pl else "", a["prio"],
                            p["endereco"] if a["tipo"] == "L" else "",
                            p["cidade"] if a["tipo"] == "L" else "",
                            p["uf"] if a["tipo"] == "L" else "",
                            p["pais"] if a["tipo"] == "L" else "",
                            p["lat"] if a["tipo"] == "L" else "",
                            p["lon"] if a["tipo"] == "L" else "",
                            p["cls1"], p["cls2"], a.get("modelo", "")])
        messagebox.showinfo(APP, f"CSV salvo em:\n{destino}")

    def dlg_credenciais(self):
        cred = carregar_credenciais()
        d = tk.Toplevel(self)
        d.title("Credenciais do Fracttal")
        d.geometry("460x260")
        d.transient(self)
        campos = {}
        for rot, chave, val in [("Client ID", "client_id", cred.get("client_id", "")),
                                ("Client Secret", "client_secret", cred.get("client_secret", "")),
                                ("Base URL", "base_url", cred.get("base_url", "https://app.fracttal.com/")),
                                ("API base", "api_base", cred.get("api_base", "https://app.fracttal.com/api/")),
                                ("Código do usuário (RH)", "code_user", cred.get("code_user", ""))]:
            lin = tk.Frame(d); lin.pack(fill="x", padx=12, pady=4)
            tk.Label(lin, text=rot, width=14, anchor="w").pack(side="left")
            e = ttk.Entry(lin, width=42, show="•" if chave == "client_secret" else None)
            e.insert(0, val); e.pack(side="left", fill="x", expand=True)
            campos[chave] = e
        tk.Label(d, text=f"Salvo em {arquivo_credenciais()} (fora da pasta compartilhada).",
                 font=("Segoe UI", 7), fg="#7a7890", wraplength=430).pack(pady=4)

        def salvar():
            dados = {k: e.get().strip() for k, e in campos.items()}
            dados["token_path"] = cred.get("token_path", "oauth/token")
            arquivo_credenciais().write_text(json.dumps(dados, indent=2), encoding="utf-8")
            self.fx = Fracttal(dados)
            d.destroy()
            messagebox.showinfo(APP, "Credenciais salvas.")
        ttk.Button(d, text="Salvar", command=salvar).pack(pady=6)

    # ---------- publicação ----------
    def publicar(self):
        if not self.ativos:
            return
        p = self.parametros()
        efetivos = self.ativos_efetivos()
        erros = [m for n, m in self.gerador.validar(p, efetivos) if n == "erro"]
        if erros:
            messagebox.showerror(APP, "Corrija antes de publicar:\n\n" + "\n".join(erros))
            return
        simular = self.sim.get()
        cred = carregar_credenciais()
        code_user = cred.get("code_user", "")
        if not simular and any(a["plano"] for a in efetivos) and not code_user:
            messagebox.showerror(APP, "Falta o 'Código do usuário (RH)' na tela de Credenciais — "
                                       "é obrigatório para vincular os planos de manutenção, que agora "
                                       "acontece automaticamente logo após a criação de cada ativo.")
            return
        alvo = f"{p['cliente']}-{p['sigla']}{p['num']}"
        obs_excl = f" ({len(self.excluidos)} excluído(s) na árvore, fora dessa contagem)" if self.excluidos else ""
        msg = (f"SIMULAÇÃO — nada será escrito no Fracttal.\n\nConferir {len(efetivos)} ativos de {alvo}{obs_excl}?"
               if simular else
               f"ATENÇÃO: isto CRIA {len(efetivos)} ativos reais no Fracttal (modelo e plano de manutenção "
               f"incluídos), em {alvo}{obs_excl}.\n\n"
               f"Ativos já existentes (mesmo código) são pulados na criação, mas ainda recebem "
               f"modelo/plano se estiverem faltando.\n\nConfirmar?")
        if not messagebox.askyesno(APP, msg, icon="warning" if not simular else "question"):
            return
        self.btn_pub.config(state="disabled")
        self.btn_parar.config(state="normal")
        self.fx.evento_parar.clear()
        self.log.delete("1.0", "end")
        threading.Thread(target=self._worker_publicar, args=(p, simular, efetivos, code_user), daemon=True).start()

    def parar(self):
        self.fx.evento_parar.set()
        self.btn_parar.config(state="disabled")
        self._log(">>> Pedido de parada enviado — aguardando a chamada em andamento terminar...")

    def _log(self, txt):
        self.fila.put(txt)

    def _drenar_fila(self):
        try:
            while True:
                txt = self.fila.get_nowait()
                if txt == "__fim__":
                    self.btn_pub.config(state="normal")
                    self.btn_parar.config(state="disabled")
                else:
                    self.log.insert("end", txt + "\n")
                    self.log.see("end")
                    self.status.config(text=txt[:120])
        except queue.Empty:
            pass
        self.after(150, self._drenar_fila)

    def _worker_publicar(self, p, simular, ativos, code_user):
        t0 = time.time()
        criados = pulados = falhas = planos_ok = planos_falha = 0
        try:
            self._log(f"[{datetime.now():%H:%M:%S}] {'SIMULAÇÃO' if simular else 'PUBLICAÇÃO REAL'} — "
                      f"{len(ativos)} ativos")
            self._log("Autenticando no Fracttal...")
            self.fx.token()
            self._log("  OK")

            raiz_cliente = self.fx.item_por_codigo(p["cliente"])
            if not raiz_cliente:
                self._log(f"Cliente '{p['cliente']}' não encontrado por código — procurando pelo nome...")
                for x in self.fx.localizacoes():
                    if not x.get("id_parent") and (x.get("field_1") or "").strip().upper() == p["cliente"]:
                        raiz_cliente = x
                        break
            if not raiz_cliente:
                self._log(f"ERRO: raiz do cliente '{p['cliente']}' não existe no Fracttal. "
                          f"Crie o cliente antes de cadastrar a usina.")
                self._log("__fim__")
                return
            self._log(f"Cliente encontrado: {raiz_cliente.get('field_1')} (id interno resolvido)")

            ids = {p["cliente"]: raiz_cliente["id"]}
            planos = self.template["planos"]
            loc_inseridos, eqp_inseridos = [], []
            lock = threading.Lock()
            MAX_PARALELO = 5  # nº de chamadas HTTP simultâneas — Fracttal limita por IP, ver 429

            def pos_processar(a):
                """Aplica modelo (equipamento) e vincula plano de manutenção — sempre que
                aplicável, tanto pra ativo recém-criado quanto pra ativo que já existia."""
                nonlocal planos_ok, planos_falha
                extras = []
                if a["tipo"] == "E" and a.get("modelo"):
                    try:
                        self.fx.put(f"items/{a['code']}", {"id_type_item": 2, "field_3": a["modelo"]})
                        extras.append("modelo aplicado")
                    except InterruptedError:
                        raise
                    except Exception as e:
                        extras.append(f"FALHA modelo: {e}")
                if a["plano"]:
                    try:
                        self.fx.vincular_plano(a["code"], planos[a["plano"]][0], code_user)
                        with lock:
                            planos_ok += 1
                        extras.append("plano vinculado")
                    except InterruptedError:
                        raise
                    except Exception as e:
                        with lock:
                            planos_falha += 1
                        extras.append(f"FALHA plano: {e}")
                return f" ({', '.join(extras)})" if extras else ""

            def processar_um(a):
                """Roda numa thread do pool: checa/cria o ativo e aplica modelo+plano.
                Retorna (code, novo_id_ou_None) — novo_id None significa que não resolveu
                (falha ou simulação), e portanto os filhos dele não poderão ser processados."""
                nonlocal criados, pulados, falhas
                existente = self.fx.item_por_codigo(a["code"])
                if existente:
                    with lock:
                        pulados += 1
                        (loc_inseridos if a["tipo"] == "L" else eqp_inseridos).append((a["code"], existente["id"]))
                    extra_txt = pos_processar(a) if not simular else ""
                    self._log(f"{a['code']} — já existe ({'LOC' if a['tipo'] == 'L' else 'EQP'}){extra_txt}")
                    return a["code"], existente["id"]

                corpo = {"id_type_item": 1 if a["tipo"] == "L" else 2,
                         "code": a["code"], "field_1": a["nome"], "code_parent_location": a["pai"],
                         "id_priority": a["prio"], "active": True, "visible_to_all": False,
                         "group_1": p["cls1"], "group_2": p["cls2"]}
                # id_group_task e field_3 (modelo) NÃO vão aqui — o POST /api/items ignora esses
                # campos em silêncio. Plano e modelo são aplicados depois, via pos_processar().
                if a["tipo"] == "L":
                    corpo.update({"field_2": p["endereco"], "field_3": p["cidade"],
                                  "field_5": p["uf"], "field_6": p["pais"],
                                  "latitude": p["lat"], "longitud": p["lon"]})
                if simular:
                    with lock:
                        criados += 1
                    self._log(f"{a['code']} — criaria ({'LOC' if a['tipo'] == 'L' else 'EQP'}, "
                              f"plano {planos[a['plano']][1] if a['plano'] else '—'})")
                    return a["code"], f"SIM-{a['code']}"
                try:
                    resp = self.fx.post("items", corpo)
                    novo = (resp.get("data") or [{}])
                    novo = novo[0] if isinstance(novo, list) and novo else {}
                    novo_id = novo.get("id")
                    if not novo_id:
                        conf = self.fx.item_por_codigo(a["code"])
                        novo_id = conf.get("id") if conf else None
                    if not novo_id:
                        raise RuntimeError("criado, mas não foi possível resolver o id")
                    with lock:
                        criados += 1
                        (loc_inseridos if a["tipo"] == "L" else eqp_inseridos).append((a["code"], novo_id))
                    extra_txt = pos_processar(a)
                    self._log(f"{a['code']} — criado ({'LOC' if a['tipo'] == 'L' else 'EQP'}){extra_txt}")
                    return a["code"], novo_id
                except InterruptedError:
                    raise
                except Exception as e:
                    with lock:
                        falhas += 1
                    self._log(f"{a['code']} — FALHA: {e}")
                    return a["code"], None

            # Processa em ONDAS: cada onda pega todo mundo cujo pai já foi resolvido e roda em
            # paralelo (até MAX_PARALELO por vez). Só avança pra próxima onda quando a atual termina
            # — isso garante que nenhum filho seja criado antes do pai, mesmo em paralelo.
            restantes = list(ativos)
            onda = 0
            total_processado = 0
            while restantes:
                prontos = [a for a in restantes if a["pai"] in ids]
                if not prontos:
                    for a in restantes:
                        falhas += 1
                        self._log(f"{a['code']} — ERRO: pai {a['pai']} não resolvido")
                    break
                restantes = [a for a in restantes if a["pai"] not in ids]
                onda += 1
                self._log(f"— onda {onda}: {len(prontos)} ativo(s) em paralelo "
                          f"(até {MAX_PARALELO} por vez) —")
                with ThreadPoolExecutor(max_workers=MAX_PARALELO) as ex:
                    futs = [ex.submit(processar_um, a) for a in prontos]
                    for fut in as_completed(futs):
                        code, novo_id = fut.result()  # deixa InterruptedError propagar
                        if novo_id is not None:
                            ids[code] = novo_id
                total_processado += len(prontos)
                self._log(f"— onda {onda} concluída — {total_processado}/{len(ativos)} processados —")

            self._log("")
            self._log(f"Resumo: {criados} {'simulados' if simular else 'criados'} · "
                      f"{pulados} já existentes · {falhas} falhas · "
                      f"{planos_ok} plano(s) vinculado(s) · {planos_falha} falha(s) de plano · "
                      f"{time.time() - t0:.0f}s")
            if not simular:
                self._log("")
                self._log(f"Ativos de instalação (LOC) — {len(loc_inseridos)} código(s):")
                for code, _iid in loc_inseridos:
                    self._log(f"  {code}")
                self._log(f"Ativos de equipamento (EQP) — {len(eqp_inseridos)} código(s):")
                for code, _iid in eqp_inseridos:
                    self._log(f"  {code}")
            if not simular and criados:
                amostra = next((a for a in ativos if a["plano"]), None)
                if amostra:
                    conf = self.fx.item_por_codigo(amostra["code"])
                    if conf:
                        self._log(f"Conferência em {amostra['code']}: "
                                  f"plano={conf.get('groups_tasks_description') or 'NÃO APLICADO'} · "
                                  f"classif.1={conf.get('groups_1_description') or 'NÃO APLICADA'} · "
                                  f"classif.2={conf.get('groups_2_description') or 'NÃO APLICADA'}")
                        self._log("Se plano/classificação vierem vazios, ajuste em massa no Fracttal "
                                  "(o restante do cadastro já está correto).")
            rel = pasta_base() / f"log_cadastro_{p['cliente']}-{p['sigla']}{p['num']}_{datetime.now():%Y%m%d_%H%M}.txt"
            rel.write_text(self.log.get("1.0", "end"), encoding="utf-8")
            self._log(f"Log salvo em {rel.name}")
        except InterruptedError:
            self._log("")
            self._log(f"⏹ Interrompido pelo usuário — {criados} criados/simulados, "
                      f"{pulados} já existentes, {falhas} falhas, {planos_ok} planos vinculados até aqui.")
            try:
                rel = pasta_base() / f"log_cadastro_{p['cliente']}-{p['sigla']}{p['num']}_{datetime.now():%Y%m%d_%H%M}_PARCIAL.txt"
                rel.write_text(self.log.get("1.0", "end"), encoding="utf-8")
                self._log(f"Log parcial salvo em {rel.name}")
            except Exception:
                pass
        except Exception as e:
            self._log(f"ERRO GERAL: {e}")
        self._log("__fim__")


if __name__ == "__main__":
    try:
        App().mainloop()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        try:
            tk.Tk().withdraw()
            messagebox.showerror(APP, f"{exc}")
        except Exception:
            pass
