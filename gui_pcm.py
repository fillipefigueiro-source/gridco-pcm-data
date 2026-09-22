"""
GUI PCM — Interface única para rodar todos os scripts do PCM.

Roda em qualquer máquina Windows com Python 3.10+ (auto-detecta a pasta SharePoint).
Botões:
  - Gerar Programação Semanal (com editor de observações da semana)
  - Atualização Diária (sync BD + sugestões PCM + cascata)
  - Gerar Relatórios (abre gui_relatorios.py)

Tudo aparece num log em tempo real. O usuário nunca precisa abrir o Python.
"""

import os
import sys
import subprocess
import threading
import traceback
import pathlib
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from datetime import datetime


# ====================== Detecção de pasta ======================

def detectar_base_dir():
    """Mesma lógica do programacao_v7.py — encontra a pasta sharepoint."""
    if os.environ.get("PCM_PROG_DIR") and os.path.isdir(os.environ["PCM_PROG_DIR"]):
        return os.environ["PCM_PROG_DIR"]
    # Diretório do próprio script (caso copiado pra pasta)
    try:
        sd = pathlib.Path(__file__).resolve().parent
        if (sd / "BD_Relatório Semanal.xlsx").exists():
            return str(sd)
    except NameError:
        pass
    sub = pathlib.Path("4. O&M") / "11.Pré-Operação" / "6. PCM" / "09. Programação Semanal"
    home = pathlib.Path.home()
    cands = [
        home / "GRID CO" / "Grid Co. - Gridco" / sub,
        home / "Grid Co. - Gridco" / sub,
        home / "OneDrive - Grid Co" / sub,
        home / "OneDrive - Gridco" / sub,
        home / "OneDrive - GRID CO" / sub,
        home / "OneDrive" / "Grid Co. - Gridco" / sub,
        home / "OneDrive" / sub,
        home / "Documents" / "Grid Co. - Gridco" / sub,
        home / "Documentos" / "Grid Co. - Gridco" / sub,
    ]
    for c in cands:
        try:
            if c.exists() and c.is_dir():
                return str(c)
        except OSError:
            continue
    return None


BASE_DIR = detectar_base_dir()
SCRIPT_V7 = "programacao_v7.py"
SCRIPT_AT = "atualizacao_semanal.py"
SCRIPT_REL = "gui_relatorios.py"
SCRIPT_CLI = "gerar_relatorio_cliente.py"   # Programação Semanal Clientes (M2)
SCRIPT_MPAS = "atualizar_mpas.py"           # Gestão MPAS: gera o mpas.json e publica
OBS_FILE = "Observacoes_Semana.txt"
OBS_ATUAL_FILE = "Observacoes_Semana_Atual.txt"   # observações da semana ATUAL (override mid-week)


# ====================== App ======================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PCM Grid Co. — Painel de Controle")
        self.geometry("1100x720")
        self.configure(bg="#f4f6fa")
        self.proc = None  # processo rodando
        self._build_ui()
        self._verifica_ambiente()

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg="#191528", height=64)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Grid Co.  —  PCM Painel de Controle",
                 bg="#191528", fg="#a9db21",
                 font=("Segoe UI", 16, "bold")).pack(side="left", padx=18, pady=14)
        self.lbl_pasta = tk.Label(hdr, text="", bg="#191528", fg="#aaa",
                                  font=("Segoe UI", 9))
        self.lbl_pasta.pack(side="right", padx=18)

        # Tabs
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=(8, 0))

        self.tab_prog = ttk.Frame(nb)
        self.tab_atu = ttk.Frame(nb)
        self.tab_obs_atual = ttk.Frame(nb)
        self.tab_rel = ttk.Frame(nb)
        self.tab_util = ttk.Frame(nb)
        nb.add(self.tab_prog, text="  Programação Semanal  ")
        nb.add(self.tab_atu, text="  Atualização Diária  ")
        nb.add(self.tab_obs_atual, text="  Observações Semana Atual  ")
        nb.add(self.tab_rel, text="  Relatórios  ")
        nb.add(self.tab_util, text="  Utilitários  ")

        self._build_tab_prog()
        self._build_tab_atu()
        self._build_tab_obs_atual()
        self._build_tab_rel()
        self._build_tab_util()

        # Log area (compartilhado entre tabs)
        log_frame = tk.LabelFrame(self, text=" Log de execução ",
                                  bg="#f4f6fa", fg="#191528",
                                  font=("Segoe UI", 10, "bold"))
        log_frame.pack(fill="both", expand=True, padx=12, pady=8)
        self.log = scrolledtext.ScrolledText(
            log_frame, height=12, bg="#1e1e2e", fg="#e5e7eb",
            font=("Consolas", 9), state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=4, pady=4)
        self.log.tag_config("info", foreground="#a9db21")
        self.log.tag_config("warn", foreground="#fbbf24")
        self.log.tag_config("error", foreground="#ef4444")

        # Footer
        ft = tk.Frame(self, bg="#f4f6fa")
        ft.pack(fill="x", padx=12, pady=4)
        tk.Button(ft, text="Limpar log", command=self._limpar_log,
                  bg="#e5e7eb", relief="flat", padx=12).pack(side="right")
        self.lbl_status = tk.Label(ft, text="Pronto", bg="#f4f6fa", fg="#6b7280")
        self.lbl_status.pack(side="left")

    def _build_tab_prog(self):
        f = self.tab_prog
        tk.Label(f, text="Gera o arquivo Programação Semana XX.xlsx para a semana seguinte.",
                 font=("Segoe UI", 11), pady=6).pack(anchor="w", padx=12, pady=(12, 4))

        # Editor de observações
        oframe = tk.LabelFrame(f, text=" Observações desta semana (opcional) ",
                               font=("Segoe UI", 10, "bold"))
        oframe.pack(fill="both", expand=True, padx=12, pady=6)
        tk.Label(oframe, text="Use para registrar arranjos especiais: clusters cobrindo outros, "
                              "ausências, folgas, etc. Uma observação por linha.",
                 font=("Segoe UI", 9), fg="#6b7280").pack(anchor="w", padx=8, pady=(4, 0))
        self.txt_obs = scrolledtext.ScrolledText(oframe, height=10,
                                                  font=("Segoe UI", 10), wrap="word")
        self.txt_obs.pack(fill="both", expand=True, padx=8, pady=6)
        self._carregar_observacoes()

        # Opções
        opts = tk.Frame(f)
        opts.pack(fill="x", padx=12, pady=4)
        tk.Label(opts, text="Semana específica (opcional):").pack(side="left")
        self.ent_semana = tk.Entry(opts, width=8)
        self.ent_semana.pack(side="left", padx=4)
        tk.Label(opts, text="Ex: 26 — deixe em branco para a próxima",
                 fg="#6b7280", font=("Segoe UI", 9)).pack(side="left", padx=4)

        # Botões
        btns = tk.Frame(f)
        btns.pack(fill="x", padx=12, pady=10)
        self.btn_prog = tk.Button(btns, text="Gerar Programação Semanal",
                                  bg="#a9db21", fg="#191528",
                                  font=("Segoe UI", 11, "bold"),
                                  relief="flat", padx=24, pady=10,
                                  command=self._rodar_programacao)
        self.btn_prog.pack(side="left")
        tk.Button(btns, text="Salvar observações",
                  bg="#e5e7eb", relief="flat", padx=14, pady=10,
                  command=self._salvar_observacoes).pack(side="left", padx=8)
        tk.Button(btns, text="Enviar semana pra nuvem",
                  bg="#e5e7eb", relief="flat", padx=14, pady=10,
                  command=self._enviar_semana_nuvem).pack(side="left", padx=8)

        # 2º passo da sexta, na MESMA linha dos outros botões de propósito: em
        # bloco próprio abaixo, ele caía na faixa da janela coberta pela barra
        # de tarefas — e a posição da janela varia de máquina para máquina.
        self.btn_cli = tk.Button(btns, text="Programação Semanal Clientes",
                                 bg="#a9db21", fg="#191528",
                                 font=("Segoe UI", 10, "bold"),
                                 relief="flat", padx=16, pady=10,
                                 command=self._rodar_prog_clientes)
        self.btn_cli.pack(side="left", padx=8)
        tk.Button(btns, text="Abrir pasta dos e-mails",
                  bg="#e5e7eb", relief="flat", padx=12, pady=10,
                  command=self._abrir_pasta_clientes).pack(side="left")

    def _build_tab_atu(self):
        f = self.tab_atu
        tk.Label(f, text="Atualiza a Programação da semana corrente: sync com BD, "
                         "sugestões de novas OS, deslocamento em cascata.",
                 font=("Segoe UI", 11), pady=6, wraplength=900, justify="left"
                 ).pack(anchor="w", padx=12, pady=(12, 4))

        # Opções
        oframe = tk.LabelFrame(f, text=" Opções ", font=("Segoe UI", 10, "bold"))
        oframe.pack(fill="x", padx=12, pady=8)

        self.var_no_sync = tk.BooleanVar()
        self.var_no_sug = tk.BooleanVar()
        tk.Checkbutton(oframe, text="Pular sync com BD (--no-sync)",
                       variable=self.var_no_sync).pack(anchor="w", padx=8, pady=2)
        tk.Checkbutton(oframe, text="Pular geração de sugestões (--no-sugestoes)",
                       variable=self.var_no_sug).pack(anchor="w", padx=8, pady=2)

        wf = tk.Frame(oframe)
        wf.pack(fill="x", padx=8, pady=4)
        tk.Label(wf, text="Semana específica:").pack(side="left")
        self.ent_semana_atu = tk.Entry(wf, width=8)
        self.ent_semana_atu.pack(side="left", padx=4)

        # Botões
        btns = tk.Frame(f)
        btns.pack(fill="x", padx=12, pady=10)
        self.btn_atu = tk.Button(btns, text="Rodar Atualização Diária",
                                 bg="#a9db21", fg="#191528",
                                 font=("Segoe UI", 11, "bold"),
                                 relief="flat", padx=24, pady=10,
                                 command=self._rodar_atualizacao)
        self.btn_atu.pack(side="left")

        # Auto-atualização (Task Scheduler)
        autoF = tk.LabelFrame(f, text=" Auto-atualização (Windows Task Scheduler) ",
                              font=("Segoe UI", 10, "bold"))
        autoF.pack(fill="x", padx=12, pady=10)
        tk.Label(autoF, text="Roda atualizacao_semanal.py em background no intervalo "
                              "definido, em janela horária (07h–19h, segunda a sexta).",
                 wraplength=900, justify="left", font=("Segoe UI", 9),
                 fg="#6b7280").pack(anchor="w", padx=8, pady=(4, 4))
        rowA = tk.Frame(autoF)
        rowA.pack(fill="x", padx=8, pady=6)
        tk.Label(rowA, text="Intervalo (min):").pack(side="left")
        self.ent_diario_intervalo = tk.Entry(rowA, width=5)
        self.ent_diario_intervalo.insert(0, "5")
        self.ent_diario_intervalo.pack(side="left", padx=4)
        tk.Button(rowA, text="Ativar agendamento",
                  bg="#10b981", fg="#fff", relief="flat", padx=12, pady=4,
                  command=self._instalar_agendamento_diario).pack(side="left", padx=8)
        tk.Button(rowA, text="Desativar",
                  bg="#e5e7eb", relief="flat", padx=12, pady=4,
                  command=self._remover_agendamento_diario).pack(side="left", padx=4)

        # Info
        info = tk.LabelFrame(f, text=" Como funciona ", font=("Segoe UI", 10, "bold"))
        info.pack(fill="both", expand=True, padx=12, pady=8)
        msg = (
            "1. Lê BD_Relatório Semanal.xlsx e Exportacao_Solicitacoes_de_Servicos.xlsx\n\n"
            "2. STEP A1 — Sincroniza status das OS já programadas com o estado atual no BD\n\n"
            "3. STEP A2 — Detecta novas OS criadas pelo programador e incorpora à "
            "Programação na data/hora que ele definiu. Preventivas (MPM/MPS/MPA) entram "
            "como 'Reprogramada'. Corretivas entram como 'Nova OS'. OSs móveis que "
            "conflitam são deslocadas em cascata.\n\n"
            "4. STEP B — Gera Sugestoes_PCM.xlsx com novas solicitações abertas, sugerindo "
            "equipe/dia/hora. Horários sugeridos são sempre 1h+ do momento atual."
        )
        tk.Label(info, text=msg, wraplength=900, justify="left",
                 fg="#374151", font=("Segoe UI", 10)).pack(anchor="w", padx=8, pady=6)

    def _build_tab_util(self):
        f = self.tab_util
        tk.Label(f, text="Utilitários e manutenção",
                 font=("Segoe UI", 11, "bold"), pady=6).pack(anchor="w", padx=12, pady=(12, 4))
        tk.Label(f, text="Operações de manutenção dos arquivos da pasta. Use com critério.",
                 font=("Segoe UI", 9), fg="#6b7280").pack(anchor="w", padx=12)

        # --- Card: Migrar abas de cluster ---
        c1 = tk.LabelFrame(f, text=" Migrar abas de cluster em arquivos existentes ",
                            font=("Segoe UI", 10, "bold"))
        c1.pack(fill="x", padx=12, pady=10)
        msg1 = (
            "Atualiza todos os arquivos Programação Semana XX.xlsx existentes na pasta para incluir uma "
            "aba para CADA cluster da Grid Co. (mesmo sem tarefas). Idempotente — abas que já existem "
            "não são modificadas. Útil porque o atualizacao_semanal.py só consegue inserir uma OS nova "
            "se a aba do cluster correspondente já existir no arquivo da semana."
        )
        tk.Label(c1, text=msg1, wraplength=900, justify="left",
                 fg="#374151", font=("Segoe UI", 10)).pack(anchor="w", padx=8, pady=6)

        sub = tk.Frame(c1)
        sub.pack(fill="x", padx=8, pady=4)
        tk.Label(sub, text="Semanas específicas (opcional):").pack(side="left")
        self.ent_migrar_semanas = tk.Entry(sub, width=18)
        self.ent_migrar_semanas.pack(side="left", padx=4)
        tk.Label(sub, text="Ex: 21 22 23 — deixe em branco pra TODAS",
                 fg="#6b7280", font=("Segoe UI", 9)).pack(side="left", padx=4)

        bt1 = tk.Frame(c1)
        bt1.pack(fill="x", padx=8, pady=10)
        self.btn_migrar = tk.Button(bt1, text="Rodar Migração",
                                     bg="#a9db21", fg="#191528",
                                     font=("Segoe UI", 11, "bold"),
                                     relief="flat", padx=24, pady=10,
                                     command=self._rodar_migracao)
        self.btn_migrar.pack(side="left")

        # --- Card: Atualizar BD via Fracttal API ---
        # Gestão MPAS: a fonte é a Gerencial no OneDrive, que o robô da nuvem não
        # enxerga — por isso esta aba só atualiza quando alguém clica aqui.
        cMP = tk.LabelFrame(f, text=" Atualizar Gestão MPAS (painel) ",
                            font=("Segoe UI", 10, "bold"))
        cMP.pack(fill="x", padx=12, pady=10)
        tk.Label(cMP, text=(
            "Lê a Gerencial - PCM_2026_R00.xlsx (abas MPAS e Compra Equip MPA 2026), cruza com o "
            "Fracttal e publica o mpas.json que alimenta a aba Gestão MPAS do painel. O robô da "
            "nuvem NÃO faz isso sozinho: a planilha está no OneDrive, fora do alcance dele. "
            "Completo leva alguns minutos (o Fracttal é a parte lenta). A opção rápida usa só a "
            "planilha — ideal quando mudou o plano ou as compras e o estado de execução pode esperar."),
            wraplength=900, justify="left", fg="#374151", font=("Segoe UI", 10)
        ).pack(anchor="w", padx=8, pady=6)
        self.var_mpas_semapi = tk.BooleanVar(value=False)
        tk.Checkbutton(cMP, text="Rápido: só a planilha, sem consultar o Fracttal (--sem-api)",
                       variable=self.var_mpas_semapi).pack(anchor="w", padx=12, pady=1)
        btMP = tk.Frame(cMP)
        btMP.pack(fill="x", padx=8, pady=(4, 8))
        self.btn_mpas = tk.Button(btMP, text="Atualizar Gestão MPAS",
                                  bg="#a9db21", fg="#191528",
                                  font=("Segoe UI", 10, "bold"),
                                  relief="flat", padx=18, pady=8,
                                  command=self._rodar_mpas)
        self.btn_mpas.pack(side="left")

        cAPI = tk.LabelFrame(f, text=" Atualizar BD via Fracttal API ",
                              font=("Segoe UI", 10, "bold"))
        cAPI.pack(fill="x", padx=12, pady=10)
        msgAPI = (
            "Substitui a exportação manual do Fracttal. Lê todas as Ordens de Trabalho "
            "via API REST e regrava o BD_Relatório Semanal.xlsx. Roda em ~2 minutos. "
            "Faz backup automático em _backup_BD/. Requer arquivo .env configurado "
            "com FRACTTAL_CLIENT_ID, FRACTTAL_CLIENT_SECRET e AUXILIAR_SOURCE_PATH."
        )
        tk.Label(cAPI, text=msgAPI, wraplength=900, justify="left",
                 fg="#374151", font=("Segoe UI", 10)).pack(anchor="w", padx=8, pady=6)

        opt_api = tk.Frame(cAPI)
        opt_api.pack(fill="x", padx=8, pady=2)
        self.var_api_no_aux = tk.BooleanVar(value=False)
        self.var_api_subtask = tk.BooleanVar(value=False)
        tk.Checkbutton(opt_api, text="Pular aba AUXILIAR (--no-auxiliar)",
                       variable=self.var_api_no_aux).pack(anchor="w", padx=8, pady=1)
        tk.Checkbutton(opt_api,
                       text="Tentar coletar subtarefas (--com-subtarefas, EXPERIMENTAL)",
                       variable=self.var_api_subtask).pack(anchor="w", padx=8, pady=1)

        sub_api = tk.Frame(cAPI)
        sub_api.pack(fill="x", padx=8, pady=4)
        tk.Label(sub_api, text="Limitar nº de OTs (opcional, debug):").pack(side="left")
        self.ent_api_limit = tk.Entry(sub_api, width=10)
        self.ent_api_limit.pack(side="left", padx=4)
        tk.Label(sub_api, text="Em branco = todas (~17.900)",
                 fg="#6b7280", font=("Segoe UI", 9)).pack(side="left", padx=4)

        btAPI = tk.Frame(cAPI)
        btAPI.pack(fill="x", padx=8, pady=10)
        self.btn_api = tk.Button(btAPI, text="Atualizar BD via Fracttal API",
                                  bg="#a9db21", fg="#191528",
                                  font=("Segoe UI", 11, "bold"),
                                  relief="flat", padx=24, pady=10,
                                  command=self._rodar_api_bd)
        self.btn_api.pack(side="left")
        tk.Button(btAPI, text="Testar autenticação",
                  bg="#e5e7eb", relief="flat", padx=14, pady=10,
                  command=self._rodar_api_test).pack(side="left", padx=8)
        tk.Button(btAPI, text="Aplicar Overrides de Cluster",
                  bg="#fde68a", fg="#191528", relief="flat", padx=14, pady=10,
                  command=self._rodar_aplicar_overrides).pack(side="left", padx=8)
        tk.Button(btAPI, text="Limpar duplicatas do BD",
                  bg="#fecaca", fg="#191528", relief="flat", padx=14, pady=10,
                  command=self._rodar_dedup_bd).pack(side="left", padx=8)

        # Linha de auto-update
        autoAPI = tk.Frame(cAPI)
        autoAPI.pack(fill="x", padx=8, pady=(4, 8))
        tk.Label(autoAPI, text="Auto-atualização (Windows Task Scheduler):",
                 font=("Segoe UI", 9, "bold"), fg="#374151").pack(side="left", padx=(0, 8))
        tk.Label(autoAPI, text="Intervalo (min):",
                 font=("Segoe UI", 9), fg="#374151").pack(side="left")
        self.ent_api_intervalo = tk.Entry(autoAPI, width=5)
        self.ent_api_intervalo.insert(0, "5")
        self.ent_api_intervalo.pack(side="left", padx=4)
        tk.Button(autoAPI, text="Ativar auto-update",
                  bg="#10b981", fg="#fff", relief="flat", padx=12, pady=4,
                  command=self._instalar_agendamento_api).pack(side="left", padx=4)
        tk.Button(autoAPI, text="Desativar",
                  bg="#e5e7eb", relief="flat", padx=12, pady=4,
                  command=self._remover_agendamento_api).pack(side="left", padx=4)

        # --- Card: Abrir pasta ---
        c2 = tk.LabelFrame(f, text=" Atalhos ", font=("Segoe UI", 10, "bold"))
        c2.pack(fill="x", padx=12, pady=10)
        bt2 = tk.Frame(c2)
        bt2.pack(fill="x", padx=8, pady=10)
        tk.Button(bt2, text="Abrir pasta da Programação",
                  bg="#e5e7eb", relief="flat", padx=14, pady=8,
                  command=self._abrir_pasta).pack(side="left", padx=(0, 8))
        tk.Button(bt2, text="Abrir editor de observações",
                  bg="#e5e7eb", relief="flat", padx=14, pady=8,
                  command=self._abrir_obs).pack(side="left", padx=8)

        # --- Card: Sobre / versão ---
        c3 = tk.LabelFrame(f, text=" Recursos ativos ", font=("Segoe UI", 10, "bold"))
        c3.pack(fill="both", expand=True, padx=12, pady=10)
        info = (
            "• Feriados NACIONAL + ESTADUAL bloqueando alocação (lê pasta Feriados/)\n"
            "• Sugestões PCM ≥ now + 1h (nunca no passado)\n"
            "• Aba por cluster mesmo sem tarefa (este utilitário migra arquivos antigos)\n"
            "• Coluna Responsável nas abas + lookup AUXILIAR\n"
            "• Observações da semana (aba _Observacoes no arquivo gerado)\n"
            "• Preventivas (MPM/MPS/MPA) nunca classificadas como 'Não Programadas'\n"
            "• Deslocamento em cascata respeitando dias passados, finalizadas e paralelas\n"
            "• Retry 5x com backoff exponencial em todos os I/O de Excel\n"
            "• Lockfile contra execuções paralelas\n"
        )
        tk.Label(c3, text=info, wraplength=900, justify="left",
                 fg="#374151", font=("Segoe UI", 10)).pack(anchor="w", padx=8, pady=8)

    def _abrir_pasta(self):
        if not BASE_DIR:
            return
        if sys.platform.startswith("win"):
            os.startfile(BASE_DIR)
        else:
            subprocess.Popen(["xdg-open", BASE_DIR])

    def _abrir_obs(self):
        if not BASE_DIR:
            return
        path = os.path.join(BASE_DIR, OBS_FILE)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write("# Observações da semana — uma por linha\n")
        if sys.platform.startswith("win"):
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])

    def _rodar_api_bd(self):
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Já rodando", "Aguarde a execução atual terminar.")
            return
        script = os.path.join(BASE_DIR, "gerar_bd_via_api.py")
        if not os.path.exists(script):
            messagebox.showerror("Não encontrado", "gerar_bd_via_api.py não foi encontrado.")
            return
        # Confirma sobrescrita
        bd_path = os.path.join(BASE_DIR, "BD_Relatório Semanal.xlsx")
        if os.path.exists(bd_path):
            ok = messagebox.askyesno(
                "Sobrescrever BD?",
                "O BD_Relatório Semanal.xlsx atual será substituído pelos dados\n"
                "vindos diretamente da API Fracttal.\n\n"
                "Um backup do arquivo atual será salvo em _backup_BD/ antes.\n\n"
                "Deseja continuar?")
            if not ok:
                return
        args = [sys.executable, "-u", script]
        if self.var_api_no_aux.get():
            args.append("--no-auxiliar")
        if self.var_api_subtask.get():
            args.append("--com-subtarefas")
        lim = self.ent_api_limit.get().strip()
        if lim.isdigit():
            args.extend(["--limit", lim])
        env = os.environ.copy()
        env["PCM_PROG_DIR"] = BASE_DIR
        self._executar(args, env)

    def _rodar_api_test(self):
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Já rodando", "Aguarde a execução atual terminar.")
            return
        script = os.path.join(BASE_DIR, "gerar_bd_via_api.py")
        if not os.path.exists(script):
            messagebox.showerror("Não encontrado", "gerar_bd_via_api.py não foi encontrado.")
            return
        args = [sys.executable, "-u", script, "--test"]
        env = os.environ.copy()
        env["PCM_PROG_DIR"] = BASE_DIR
        self._executar(args, env)

    def _rodar_aplicar_overrides(self):
        """Aplica overrides de 'Ativo Classificação 2' no BD_Relatório Semanal.xlsx.
        Mapa fixo de 14 ativos -> clusters corretos (regra padrão Grid Co)."""
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Já rodando", "Aguarde a execução atual terminar.")
            return
        script = os.path.join(BASE_DIR, "aplicar_overrides_classificacao.py")
        if not os.path.exists(script):
            messagebox.showerror("Não encontrado",
                                 "aplicar_overrides_classificacao.py não foi encontrado.")
            return
        bd_path = os.path.join(BASE_DIR, "BD_Relatório Semanal.xlsx")
        if not os.path.exists(bd_path):
            messagebox.showerror("BD não encontrado",
                                 "BD_Relatório Semanal.xlsx não existe na pasta.")
            return
        ok = messagebox.askyesno(
            "Aplicar overrides de Cluster?",
            "Vou ajustar a coluna 'Ativo Classificação 2' das 14 usinas mapeadas\n"
            "(Nova Xavantina, São José do Egito, Aparecida 3, Guaratinguetá 5,\n"
            "Araçoiaba da Serra 1/2, Elias Fausto 1, etc).\n\n"
            "IMPORTANTE: feche o BD_Relatório Semanal.xlsx no Excel antes.\n\n"
            "Continuar?")
        if not ok:
            return
        args = [sys.executable, "-u", script]
        env = os.environ.copy()
        env["PCM_PROG_DIR"] = BASE_DIR
        self._executar(args, env)

    def _rodar_dedup_bd(self):
        """Remove linhas duplicadas do BD_Relatório Semanal.xlsx.
        Fix do bug intermitente da paginação Fracttal (task #167)."""
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Já rodando", "Aguarde a execução atual terminar.")
            return
        script = os.path.join(BASE_DIR, "dedup_bd_relatorio.py")
        if not os.path.exists(script):
            messagebox.showerror("Não encontrado",
                                 "dedup_bd_relatorio.py não foi encontrado.")
            return
        bd_path = os.path.join(BASE_DIR, "BD_Relatório Semanal.xlsx")
        if not os.path.exists(bd_path):
            messagebox.showerror("BD não encontrado",
                                 "BD_Relatório Semanal.xlsx não existe na pasta.")
            return
        modo = messagebox.askyesnocancel(
            "Limpar duplicatas do BD?",
            "Vou remover linhas duplicadas do BD_Relatório Semanal.xlsx.\n"
            "Causa do bug: paginação da API Fracttal ficou em loop em alguma rodada,\n"
            "gerando 180 cópias de cada linha.\n\n"
            "Será criado um backup em _backup_BD/ antes de mexer.\n\n"
            "IMPORTANTE: feche o BD_Relatório Semanal.xlsx no Excel antes.\n\n"
            "SIM = aplica (remove duplicatas)\n"
            "NÃO = simula (--dry-run, só mostra o que mudaria)\n"
            "CANCELAR = não faz nada")
        if modo is None:
            return
        args = [sys.executable, "-u", script]
        if not modo:  # NÃO → dry-run
            args.append("--dry-run")
        env = os.environ.copy()
        env["PCM_PROG_DIR"] = BASE_DIR
        self._executar(args, env)

    def _instalar_agendamento_diario(self):
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Já rodando", "Aguarde a execução atual terminar.")
            return
        ps1 = os.path.join(BASE_DIR, "instalar_agendamento.ps1")
        if not os.path.exists(ps1):
            messagebox.showerror("Não encontrado",
                                 "instalar_agendamento.ps1 não foi encontrado.")
            return
        intervalo = self.ent_diario_intervalo.get().strip() or "5"
        if not intervalo.isdigit() or int(intervalo) < 1:
            messagebox.showerror("Inválido", "Intervalo deve ser número inteiro >= 1")
            return
        ok = messagebox.askyesno(
            "Ativar agendamento?",
            f"Vai criar/atualizar tarefa no Windows que roda atualizacao_semanal.py\n"
            f"a cada {intervalo} minutos, das 07h às 19h, segunda a sexta.\n\n"
            f"Continuar?")
        if not ok:
            return
        args = ["powershell", "-ExecutionPolicy", "Bypass", "-File", ps1,
                "-IntervaloMin", intervalo]
        env = os.environ.copy()
        env["PCM_PROG_DIR"] = BASE_DIR
        self._executar(args, env)

    def _remover_agendamento_diario(self):
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Já rodando", "Aguarde a execução atual terminar.")
            return
        ps1 = os.path.join(BASE_DIR, "instalar_agendamento.ps1")
        if not os.path.exists(ps1):
            messagebox.showerror("Não encontrado",
                                 "instalar_agendamento.ps1 não foi encontrado.")
            return
        ok = messagebox.askyesno(
            "Desativar agendamento?",
            "Vai remover a tarefa do Windows. atualizacao_semanal.py não vai mais "
            "rodar automaticamente.\n\nContinuar?")
        if not ok:
            return
        args = ["powershell", "-ExecutionPolicy", "Bypass", "-File", ps1, "-Remover"]
        env = os.environ.copy()
        env["PCM_PROG_DIR"] = BASE_DIR
        self._executar(args, env)

    def _instalar_agendamento_api(self):
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Já rodando", "Aguarde a execução atual terminar.")
            return
        ps1 = os.path.join(BASE_DIR, "instalar_agendamento_bd_api.ps1")
        if not os.path.exists(ps1):
            messagebox.showerror("Não encontrado",
                                 "instalar_agendamento_bd_api.ps1 não foi encontrado.")
            return
        intervalo = self.ent_api_intervalo.get().strip() or "5"
        if not intervalo.isdigit() or int(intervalo) < 1:
            messagebox.showerror("Inválido", "Intervalo deve ser número inteiro >= 1")
            return
        ok = messagebox.askyesno(
            "Ativar auto-update?",
            f"Vai criar uma tarefa no Agendador de Tarefas do Windows que roda a cada "
            f"{intervalo} minutos, 24h por dia.\n\n"
            f"Cada execução leva ~2 min e sobrescreve o BD com dados do Fracttal.\n\n"
            f"Continuar?")
        if not ok:
            return
        args = ["powershell", "-ExecutionPolicy", "Bypass", "-File", ps1,
                "-IntervaloMin", intervalo]
        env = os.environ.copy()
        env["PCM_PROG_DIR"] = BASE_DIR
        self._executar(args, env)

    def _remover_agendamento_api(self):
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Já rodando", "Aguarde a execução atual terminar.")
            return
        ps1 = os.path.join(BASE_DIR, "instalar_agendamento_bd_api.ps1")
        if not os.path.exists(ps1):
            messagebox.showerror("Não encontrado",
                                 "instalar_agendamento_bd_api.ps1 não foi encontrado.")
            return
        ok = messagebox.askyesno(
            "Desativar auto-update?",
            "Vai remover a tarefa agendada do Windows. O BD não vai mais ser "
            "atualizado automaticamente.\n\nContinuar?")
        if not ok:
            return
        args = ["powershell", "-ExecutionPolicy", "Bypass", "-File", ps1, "-Remover"]
        env = os.environ.copy()
        env["PCM_PROG_DIR"] = BASE_DIR
        self._executar(args, env)

    def _rodar_migracao(self):
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Já rodando", "Aguarde a execução atual terminar.")
            return
        script_path = os.path.join(BASE_DIR, "migrar_abas_clusters.py")
        if not os.path.exists(script_path):
            messagebox.showerror("Não encontrado",
                                 "migrar_abas_clusters.py não foi encontrado na pasta.")
            return
        args = [sys.executable, "-u", script_path]
        semanas_txt = self.ent_migrar_semanas.get().strip()
        if semanas_txt:
            for s in semanas_txt.split():
                if s.isdigit():
                    args.append(s)
        env = os.environ.copy()
        env["PCM_PROG_DIR"] = BASE_DIR
        self._executar(args, env)

    def _build_tab_rel(self):
        f = self.tab_rel
        tk.Label(f, text="Geração de relatórios analíticos (PDF/DOCX).",
                 font=("Segoe UI", 11)).pack(anchor="w", padx=12, pady=(12, 8))

        msg = (
            "Abre a interface de Relatórios em uma nova janela.\n"
            "Lá você escolhe: cliente, período (semanal/mensal/semestral/anual), "
            "escopo (cliente ou usina), formato (PDF/DOCX), e clica Gerar.\n\n"
            "Os relatórios saem em: Relatórios/<Cliente>/<Período>/"
        )
        tk.Label(f, text=msg, wraplength=900, justify="left",
                 fg="#374151", font=("Segoe UI", 10)).pack(anchor="w", padx=12, pady=8)

        tk.Button(f, text="Abrir Interface de Relatórios",
                  bg="#a9db21", fg="#191528",
                  font=("Segoe UI", 11, "bold"),
                  relief="flat", padx=24, pady=10,
                  command=self._abrir_relatorios).pack(anchor="w", padx=12, pady=12)

    # ====================== Utilitários ======================

    def _verifica_ambiente(self):
        if not BASE_DIR:
            messagebox.showerror(
                "Pasta não encontrada",
                "A pasta '09. Programação Semanal' não foi localizada na sua máquina.\n\n"
                "Verifique se você sincronizou a pasta SharePoint via OneDrive, "
                "ou defina a variável de ambiente PCM_PROG_DIR.")
            self.lbl_pasta.config(text="✗ Pasta NÃO encontrada", fg="#ef4444")
            self.btn_prog.config(state="disabled")
            self.btn_atu.config(state="disabled")
        else:
            short = BASE_DIR
            if len(short) > 70:
                short = "..." + short[-67:]
            self.lbl_pasta.config(text="📁 " + short, fg="#a9db21")
            self._log("Pasta detectada: " + BASE_DIR, "info")

    def _carregar_observacoes(self):
        if not BASE_DIR:
            return
        path = os.path.join(BASE_DIR, OBS_FILE)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.txt_obs.delete("1.0", "end")
                    self.txt_obs.insert("1.0", f.read())
            except OSError as e:
                self._log(f"Erro lendo {OBS_FILE}: {e}", "error")

    def _salvar_observacoes(self):
        if not BASE_DIR:
            return
        path = os.path.join(BASE_DIR, OBS_FILE)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.txt_obs.get("1.0", "end").rstrip() + "\n")
            self._log(f"Observações salvas em {OBS_FILE}", "info")
            self.lbl_status.config(text="Observações salvas")
        except OSError as e:
            messagebox.showerror("Erro", f"Não foi possível salvar: {e}")

    # ---- Observações da SEMANA ATUAL (override mid-week) ----
    def _build_tab_obs_atual(self):
        f = self.tab_obs_atual
        tk.Label(f, text="Intervenções na SEMANA ATUAL. Tarefas novas já entram sozinhas por RPN na nuvem; "
                         "aqui você ajusta o que quiser. Ao enviar, a nuvem aplica em ~15 min (não precisa de PC).",
                 font=("Segoe UI", 11), pady=6, wraplength=900, justify="left"
                 ).pack(anchor="w", padx=12, pady=(12, 4))

        oframe = tk.LabelFrame(f, text=" Observações da semana atual ",
                               font=("Segoe UI", 10, "bold"))
        oframe.pack(fill="both", expand=True, padx=12, pady=6)
        tk.Label(oframe,
                 text=("Mesma gramática da sexta. Uma por linha:\n"
                       "  • Reprogramar:     OS; dia; tarefa (opcional); turno    ex.:  7981; ter; [Athon] Substituição de TCUs; manhã\n"
                       "  • Tirar da semana: OS; não                              ex.:  7981; não\n"
                       "Dias: seg/ter/qua/qui/sex · Turnos: manhã/tarde/noite. Ao aplicar, os conflitos são empurrados."),
                 font=("Consolas", 9), fg="#6b7280", justify="left").pack(anchor="w", padx=8, pady=(4, 0))
        self.txt_obs_atual = scrolledtext.ScrolledText(oframe, height=10,
                                                       font=("Segoe UI", 10), wrap="word")
        self.txt_obs_atual.pack(fill="both", expand=True, padx=8, pady=6)
        self._carregar_obs_atual()

        btns = tk.Frame(f)
        btns.pack(fill="x", padx=12, pady=10)
        tk.Button(btns, text="Enviar pra nuvem (aplica em ~15 min)",
                  bg="#a9db21", fg="#191528", font=("Segoe UI", 11, "bold"),
                  relief="flat", padx=24, pady=10,
                  command=self._aplicar_obs_atual).pack(side="left")
        tk.Button(btns, text="Salvar observações",
                  bg="#e5e7eb", relief="flat", padx=14, pady=10,
                  command=self._salvar_obs_atual).pack(side="left", padx=8)

    def _carregar_obs_atual(self):
        if not BASE_DIR:
            return
        path = os.path.join(BASE_DIR, OBS_ATUAL_FILE)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    self.txt_obs_atual.delete("1.0", "end")
                    self.txt_obs_atual.insert("1.0", fh.read())
            except OSError as e:
                self._log(f"Erro lendo {OBS_ATUAL_FILE}: {e}", "error")

    def _salvar_obs_atual(self):
        if not BASE_DIR:
            return
        path = os.path.join(BASE_DIR, OBS_ATUAL_FILE)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.txt_obs_atual.get("1.0", "end").rstrip() + "\n")
            self._log(f"Observações da semana atual salvas em {OBS_ATUAL_FILE}", "info")
            self.lbl_status.config(text="Observações da semana atual salvas")
        except OSError as e:
            messagebox.showerror("Erro", f"Não foi possível salvar: {e}")

    def _aplicar_obs_atual(self):
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Já rodando", "Aguarde a execução atual terminar.")
            return
        self._salvar_obs_atual()
        # Envia as observações pro repo (GitHub). O robô da nuvem (semanal.yml) aplica
        # no próximo ciclo (~15 min) — status vivo + novas OS por RPN + suas intervenções.
        args = [sys.executable, "-u", os.path.join(BASE_DIR, "publicar_observacoes_github.py"), "--atual"]
        env = os.environ.copy()
        env["PCM_PROG_DIR"] = BASE_DIR
        self._executar(args, env)

    def _enviar_semana_nuvem(self):
        """Sexta: publica a Programação Semana XX (maior nº) + observações no repo,
        pra o robô da nuvem usar como base. Sem upload manual no GitHub."""
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Já rodando", "Aguarde a execução atual terminar.")
            return
        self._salvar_observacoes()
        args = [sys.executable, "-u", os.path.join(BASE_DIR, "publicar_semana_github.py")]
        env = os.environ.copy()
        env["PCM_PROG_DIR"] = BASE_DIR
        self._executar(args, env)

    def _rodar_programacao(self):
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Já rodando", "Aguarde a execução atual terminar.")
            return
        self._salvar_observacoes()
        args = [sys.executable, "-u", os.path.join(BASE_DIR, SCRIPT_V7)]
        sem = self.ent_semana.get().strip()
        # programacao_v7 não tem --semana (calcula automaticamente),
        # mas se quiser forçar, pode definir env var
        env = os.environ.copy()
        env["PCM_PROG_DIR"] = BASE_DIR
        if sem:
            env["PCM_WEEK_FORCE"] = sem
        self._executar(args, env)

    def _rodar_mpas(self):
        """Gera o mpas.json (Gerencial + Fracttal) e publica, num passo só."""
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Já rodando", "Aguarde a execução atual terminar.")
            return
        args = [sys.executable, "-u", os.path.join(BASE_DIR, SCRIPT_MPAS)]
        if self.var_mpas_semapi.get():
            args.append("--sem-api")
        env = os.environ.copy()
        env["PCM_PROG_DIR"] = BASE_DIR
        self._executar(args, env)

    def _rodar_prog_clientes(self):
        """M2: gera um .eml/.html por cliente a partir do banco_dados.json.

        Lê a MESMA semana que o painel publica, então precisa rodar DEPOIS de
        gerar a programação — senão sai o e-mail da semana anterior."""
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Já rodando", "Aguarde a execução atual terminar.")
            return
        args = [sys.executable, "-u", os.path.join(BASE_DIR, SCRIPT_CLI)]
        sem = self.ent_semana.get().strip()
        if sem:
            args.extend(["--semana", sem])
        env = os.environ.copy()
        env["PCM_PROG_DIR"] = BASE_DIR
        self._executar(args, env)

    def _abrir_pasta_clientes(self):
        pasta = os.path.join(BASE_DIR, "_relatorios_cliente")
        if not os.path.isdir(pasta):
            messagebox.showinfo("Ainda não existe",
                                "A pasta é criada na primeira geração.\n"
                                "Clique em 'Gerar Programação Semanal Clientes' antes.")
            return
        os.startfile(pasta)

    def _rodar_atualizacao(self):
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Já rodando", "Aguarde a execução atual terminar.")
            return
        args = [sys.executable, "-u", os.path.join(BASE_DIR, SCRIPT_AT)]
        if self.var_no_sync.get():
            args.append("--no-sync")
        if self.var_no_sug.get():
            args.append("--no-sugestoes")
        sem = self.ent_semana_atu.get().strip()
        if sem:
            args.extend(["--semana", sem])
        env = os.environ.copy()
        env["PCM_PROG_DIR"] = BASE_DIR
        self._executar(args, env)

    def _abrir_relatorios(self):
        if not BASE_DIR:
            return
        path = os.path.join(BASE_DIR, SCRIPT_REL)
        if not os.path.exists(path):
            messagebox.showerror("Não encontrado",
                                 f"{SCRIPT_REL} não foi encontrado na pasta.")
            return
        try:
            env = os.environ.copy()
            env["PCM_PROG_DIR"] = BASE_DIR
            subprocess.Popen([sys.executable, path], env=env, cwd=BASE_DIR)
            self._log("Interface de Relatórios aberta em janela separada", "info")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def _executar(self, args, env):
        """Roda subprocess e pipe stdout/stderr pro log + arquivo de log."""
        # Inicializa buffer para coleta de linhas (pra popup de erro)
        self._linhas_buffer = []
        self._teve_error_tag = False

        # Abre arquivo de log persistente em _log_painel/
        try:
            log_dir = os.path.join(BASE_DIR, "_log_painel")
            os.makedirs(log_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            script_nm = os.path.basename(args[2]) if len(args) > 2 else "script"
            self._log_file_path = os.path.join(
                log_dir, f"{ts}_{script_nm.replace('.py','')}.log")
            self._log_file = open(self._log_file_path, "w", encoding="utf-8")
            self._log_file.write(f"=== Iniciado em {datetime.now().isoformat()} ===\n")
            self._log_file.write(f"Comando: {args}\n")
            self._log_file.write(f"Pasta:   {BASE_DIR}\n")
            self._log_file.write("=" * 70 + "\n\n")
            self._log_file.flush()
        except Exception as e:
            self._log_file = None
            self._log_file_path = None
            self._log(f"! Não foi possível criar arquivo de log: {e}", "warn")

        cmd_str = " ".join(f'"{a}"' if " " in a else a for a in args[1:])
        self._log("=" * 70, "info")
        self._log(f"[{datetime.now().strftime('%H:%M:%S')}] Iniciando: {cmd_str}", "info")
        if self._log_file_path:
            self._log(f"Log persistente: {os.path.basename(self._log_file_path)}", "info")
        self._log("=" * 70, "info")
        self.lbl_status.config(text="Executando...", fg="#f59e0b")
        self.btn_prog.config(state="disabled")
        self.btn_atu.config(state="disabled")
        # Forca UTF-8 nos child processes (evita UnicodeEncodeError no Windows cp1252)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        try:
            self.proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                cwd=BASE_DIR, env=env, text=True, encoding="utf-8",
                errors="replace", bufsize=1)
        except Exception as e:
            tb = traceback.format_exc()
            self._log(f"FALHA ao iniciar subprocess: {e}", "error")
            for ln in tb.splitlines():
                self._log("  " + ln, "error")
            messagebox.showerror(
                "Falha ao iniciar",
                f"Nao consegui iniciar o script.\n\n{e}\n\n"
                f"Verifique se o Python esta acessivel e se o arquivo existe.")
            self._fim(rc=-1)
            return
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        """Le linha-a-linha. Robusto contra exceptions."""
        try:
            for line in self.proc.stdout:
                line = line.rstrip()
                tag = "info"
                up = line.upper()
                if ("ERROR" in up or "TRACEBACK" in up or "ERRO" in up
                        or "EXCEPTION" in up or "NAMEERROR" in up
                        or "TYPEERROR" in up or "VALUEERROR" in up
                        or "KEYERROR" in up or "ATTRIBUTEERROR" in up
                        or "FILENOTFOUND" in up or "PERMISSIONERROR" in up
                        or "FILE \"" in up):
                    tag = "error"
                    self._teve_error_tag = True
                elif "WARN" in up or "AVISO" in up:
                    tag = "warn"
                self._linhas_buffer.append((line, tag))
                if len(self._linhas_buffer) > 200:
                    self._linhas_buffer.pop(0)
                self.after(0, self._log, line, tag)
        except Exception as e:
            tb = traceback.format_exc()
            self.after(0, self._log,
                       f"! Reader thread crashou: {type(e).__name__}: {e}", "error")
            for ln in tb.splitlines():
                self.after(0, self._log, "  " + ln, "error")
        finally:
            try:
                rc = self.proc.wait(timeout=2)
            except Exception:
                rc = -999
            self.after(0, self._log, f"=== Fim (codigo de saida: {rc}) ===",
                       "info" if rc == 0 else "error")
            self.after(0, self._fim, rc)

    def _fim(self, rc=None):
        self.btn_prog.config(state="normal")
        self.btn_atu.config(state="normal")
        if hasattr(self, "btn_migrar"):
            self.btn_migrar.config(state="normal")
        if hasattr(self, "btn_api"):
            self.btn_api.config(state="normal")

        if getattr(self, "_log_file", None):
            try:
                self._log_file.write(
                    f"\n=== Encerrado em {datetime.now().isoformat()} (rc={rc}) ===\n")
                self._log_file.close()
            except Exception:
                pass

        teve_erro = (rc not in (0, None)) or getattr(self, "_teve_error_tag", False)

        if rc == 0 and not teve_erro:
            self.lbl_status.config(text="Concluido com sucesso", fg="#10b981")
        elif rc == 0 and teve_erro:
            self.lbl_status.config(text="Concluiu mas teve erros no log", fg="#f59e0b")
            self._mostrar_popup_erro(rc, parcial=True)
        elif rc is not None:
            self.lbl_status.config(text=f"FALHOU (codigo {rc})", fg="#ef4444")
            self._mostrar_popup_erro(rc, parcial=False)
        else:
            self.lbl_status.config(text="Pronto", fg="#6b7280")

    def _mostrar_popup_erro(self, rc, parcial=False):
        linhas_erro = [ln for ln, tag in getattr(self, "_linhas_buffer", []) if tag == "error"]
        ultimas = linhas_erro[-15:] if linhas_erro else [
            ln for ln, _ in self._linhas_buffer[-15:]
        ]
        texto = "\n".join(ultimas) if ultimas else "(sem mensagens capturadas)"
        titulo = "Script terminou com erros" if parcial else f"Script FALHOU (codigo {rc})"
        log_path = getattr(self, "_log_file_path", None) or "(arquivo nao criado)"
        msg_topo = (
            f"O script terminou com codigo {rc}.\n"
            "Veja as ultimas linhas de erro abaixo. O log completo esta em:\n"
            f"{log_path}\n"
        )
        top = tk.Toplevel(self)
        top.title(titulo)
        top.geometry("900x520")
        top.configure(bg="#fff5f5")
        tk.Label(top, text=titulo, font=("Segoe UI", 13, "bold"),
                 fg="#b91c1c", bg="#fff5f5").pack(anchor="w", padx=14, pady=(14, 4))
        tk.Label(top, text=msg_topo, justify="left", wraplength=860,
                 fg="#374151", bg="#fff5f5").pack(anchor="w", padx=14)
        st = scrolledtext.ScrolledText(top, height=18, bg="#1e1e2e", fg="#fca5a5",
                                        font=("Consolas", 9), wrap="word")
        st.pack(fill="both", expand=True, padx=14, pady=10)
        st.insert("1.0", texto)
        st.config(state="disabled")
        bf = tk.Frame(top, bg="#fff5f5")
        bf.pack(fill="x", padx=14, pady=(0, 14))
        if log_path and os.path.exists(log_path):
            tk.Button(bf, text="Abrir log completo",
                      bg="#e5e7eb", relief="flat", padx=12, pady=6,
                      command=lambda p=log_path: self._abrir_arquivo(p)
                      ).pack(side="left", padx=(0, 8))
            tk.Button(bf, text="Abrir pasta dos logs",
                      bg="#e5e7eb", relief="flat", padx=12, pady=6,
                      command=lambda p=os.path.dirname(log_path): self._abrir_arquivo(p)
                      ).pack(side="left", padx=(0, 8))
        tk.Button(bf, text="Fechar",
                  bg="#a9db21", fg="#191528", font=("Segoe UI", 10, "bold"),
                  relief="flat", padx=18, pady=6,
                  command=top.destroy).pack(side="right")

    def _abrir_arquivo(self, path):
        if not path:
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("Nao consegui abrir", str(e))

    def _log(self, msg, tag="info"):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n", tag)
        self.log.see("end")
        self.log.config(state="disabled")
        if getattr(self, "_log_file", None):
            try:
                self._log_file.write(msg + "\n")
                self._log_file.flush()
            except Exception:
                pass

    def _limpar_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")


if __name__ == "__main__":
    app = App()
    app.mainloop()
