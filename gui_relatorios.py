# -*- coding: utf-8 -*-
"""
Interface grafica (Grid Co.) para gerar relatorios de manutencao.
Permite escolher periodo, escopo (cliente/usina/todos), referencia e formato.
Execute:  python gui_relatorios.py    (ou via Gerar_Relatorios.bat / .exe)
"""
import os, sys, threading, datetime as dt, traceback
import tkinter as tk
from tkinter import ttk, messagebox
import relatorio_clientes as R

NAVY="#191528"; GRAY="#504C63"; LIME="#A9DB21"; WHITE="#FFFFFF"; LIGHT="#F2F3F5"
MESES=["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"]

class App:
    def __init__(self,root):
        self.root=root; root.title("Grid Co. · Relatórios de Manutenção"); root.configure(bg=WHITE)
        root.geometry("580x680"); root.resizable(False,False)
        self.idx=self.rows=self.aux=None; self.clientes=[]; self.usinas_por_cli={}
        self._build(); self._carregar_async()

    def _hdr(self):
        f=tk.Frame(self.root,bg=NAVY,height=70); f.pack(fill="x"); f.pack_propagate(False)
        # emblema se existir
        try:
            from PIL import Image, ImageTk
            p=os.path.join(R.ASSETS,"emblema_white.png")
            if os.path.exists(p):
                im=Image.open(p).convert("RGBA"); im.thumbnail((46,46))
                self._logo=ImageTk.PhotoImage(im); tk.Label(f,image=self._logo,bg=NAVY).pack(side="left",padx=16)
        except Exception: pass
        tk.Label(f,text="Relatórios de Manutenção",bg=NAVY,fg=WHITE,font=("Segoe UI",16,"bold")).pack(side="left",pady=18)

    def _build(self):
        self._hdr()
        body=tk.Frame(self.root,bg=WHITE); body.pack(fill="both",expand=True,padx=22,pady=14)
        def lbl(t,r):
            tk.Label(body,text=t,bg=WHITE,fg=NAVY,font=("Segoe UI",10,"bold")).grid(row=r,column=0,sticky="w",pady=(10,2))
        # Periodo
        lbl("Período",0)
        self.periodo=ttk.Combobox(body,values=["mensal","semanal","semestral","anual"],state="readonly",width=20)
        self.periodo.set("mensal"); self.periodo.grid(row=0,column=1,sticky="w"); self.periodo.bind("<<ComboboxSelected>>",self._upd_ref)
        # Referencia
        lbl("Referência",1)
        self.ref=ttk.Entry(body,width=22); self.ref.grid(row=1,column=1,sticky="w")
        hoje=dt.date.today(); self.ref.insert(0,f"{hoje.year}-{hoje.month:02d}")
        self.refhint=tk.Label(body,text="ex.: 2026-04 (ano-mês)",bg=WHITE,fg=GRAY,font=("Segoe UI",8)); self.refhint.grid(row=1,column=2,sticky="w",padx=8)
        # Escopo
        lbl("Escopo",2)
        self.escopo=tk.StringVar(value="cliente")
        ef=tk.Frame(body,bg=WHITE); ef.grid(row=2,column=1,columnspan=2,sticky="w")
        for txt,val in [("Cliente","cliente"),("Usina","usina"),("Todos os clientes","todos"),("Portfólio Grid","portfolio")]:
            tk.Radiobutton(ef,text=txt,variable=self.escopo,value=val,bg=WHITE,fg=NAVY,selectcolor=LIGHT,
                           activebackground=WHITE,command=self._upd_escopo,font=("Segoe UI",9)).pack(side="left",padx=4)
        # Cliente
        lbl("Cliente",3)
        self.cli=ttk.Combobox(body,values=[],state="readonly",width=30); self.cli.grid(row=3,column=1,columnspan=2,sticky="w")
        self.cli.bind("<<ComboboxSelected>>",self._upd_usinas)
        # Usina(s) — seleção múltipla
        self._lbl_lista=tk.Label(body,text="Usina(s)",bg=WHITE,fg=NAVY,font=("Segoe UI",10,"bold")); self._lbl_lista.grid(row=4,column=0,sticky="nw",pady=(10,2))
        uf=tk.Frame(body,bg=WHITE); uf.grid(row=4,column=1,columnspan=2,sticky="w")
        self.usi=tk.Listbox(uf,selectmode="extended",height=6,width=44,exportselection=False,
                            bg=LIGHT,fg=NAVY,highlightthickness=0,relief="flat",font=("Segoe UI",9))
        sb=tk.Scrollbar(uf,orient="vertical",command=self.usi.yview); self.usi.config(yscrollcommand=sb.set)
        self.usi.pack(side="left"); sb.pack(side="left",fill="y")
        tk.Label(uf,text="  Ctrl/Shift\n  p/ várias",bg=WHITE,fg=GRAY,font=("Segoe UI",8),justify="left").pack(side="left",padx=4)
        # Formato
        lbl("Formato",5)
        self.formato=ttk.Combobox(body,values=["pdf","docx","ambos"],state="readonly",width=12); self.formato.set("pdf")
        self.formato.grid(row=5,column=1,sticky="w")
        # Botao
        self.btn=tk.Button(body,text="Gerar relatório",bg=LIME,fg=NAVY,font=("Segoe UI",11,"bold"),
                           relief="flat",padx=18,pady=8,command=self._gerar,state="disabled")
        self.btn.grid(row=6,column=0,columnspan=3,pady=18)
        # Log
        self.log=tk.Text(body,height=9,width=64,bg=LIGHT,fg=NAVY,font=("Consolas",8),relief="flat")
        self.log.grid(row=7,column=0,columnspan=3,sticky="we")
        self._log("Carregando base de dados...")
        self._upd_escopo()

    def _log(self,t):
        self.log.insert("end",t+"\n"); self.log.see("end"); self.root.update_idletasks()
    def _upd_ref(self,*_):
        p=self.periodo.get(); hoje=dt.date.today()
        ex={"mensal":(f"{hoje.year}-{hoje.month:02d}","ex.: 2026-04 (ano-mês)"),
            "semanal":(f"{hoje.year}-W{hoje.isocalendar()[1]:02d}","ex.: 2026-W22 (ano-semana)"),
            "semestral":(f"{hoje.year}-H1","ex.: 2026-H1 ou 2026-H2"),
            "anual":(f"{hoje.year}","ex.: 2026")}[p]
        self.ref.delete(0,"end"); self.ref.insert(0,ex[0]); self.refhint.config(text=ex[1])
    def _upd_escopo(self,*_):
        e=self.escopo.get()
        self.cli.config(state=("readonly" if e in ("cliente","usina") else "disabled"))
        self.usi.config(state=("normal" if e in ("usina","portfolio") else "disabled"))
        if e=="portfolio":
            self._lbl_lista.config(text="Cliente(s)")
            self.usi.delete(0,"end")
            for c in self.clientes: self.usi.insert("end",c)
            self.usi.selection_set(0,"end")
        elif e=="usina":
            self._lbl_lista.config(text="Usina(s)"); self._upd_usinas()
        else:
            self._lbl_lista.config(text="Usina(s)"); self.usi.delete(0,"end")
    def _upd_usinas(self,*_):
        c=self.cli.get(); us=sorted(self.usinas_por_cli.get(c,[]))
        self.usi.delete(0,"end")
        for u in us: self.usi.insert("end",u)
        if us: self.usi.selection_set(0)

    def _carregar_async(self):
        threading.Thread(target=self._carregar,daemon=True).start()
    def _carregar(self):
        try:
            pasta=R.achar_pasta()
            self.idx,self.rows,self.aux,cu=R.carregar(pasta)
            self.clientes=sorted([c for c in cu.keys() if c and c!="—"])
            self.usinas_por_cli={c:sorted(v) for c,v in cu.items()}
            self.cli.config(values=self.clientes)
            if self.clientes: self.cli.set(self.clientes[0]); self._upd_usinas()
            self.btn.config(state="normal"); self._log(f"Pronto. {len(self.rows)} OS · {len(self.clientes)} clientes.")
        except Exception as e:
            self._log("ERRO ao carregar: "+str(e)); self._log(traceback.format_exc())

    def _gerar(self):
        self.btn.config(state="disabled"); threading.Thread(target=self._gerar_run,daemon=True).start()
    def _gerar_run(self):
        try:
            per=self.periodo.get(); ref=self.ref.get().strip(); fmt=self.formato.get(); e=self.escopo.get()
            pasta=R.achar_pasta()
            alvos=[]
            if e=="portfolio":
                sel=[self.usi.get(i) for i in self.usi.curselection()]
                cl=sel if (sel and len(sel)<len(self.clientes)) else None
                self._log(f"Gerando Portfólio Grid ({'todos os clientes' if not cl else ', '.join(cl)})...")
                out,k=R.gerar_portfolio(per,ref,self.idx,self.rows,self.aux,pasta,clientes=cl)
                final=out
                if fmt in ("pdf","ambos"):
                    pdf=R.to_pdf(out)
                    if pdf:
                        final=pdf
                        if fmt=="pdf":
                            try: os.remove(out)
                            except Exception: pass
                self._log(f"OK ({k['n']} tarefas) → {os.path.basename(final)}")
                messagebox.showinfo("Grid Co.","Relatório de Portfólio gerado!"); self.btn.config(state="normal"); return
            if e=="todos":
                alvos=[("cliente",c,c) for c in self.clientes]
            elif e=="cliente":
                c=self.cli.get(); alvos=[("cliente",c,c)]
            else:
                sel=[self.usi.get(i) for i in self.usi.curselection()]
                if not sel: self._log("Selecione ao menos uma usina."); self.btn.config(state="normal"); return
                alvos=[("usina",u,(R.norm_cli(u.split(" - ")[0]) if " - " in u else self.cli.get())) for u in sel]
            self._log(f"Gerando {len(alvos)} relatório(s) [{per}/{ref}/{fmt}]...")
            ok=0
            for et,nome,cp in alvos:
                self._log(f"  · {nome} ...")
                out,k=R.gerar(et,nome,cp,per,ref,self.idx,self.rows,self.aux,pasta)
                final=out
                if fmt in ("pdf","ambos"):
                    pdf=R.to_pdf(out)
                    if pdf:
                        final=pdf
                        if fmt=="pdf":
                            try: os.remove(out)
                            except Exception: pass
                    else:
                        self._log("    [aviso] PDF indisponível (instale Word ou LibreOffice). DOCX mantido.")
                ok+=1; self._log(f"    OK ({k['n']} OS) → {os.path.basename(final)}")
            self._log(f"Concluído: {ok} relatório(s) em Relatórios/.")
            messagebox.showinfo("Grid Co.",f"{ok} relatório(s) gerado(s) com sucesso!")
        except Exception as ex:
            self._log("ERRO: "+str(ex)); self._log(traceback.format_exc())
            messagebox.showerror("Erro",str(ex))
        finally:
            self.btn.config(state="normal")

if __name__=="__main__":
    root=tk.Tk(); App(root); root.mainloop()
