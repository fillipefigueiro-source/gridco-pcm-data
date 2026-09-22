# -*- coding: utf-8 -*-
"""
Lancamento de Desembolsos de Equipamentos
-----------------------------------------
Interface (aba) para inserir compras/desembolsos direto na aba
"Equipamentos - Desembolsos" do arquivo financeiro (Tabela do Excel).

- Usina: lista suspensa com busca (filtra conforme voce digita).
- Item, Fornecedor, Valor previsto total, Nº de parcelas.
- Parcelas iguais (auto) ou valores manuais por parcela (so grava se a
  soma bater com o valor total).
- Datas: parcelas iguais avancam 1 mes; ou data manual por parcela.
- Status sempre "Pagamento previsto" nesta primeira entrada.
- Codigo e Classe Contabil.

Cliente, Cluster, MWp e "Codigo da compra" sao preenchidos automaticamente
pelas formulas da propria tabela (nao precisam ser digitados).
"""
from __future__ import annotations
import os
import sys
import threading
import datetime as _dt

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import desembolsos_core as core

# ---- Caminho da planilha OFICIAL "Financeiro - PCM" (portatil entre PCs) ----
# Caminho relativo dentro da biblioteca sincronizada do SharePoint.
_REL_FIN = os.path.join("4. O&M", "11.Pré-Operação", "1. Gerencial",
                        "4. Gerencial - MPAS e Zeladoria", "Financeiro - PCM")


def _raizes_sync():
    """Possiveis raizes onde a biblioteca do SharePoint fica sincronizada
    (varia por usuario/maquina)."""
    home = os.path.expanduser("~")
    cands = [
        os.path.join(home, "GRID CO", "GRID CO. - Gridco"),
        os.environ.get("OneDriveCommercial", ""),
        os.environ.get("OneDrive", ""),
        os.path.join(home, "OneDrive - Grid Co"),
    ]
    return [c for c in cands if c]


def _detectar_arquivo():
    # 1) override explicito por variavel de ambiente
    if os.environ.get("PCM_FIN_XLSX"):
        return os.environ["PCM_FIN_XLSX"]
    # 2) procura a planilha nas raizes de sincronizacao conhecidas (.xlsm preferido)
    for raiz in _raizes_sync():
        base = os.path.join(raiz, _REL_FIN)
        for ext in (".xlsm", ".xlsx"):
            if os.path.exists(base + ext):
                return base + ext
    # 3) fallback: caminho padrao (mesmo que ainda nao exista)
    return os.path.join(os.path.expanduser("~"), "GRID CO", "GRID CO. - Gridco",
                        _REL_FIN) + ".xlsm"


DEFAULT_XLSX = _detectar_arquivo()

# ---- Paleta (estilo do app de Relatorios) ----
COR_HEADER = "#0d1b3e"
COR_HEADER_TXT = "#ffffff"
COR_AZUL = "#2f6fed"
COR_VERDE = "#8bc53f"
COR_BG = "#f4f5f7"
COR_OK = "#1a7f37"
COR_ERR = "#c0392b"

# Opções fixas do campo Código
CODIGO_OPCOES = ["(P) Pessoal", "(M) Material", "(S) Serviços", "(O) Outros"]


def parse_valor(txt: str) -> float:
    """Aceita '1.234,56', '1234,56', '1234.56', '1234'."""
    s = (txt or "").strip().replace("R$", "").replace(" ", "")
    if not s:
        raise ValueError("valor vazio")
    if "," in s:                      # formato BR: ponto=milhar, virgula=decimal
        s = s.replace(".", "").replace(",", ".")
    return float(s)


def fmt_valor(v: float) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def parse_data(txt: str) -> _dt.date:
    return _dt.datetime.strptime(txt.strip(), "%d/%m/%Y").date()


def fmt_data(d: _dt.date) -> str:
    return d.strftime("%d/%m/%Y")


class AutocompleteEntry(ttk.Entry):
    """Campo de texto com lista popup que filtra ao vivo conforme voce digita
    (estilo Excel) — SEM roubar o foco do campo. Setas navegam, Enter/clique
    seleciona, Esc fecha, seta p/ baixo abre a lista completa."""

    def __init__(self, master=None, **kw):
        super().__init__(master, **kw)
        self._all = []
        self._popup = None
        self._listbox = None
        self._hl = -1
        self._clicking = False
        self.bind("<KeyRelease>", self._on_keyrelease)
        self.bind("<Down>", self._nav_down)
        self.bind("<Up>", self._nav_up)
        self.bind("<Return>", self._on_return)
        self.bind("<Escape>", lambda e: self._hide())
        self.bind("<FocusOut>", self._on_focusout)
        self.bind("<Destroy>", lambda e: self._hide())

    # --- API compativel com o codigo existente ---
    def set_completion_list(self, lista):
        self._all = list(lista)

    def set(self, value):
        self.delete(0, "end")
        self.insert(0, value)

    # --- filtragem ---
    def _matches(self, txt):
        t = (txt or "").strip().lower()
        if not t:
            return list(self._all)
        comeca = [x for x in self._all if x.lower().startswith(t)]
        contem = [x for x in self._all if t in x.lower() and not x.lower().startswith(t)]
        return comeca + contem

    def _on_keyrelease(self, event):
        if event.keysym in ("Up", "Down", "Return", "Escape", "Left", "Right",
                            "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L",
                            "Alt_R", "Tab"):
            return
        txt = self.get()
        if not txt.strip():
            self._hide()
            return
        matches = self._matches(txt)
        if matches:
            self._show(matches)
        else:
            self._hide()

    # --- popup ---
    def _show(self, matches):
        if self._popup is None or not self._popup.winfo_exists():
            self._popup = tk.Toplevel(self)
            self._popup.wm_overrideredirect(True)
            try:
                self._popup.attributes("-topmost", True)
            except tk.TclError:
                pass
            self._listbox = tk.Listbox(
                self._popup, activestyle="none", font=("Segoe UI", 10),
                highlightthickness=1, highlightbackground="#8aa0c8",
                selectbackground="#2f6fed", selectforeground="white",
                exportselection=False, bd=0)
            self._listbox.pack(fill="both", expand=True)
            self._listbox.bind("<ButtonPress-1>", lambda e: setattr(self, "_clicking", True))
            self._listbox.bind("<ButtonRelease-1>", self._on_click)
            self._listbox.bind("<Motion>", self._on_motion)
        lb = self._listbox
        lb.delete(0, "end")
        for m in matches:
            lb.insert("end", m)
        lb.configure(height=min(len(matches), 8))
        self._hl = 0
        self._highlight()
        self.update_idletasks()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        w = self.winfo_width()
        self._popup.wm_geometry("%dx%d+%d+%d" % (w, lb.winfo_reqheight(), x, y))
        self._popup.deiconify()

    def _hide(self):
        if self._popup is not None:
            try:
                self._popup.destroy()
            except tk.TclError:
                pass
        self._popup = None
        self._listbox = None
        self._hl = -1

    def _highlight(self):
        if not self._listbox:
            return
        self._listbox.selection_clear(0, "end")
        if 0 <= self._hl < self._listbox.size():
            self._listbox.selection_set(self._hl)
            self._listbox.activate(self._hl)
            self._listbox.see(self._hl)

    def _nav_down(self, event):
        if not self._listbox:
            m = self._matches(self.get())
            if m:
                self._show(m)
            return "break"
        self._hl = min(self._hl + 1, self._listbox.size() - 1)
        self._highlight()
        return "break"

    def _nav_up(self, event):
        if not self._listbox:
            return
        self._hl = max(self._hl - 1, 0)
        self._highlight()
        return "break"

    def _on_return(self, event):
        if self._listbox and 0 <= self._hl < self._listbox.size():
            self._choose(self._listbox.get(self._hl))
            return "break"

    def _on_click(self, event):
        self._clicking = False
        idx = self._listbox.nearest(event.y)
        if idx >= 0:
            self._choose(self._listbox.get(idx))

    def _on_motion(self, event):
        idx = self._listbox.nearest(event.y)
        if idx >= 0 and idx != self._hl:
            self._hl = idx
            self._highlight()

    def _choose(self, value):
        self.set(value)
        self._hide()
        self.focus_set()
        self.icursor("end")

    def _on_focusout(self, event):
        # nao fecha se o usuario esta clicando num item da lista
        if self._clicking:
            self._clicking = False
            return
        self.after(150, self._hide)


class ParcelaRow:
    """Uma linha de parcela na tabela dinamica."""
    def __init__(self, parent, idx, on_change):
        self.numero = idx
        self.valor_var = tk.StringVar()
        self.data_var = tk.StringVar()
        self.lbl = ttk.Label(parent, text=f"{idx}", width=5, anchor="center")
        self.valor_entry = ttk.Entry(parent, textvariable=self.valor_var, width=16, justify="right")
        self.data_entry = ttk.Entry(parent, textvariable=self.data_var, width=14, justify="center")
        self.valor_var.trace_add("write", lambda *a: on_change())

    def grid(self, r):
        self.lbl.grid(row=r, column=0, padx=2, pady=1)
        self.valor_entry.grid(row=r, column=1, padx=2, pady=1)
        self.data_entry.grid(row=r, column=2, padx=2, pady=1)

    def destroy(self):
        self.lbl.destroy()
        self.valor_entry.destroy()
        self.data_entry.destroy()

    def set_editable(self, editable: bool):
        st = "normal" if editable else "readonly"
        self.valor_entry.configure(state=st)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Grid Co. · Lançamento de Desembolsos")
        self.geometry("760x820")
        self.configure(bg=COR_BG)
        self.minsize(720, 720)

        self.xlsx_path = tk.StringVar(value=DEFAULT_XLSX)
        self.usinas = []
        self.fornecedores = []
        self.ferramentas = []
        self.mapa_usinas = {}
        self.parcela_rows = []
        self._rebuilding = False

        self._build_style()
        self._build_header()
        self._build_form()
        self._build_log()

        self.after(200, self._carregar_base)

    # ---------------- estilo ----------------
    def _build_style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("TLabel", background=COR_BG, font=("Segoe UI", 10))
        st.configure("Bold.TLabel", background=COR_BG, font=("Segoe UI", 10, "bold"))
        st.configure("TButton", font=("Segoe UI", 10))
        st.configure("Grav.TButton", font=("Segoe UI", 11, "bold"))
        st.configure("TEntry", padding=2)
        st.configure("TCheckbutton", background=COR_BG, font=("Segoe UI", 10))

    # ---------------- header ----------------
    def _build_header(self):
        h = tk.Frame(self, bg=COR_HEADER, height=78)
        h.pack(fill="x", side="top")
        h.pack_propagate(False)
        logo = tk.Label(h, text="◔", bg=COR_HEADER, fg=COR_HEADER_TXT, font=("Segoe UI", 34, "bold"))
        logo.pack(side="left", padx=(18, 8))
        box = tk.Frame(h, bg=COR_HEADER)
        box.pack(side="left")
        tk.Label(box, text="Lançamento de Desembolsos", bg=COR_HEADER, fg=COR_HEADER_TXT,
                 font=("Segoe UI", 17, "bold")).pack(anchor="w")
        tk.Label(box, text="Equipamentos · aba \"Equipamentos - Desembolsos\"",
                 bg=COR_HEADER, fg="#9fb3d1", font=("Segoe UI", 9)).pack(anchor="w")

    # ---------------- formulario ----------------
    def _build_form(self):
        wrap = tk.Frame(self, bg=COR_BG)
        wrap.pack(fill="both", expand=True, padx=18, pady=10)
        for c in range(4):
            wrap.columnconfigure(c, weight=0)
        wrap.columnconfigure(1, weight=1)

        r = 0
        # arquivo
        ttk.Label(wrap, text="Arquivo", style="Bold.TLabel").grid(row=r, column=0, sticky="w", pady=4)
        frow = tk.Frame(wrap, bg=COR_BG)
        frow.grid(row=r, column=1, columnspan=3, sticky="ew", pady=4)
        frow.columnconfigure(0, weight=1)
        self.ent_arquivo = ttk.Entry(frow, textvariable=self.xlsx_path)
        self.ent_arquivo.grid(row=0, column=0, sticky="ew")
        ttk.Button(frow, text="Procurar…", command=self._procurar).grid(row=0, column=1, padx=(6, 0))

        r += 1
        ttk.Label(wrap, text="Usina", style="Bold.TLabel").grid(row=r, column=0, sticky="w", pady=4)
        self.cb_usina = AutocompleteEntry(wrap)
        self.cb_usina.grid(row=r, column=1, columnspan=3, sticky="ew", pady=4)

        r += 1
        ttk.Label(wrap, text="Item (Ferramenta)", style="Bold.TLabel").grid(row=r, column=0, sticky="w", pady=4)
        itbox = tk.Frame(wrap, bg=COR_BG)
        itbox.grid(row=r, column=1, columnspan=3, sticky="ew", pady=4)
        itbox.columnconfigure(0, weight=1)
        self.cb_item = AutocompleteEntry(itbox)
        self.cb_item.grid(row=0, column=0, sticky="ew")
        ttk.Button(itbox, text="＋ Nova ferramenta", width=18,
                   command=self._cadastrar_ferramenta).grid(row=0, column=1, padx=(6, 0))

        r += 1
        ttk.Label(wrap, text="Fornecedor", style="Bold.TLabel").grid(row=r, column=0, sticky="w", pady=4)
        fnbox = tk.Frame(wrap, bg=COR_BG)
        fnbox.grid(row=r, column=1, columnspan=3, sticky="ew", pady=4)
        fnbox.columnconfigure(0, weight=1)
        self.cb_forn = AutocompleteEntry(fnbox)
        self.cb_forn.grid(row=0, column=0, sticky="ew")
        ttk.Button(fnbox, text="＋ Novo fornecedor", width=18,
                   command=self._cadastrar_fornecedor).grid(row=0, column=1, padx=(6, 0))

        r += 1
        ttk.Label(wrap, text="Valor previsto total (R$)", style="Bold.TLabel").grid(row=r, column=0, sticky="w", pady=4)
        self.ent_total = ttk.Entry(wrap)
        self.ent_total.grid(row=r, column=1, sticky="ew", pady=4)
        self.ent_total.bind("<KeyRelease>", lambda e: self._rebuild_parcelas())

        r += 1
        ttk.Label(wrap, text="Nº de parcelas", style="Bold.TLabel").grid(row=r, column=0, sticky="w", pady=4)
        self.var_nparc = tk.StringVar(value="3")
        self.spin_parc = ttk.Spinbox(wrap, from_=1, to=60, width=6, textvariable=self.var_nparc,
                                     command=self._rebuild_parcelas)
        self.spin_parc.grid(row=r, column=1, sticky="w", pady=4)
        self.spin_parc.bind("<KeyRelease>", lambda e: self._rebuild_parcelas())

        r += 1
        self.var_iguais = tk.BooleanVar(value=True)
        chk = ttk.Checkbutton(wrap, text="Parcelas iguais", variable=self.var_iguais,
                              command=self._rebuild_parcelas)
        chk.grid(row=r, column=1, sticky="w", pady=2)

        r += 1
        ttk.Label(wrap, text="Data da 1ª parcela", style="Bold.TLabel").grid(row=r, column=0, sticky="w", pady=4)
        self.var_data1 = tk.StringVar(value=fmt_data(_dt.date.today()))
        self.ent_data1 = ttk.Entry(wrap, textvariable=self.var_data1, width=14)
        self.ent_data1.grid(row=r, column=1, sticky="w", pady=4)
        self.ent_data1.bind("<KeyRelease>", lambda e: self._rebuild_parcelas())
        ttk.Label(wrap, text="(dd/mm/aaaa)").grid(row=r, column=1, sticky="e", padx=(0, 40))

        # --- tabela de parcelas ---
        r += 1
        pbox = tk.LabelFrame(wrap, text=" Parcelas ", bg=COR_BG, font=("Segoe UI", 10, "bold"),
                             fg=COR_HEADER, padx=8, pady=6)
        pbox.grid(row=r, column=0, columnspan=4, sticky="ew", pady=(8, 4))
        hdr = tk.Frame(pbox, bg=COR_BG)
        hdr.pack(fill="x")
        ttk.Label(hdr, text="Parc.", style="Bold.TLabel", width=5, anchor="center").grid(row=0, column=0, padx=2)
        ttk.Label(hdr, text="Valor (R$)", style="Bold.TLabel", width=16, anchor="center").grid(row=0, column=1, padx=2)
        ttk.Label(hdr, text="Data prevista", style="Bold.TLabel", width=14, anchor="center").grid(row=0, column=2, padx=2)
        self.parc_frame = tk.Frame(pbox, bg=COR_BG)
        self.parc_frame.pack(fill="x")
        self.lbl_soma = ttk.Label(pbox, text="", style="Bold.TLabel")
        self.lbl_soma.pack(anchor="e", pady=(4, 0))

        # --- codigo / classe / nº compra / status ---
        r += 1
        grid2 = tk.Frame(wrap, bg=COR_BG)
        grid2.grid(row=r, column=0, columnspan=4, sticky="ew", pady=(4, 2))
        grid2.columnconfigure(1, weight=1)
        grid2.columnconfigure(3, weight=1)

        ttk.Label(grid2, text="Código", style="Bold.TLabel").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 6))
        self.cb_codigo = ttk.Combobox(grid2, values=CODIGO_OPCOES, state="readonly")
        self.cb_codigo.set("(M) Material")
        self.cb_codigo.grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(grid2, text="Classe Contábil", style="Bold.TLabel").grid(row=0, column=2, sticky="w", pady=4, padx=(12, 6))
        self.cb_classe = ttk.Combobox(grid2, values=["CAPEX", "OPEX"])
        self.cb_classe.set("CAPEX")
        self.cb_classe.grid(row=0, column=3, sticky="ew", pady=4)

        ttk.Label(grid2, text="Nº da compra", style="Bold.TLabel").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 6))
        self.ent_compra = ttk.Entry(grid2, width=10)
        self.ent_compra.grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(grid2, text="Status", style="Bold.TLabel").grid(row=1, column=2, sticky="w", pady=4, padx=(12, 6))
        ttk.Label(grid2, text=core.STATUS_PADRAO + "  (fixo)", foreground=COR_AZUL).grid(row=1, column=3, sticky="w", pady=4)

        # --- botao gravar ---
        r += 1
        self.btn_gravar = tk.Button(wrap, text="Gravar no Excel", command=self._gravar,
                                    bg=COR_VERDE, fg="#14340a", font=("Segoe UI", 12, "bold"),
                                    relief="flat", height=2, cursor="hand2", activebackground="#7ab032")
        self.btn_gravar.grid(row=r, column=0, columnspan=4, sticky="ew", pady=(10, 4))

        self._rebuild_parcelas()

    def _build_log(self):
        lf = tk.Frame(self, bg=COR_BG)
        lf.pack(fill="both", expand=False, padx=18, pady=(0, 12))
        self.log = tk.Text(lf, height=6, bg="#eef1f5", relief="flat", font=("Consolas", 9),
                           fg="#22314f", wrap="word")
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")

    # ---------------- logica ----------------
    def _log(self, msg, cor=None):
        self.log.configure(state="normal")
        tag = None
        if cor:
            tag = cor
            self.log.tag_configure(tag, foreground=cor)
        self.log.insert("end", msg + "\n", tag or ())
        self.log.see("end")
        self.log.configure(state="disabled")
        self.update_idletasks()

    def _procurar(self):
        p = filedialog.askopenfilename(title="Selecione o arquivo financeiro",
                                       filetypes=[("Excel", "*.xlsx *.xlsm")])
        if p:
            self.xlsx_path.set(p)
            self.after(100, self._carregar_base)

    def _carregar_base(self):
        path = self.xlsx_path.get()
        if not os.path.exists(path):
            self._log(f"⚠ Arquivo não encontrado:\n  {path}", COR_ERR)
            return
        self._log("Carregando base de dados…")
        self.btn_gravar.configure(state="disabled")

        def worker():
            try:
                dados = core.carregar_tudo(path)
                self.mapa_usinas = dados.get("mapa", {})
                self.after(0, lambda: self._base_carregada(
                    dados["usinas"], dados["proximo"], dados["fornecedores"], dados["ferramentas"]))
            except Exception as e:
                msg = str(e)
                self.after(0, lambda: self._log(f"✖ Erro ao ler o arquivo: {msg}", COR_ERR))

        threading.Thread(target=worker, daemon=True).start()

    def _base_carregada(self, usinas, prox, forns, ferrs):
        self.usinas = usinas
        self.fornecedores = forns
        self.ferramentas = ferrs
        self.cb_usina.set_completion_list(usinas)
        self.cb_forn.set_completion_list(forns)
        self.cb_item.set_completion_list(ferrs)
        self.ent_compra.delete(0, "end")
        self.ent_compra.insert(0, str(prox))
        # Codigo e Classe tem opcoes fixas
        self.cb_codigo.configure(values=CODIGO_OPCOES)
        self.cb_classe.configure(values=["CAPEX", "OPEX"])
        self.btn_gravar.configure(state="normal")
        self._log(f"✓ Base carregada: {len(usinas)} usinas, {len(forns)} fornecedores, "
                  f"{len(ferrs)} ferramentas. Próximo Nº da compra: {prox}.", COR_OK)

    def _rebuild_parcelas(self):
        if self._rebuilding:
            return
        self._rebuilding = True
        try:
            try:
                n = max(1, min(60, int(self.var_nparc.get())))
            except (ValueError, tk.TclError):
                n = 1
            iguais = self.var_iguais.get()
            try:
                total = parse_valor(self.ent_total.get())
            except ValueError:
                total = 0.0
            try:
                data_ini = parse_data(self.var_data1.get())
            except ValueError:
                data_ini = _dt.date.today()

            # preserva valores manuais ja digitados (modo desigual) qdo possivel
            prev_vals = [row.valor_var.get() for row in self.parcela_rows]
            prev_datas = [row.data_var.get() for row in self.parcela_rows]

            for row in self.parcela_rows:
                row.destroy()
            self.parcela_rows = []

            sugest = core.gerar_parcelas_iguais(total, n, data_ini) if total > 0 \
                else [core.Parcela(i + 1, 0.0, core.add_months(data_ini, i)) for i in range(n)]

            for i in range(n):
                row = ParcelaRow(self.parc_frame, i + 1, self._update_soma)
                if iguais:
                    row.valor_var.set(fmt_valor(sugest[i].valor))
                    row.data_var.set(fmt_data(sugest[i].data))
                    row.set_editable(False)
                else:
                    if i < len(prev_vals) and prev_vals[i]:
                        row.valor_var.set(prev_vals[i])
                    else:
                        row.valor_var.set(fmt_valor(sugest[i].valor))
                    if i < len(prev_datas) and prev_datas[i]:
                        row.data_var.set(prev_datas[i])
                    else:
                        row.data_var.set(fmt_data(sugest[i].data))
                    row.set_editable(True)
                row.grid(i)
                self.parcela_rows.append(row)
        finally:
            self._rebuilding = False
        self._update_soma()

    def _update_soma(self):
        try:
            total = parse_valor(self.ent_total.get())
        except ValueError:
            total = 0.0
        soma = 0.0
        ok_parse = True
        for row in self.parcela_rows:
            try:
                soma += parse_valor(row.valor_var.get())
            except ValueError:
                ok_parse = False
        difere = abs(soma - total) > 0.01
        txt = f"Soma das parcelas: R$ {fmt_valor(soma)}   |   Total: R$ {fmt_valor(total)}"
        if not ok_parse:
            self.lbl_soma.configure(text=txt + "   (valor inválido)", foreground=COR_ERR)
        elif difere:
            self.lbl_soma.configure(text=txt + "   ✖ não confere", foreground=COR_ERR)
        else:
            self.lbl_soma.configure(text=txt + "   ✓ confere", foreground=COR_OK)

    def _coletar(self):
        path = self.xlsx_path.get()
        if not os.path.exists(path):
            raise ValueError("Arquivo não encontrado.")
        usina = self.cb_usina.get().strip()
        if not usina:
            raise ValueError("Selecione a Usina.")
        if self.usinas and usina not in self.usinas:
            raise ValueError("Usina não encontrada na base (AUXILIAR). Selecione uma da lista.")
        item = self.cb_item.get().strip()
        if not item:
            raise ValueError("Preencha o Item (Ferramenta).")
        forn = self.cb_forn.get().strip()
        if not forn:
            raise ValueError("Preencha o Fornecedor.")
        total = parse_valor(self.ent_total.get())
        if total <= 0:
            raise ValueError("Valor previsto total inválido.")
        try:
            num_compra = int(self.ent_compra.get().strip())
        except ValueError:
            raise ValueError("Nº da compra inválido.")
        codigo = self.cb_codigo.get().strip()
        classe = self.cb_classe.get().strip()

        parcelas = []
        for row in self.parcela_rows:
            try:
                v = parse_valor(row.valor_var.get())
            except ValueError:
                raise ValueError(f"Valor inválido na parcela {row.numero}.")
            try:
                dt = parse_data(row.data_var.get())
            except ValueError:
                raise ValueError(f"Data inválida na parcela {row.numero} (use dd/mm/aaaa).")
            parcelas.append(core.Parcela(row.numero, v, dt))

        if not core.validar_soma(parcelas, total):
            raise ValueError("A soma das parcelas não confere com o Valor previsto total.")

        cliente, cluster, mwp = self.mapa_usinas.get(usina, (None, None, None))
        return core.Desembolso(usina=usina, item=item, fornecedor=forn, valor_total=total,
                               codigo=codigo, classe=classe, num_compra=num_compra, parcelas=parcelas,
                               cliente=cliente, cluster=cluster, mwp=mwp)

    def _gravar(self):
        try:
            d = self._coletar()
        except ValueError as e:
            messagebox.showwarning("Verifique os dados", str(e))
            return

        resumo = (f"Confirmar lançamento?\n\n"
                  f"Nº da compra: {d.num_compra}\nUsina: {d.usina}\nItem: {d.item}\n"
                  f"Fornecedor: {d.fornecedor}\nValor total: R$ {fmt_valor(d.valor_total)}\n"
                  f"Parcelas: {len(d.parcelas)}\nStatus: {d.status}")
        if not messagebox.askyesno("Confirmar", resumo):
            return

        self.btn_gravar.configure(state="disabled", text="Gravando…")
        self._log(f"Gravando compra Nº {d.num_compra} ({d.usina}, {len(d.parcelas)} parcela(s))…")

        def worker():
            try:
                res = core.gravar_desembolso(self.xlsx_path.get(), d)
                self.after(0, lambda: self._gravou(res))
            except Exception as e:
                self.after(0, lambda: self._erro_gravar(e))

        threading.Thread(target=worker, daemon=True).start()

    def _gravou(self, res):
        self.btn_gravar.configure(state="normal", text="Gravar no Excel")
        self._log(f"✓ Gravado! Compra Nº {res['num_compra']} · {res['parcelas']} parcela(s) "
                  f"nas linhas {res['linhas']}.", COR_OK)
        messagebox.showinfo("Sucesso", "Desembolso lançado no Excel com sucesso!")
        # prepara proximo lançamento SEM reler o arquivo (evita travar com Excel ocupado):
        # a lista de usinas/fornec/ferram nao muda apos um desembolso — so avança o Nº.
        try:
            prox = int(res["num_compra"]) + 1
        except (ValueError, TypeError, KeyError):
            prox = None
        if prox is not None:
            self.ent_compra.delete(0, "end")
            self.ent_compra.insert(0, str(prox))
        self.cb_usina.set("")
        self.cb_item.set("")
        self.cb_forn.set("")
        self.ent_total.delete(0, "end")
        self._rebuild_parcelas()
        self._log(f"Pronto para o próximo (compra Nº {prox}).", COR_AZUL)

    def _erro_gravar(self, e):
        self.btn_gravar.configure(state="normal", text="Gravar no Excel")
        self._log(f"✖ Erro ao gravar: {e}", COR_ERR)
        messagebox.showerror("Erro", f"Não foi possível gravar:\n\n{e}")

    # ---------------- cadastro de fornecedor / ferramenta ----------------
    def _modal_cadastro(self, titulo, campos):
        """campos: lista de (label, key, obrigatorio). Retorna dict ou None."""
        top = tk.Toplevel(self)
        top.title(titulo)
        top.configure(bg=COR_BG)
        top.transient(self)
        top.grab_set()
        top.resizable(False, False)
        entries = {}
        for i, (lbl, key, req) in enumerate(campos):
            ttk.Label(top, text=lbl + (" *" if req else ""), style="Bold.TLabel").grid(
                row=i, column=0, sticky="w", padx=12, pady=5)
            e = ttk.Entry(top, width=38)
            e.grid(row=i, column=1, padx=12, pady=5)
            entries[key] = e
        if campos:
            entries[campos[0][1]].focus_set()
        result = {}

        def salvar():
            vals = {}
            for lbl, key, req in campos:
                v = entries[key].get().strip()
                if req and not v:
                    messagebox.showwarning("Campo obrigatório", f"Preencha: {lbl}", parent=top)
                    return
                vals[key] = v
            result.update(vals)
            top.destroy()

        btns = tk.Frame(top, bg=COR_BG)
        btns.grid(row=len(campos), column=0, columnspan=2, pady=12)
        ttk.Button(btns, text="Cancelar", command=top.destroy).pack(side="left", padx=6)
        tk.Button(btns, text="Salvar", command=salvar, bg=COR_VERDE, fg="#14340a",
                  relief="flat", font=("Segoe UI", 10, "bold"), cursor="hand2").pack(side="left", padx=6)
        top.bind("<Return>", lambda e: salvar())
        self.update_idletasks()
        top.geometry(f"+{self.winfo_rootx() + 120}+{self.winfo_rooty() + 120}")
        top.wait_window()
        return result or None

    def _cadastrar_ferramenta(self):
        if not os.path.exists(self.xlsx_path.get()):
            messagebox.showwarning("Arquivo", "Selecione um arquivo válido primeiro.")
            return
        campos = [("Ferramenta", "ferramenta", True), ("Nome Vendedores", "vendedor", False),
                  ("Email", "email", False), ("Telefone", "telefone", False),
                  ("Estado", "estado", False), ("Serviço", "servico", False),
                  ("Avaliação por Serviço", "avaliacao", False)]
        dados = self._modal_cadastro("Cadastrar ferramenta", campos)
        if not dados:
            return
        self._executar_cadastro(
            "ferramenta", dados["ferramenta"],
            lambda: core.cadastrar_ferramenta(
                self.xlsx_path.get(), dados["ferramenta"], vendedor=dados["vendedor"],
                email=dados["email"], telefone=dados["telefone"], estado=dados["estado"],
                servico=dados["servico"], avaliacao=dados["avaliacao"]),
            lambda p: core.carregar_lista(p, core.FERR_SHEET), self.cb_item)

    def _cadastrar_fornecedor(self):
        if not os.path.exists(self.xlsx_path.get()):
            messagebox.showwarning("Arquivo", "Selecione um arquivo válido primeiro.")
            return
        campos = [("Fornecedor", "fornecedor", True), ("Nome dos vendedores", "vendedor", False),
                  ("Email", "email", False), ("Telefone", "telefone", False),
                  ("Estado", "estado", False), ("Serviço", "servico", False),
                  ("Avaliação por Serviço", "avaliacao", False)]
        dados = self._modal_cadastro("Cadastrar fornecedor", campos)
        if not dados:
            return
        self._executar_cadastro(
            "fornecedor", dados["fornecedor"],
            lambda: core.cadastrar_fornecedor(
                self.xlsx_path.get(), dados["fornecedor"], vendedor=dados["vendedor"],
                email=dados["email"], telefone=dados["telefone"], estado=dados["estado"],
                servico=dados["servico"], avaliacao=dados["avaliacao"]),
            lambda p: core.carregar_lista(p, core.FORN_SHEET), self.cb_forn)

    def _executar_cadastro(self, tipo, nome, func_grava, func_lista, combobox):
        self._log(f"Cadastrando {tipo} '{nome}'…")
        self.btn_gravar.configure(state="disabled")

        def worker():
            try:
                func_grava()
                lista = func_lista(self.xlsx_path.get())
                self.after(0, lambda: self._cadastro_ok(tipo, nome, lista, combobox))
            except Exception as e:
                self.after(0, lambda: self._cadastro_erro(tipo, e))

        threading.Thread(target=worker, daemon=True).start()

    def _cadastro_ok(self, tipo, nome, lista, combobox):
        combobox.set_completion_list(lista)
        combobox.set(nome)
        self.btn_gravar.configure(state="normal")
        self._log(f"✓ {tipo.capitalize()} '{nome}' cadastrado e selecionado.", COR_OK)

    def _cadastro_erro(self, tipo, e):
        self.btn_gravar.configure(state="normal")
        self._log(f"✖ Erro ao cadastrar {tipo}: {e}", COR_ERR)
        messagebox.showerror("Erro", f"Não foi possível cadastrar o {tipo}:\n\n{e}")


if __name__ == "__main__":
    # smoke test opcional: python lancamento_desembolsos.py --smoke
    if "--smoke" in sys.argv:
        app = App()
        app.after(800, app.destroy)
        app.mainloop()
        print("SMOKE OK")
    else:
        App().mainloop()
