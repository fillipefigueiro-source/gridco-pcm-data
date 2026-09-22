# -*- coding: utf-8 -*-
"""
================================================================================
 GRID CO. | Gerador de Relatorios de Manutencao  (v3)
================================================================================
Le 'BD_Relatório Semanal.xlsx' e gera relatorios (PDF/DOCX) por CLIENTE ou USINA.
Regras principais:
  - OS canceladas sao IGNORADAS em tudo.
  - Usina definida por 'Ativo Classificação 1'.
  - Mes de referencia: considera tarefas CONCLUIDAS no mes (por data de conclusao)
    e tarefas ABERTAS/EM ANDAMENTO no mes (abertas antes, ainda nao concluidas).
  - Pagina de preventivas MPM (mensal) / MPS (semestral) / MPA (anual) com avanco.
  - MTTR / MTBF / Disponibilidade Inerente por TIPOLOGIA de ativo (formulas Grid Co.).
Uso:
  python relatorio_clientes.py --periodo mensal --ref 2026-04 --usina "Athon - Matões 100"
  python relatorio_clientes.py --periodo mensal --ref 2026-04 --cliente Thopen --formato pdf
  python relatorio_clientes.py --periodo mensal --ref 2026-04 --todos --formato ambos
"""
import os, sys, argparse, datetime as dt, unicodedata, re, glob, tempfile
from collections import defaultdict, Counter
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Wedge, Polygon, Circle
from matplotlib.font_manager import FontProperties
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

# ----------------------------------------------------------------- MARCA
NAVY="191528"; GRAY="504C63"; LIME="A9DB21"; WHITE="FFFFFF"; LIGHT="F2F3F5"; MID="8A8794"; INK="2A2533"
def hx(h): return RGBColor(int(h[0:2],16),int(h[2:4],16),int(h[4:6],16))
C_NAVY="#191528"; C_GRAY="#504C63"; C_LIME="#A9DB21"; C_LIGHT="#F2F3F5"; C_MID="#8A8794"
ORDER_CAT=["Preventiva","Preditiva","Zeladoria","Corretiva","Administrativa","Religamento","Religamento Remoto","Handover","Outros"]
# Paleta: preventivas em verde (lime→oliva); Corretiva = cinza-escuro âncora;
# família Administrativa/Religamentos em degradê AZUL (2026-07: melhora a distinção
# entre as barras, que antes eram todas cinza e "coladas" ao olho humano).
COR_CAT={"Preventiva":"#A9DB21","Preditiva":"#7FB800","Zeladoria":"#5C8A00","Corretiva":"#504C63",
 "Administrativa":"#2F6E8F","Religamento":"#4E92B8","Religamento Remoto":"#86BAD6","Handover":"#BBD9E8","Outros":"#DCE6EC"}
PROGRAMADAS={"Preventiva","Preditiva","Handover"}   # categorias consideradas "tarefa programada"
DATA_INICIO_SISTEMA=dt.datetime(2025,10,20)
HORAS_GERACAO_DIA=12          # UFV opera ~12 h/dia (uptime do MTBF em horas de geração)
FATOR_GERACAO=HORAS_GERACAO_DIA/24.0
TURNO_INI=7.0; TURNO_FIM=17.0; ALMOCO_H=1.2   # 07:00-17:00, almoço 12:00-13:12 (1h12)
HH_DIA=(TURNO_FIM-TURNO_INI)-ALMOCO_H          # 8.8 h/dia por pessoa
BASE=getattr(sys,"_MEIPASS",None) or os.path.dirname(os.path.abspath(__file__)); ASSETS=os.path.join(BASE,"assets")
CHARTS=os.path.join(tempfile.gettempdir(),"gridco_charts"); os.makedirs(CHARTS,exist_ok=True)
FB="/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"; FR="/usr/share/fonts/truetype/google-fonts/Poppins-Regular.ttf"; FS="/usr/share/fonts/truetype/google-fonts/Poppins-SemiBold.ttf"
def fp(p,s): return FontProperties(fname=p,size=s) if os.path.exists(p) else FontProperties(size=s)
MESES=["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"]
MES3=[m[:3] for m in MESES]

# ----------------------------------------------------------------- UTIL
def sa(s):
    if s is None: return ""
    return "".join(c for c in unicodedata.normalize("NFD",str(s)) if unicodedata.category(c)!="Mn")
def parse_dur(v):
    if v in (None,""): return 0.0
    if isinstance(v,dt.timedelta): return v.total_seconds()/3600
    if isinstance(v,dt.time): return v.hour+v.minute/60+v.second/3600
    if isinstance(v,(int,float)): return float(v)*24 if 0<v<3 else float(v)
    s=str(v).strip()
    m=re.match(r"^(\d+):(\d{1,2}):(\d{1,2})$",s)
    if m: return int(m[1])+int(m[2])/60+int(m[3])/3600
    m=re.match(r"^(\d+):(\d{1,2})$",s)
    if m: return int(m[1])+int(m[2])/60
    try: return float(s)
    except: return 0.0
def parse_dt(v):
    if v in (None,""): return None
    if isinstance(v,dt.datetime): return v
    if isinstance(v,dt.date): return dt.datetime(v.year,v.month,v.day)
    s=str(v).strip()
    for f in ("%Y-%m-%d %H:%M:%S","%Y-%m-%d %H:%M","%Y-%m-%d","%d/%m/%Y %H:%M","%d/%m/%Y"):
        try: return dt.datetime.strptime(s,f)
        except: pass
    return None
def dias_uteis(ini,fim):
    n=0; d=ini.date() if hasattr(ini,"date") else ini
    fimd=fim.date() if hasattr(fim,"date") else fim
    while d<fimd:
        if d.weekday()<5: n+=1
        d+=dt.timedelta(days=1)
    return n
_FER_CACHE={}
def get_feriados():
    try: pasta=achar_pasta()
    except Exception: return None
    if pasta in _FER_CACHE: return _FER_CACHE[pasta]
    import glob as _g
    cand=_g.glob(os.path.join(pasta,"Feriados","*.xlsx"))+_g.glob(os.path.join(pasta,"feriados","*.xlsx"))
    fer={"nac":set(),"est":defaultdict(set),"mun":defaultdict(set)}
    if cand:
        try:
            from python_calamine import CalamineWorkbook
            wb=CalamineWorkbook.from_path(cand[0]); sh=wb.sheet_names[0]
            d=wb.get_sheet_by_name(sh).to_python(skip_empty_area=False)
            for r in d[2:]:
                # bloco 1: NACIONAL/ESTADUAL (col0 tipo, col1 uf, col2 data)
                t=str(r[0]).strip().upper() if len(r)>2 and r[0] else ""
                dd=parse_dt(r[2]) if len(r)>2 else None
                if dd:
                    if t=="NACIONAL": fer["nac"].add(dd.date())
                    elif t=="ESTADUAL": fer["est"][str(r[1]).strip().upper()].add(dd.date())
                # bloco 2: MUNICIPAL (col6 tipo, col7 uf, col8 municipio, col9 data)
                if len(r)>9 and r[6] and str(r[6]).strip().upper()=="MUNICIPAL":
                    dm=parse_dt(r[9]); 
                    if dm: fer["mun"][sa(r[8]).upper().strip()].add(dm.date())
        except Exception: pass
    _FER_CACHE[pasta]=fer; return fer
def feriados_uteis(ini,fim,fer,uf=None,muni=None):
    if not fer: return 0
    n=0; d=ini.date() if hasattr(ini,"date") else ini; fimd=fim.date() if hasattr(fim,"date") else fim
    while d<fimd:
        if d.weekday()<5 and (d in fer["nac"] or (uf and d in fer["est"].get(uf,set())) or (muni and d in fer["mun"].get(muni,set()))): n+=1
        d+=dt.timedelta(days=1)
    return n
def hh_pessoa_mes(ini,fim,fer=None,uf=None,muni=None):
    return max(0,(dias_uteis(ini,fim)-feriados_uteis(ini,fim,fer,uf,muni)))*HH_DIA
def fnum(n,dec=0): return f"{n:,.{dec}f}".replace(",","§").replace(".",",").replace("§",".")
def fdate(d): return d.strftime("%d/%m/%Y") if isinstance(d,(dt.datetime,dt.date)) else "—"
def fdt(d): return d.strftime("%d/%m/%Y %H:%M") if isinstance(d,(dt.datetime,dt.date)) else "—"

# ----------------------------------------------------------------- CAMINHO / DADOS
def achar_pasta():
    env=os.environ.get("PCM_PROG_DIR")
    if env and os.path.isdir(env): return env
    home=os.path.expanduser("~")
    c=[os.path.join(home,"GRID CO","Grid Co. - Gridco","4. O&M","11.Pré-Operação","6. PCM","09. Programação Semanal"),
       os.path.join(home,"OneDrive - Grid Co","4. O&M","11.Pré-Operação","6. PCM","09. Programação Semanal")]
    c+=glob.glob("/sessions/*/mnt/09. Programação Semanal"); c.append(BASE)
    for x in c:
        if x and os.path.exists(os.path.join(x,"BD_Relatório Semanal.xlsx")): return x
    raise SystemExit("Pasta nao encontrada. Defina PCM_PROG_DIR.")

def carregar(pasta):
    """Carrega OS da API Fracttal (cache TTL) + cadastro do AUXILIAR - FABRICIO.xlsx.
    Migração 2026-07: NÃO depende mais de BD_Relatório Semanal.xlsx.
    Retorna idx, rows, aux, cli_usinas (mesma assinatura de antes)."""
    import pickle, time as _time
    # 1) OS/tarefas: direto da API Fracttal, com cache local (TTL) p/ não puxar toda hora
    cache=os.path.join(pasta,".cache_bd_api.pkl")
    ttl=int(os.environ.get("REL_API_TTL_MIN","15"))*60
    idx=rows=None
    if os.path.exists(cache):
        try:
            if _time.time()-os.path.getmtime(cache) < ttl:
                d=pickle.load(open(cache,"rb"))
                if d.get("v")==4: idx,rows=d["idx"],d["rows"]
        except Exception: idx=rows=None
    if rows is None:
        idx,rows=_carregar_os_api()
        try: pickle.dump({"v":4,"idx":idx,"rows":rows},open(cache,"wb"))
        except Exception: pass
    # 2) AUXILIAR (cadastro das usinas) — de AUXILIAR - FABRICIO.xlsx
    aux=_carregar_auxiliar(pasta)
    # 3) cli_usinas a partir das OS (Ativo Classificação 1), ignorando canceladas
    cu2=defaultdict(set); sidx=idx.get('Ativo Classificação 1'); sstat=idx.get('Status')
    if sidx is not None:
        for r in rows:
            if sstat is not None and str(r[sstat]).strip()=="Cancelado": continue
            ac1=r[sidx]
            if not ac1: continue
            u=re.sub(r"\s{2,}"," ",re.sub(r"\s*-\s*[A-Z]{2}\s*$","",str(ac1).strip())).strip()
            c=norm_cli(u.split(" - ")[0]) if " - " in u else norm_cli(u)
            cu2[c].add(u)
    return idx,rows,aux,cu2

def _carregar_os_api():
    """Puxa todas as OS da API Fracttal (view tasks.v_works_orders_list_new) e devolve
    (idx, rows) no MESMO formato/colunas que o BD tinha. Reusa gerar_bd_via_api
    (mesmo client OAuth + transformar_wo_para_bd). Dedup defensivo por id de tarefa."""
    import gerar_bd_via_api as _bd
    client=_bd.FracttalClient(_bd.CLIENT_ID,_bd.CLIENT_SECRET,_bd.BASE_URL)
    client.autenticar()
    cols=list(_bd.COLS_BD_SEMANAL); idx={h:i for i,h in enumerate(cols)}
    # Normaliza códigos crus de Estado da Tarefa que o TASK_STATUS_MAP não cobre
    # (a API às vezes devolve IN_PROGRESS em vez de STARTED). NÃO é Status da OS.
    _EST_FIX={"IN_PROGRESS":"Em progresso","STARTED":"Em progresso",
              "NO_STARTED":"Não Iniciada","NOT_STARTED":"Não Iniciada",
              "PAUSED":"pausado","DONE":"Finalizados"}
    seen=set(); rows=[]
    for it in client.paginar("work_orders",page_size=100):
        d=_bd.transformar_wo_para_bd(it)
        _e=d.get("Estado da Tarefa")
        if _e in _EST_FIX: d["Estado da Tarefa"]=_EST_FIX[_e]
        wt=d.get("_id_work_orders_tasks")
        key=("wt",wt) if wt else ("combo",d.get("OSs ID"),d.get("Código"),d.get("Tarefa"))
        if key in seen: continue
        seen.add(key)
        rows.append([d.get(c) for c in cols])
    return idx,rows

def _carregar_auxiliar(pasta):
    """Lê o cadastro de usinas do AUXILIAR - FABRICIO.xlsx (aba Operacoes_1):
    cliente, cluster, capacidade (MWp), mobilização, cidade/UF, responsável O&M."""
    path=os.environ.get("REL_AUXILIAR_PATH") or os.path.join(pasta,"AUXILIAR - FABRICIO.xlsx")
    aux={}
    if not os.path.exists(path): return aux
    try:
        from python_calamine import CalamineWorkbook
        wb=CalamineWorkbook.from_path(path); names=wb.sheet_names
        sn="Operacoes_1" if "Operacoes_1" in names else names[0]
        data=wb.get_sheet_by_name(sn).to_python(skip_empty_area=False)
        ha=list(data[0]); ia={str(h).strip():i for i,h in enumerate(ha)}; src=data[1:]
    except Exception:
        import openpyxl
        wb=openpyxl.load_workbook(path,read_only=True,data_only=True)
        ws=wb["Operacoes_1"] if "Operacoes_1" in wb.sheetnames else wb[wb.sheetnames[0]]
        it=ws.iter_rows(values_only=True); ha=list(next(it)); ia={str(h).strip():i for i,h in enumerate(ha)}; src=list(it); wb.close()
    g=lambda r,k: r[ia[k]] if k in ia else None
    for r in src:
        ufv=g(r,'UFV')
        if not ufv: continue
        cli=(str(g(r,'CLIENTE')).strip() if g(r,'CLIENTE') else "—")
        entry={"ufv":ufv,"cliente":cli,"status":g(r,'STATUS'),
            "cap":g(r,'CAPACIDADE INSTALADA (MWp)'),"cidade":g(r,'CIDADE'),"uf":g(r,'UF'),
            "resp":g(r,'RESPONSÁVEL O&M'),"cluster":g(r,'CLUSTER'),"mob":g(r,'Data Mobilização')}
        key=sa(ufv).lower().strip(); aux[key]=entry
        # alias N00->N: o AUXILIAR usa "Marabá 100/200", o Fracttal usa "Marabá 1/2"
        m=re.search(r"(.*?)(\d)00\s*$",key)
        if m: aux.setdefault((m.group(1)+m.group(2)).strip(),entry)
        # alias numeral romano no fim: "Rodrigues I/II/III" -> "Rodrigues 1/2/3"
        mr=re.search(r"^(.*?)\s+(iii|ii|iv|v|i)\s*$",key)
        if mr:
            _rn={"i":"1","ii":"2","iii":"3","iv":"4","v":"5"}[mr.group(2)]
            aux.setdefault(f"{mr.group(1)} {_rn}".strip(),entry)
        # alias typo cliente: AUXILIAR "Ultragaz" vs Fracttal "Utragaz"
        if key.startswith("ultragaz"): aux.setdefault("utragaz"+key[len("ultragaz"):],entry)
    # De->para de nomes arbitrários (Fracttal -> AUXILIAR). Chaves já normalizadas
    # (sem acento, minúsculas). Adicione aqui novos casos de nome divergente.
    _OV={"thopen - campos dos goytacazes 1":"thopen - goytacazes 1",
         "thopen - santo inacio 12":"thopen - santo inacio 1 e 2"}
    for _frac,_ax in _OV.items():
        if _ax in aux: aux.setdefault(_frac,aux[_ax])
    return aux

def norm_cli(c):
    c=(c or "").strip()
    return {"utragaz":"Ultragaz","ultragaz":"Ultragaz","greenyellow":"GreenYellow","renogrid":"RenoGrid"}.get(c.lower(),c)

_UCACHE={}
def limpa_usina(ac1):
    s=str(ac1 or "").strip()
    s=re.sub(r"\s*-\s*[A-Z]{2}\s*$","",s)
    return re.sub(r"\s{2,}"," ",s).strip()
def resolve_usina(ac1,aux):
    """(cliente, usina, cluster, mob, cap) com 'Ativo Classificação 1' como chave da usina."""
    if ac1 in _UCACHE: return _UCACHE[ac1]
    if not ac1:
        _UCACHE[ac1]=(None,None,"—",None,0.0); return _UCACHE[ac1]
    usina=limpa_usina(ac1); cli=norm_cli(usina.split(" - ")[0]) if " - " in usina else norm_cli(usina)
    cluster="—"; mob=None; cap=0.0; ku=sa(usina).lower().strip(); match=aux.get(ku)
    if not match:
        for k,a in aux.items():
            if k==ku or k.startswith(ku+" ") or ku.startswith(k+" "): match=a; break
    if match:
        cli=norm_cli(match["cliente"]); cluster=match.get("cluster") or "—"
        mob=parse_dt(match.get("mob")) if match.get("mob") else None
        cap=match.get("cap") if isinstance(match.get("cap"),(int,float)) else 0.0
    res=(cli,usina,cluster,mob,cap); _UCACHE[ac1]=res; return res

# tipologia de ativo
TIPOLOGIAS=[
    ("Inversor",["inversor","inverter"]),
    ("Tracker",["tracker","rastreador","tcu"]),
    ("Cabine/Subestação",["cabine","subestac","subestaç","skid","transformador","trafo","cubiculo","cubículo","media tensao","média tensão"]),
    ("Proteção/Disjuntor",["disjuntor","protec","proteç","rele","relé","seccionador","fusivel","fusível"]),
    ("Módulos/String",["modulo","módulo","string","painel","placa","mppt","caixa de junc"]),
    ("Estrutura",["estrutura","mesa","fundac","fundaç","stringbox","string box"]),
    ("Segurança",["seguranca","segurança","cftv","camera","câmera","cerca","alarme","incendio","incêndio"]),
    ("Automação/Supervisório",["supervis","automac","automaç","scada","clp","comunic","conectiv","datalogger","gateway"]),
    ("Climatização",["ar condicionado","climatiz","hvac","exaustor"]),
    ("Instalações/Civil",["instalac","instalaç","civil","predial","iluminac","iluminaç","portao","portão","capina","vegetac","vegetaç","limpeza"]),
]
def tipologia_ativo(ativo):
    a=sa(ativo).lower()
    if not a.strip(): return "Não classificado"
    for nome,keys in TIPOLOGIAS:
        for kw in keys:
            if sa(kw) in a: return nome
    return "Outros"
def canon_equipe(s):
    s=re.sub(r"\s+"," ",str(s or "").strip())
    return s.upper() if s else "—"
def categoria(tipo,cl2):
    if str(cl2).strip().lower()=="zeladoria": return "Zeladoria"
    if tipo in ("Corretiva","Corretiva Emergencial"): return "Corretiva"
    if tipo in ("Preventiva","Inspeção"): return "Preventiva"
    if tipo=="Preditiva": return "Preditiva"
    if tipo=="Administrativa": return "Administrativa"
    if tipo=="Religamento": return "Religamento"
    if tipo=="Religamento Remoto": return "Religamento Remoto"
    if tipo=="Handover": return "Handover"
    return "Outros"
def cat_de(cat): return "Planejada" if cat in ("Preventiva","Preditiva","Zeladoria") else ("Corretiva" if cat=="Corretiva" else "Outras")
MP_LABEL={"MPW":"MPW — Semanal","MPQ":"MPQ — Quinzenal","MPM":"MPM — Mensal","MPT":"MPT — Trimestral",
          "MPS":"MPS — Semestral","MPA":"MPA — Anual","MPB":"MPB — Bianual"}
MP_ORDER=["MPW","MPQ","MPM","MPT","MPS","MPA","MPB"]
MP_PALAVRA=[("BIANUAL","MPB"),("BIENAL","MPB"),("SEMESTRAL","MPS"),("TRIMESTRAL","MPT"),
            ("QUINZENAL","MPQ"),("QUINZENA","MPQ"),("SEMANAL","MPW"),("MENSAL","MPM"),("ANUAL","MPA")]
def mp_code(tarefa):
    t=sa(tarefa).upper()
    for c in MP_ORDER:
        if re.search(r"\b"+c+r"\b",t): return c
    for w,c in MP_PALAVRA:
        if w in t: return c
    return None
FINALIZADO=lambda r: (r["estado"]=="Finalizados" or r["status"]=="Finalizados")

# ----------------------------------------------------------------- PERIODO
def janela(periodo,ref):
    p=periodo.lower()
    if p=="mensal":
        m=re.match(r"(\d{4})-(\d{1,2})",ref); y,mo=int(m[1]),int(m[2])
        ini=dt.datetime(y,mo,1); fim=dt.datetime(y+(mo//12),(mo%12)+1,1); rot=f"{MESES[mo-1]} de {y}"; tipo="Relatório Mensal"
    elif p=="semanal":
        m=re.match(r"(\d{4})-?W(\d{1,2})",ref,re.I)
        ini=dt.datetime.fromisocalendar(int(m[1]),int(m[2]),1) if m else (parse_dt(ref)-dt.timedelta(days=parse_dt(ref).weekday()))
        fim=ini+dt.timedelta(days=7); rot=f"Semana {ini.isocalendar()[1]:02d} de {ini.year}"; tipo="Relatório Semanal"
    elif p=="semestral":
        m=re.match(r"(\d{4})-?H?([12])",ref,re.I); y,h=int(m[1]),int(m[2])
        ini,fim,rot=(dt.datetime(y,1,1),dt.datetime(y,7,1),f"1º Semestre de {y}") if h==1 else (dt.datetime(y,7,1),dt.datetime(y+1,1,1),f"2º Semestre de {y}"); tipo="Relatório Semestral"
    elif p=="anual":
        y=int(re.match(r"(\d{4})",ref)[1]); ini,fim,rot=dt.datetime(y,1,1),dt.datetime(y+1,1,1),f"Ano de {y}"; tipo="Relatório Anual"
    else: raise SystemExit("periodo invalido")
    return ini,fim,rot,tipo

# ----------------------------------------------------------------- COLETA
def coletar(escopo_tipo,escopo_nome,idx,rows,aux):
    g=lambda r,k:r[idx[k]]
    regs=[]
    for r in rows:
        if str(g(r,'Status')).strip()=="Cancelado": continue          # ignora cancelados
        ac1=g(r,'Ativo Classificação 1')
        cli,ufv,cluster,ufv_mob,ufv_cap=resolve_usina(ac1,aux)
        _muf=re.search(r"-\s*([A-Z]{2})\s*$",str(ac1 or ""))
        _uf=_muf.group(1) if _muf else None
        _u=ufv or ""
        _muni=_u.split(" - ",1)[1] if " - " in _u else _u
        _muni=sa(re.sub(r"\s*\d.*$","",_muni)).upper().strip()
        if escopo_tipo=="cliente" and cli!=escopo_nome: continue
        if escopo_tipo=="usina" and ufv!=escopo_nome: continue
        tipo=g(r,'Tipo de tarefa') or "—"; cl2=g(r,'Tarefa -> Classificação 2'); catg=categoria(tipo,cl2)
        regs.append(dict(osid=g(r,'OSs ID'),numsol=g(r,'Número de Solicitação'),cli=cli,ufv=ufv or (ac1 or "—"),cluster=cluster,
            tipo=tipo,categoria=catg,cat=cat_de(catg),programada=(catg in PROGRAMADAS),
            estado=g(r,'Estado da Tarefa') or "",status=g(r,'Status') or "",
            dprog=parse_dt(g(r,'Data Programada')) or parse_dt(g(r,'Data Calculada')),
            dcri=parse_dt(g(r,'Data de Criação da OS')),dini=parse_dt(g(r,'Data inicial')),
            dfim=parse_dt(g(r,'Data final')),dfinos=parse_dt(g(r,'Data de finalização da OS')),
            devento=parse_dt(g(r,'Data do Incidente')),dur=parse_dur(g(r,'Tempo de execução')),
            tot=parse_dur(g(r,'Total de Horas')) or parse_dur(g(r,'Tempo de execução')),
            crit=g(r,'Tarefa -> Criticidade') or "—",tarefa=g(r,'Tarefa') or "—",ativo=g(r,'Ativo') or "—",
            sistema=g(r,'Tarefa -> Classificação 2') or "—",tipologia=tipologia_ativo(g(r,'Ativo')),
            resp=g(r,'Responsável') or "—",obs=g(r,'Ordem de Serviço -> Observação') or "",
            mp=mp_code(g(r,'Tarefa')),mob=ufv_mob,cap=ufv_cap,
            equipe=canon_equipe(g(r,'Ativo Classificação 2')),dur_est=parse_dur(g(r,'Tarefa -> Duração estimada')),
            uf=_uf,muni=_muni))
    return regs

# ----------------------------------------------------------------- KPIs / JANELA
def dedupe_os(lst):
    seen=set(); out=[]
    for x in lst:
        key=x["osid"] if x["osid"] not in (None,"") else id(x)
        if key in seen: continue
        seen.add(key); out.append(x)
    return out
# Só o plano preventivo/preditivo mantém a exceção. Inspeção, Administrativa e
# Handover saíram em 07/08/2026 (decisão do Fabrício): passam a entrar pelas três
# datas, como as corretivas.
TIPOS_PROG_EXC={"Preventiva","Preditiva"}
def no_mes(x,ini,fim):
    """Pertence ao mês de referência: Data Programada OU Data final OU Data inicial no mês.
    Exceção: preventiva/preditiva NÃO INICIADA só entra se a Data Programada for do mês."""
    def im(d): return bool(d and ini<=d<fim)
    nao_ini=str(x.get("estado","")).strip()=="Não Iniciada"
    if x["tipo"] in TIPOS_PROG_EXC and nao_ini:
        return im(x["dprog"])
    return im(x["dprog"]) or im(x["dfim"]) or im(x["dini"])
def kpis_mes(regs,ini,fim):
    mes=[x for x in regs if no_mes(x,ini,fim)]                      # universo do mês (regra Grid)
    conc=mes                                                       # base de análise = tarefas do mês
    abert=[x for x in mes if not (FINALIZADO(x) or x["dfim"])]      # em aberto (não finalizadas/sem fim)
    win=conc
    pc=Counter(x["categoria"] for x in conc)
    n=len(conc); nprev=pc.get("Preventiva",0); ncorr=pc.get("Corretiva",0)
    emerg=sum(1 for x in conc if x["tipo"]=="Corretiva Emergencial")
    base_pc=nprev+ncorr; pct_prev=100*nprev/base_pc if base_pc else 0
    prog=sum(1 for x in conc if x["programada"]); nprog=n-prog
    base_pr=prog+nprog; pct_prog=100*prog/base_pr if base_pr else 0
    conc_os=conc; pco=Counter(x["categoria"] for x in conc_os)
    n_os=len(conc_os); nprev_os=pco.get("Preventiva",0); ncorr_os=pco.get("Corretiva",0)
    base_o=nprev_os+ncorr_os; pct_prev_os=100*nprev_os/base_o if base_o else 0
    prog_os=sum(1 for x in conc_os if x["programada"]); nprog_os=n_os-prog_os
    base_po=prog_os+nprog_os; pct_prog_os=100*prog_os/base_po if base_po else 0
    abert_os=len(abert)
    return dict(conc=conc,abert=abert,win=conc,n=n,por_categoria=pc,nprev=nprev,ncorr=ncorr,emerg=emerg,
        pct_prev=pct_prev,prog=prog,nprog=nprog,pct_prog=pct_prog,n_abertas=len(abert),
        conc_os=conc_os,n_os=n_os,nprev_os=nprev_os,ncorr_os=ncorr_os,pct_prev_os=pct_prev_os,
        prog_os=prog_os,nprog_os=nprog_os,pct_prog_os=pct_prog_os,por_categoria_os=pco,abert_os=abert_os,
        usinas=Counter(x["ufv"] for x in conc),corr_equip=Counter(x["tarefa"] for x in conc if x["categoria"]=="Corretiva"),
        corr_ativo=Counter(x["ativo"] for x in conc if x["categoria"]=="Corretiva"))

def historico_mensal(regs,fim):
    cy,cm=(fim - dt.timedelta(days=1)).year,(fim - dt.timedelta(days=1)).month
    out=[]
    for mm in range(1,cm+1):
        a=dt.datetime(cy,mm,1); b=dt.datetime(cy+(mm//12),(mm%12)+1,1)
        w=[x for x in regs if no_mes(x,a,b)]
        nprev=sum(1 for x in w if x["categoria"]=="Preventiva"); nc=sum(1 for x in w if x["categoria"]=="Corretiva")
        base=nprev+nc
        out.append(dict(rot=MES3[mm-1],total=len(w),prev=nprev,corr=nc,outras=len(w)-nprev-nc,pct=100*nprev/base if base else 0,cats=Counter(x["categoria"] for x in w)))
    return out

def historico_prog(regs,fim):
    cy,cm=(fim - dt.timedelta(days=1)).year,(fim - dt.timedelta(days=1)).month
    out=[]
    for mm in range(1,cm+1):
        a=dt.datetime(cy,mm,1); b=dt.datetime(cy+(mm//12),(mm%12)+1,1)
        w=[x for x in regs if no_mes(x,a,b)]
        prog=sum(1 for x in w if x["programada"]); nprog=len(w)-prog
        out.append(dict(rot=MES3[mm-1],prog=prog,nprog=nprog,total=len(w),
            pct=100*prog/len(w) if w else 0))
    return out

def por_cluster(win):
    c=defaultdict(lambda: dict(n=0,prev=0,corr=0))
    for x in win:
        d=c[x["cluster"]]; d["n"]+=1
        if x["categoria"]=="Preventiva": d["prev"]+=1
        elif x["categoria"]=="Corretiva": d["corr"]+=1
    return c
def por_usina_tab(win):
    u=defaultdict(lambda: dict(n=0,prev=0,corr=0,emerg=0,crit_alta=0,hh=0.0))
    for x in win:
        d=u[x["ufv"]]; d["n"]+=1; d["hh"]+=x["tot"]
        if x["categoria"]=="Preventiva": d["prev"]+=1
        elif x["categoria"]=="Corretiva":
            d["corr"]+=1
            if x["tipo"]=="Corretiva Emergencial": d["emerg"]+=1
            if str(x["crit"]).strip().lower() in ("alto","muito alto","alta","muito alta"): d["crit_alta"]+=1
    for d in u.values():
        base=d["prev"]+d["corr"]; d["pct_prev"]=100*d["prev"]/base if base else 0
    return u

# ----------------------------------------------------------------- PREVENTIVAS (MPM/MPS/MPA)
def mp_ref(x):
    """Data de referência da preventiva: execução (Data final) ou, se não executada, Data Programada/Inicial."""
    return x["dfim"] or x["dprog"] or x["dini"]
def mp_apos_mob(x):
    """Cronograma de preventivas inicia na mobilização da UFV."""
    r=mp_ref(x)
    return (not x["mob"]) or (r and r>=x["mob"])
def mp_mes(regs,ini,fim):
    out={}
    for code in MP_ORDER:
        planj=[x for x in regs if x["mp"]==code and mp_apos_mob(x) and mp_ref(x) and ini<=mp_ref(x)<fim]
        fin=[x for x in planj if FINALIZADO(x)]
        out[code]=dict(plan=len(planj),fin=len(fin),pend=len(planj)-len(fin),
            pct=100*len(fin)/len(planj) if planj else 0,
            pendentes=[x for x in planj if not FINALIZADO(x)])
    tp=sum(out[c]["plan"] for c in MP_ORDER); tf=sum(out[c]["fin"] for c in MP_ORDER)
    out["TOTAL"]=dict(plan=tp,fin=tf,pend=tp-tf,pct=100*tf/tp if tp else 0,pendentes=[])
    return out
def mp_12_por_code(regs,fim):
    """Consolidado dos últimos 12 meses por periodicidade."""
    cy,cm=(fim - dt.timedelta(days=1)).year,(fim - dt.timedelta(days=1)).month
    a=dt.datetime(cy,cm,1)
    for _ in range(11): a=(a - dt.timedelta(days=1)).replace(day=1)
    b=dt.datetime(cy+(cm//12),(cm%12)+1,1)
    out={}
    for code in MP_ORDER:
        planj=[x for x in regs if x["mp"]==code and mp_apos_mob(x) and mp_ref(x) and a<=mp_ref(x)<b]
        fin=[x for x in planj if FINALIZADO(x)]
        out[code]=dict(plan=len(planj),fin=len(fin),pend=len(planj)-len(fin),pct=100*len(fin)/len(planj) if planj else 0)
    tp=sum(out[c]["plan"] for c in MP_ORDER); tf=sum(out[c]["fin"] for c in MP_ORDER)
    out["TOTAL"]=dict(plan=tp,fin=tf,pend=tp-tf,pct=100*tf/tp if tp else 0)
    return out,(a,b)
def mp_12(regs,fim):
    cy,cm=(fim - dt.timedelta(days=1)).year,(fim - dt.timedelta(days=1)).month
    seq=[]
    for i in range(11,-1,-1):
        mm=cm-i; yy=cy
        while mm<=0: mm+=12; yy-=1
        seq.append((yy,mm))
    base=[]
    for yy,mm in seq:
        a=dt.datetime(yy,mm,1); b=dt.datetime(yy+(mm//12),(mm%12)+1,1)
        planj=[x for x in regs if x["mp"] and mp_apos_mob(x) and mp_ref(x) and a<=mp_ref(x)<b]
        fin=[x for x in planj if FINALIZADO(x)]
        base.append([f"{MES3[mm-1]}/{str(yy)[2:]}",len(planj),len(fin)])
    # cronograma começa no 1º mês com plano (mobilização)
    i0=next((i for i,b in enumerate(base) if b[1]>0),0)
    base=base[i0:]
    out=[]; acc_p=acc_f=0
    for rot,pl,fi in base:
        acc_p+=pl; acc_f+=fi
        out.append(dict(rot=rot,plan=pl,fin=fi,pct=100*fi/pl if pl else 0,acc=100*acc_f/acc_p if acc_p else 0))
    return out

# ----------------------------------------------------------------- CONFIABILIDADE (MTTR/MTBF/Disp por tipologia)
def _mttr_horas(devento,dfim):
    if not devento or not dfim or dfim<devento: return None
    dias=(dfim-devento).total_seconds()/86400.0
    return dias*12 if dias*24>24 else dias*24
def confiab_tipologia(regs,ref_final):
    """MTTR, MTBF e Disponibilidade Inerente por tipologia (desde DATA_INICIO_SISTEMA)."""
    corr=[x for x in regs if x["categoria"]=="Corretiva"]
    # MTTR por tipologia
    mttr=defaultdict(list)
    for x in corr:
        h=_mttr_horas(x["devento"],x["dfim"])
        if h is not None: mttr[x["tipologia"]].append(h)
    # qtd corretivas desde inicio (por tipologia)
    qtd=defaultdict(int)
    for x in corr:
        din=x["dini"] or x["dfinos"]
        if din and din>=DATA_INICIO_SISTEMA: qtd[x["tipologia"]]+=1
    # uptime por equipamento
    equip={}   # ativo -> {tip,mob}
    for x in regs:
        if x["ativo"] not in equip: equip[x["ativo"]]={"tip":x["tipologia"],"mob":x["mob"]}
    downtime=defaultdict(float)   # ativo -> horas parada corretiva
    for x in corr:
        if x["dini"]:
            mobeff=max(x["mob"] or DATA_INICIO_SISTEMA,DATA_INICIO_SISTEMA)
            if x["dini"]>=mobeff:
                fim=x["dfim"] or ref_final
                downtime[x["ativo"]]+=max(0,(fim-x["dini"]).total_seconds()/3600)*FATOR_GERACAO
    uptime_tip=defaultdict(float)
    for a,info in equip.items():
        mobeff=max(info["mob"] or DATA_INICIO_SISTEMA,DATA_INICIO_SISTEMA)
        horas=max(0,(ref_final-mobeff).total_seconds()/3600)*FATOR_GERACAO
        uptime_tip[info["tip"]]+=max(0,horas-downtime.get(a,0))
    out=[]
    for tip in set(list(qtd)+list(mttr)):
        q=qtd.get(tip,0); mt=sum(mttr[tip])/len(mttr[tip]) if mttr.get(tip) else 0
        mb=(uptime_tip.get(tip,0)/q) if q else 0
        disp=100*mb/(mb+mt) if (mb+mt)>0 else 0
        out.append(dict(tip=tip,corr=q,mttr=mt,mtbf=mb,disp=disp))
    return sorted([o for o in out if o["corr"]>0],key=lambda r:r["corr"],reverse=True)
def disponibilidade_grid(conc,ini,fim,n_usinas=1):
    """Disponibilidade Grid = 1 - (paradas por corretiva) / horas do período. Exclui religamentos (perdas da rede)."""
    horas=(fim-ini).total_seconds()/3600
    def dwt(x):
        if x.get("inativ") and x["inativ"]>0: return x["inativ"]
        if x["dini"] and x["dfim"] and x["dfim"]>=x["dini"]: return (x["dfim"]-x["dini"]).total_seconds()/3600
        return 0.0
    parada=sum(dwt(x) for x in conc if x["categoria"]=="Corretiva")
    denom=horas*max(1,n_usinas)
    return 100*max(0.0,1-(parada/denom)) if denom else 100.0
def crit_corretivas(win):
    ordem=["Muito alto","Alto","Médio","Baixo","—"]; c=Counter()
    for x in win:
        if x["categoria"]=="Corretiva":
            cr=str(x["crit"]).strip() or "—"
            cr={"muito alta":"Muito alto","alta":"Alto","medio":"Médio","médio":"Médio","baixo":"Baixo"}.get(cr.lower(),cr)
            c[cr]+=1
    return [(k,c[k]) for k in ordem if c.get(k)]+[(k,v) for k,v in c.items() if k not in ordem]
def confiab_ativo(regs,ini,fim):
    pini=(ini - dt.timedelta(days=1)).replace(day=1)
    cur=Counter(x["ativo"] for x in regs if x["categoria"]=="Corretiva" and x["dfinos"] and ini<=x["dfinos"]<fim)
    pre=Counter(x["ativo"] for x in regs if x["categoria"]=="Corretiva" and x["dfinos"] and pini<=x["dfinos"]<ini)
    linhas=[dict(ativo=a,corr=cur.get(a,0),prev=pre.get(a,0),delta=cur.get(a,0)-pre.get(a,0)) for a in (set(cur)|set(pre))]
    return linhas

def tempos_atend(conc):
    corr=[x for x in conc if x["categoria"]=="Corretiva"]
    emg=[x for x in corr if x["tipo"]=="Corretiva Emergencial"]
    def mean_h(lst,a,b):
        vals=[(x[b]-x[a]).total_seconds()/3600 for x in lst if x[a] and x[b] and x[b]>=x[a]]
        return (sum(vals)/len(vals)) if vals else 0
    return dict(resp_emg=mean_h(emg,"dcri","dini"),resp_corr=mean_h(corr,"dcri","dini"),
        reparo=mean_h(corr,"dini","dfim"),ciclo=mean_h(corr,"dcri","dfinos"),
        n_emg=len(emg),n_corr=len(corr))
def aderencia_prev(regs,ini,fim):
    planj=[x for x in regs if x["mp"] and x["dprog"] and ini<=x["dprog"]<fim]
    fin=[x for x in planj if FINALIZADO(x)]
    no_prazo=[x for x in fin if x["dfinos"] and x["dprog"] and x["dfinos"].date()<=x["dprog"].date()]
    return dict(plan=len(planj),fin=len(fin),no_prazo=len(no_prazo),
        pct_prazo=100*len(no_prazo)/len(fin) if fin else 0,
        pct_avanco=100*len(fin)/len(planj) if planj else 0)
def pareto_equip(conc):
    return Counter(x["ativo"] for x in conc if x["categoria"]=="Corretiva")
def bad_actors(regs,fim,nmeses=12):
    cy,cm=(fim - dt.timedelta(days=1)).year,(fim - dt.timedelta(days=1)).month
    ini12=dt.datetime(cy,cm,1)
    for _ in range(nmeses-1):
        ini12=(ini12 - dt.timedelta(days=1)).replace(day=1)
    c=Counter(x["ativo"] for x in regs if x["categoria"]=="Corretiva" and x["dfinos"] and ini12<=x["dfinos"]<fim)
    return c

# ----------------------------------------------------------------- GRAFICOS
def _save(fig,fn,tight=True):
    p=os.path.join(CHARTS,fn)
    if tight: fig.savefig(p,dpi=200,bbox_inches="tight",transparent=True)
    else: fig.savefig(p,dpi=200,transparent=True)
    plt.close(fig); return p
def _title(ax,t): ax.set_title(t,loc="left",fontproperties=fp(FR,9),color=C_MID,pad=8)
def g_donut(k,fn):
    pc=k["por_categoria_os"]; cats=[c for c in ORDER_CAT if pc.get(c,0)>0] or ["Preventiva"]
    vals=[pc[c] for c in cats]; cols=[COR_CAT[c] for c in cats]
    fig=plt.figure(figsize=(3.9,4.2)); ax=fig.add_axes([0.06,0.40,0.88,0.55])
    fig.text(0.5,0.97,"Distribuição por categoria",ha="center",fontproperties=fp(FR,9),color=C_MID)
    if sum(vals)==0: vals=[1]
    ax.pie(vals,colors=cols,startangle=90,counterclock=False,radius=1.0,wedgeprops=dict(width=0.40,edgecolor="white",linewidth=2))
    ax.set_aspect("equal")
    ax.text(0,0.10,f"{k['pct_prev_os']:.0f}%",ha="center",va="center",fontproperties=fp(FB,22),color=C_NAVY)
    ax.text(0,-0.20,"preventiva",ha="center",va="center",fontproperties=fp(FR,9.5),color=C_MID)
    h=[plt.matplotlib.patches.Patch(color=cols[i],label=f"{cats[i]} ({vals[i]})") for i in range(len(cats))]
    fig.legend(handles=h,loc="lower center",bbox_to_anchor=(0.5,0.02),ncol=2,frameon=False,prop=fp(FR,7.8),handlelength=1.0,columnspacing=1.0,labelspacing=0.3)
    return _save(fig,fn,tight=False)
def g_categorias(pc,fn):
    cats=[c for c in ORDER_CAT if pc.get(c,0)>0] or ["Outros"]
    import numpy as np; tot=sum(pc.values()) or 1
    fig,ax=plt.subplots(figsize=(3.7,3.0)); _title(ax,"Distribuição por categoria"); y=np.arange(len(cats))[::-1]
    vals=[pc.get(c,0) for c in cats]; cols=[COR_CAT[c] for c in cats]; mx=max(vals or [1])
    ax.barh(y,vals,color=cols,height=0.66)
    for i,v in zip(y,vals): ax.text(v+mx*0.015,i,f"{100*v/tot:.0f}%",va="center",fontproperties=fp(FS,8.5),color=C_NAVY)
    ax.set_xlim(0,mx*1.32); ax.set_yticks(y); ax.set_yticklabels(cats,fontproperties=fp(FR,8.5))
    for sp in ["top","right","bottom"]: ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color("#DDD"); ax.tick_params(length=0); ax.set_xticks([])
    return _save(fig,fn)
def g_prog(k,fn):
    """OS programadas x nao programadas (nivel OS)."""
    import numpy as np
    prog=k["prog_os"]; nprog=k["nprog_os"]; tot=prog+nprog or 1
    fig,ax=plt.subplots(figsize=(6.4,1.7)); _title(ax,"Tarefas programadas × não programadas")
    ax.barh([1],[prog],color=C_LIME,height=0.55); ax.barh([0],[nprog],color=C_GRAY,height=0.55)
    mx=max(prog,nprog,1)
    ax.text(prog+mx*0.02,1,f"{prog}  ({100*prog/tot:.0f}%)",va="center",fontproperties=fp(FS,11),color=C_NAVY)
    ax.text(nprog+mx*0.02,0,f"{nprog}  ({100*nprog/tot:.0f}%)",va="center",fontproperties=fp(FS,11),color=C_NAVY)
    ax.set_yticks([1,0]); ax.set_yticklabels(["Programadas","Não programadas"],fontproperties=fp(FS,9.5))
    ax.set_xlim(0,mx*1.18)
    for sp in ["top","right","bottom"]: ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color("#DDD"); ax.tick_params(length=0); ax.set_xticks([])
    return _save(fig,fn)
def g_prog_temporal(hp,fn):
    """Evolucao mensal de OS programadas x nao programadas (nivel OS)."""
    import numpy as np
    fig,ax=plt.subplots(figsize=(6.6,2.9)); _title(ax,"Tarefas programadas × não programadas — ano vigente"); x=np.arange(len(hp))
    prog=[h["prog"] for h in hp]; nprog=[h["nprog"] for h in hp]
    ax.bar(x,prog,color=C_LIME,label="Programadas"); ax.bar(x,nprog,bottom=prog,color=C_GRAY,label="Não programadas")
    ax2=ax.twinx(); ax2.plot(x,[h["pct"] for h in hp],color=C_NAVY,marker="o",lw=2); ax2.set_ylim(0,105)
    for i,h in enumerate(hp): ax2.text(i,h["pct"]+4,f"{h['pct']:.0f}%",ha="center",fontproperties=fp(FS,7.5),color=C_NAVY)
    ax.set_xticks(x); ax.set_xticklabels([h["rot"] for h in hp],fontproperties=fp(FR,8.5))
    for s in ["top"]: ax.spines[s].set_visible(False); ax2.spines[s].set_visible(False)
    ax.spines["right"].set_visible(False); ax2.spines["left"].set_visible(False)
    for lab in ax.get_yticklabels()+ax2.get_yticklabels(): lab.set_fontproperties(fp(FR,8))
    ax.tick_params(length=0); ax2.tick_params(length=0)
    ax.legend(frameon=False,prop=fp(FR,8),ncol=2,loc="lower center",bbox_to_anchor=(0.5,-0.30)); fig.subplots_adjust(bottom=0.26)
    return _save(fig,fn,tight=False)
def _legenda_rodape(fig,ax,ncol=4,fonte=7.5,folga=0.08):
    """Legenda no rodapé da FIGURA, com o espaço reservado pela altura medida.

    Antes a legenda era ancorada no EIXO (bbox_to_anchor=(0.5,-0.34)) com
    subplots_adjust fixo: ao encolher o eixo, a legenda descia junto, então
    a partir de 6 categorias (3 linhas) ela cobria os nomes dos meses — foi o
    que apareceu no relatório da Thopen (9 categorias). Ancorando na figura e
    medindo a altura real da legenda + dos rótulos, funciona com qualquer nº.
    """
    leg=ax.legend(frameon=False,prop=fp(FR,fonte),ncol=ncol,loc="lower center",
                  bbox_to_anchor=(0.5,0.01),bbox_transform=fig.transFigure)
    fig.canvas.draw()
    r=fig.canvas.get_renderer(); H=fig.bbox.height
    h_leg=leg.get_window_extent(r).height/H
    ticks=ax.get_xticklabels()
    h_tick=(max(t.get_window_extent(r).height for t in ticks)/H) if ticks else 0.0
    fig.subplots_adjust(bottom=0.01+h_leg+h_tick+folga)
    return leg
def g_hist(hist,fn):
    import numpy as np
    fig,ax=plt.subplots(figsize=(6.6,2.9)); _title(ax,"Evolução mensal — ano vigente"); x=np.arange(len(hist))
    cats_presentes=[c for c in ORDER_CAT if any(h.get("cats",{}).get(c,0) for h in hist)]
    bottom=np.zeros(len(hist))
    for c in cats_presentes:
        vals=np.array([h.get("cats",{}).get(c,0) for h in hist])
        ax.bar(x,vals,bottom=bottom,color=COR_CAT[c],label=c); bottom=bottom+vals
    ax2=ax.twinx(); ax2.plot(x,[h["pct"] for h in hist],color=C_NAVY,marker="o",lw=2); ax2.set_ylim(0,105)
    for i,h in enumerate(hist): ax2.text(i,h["pct"]+4,f"{h['pct']:.0f}%",ha="center",fontproperties=fp(FS,8),color=C_NAVY)
    ax.set_xticks(x); ax.set_xticklabels([h["rot"] for h in hist],fontproperties=fp(FR,8.5))
    for s in ["top"]: ax.spines[s].set_visible(False); ax2.spines[s].set_visible(False)
    ax.spines["right"].set_visible(False); ax2.spines["left"].set_visible(False)
    for lab in ax.get_yticklabels()+ax2.get_yticklabels(): lab.set_fontproperties(fp(FR,8))
    ax.tick_params(length=0); ax2.tick_params(length=0)
    _legenda_rodape(fig,ax,ncol=4,fonte=7.5)
    return _save(fig,fn,tight=False)
def g_corr_ano(hist,fn):
    import numpy as np
    fig,ax=plt.subplots(figsize=(6.6,2.7)); _title(ax,"Corretivas por mês — ano vigente"); x=np.arange(len(hist)); corr=[h["corr"] for h in hist]
    media=sum(corr)/len(corr) if corr else 0
    cols=[C_NAVY if i==len(hist)-1 else C_GRAY for i in range(len(hist))]
    ax.bar(x,corr,color=cols,width=0.62)
    for i,v in enumerate(corr): ax.text(i,v+max(corr or [1])*0.02,str(v),ha="center",fontproperties=fp(FS,8),color=C_NAVY)
    ax.axhline(media,color=C_LIME,lw=2,ls="--"); ax.text(len(hist)-0.5,media,f" média {media:.0f}",va="bottom",ha="right",fontproperties=fp(FR,8),color="#5C8A00")
    ax.set_xticks(x); ax.set_xticklabels([h["rot"] for h in hist],fontproperties=fp(FR,8.5))
    for sp in ["top","right"]: ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color("#DDD"); ax.spines["bottom"].set_color("#DDD"); ax.tick_params(length=0)
    for lab in ax.get_yticklabels(): lab.set_fontproperties(fp(FR,8))
    return _save(fig,fn)
def g_mp12(m12,fn):
    import numpy as np
    fig,ax=plt.subplots(figsize=(6.6,2.9)); _title(ax,"Cumprimento de preventivas — 12 meses"); x=np.arange(len(m12))
    ax.bar(x,[m["pct"] for m in m12],color=C_LIME,width=0.6,label="% no mês")
    ax.plot(x,[m["acc"] for m in m12],color=C_NAVY,marker="o",lw=2,label="% acumulado")
    for i,m in enumerate(m12): ax.text(i,m["acc"]+2,f"{m['acc']:.0f}%",ha="center",fontproperties=fp(FS,7.5),color=C_NAVY)
    ax.set_ylim(0,110); ax.set_xticks(x); ax.set_xticklabels([m["rot"] for m in m12],fontproperties=fp(FR,7.5),rotation=0)
    for sp in ["top","right"]: ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color("#DDD"); ax.spines["bottom"].set_color("#DDD"); ax.tick_params(length=0)
    for lab in ax.get_yticklabels(): lab.set_fontproperties(fp(FR,8))
    ax.legend(frameon=False,prop=fp(FR,8),ncol=2,loc="lower center",bbox_to_anchor=(0.5,-0.32)); fig.subplots_adjust(bottom=0.28)
    return _save(fig,fn,tight=False)
def g_barh(data,fn,color=C_LIME,maxn=10,title=None):
    items=sorted(data.items(),key=lambda kv:kv[1],reverse=True)[:maxn][::-1]
    if not items: items=[("—",0)]
    fig,ax=plt.subplots(figsize=(6.4,max(1.8,0.42*len(items)+0.6)))
    if title: _title(ax,title)
    nomes=[str(k).split(" - ")[-1][:30] for k,_ in items]; vals=[v for _,v in items]; mx=max(vals or [1])
    ax.barh(nomes,vals,color=color,height=0.62)
    for i,v in enumerate(vals): ax.text(v+mx*0.01,i,str(v),va="center",fontproperties=fp(FS,9),color=C_NAVY)
    ax.set_xlim(0,mx*1.12)
    for s in ["top","right","bottom"]: ax.spines[s].set_visible(False)
    ax.spines["left"].set_color("#DDD"); ax.tick_params(length=0); ax.set_xticks([])
    for lab in ax.get_yticklabels(): lab.set_fontproperties(fp(FR,8.5))
    return _save(fig,fn)
def g_pareto(counter,fn,maxn=12):
    import numpy as np
    items=counter.most_common(maxn)
    if not items: return None
    nomes=[str(k).split(" - ")[-1][:22] for k,_ in items]; vals=[v for _,v in items]
    tot=sum(counter.values()) or 1; cum=[]; acc=0
    for v in vals: acc+=v; cum.append(100*acc/tot)
    fig,ax=plt.subplots(figsize=(6.6,3.0)); _title(ax,"Pareto de corretivas por equipamento (80/20)")
    x=np.arange(len(items)); ax.bar(x,vals,color=C_GRAY,width=0.6)
    for i,v in enumerate(vals): ax.text(i,v+max(vals)*0.02,str(v),ha="center",fontproperties=fp(FS,7.5),color=C_NAVY)
    ax2=ax.twinx(); ax2.plot(x,cum,color=C_LIME,marker="o",lw=2); ax2.set_ylim(0,105)
    ax2.axhline(80,color=C_NAVY,ls="--",lw=1); ax2.text(len(items)-0.5,82,"80%",ha="right",fontproperties=fp(FR,7.5),color=C_NAVY)
    ax.set_xticks(x); ax.set_xticklabels(nomes,rotation=35,ha="right",fontproperties=fp(FR,7))
    for sp in ["top"]: ax.spines[sp].set_visible(False); ax2.spines[sp].set_visible(False)
    for lab in ax.get_yticklabels()+ax2.get_yticklabels(): lab.set_fontproperties(fp(FR,8))
    ax.tick_params(length=0); ax2.tick_params(length=0); fig.subplots_adjust(bottom=0.30)
    return _save(fig,fn,tight=False)

def g_grupos(metrics,fn,title,maxn=12):
    import numpy as np
    items=sorted(metrics.items(),key=lambda kv:kv[1]["n"],reverse=True)[:maxn][::-1]
    if not items: return None
    fig,ax=plt.subplots(figsize=(6.6,max(2.0,0.5*len(items)+0.7))); _title(ax,title)
    y=np.arange(len(items)); nomes=[str(k).split(" - ")[-1][:22] for k,_ in items]
    prev=[v["prev"] for _,v in items]; corr=[v["corr"] for _,v in items]; dem=[v["n"]-v["prev"]-v["corr"] for _,v in items]
    ax.barh(y,prev,color=C_LIME,label="Preventiva"); ax.barh(y,corr,left=prev,color=C_GRAY,label="Corretiva")
    ax.barh(y,dem,left=[prev[i]+corr[i] for i in range(len(items))],color="#CFCDD6",label="Demais")
    for i,(_,v) in zip(y,items): ax.text(v["n"]+0.5,i,str(v["n"]),va="center",fontproperties=fp(FS,8.5),color=C_NAVY)
    ax.set_yticks(y); ax.set_yticklabels(nomes,fontproperties=fp(FR,8.5))
    for sp in ["top","right"]: ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color("#DDD"); ax.spines["bottom"].set_color("#DDD"); ax.tick_params(length=0)
    for lab in ax.get_xticklabels(): lab.set_fontproperties(fp(FR,8))
    ax.legend(frameon=False,prop=fp(FR,8),ncol=3,loc="lower center",bbox_to_anchor=(0.5,-0.16)); fig.subplots_adjust(bottom=0.16)
    return _save(fig,fn,tight=False)
def g_hh(metrics,fn,title):
    import numpy as np
    items=sorted(metrics.items(),key=lambda kv:kv[1]["hh"],reverse=True)[:12][::-1]
    if not items: return None
    fig,ax=plt.subplots(figsize=(6.6,max(2.0,0.45*len(items)+0.7))); _title(ax,title)
    y=np.arange(len(items)); nomes=[str(k).split(" - ")[-1][:22] for k,_ in items]; vals=[v["hh"] for _,v in items]
    cols=[(C_LIME if v["util"]<=100 else "#C0392B") for _,v in items]; mx=max(vals or [1])
    ax.barh(y,vals,color=cols,height=0.6)
    for i,(_,v) in zip(y,items): ax.text(v["hh"]+mx*0.01,i,f"{fnum(v['hh'],0)}h · {v['util']:.0f}%",va="center",fontproperties=fp(FS,8),color=C_NAVY)
    ax.set_yticks(y); ax.set_yticklabels(nomes,fontproperties=fp(FR,8.5)); ax.set_xlim(0,mx*1.22)
    for sp in ["top","right","bottom"]: ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color("#DDD"); ax.tick_params(length=0); ax.set_xticks([])
    return _save(fig,fn)
def g_cluster(cl,fn):
    import numpy as np
    items=sorted(cl.items(),key=lambda kv:kv[1]["n"],reverse=True)[:12]
    if not items: return None
    fig,ax=plt.subplots(figsize=(6.6,max(2.0,0.5*len(items)+0.7))); _title(ax,"OTs por cluster (preventiva × corretiva)")
    y=np.arange(len(items))[::-1]; nomes=[k for k,_ in items]
    ax.barh(y,[v["prev"] for _,v in items],color=C_LIME,label="Preventiva")
    ax.barh(y,[v["corr"] for _,v in items],left=[v["prev"] for _,v in items],color=C_GRAY,label="Corretiva")
    ax.barh(y,[v["n"]-v["prev"]-v["corr"] for _,v in items],left=[v["prev"]+v["corr"] for _,v in items],color="#CFCDD6",label="Demais")
    ax.set_yticks(y); ax.set_yticklabels(nomes,fontproperties=fp(FR,8.5))
    for i,(_,v) in zip(y,items): ax.text(v["n"]+0.4,i,str(v["n"]),va="center",fontproperties=fp(FS,8.5),color=C_NAVY)
    for s in ["top","right"]: ax.spines[s].set_visible(False)
    ax.spines["left"].set_color("#DDD"); ax.spines["bottom"].set_color("#DDD"); ax.tick_params(length=0)
    for lab in ax.get_xticklabels(): lab.set_fontproperties(fp(FR,8))
    ax.legend(frameon=False,prop=fp(FR,8),ncol=3,loc="lower center",bbox_to_anchor=(0.5,-0.18)); fig.subplots_adjust(bottom=0.16)
    return _save(fig,fn,tight=False)

def g_capa(nome,sub_cliente,competencia,tipo,fn):
    """Capa minimalista e criativa: fundo navy, emblema-marca d'agua em verde, faixa e tipografia."""
    fig=plt.figure(figsize=(8.27,11.69),dpi=180); ax=fig.add_axes([0,0,1,1]); ax.axis("off")
    ax.add_patch(plt.Rectangle((0,0),1,1,color="#191528"))
    # marca d'agua: emblema grande, baixa opacidade, no canto inferior direito
    try:
        import matplotlib.image as mpimg
        em=mpimg.imread(os.path.join(ASSETS,"emblema_white.png"))
        axw=fig.add_axes([0.42,-0.06,0.72,0.52]); axw.imshow(em,alpha=0.06); axw.axis("off")
    except Exception: pass
    # faixa verde fina vertical a esquerda
    ax.add_patch(plt.Rectangle((0.0,0.0),0.018,1,color="#A9DB21"))
    # emblema no topo
    try:
        em2=mpimg.imread(os.path.join(ASSETS,"emblema_lime.png"))
        axe=fig.add_axes([0.10,0.80,0.13,0.13]); axe.imshow(em2); axe.axis("off")
    except Exception: pass
    ax.text(0.235,0.845,"Grid Co.",fontproperties=fp(FB,26),color="#FFFFFF",transform=ax.transAxes)
    ax.text(0.235,0.815,"Operação & Manutenção",fontproperties=fp(FR,11),color="#A9DB21",transform=ax.transAxes)
    # bloco central
    ax.text(0.10,0.50,tipo.upper(),fontproperties=fp(FR,15),color="#8A8794",transform=ax.transAxes)
    ax.text(0.10,0.40,"Relatório de",fontproperties=fp(FR,30),color="#FFFFFF",transform=ax.transAxes)
    ax.text(0.10,0.325,"Manutenção",fontproperties=fp(FB,46),color="#A9DB21",transform=ax.transAxes)
    ax.add_patch(plt.Rectangle((0.105,0.30),0.20,0.006,color="#A9DB21",transform=ax.transAxes))
    # cliente / usina e competencia
    ax.text(0.10,0.20,(sub_cliente or "").upper(),fontproperties=fp(FR,11),color="#8A8794",transform=ax.transAxes)
    ax.text(0.10,0.15,nome,fontproperties=fp(FB,24),color="#FFFFFF",transform=ax.transAxes)
    ax.text(0.10,0.105,competencia,fontproperties=fp(FS,16),color="#A9DB21",transform=ax.transAxes)
    ax.text(0.10,0.045,dt.date.today().strftime("Emitido em %d/%m/%Y"),fontproperties=fp(FR,9),color="#8A8794",transform=ax.transAxes)
    p=os.path.join(CHARTS,fn); fig.savefig(p,dpi=180); plt.close(fig); return p

# ----------------------------------------------------------------- DOCX helpers
def shade(c,h):
    s=OxmlElement("w:shd"); s.set(qn("w:val"),"clear"); s.set(qn("w:fill"),h); c._tc.get_or_add_tcPr().append(s)
def no_borders(t):
    b=OxmlElement("w:tblBorders")
    for e in ("top","left","bottom","right","insideH","insideV"):
        el=OxmlElement(f"w:{e}"); el.set(qn("w:val"),"none"); b.append(el)
    t._tbl.tblPr.append(b)
def cmarg(c,t=70,b=70,l=110,r=110):
    m=OxmlElement("w:tcMar")
    for k,v in (("top",t),("bottom",b),("start",l),("end",r)):
        e=OxmlElement(f"w:{k}"); e.set(qn("w:w"),str(v)); e.set(qn("w:type"),"dxa"); m.append(e)
    c._tc.get_or_add_tcPr().append(m)
def H(doc,txt,lvl=1):
    p=doc.add_paragraph()
    if lvl==1:
        b=p.add_run("▎ "); b.font.color.rgb=hx(LIME); b.font.size=Pt(15)
    r=p.add_run(txt); r.font.name="Poppins"; r.font.bold=True; r.font.size=Pt(14 if lvl==1 else 11.5); r.font.color.rgb=hx(NAVY)
    p.paragraph_format.space_before=Pt(12); p.paragraph_format.space_after=Pt(5); return p
def body(doc,txt,size=10.5,color=INK):
    p=doc.add_paragraph(); r=p.add_run(txt); r.font.name="Calibri"; r.font.size=Pt(size); r.font.color.rgb=hx(color)
    p.paragraph_format.space_after=Pt(6); p.paragraph_format.line_spacing=1.25; return p
def callout(doc,txt):
    t=doc.add_table(rows=1,cols=1); no_borders(t); c=t.cell(0,0); shade(c,LIGHT); cmarg(c,150,150,180,180)
    p=c.paragraphs[0]; b=p.add_run("► "); b.font.color.rgb=hx(LIME); b.font.bold=True; b.font.size=Pt(11)
    r=p.add_run(txt); r.font.size=Pt(11); r.font.bold=True; r.font.color.rgb=hx(NAVY); r.font.name="Poppins"; doc.add_paragraph()
def add_img(doc,path,w):
    if path and os.path.exists(path): doc.add_picture(path,width=Inches(w)); doc.paragraphs[-1].alignment=WD_ALIGN_PARAGRAPH.CENTER
def footer(sec):
    f=sec.footer; f.is_linked_to_previous=False; p=f.paragraphs[0]; p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.add_run("Grid Co.  ·  Operação & Manutenção  ·  Documento confidencial"); r.font.name="Poppins"; r.font.size=Pt(7.5); r.font.color.rgb=hx(MID)
def _pbottom(p,color=LIME,sz=10):
    pPr=p._p.get_or_add_pPr(); b=OxmlElement("w:pBdr"); e=OxmlElement("w:bottom")
    e.set(qn("w:val"),"single"); e.set(qn("w:sz"),str(sz)); e.set(qn("w:space"),"6"); e.set(qn("w:color"),color); b.append(e); pPr.append(b)
def _cell_bottom(cell,color=LIME,sz=18):
    tcPr=cell._tc.get_or_add_tcPr(); b=tcPr.find(qn("w:tcBorders"))
    if b is None: b=OxmlElement("w:tcBorders"); tcPr.append(b)
    e=OxmlElement("w:bottom"); e.set(qn("w:val"),"single"); e.set(qn("w:sz"),str(sz)); e.set(qn("w:space"),"0"); e.set(qn("w:color"),color); b.append(e)
def aplicar_estilo_tabelas(doc):
    """Identidade visual: cabeçalho navy centralizado, zebra, 1ª coluna à esquerda e demais centralizadas."""
    for t in doc.tables:
        try: nome=t.style.name
        except Exception: nome=None
        if nome!="Table Grid": continue
        for i,row in enumerate(t.rows):
            is_total=(row.cells[0].text.strip().upper()=="TOTAL")
            for j,cell in enumerate(row.cells):
                for p in cell.paragraphs:
                    p.alignment=WD_ALIGN_PARAGRAPH.CENTER if (i==0 or j>0) else WD_ALIGN_PARAGRAPH.LEFT
                if i>0:
                    shade(cell,("DDE7C8" if is_total else ("F2F3F5" if i%2==0 else "FFFFFF")))
def header_setup(section,titulo,data_dir,width_in=6.5):
    h=section.header; h.is_linked_to_previous=False
    p0=h.paragraphs[0]; p0.text=""; p0.paragraph_format.space_after=Pt(0); 
    for r in p0.runs: r.font.size=Pt(1)
    t=h.add_table(rows=1,cols=3,width=Inches(width_in)); t.alignment=WD_TABLE_ALIGNMENT.CENTER; no_borders(t)
    t._tbl.getparent().remove(t._tbl); p0._p.addprevious(t._tbl)
    L,M,R=t.rows[0].cells
    L.width=Inches(width_in*0.33); M.width=Inches(width_in*0.40); R.width=Inches(width_in*0.27)
    run=L.paragraphs[0].add_run(); logo=os.path.join(ASSETS,"logo_navy.png")
    if os.path.exists(logo):
        try: run.add_picture(logo,height=Inches(0.22))
        except Exception: pass
    L.paragraphs[0].alignment=WD_ALIGN_PARAGRAPH.LEFT
    pm=M.paragraphs[0]; pm.alignment=WD_ALIGN_PARAGRAPH.CENTER
    rm=pm.add_run(titulo); rm.font.name="Poppins"; rm.font.bold=True; rm.font.size=Pt(11); rm.font.color.rgb=hx(NAVY)
    pr=R.paragraphs[0]; pr.alignment=WD_ALIGN_PARAGRAPH.RIGHT
    rr=pr.add_run(data_dir); rr.font.name="Poppins"; rr.font.size=Pt(9); rr.font.color.rgb=hx(MID)
    for c in (L,M,R): _cell_bottom(c,LIME,20); cmarg(c,30,90,40,40); c.vertical_alignment=1
def th_row(t,labels):
    for j,h in enumerate(labels):
        c=t.rows[0].cells[j]; shade(c,NAVY); r=c.paragraphs[0].add_run(h); r.font.color.rgb=hx(WHITE); r.font.bold=True; r.font.size=Pt(8.5); r.font.name="Poppins"
def td(c,txt,size=8.5,bold=False,color=INK):
    r=c.paragraphs[0].add_run(str(txt)); r.font.size=Pt(size); r.font.bold=bold; r.font.color.rgb=hx(color)
def bullet(doc,txt,cor=LIME,size=10):
    p=doc.add_paragraph(); p.paragraph_format.left_indent=Inches(0.12)
    b=p.add_run("● "); b.font.color.rgb=hx(cor); b.font.size=Pt(9)
    r=p.add_run(txt); r.font.size=Pt(size); r.font.color.rgb=hx(INK); p.paragraph_format.space_after=Pt(2)

ST_G="6FA800"; ST_Y="D99A00"; ST_R="C0392B"
def status_abertas(n,total):
    if total<=0: return ("Neutro","504C63")
    if n==0: return ("Bom",ST_G)
    p=100*n/total
    if p<=5: return ("Neutro","504C63")
    if p<=10: return ("Atenção",ST_Y)
    return ("Crítico",ST_R)
def status_av(val,g,y,hib=True):
    if hib:
        if val>=g: return ("Bom",ST_G)
        if val>=y: return ("Atenção",ST_Y)
        return ("Crítico",ST_R)
    else:
        if val<=g: return ("Bom",ST_G)
        if val<=y: return ("Atenção",ST_Y)
        return ("Crítico",ST_R)
def tile(cell,valor,rotulo,statuslabel,corhex):
    shade(cell,corhex); cmarg(cell,140,140,150,150); cell.vertical_alignment=1
    p=cell.paragraphs[0]; r=p.add_run(valor); r.font.size=Pt(22); r.font.bold=True; r.font.color.rgb=hx(WHITE); r.font.name="Poppins"
    p2=cell.add_paragraph(); r2=p2.add_run(rotulo); r2.font.size=Pt(8.5); r2.font.color.rgb=hx(WHITE); r2.font.name="Poppins"
    p3=cell.add_paragraph(); r3=p3.add_run("● "+statuslabel); r3.font.size=Pt(8); r3.font.bold=True; r3.font.color.rgb=hx(WHITE); r3.font.name="Poppins"
    p2.paragraph_format.space_before=Pt(1); p3.paragraph_format.space_before=Pt(1)

HORAS_MES_PESSOA=44*52/12.0   # 44 h/semana -> ~190.7 h/mês por pessoa (capacidade HH)
def agrupa(conc,keyfn,resp_cap=None):
    g=defaultdict(lambda: dict(n=0,prev=0,corr=0,emerg=0,crit_alta=0,hh=0.0,resp=set()))
    for x in conc:
        kk=keyfn(x) or "—"; d=g[kk]; d["n"]+=1; d["hh"]+=x["tot"]; d["prog_h"]=d.get("prog_h",0)+x["dur_est"]
        if x["resp"] and x["resp"]!="—": d["resp"].add(x["resp"])
        if x["categoria"]=="Preventiva": d["prev"]+=1
        elif x["categoria"]=="Corretiva":
            d["corr"]+=1
            if x["tipo"]=="Corretiva Emergencial": d["emerg"]+=1
            if str(x["crit"]).strip().lower() in ("alto","muito alto","alta","muito alta"): d["crit_alta"]+=1
    for d in g.values():
        base=d["prev"]+d["corr"]; d["pct_prev"]=100*d["prev"]/base if base else 0
        d["nexec"]=len(d["resp"]); cap=sum(resp_cap.get(r,0) for r in d["resp"]) if resp_cap else 0
        d["util"]=100*d["hh"]/cap if cap else 0
    return g
def mp_por_grupo(regs,ini,fim,keyfn):
    g=defaultdict(lambda: dict(plan=0,fin=0))
    for x in regs:
        if x["mp"] and mp_apos_mob(x) and mp_ref(x) and ini<=mp_ref(x)<fim:
            kk=keyfn(x) or "—"; g[kk]["plan"]+=1
            if FINALIZADO(x): g[kk]["fin"]+=1
    for d in g.values(): d["pct"]=100*d["fin"]/d["plan"] if d["plan"] else 0
    return g
def outliers(conc):
    """Tarefas com tempo de execução muito acima da média (> média + 2 desvios)."""
    durs=[x["dur"] for x in conc if x["dur"]>0]
    if len(durs)<5: return [],0,0
    m=sum(durs)/len(durs); var=sum((d-m)**2 for d in durs)/len(durs); sd=var**0.5
    lim=m+2*sd
    out=[x for x in conc if x["dur"]>lim]
    return sorted(out,key=lambda x:-x["dur"]), m, lim
def horas_prog_exec(conc):
    prog=sum(x["dur_est"] for x in conc); exe=sum(x["tot"] for x in conc)
    return prog,exe
def os_de_solicitacao(conc):
    return [x for x in conc if str(x.get("numsol") or "").strip() not in ("","None")]
def top_corretivas_detalhe(conc,topn=3,maxos=6):
    cnt=Counter(x["ativo"] for x in conc if x["categoria"]=="Corretiva")
    out=[]
    for ativo,n in cnt.most_common(topn):
        oss=[x for x in conc if x["categoria"]=="Corretiva" and x["ativo"]==ativo]
        out.append((ativo,n,oss[:maxos]))
    return out
def acao_sugerida(ativo,n):
    a=sa(ativo).lower()
    if "inversor" in a: base="Inspeção termográfica e revisão de conexões/ventilação; abrir RCA junto ao fabricante."
    elif "tracker" in a: base="Verificar atuadores/sensores e calibração; revisar plano de lubrificação."
    elif "cabine" in a or "subesta" in a or "trafo" in a or "transform" in a: base="Análise de óleo/termografia em média tensão; checar proteções."
    elif "disjuntor" in a or "prote" in a: base="Testar ajustes de proteção e contatos; revisar coordenação."
    elif "segur" in a or "cftv" in a: base="Revisar alimentação/rede do sistema; substituir componentes recorrentes."
    else: base="Abrir análise de causa raiz (RCA) e revisar o plano de manutenção do ativo."
    if n>=4: base="PRIORIDADE ALTA — "+base
    return base

def metodologia(doc):
    doc.add_page_break(); H(doc,"Glossário dos Indicadores")
    body(doc,"Esta página explica, em linguagem direta, o que cada indicador do relatório representa e por que ele importa "
            "para a confiabilidade e a disponibilidade das usinas.")
    def item(tit,txt):
        p=doc.add_paragraph(); r=p.add_run(tit+": "); r.font.bold=True; r.font.size=Pt(10); r.font.color.rgb=hx(NAVY); r.font.name="Poppins"
        r2=p.add_run(txt); r2.font.size=Pt(10); r2.font.color.rgb=hx(INK); p.paragraph_format.space_after=Pt(4); p.paragraph_format.line_spacing=1.2
    H(doc,"Manutenção e Categorias",2)
    item("Manutenção preventiva","atividades planejadas para evitar falhas e preservar o desempenho dos ativos. Organizada por periodicidade (semanal, quinzenal, mensal, trimestral, semestral, anual e bianual).")
    item("Manutenção corretiva","intervenções para restabelecer um ativo após uma falha. Quanto menor a proporção de corretivas, mais madura e confiável é a operação.")
    item("Corretiva emergencial","corretiva de caráter urgente, indicando falha relevante que exigiu ação imediata.")
    item("Religamento","retorno de operação após eventos da rede elétrica (concessionária), em geral fora do controle da O&M.")
    H(doc,"Avanço das Preventivas",2)
    item("Avanço de preventivas (mês)","quanto do plano preventivo previsto para o mês foi efetivamente concluído.")
    item("Avanço de preventivas (12 meses)","cumprimento acumulado do plano preventivo ao longo do último ano, mostrando a consistência da execução. O cronograma de cada usina passa a valer a partir da sua mobilização.")
    item("Aderência ao cronograma","quanto das preventivas foi concluído dentro do prazo planejado.")
    H(doc,"Confiabilidade e Disponibilidade",2)
    item("MTTR (tempo médio de reparo)","tempo médio que a equipe leva para restabelecer um ativo após uma falha. Quanto menor, mais ágil a resposta.")
    item("MTBF (tempo médio entre falhas)","intervalo médio de operação entre falhas de um ativo. Quanto maior, mais confiável é o equipamento.")
    item("Disponibilidade inerente","indicador de confiabilidade que combina a frequência de falhas e a rapidez dos reparos, por tipologia de ativo.")
    item("Disponibilidade Grid","disponibilidade dos ativos considerando apenas o que está sob gestão da O&M, desconsiderando as perdas causadas por eventos da rede elétrica (religamentos).")
    item("Pareto e ativos recorrentes","destacam os poucos equipamentos que concentram a maior parte das corretivas, direcionando a análise de causa raiz para onde há maior ganho.")
    H(doc,"Produtividade",2)
    item("Tarefas programadas","parcela das atividades planejadas com antecedência. Uma maior programação reflete planejamento maduro e menor reatividade.")
    item("Hora-homem (utilização)","compara o esforço efetivamente aplicado pela equipe com a capacidade disponível no mês (considerando jornada e feriados), indicando sobrecarga ou folga.")
    item("Tarefas em aberto","atividades do mês ainda não concluídas; um volume baixo indica boa vazão do backlog.")

# ----------------------------------------------------------------- RELATORIO
def gerar(escopo_tipo,escopo_nome,cliente_pai,periodo,ref,idx,rows,aux,saida_base):
    ini,fim,rot,tipo=janela(periodo,ref)
    regs=coletar(escopo_tipo,escopo_nome,idx,rows,aux)
    regs_os=regs                                  # ANÁLISE POR TAREFA (sem dedup por OS)
    k=kpis_mes(regs_os,ini,fim); conc=k["conc"]; abert=k["abert"]
    hist=historico_mensal(regs_os,fim); clusters=por_cluster(conc); utab=por_usina_tab(conc)
    mpm=mp_mes(regs,ini,fim); m12=mp_12(regs,fim); mp12c,(_a12,_b12)=mp_12_por_code(regs,fim)   # preventivas (tarefa)
    tipos=confiab_tipologia(regs,fim); crit_list=crit_corretivas(conc)   # MTTR/MTBF: nível tarefa (fórmula de linha)
    ativos_conf=confiab_ativo(regs_os,ini,fim)
    n_usinas=len([u for u in k["usinas"] if u and u!="—"])
    cap_por_usina={x["ufv"]:(x.get("cap") or 0) for x in regs}
    cap=sum(cap_por_usina.values())
    tempos=tempos_atend(conc); ader=aderencia_prev(regs,ini,fim); bad=bad_actors(regs_os,fim)
    par_eq=pareto_equip(conc); gpar=g_pareto(par_eq,"pareto.png")
    tot_ct=sum(t["corr"] for t in tipos); disp_media=(sum(t["disp"]*t["corr"] for t in tipos)/tot_ct) if tot_ct else 0
    disp_grid=disponibilidade_grid(conc,ini,fim,max(1,n_usinas))

    sub="Cliente" if escopo_tipo=="cliente" else f"Cliente {cliente_pai}"
    capa=g_capa(escopo_nome,sub,rot,tipo,"capa.png")
    don=g_donut(k,"donut.png"); gca=g_categorias(k["por_categoria_os"],"categorias.png"); gprog=g_prog(k,"prog.png")
    gh=g_hist(hist,"hist.png"); gano=g_corr_ano(hist,"corr_ano.png"); gmp=g_mp12(m12,"mp12.png")
    hp=historico_prog(regs_os,fim); gpt=g_prog_temporal(hp,"prog_ano.png")
    _cl_ok=escopo_tipo=="cliente" and len([c for c in clusters if c and c!="—"])>=1
    gcl=g_cluster(clusters,"cluster.png") if _cl_ok else None
    gus=g_barh(k["usinas"],"usinas.png",title="Usinas com maior demanda") if escopo_tipo=="cliente" else None

    doc=Document(); st=doc.styles["Normal"]; st.font.name="Calibri"; st.font.size=Pt(10.5)
    sec=doc.sections[0]
    for m in ("top_margin","bottom_margin","left_margin","right_margin"): setattr(sec,m,Inches(0))
    doc.add_picture(capa,width=Inches(8.27))
    doc.add_section(); sec2=doc.sections[1]
    for m in ("top_margin","bottom_margin","left_margin","right_margin"): setattr(sec2,m,Inches(0.85))
    sec2.top_margin=Inches(0.95); footer(sec2)
    titulo_hdr=("Usina "+escopo_nome) if escopo_tipo=="usina" else ("Cliente "+escopo_nome)
    header_setup(sec2,titulo_hdr,rot,width_in=6.5)

    # (Scorecard Executivo removido a pedido do usuário — 2026-07-07)
    # ----- RESUMO EXECUTIVO (texto robusto, sem KPI cards)
    H(doc,"Resumo Executivo")
    pico=hist[-2]["total"] if len(hist)>=2 else 0; var=k["n"]-pico
    os_pico=hp[-2]["total"] if len(hp)>=2 else 0
    tend="alta" if var>0 else ("queda" if var<0 else "estabilidade")
    crit_alta=sum(v for n,v in crit_list if n in ("Muito alto","Alto"))
    top_ativo=k["corr_ativo"].most_common(1)[0] if k["corr_ativo"] else None
    callout(doc,f"Em {rot}, {('a usina '+escopo_nome) if escopo_tipo=='usina' else ('o cliente '+escopo_nome)} "
                f"registrou {k['n_os']} ordens de trabalho no mês ({k['n_os']-k['abert_os']} concluídas, {k['abert_os']} em aberto) — {k['nprev_os']} preventivas e {k['ncorr_os']} corretivas "
                f"({k['pct_prev_os']:.0f}% de preventiva) — com {k['abert_os']} tarefa(s) ainda em aberto no período.")
    cap_txt=f" ({fnum(cap,1)} MWp)" if cap and cap>0 else ""
    body(doc,f"O programa de manutenção {('da usina' if escopo_tipo=='usina' else 'do portfólio de '+str(n_usinas)+' usina(s)')}"
            f"{cap_txt} registrou {k['n_os']} ordens de trabalho no mês. "
            f"A relação preventiva×corretiva alcançou {k['pct_prev_os']:.0f}% de preventiva, "
            f"{('superior' if k['pct_prev_os']>=70 else 'aquém')} do patamar de referência de 70% para um regime confiável. "
            + (f"Em volume, houve {('alta' if k['n_os']-os_pico>0 else ('queda' if k['n_os']-os_pico<0 else 'estabilidade'))} frente ao mês anterior ({os_pico}). " if os_pico else "")
            + (f"As corretivas concentraram {crit_alta} ocorrência(s) de criticidade alta/muito alta. " if crit_alta else "")
            + (f"O ativo com maior incidência corretiva foi '{str(top_ativo[0])[:48]}'. " if top_ativo else ""))
    body(doc,f"Quanto à previsibilidade, {k['pct_prog_os']:.0f}% das tarefas concluídas foram PROGRAMADAS "
            f"(preventivas, preditivas e handover: {k['prog_os']}) e {100-k['pct_prog_os']:.0f}% NÃO programadas "
            f"({k['nprog_os']}). Uma maior parcela programada reflete planejamento maduro e menor reatividade da operação.")
    add_img(doc,gprog,5.6)
    tg=doc.add_table(rows=1,cols=2); no_borders(tg)
    c1,c2=tg.rows[0].cells; c1.width=Inches(2.7); c2.width=Inches(3.4)
    r=c1.paragraphs[0].add_run()
    if os.path.exists(don): r.add_picture(don,width=Inches(2.5))
    r2=c2.paragraphs[0].add_run()
    if os.path.exists(gca): r2.add_picture(gca,width=Inches(3.2))
    p=doc.add_paragraph(); rr=p.add_run("Relação preventiva × corretiva (esq.) e distribuição relativa por categoria (dir.)."); rr.font.size=Pt(8); rr.font.italic=True; rr.font.color.rgb=hx(MID); p.alignment=WD_ALIGN_PARAGRAPH.CENTER

    # ----- ANALISE CONSOLIDADA (ano vigente)
    doc.add_page_break(); H(doc,"Análise Consolidada")
    body(doc,f"A série de {hist[0]['rot']} a {hist[-1]['rot']} do ano vigente mostra a evolução da demanda de manutenção "
            "e da relação preventiva×corretiva. Uma parcela de preventiva acima de 70% indica um regime saudável; abaixo disso, "
            "recomenda-se reforço do plano preventivo para reduzir corretivas e perdas de geração.")
    add_img(doc,gh,6.4)
    H(doc,"Programadas × Não Programadas no Tempo",2)
    prog_ini=hp[0]["pct"] if hp else 0; prog_fim=hp[-1]["pct"] if hp else 0
    tendp=("evolução positiva" if prog_fim>prog_ini else ("retração" if prog_fim<prog_ini else "estabilidade"))
    body(doc,f"A previsibilidade da operação saiu de {prog_ini:.0f}% de tarefas programadas em {hp[0]['rot']} para "
            f"{prog_fim:.0f}% em {hp[-1]['rot']} — {tendp}. Quanto maior a parcela programada, menor a reatividade "
            "e a exposição a falhas não planejadas.")
    add_img(doc,gpt,6.4)
    if gcl: H(doc,"Comportamento por Cluster",2); body(doc,"Volume de OTs por cluster operacional, com o equilíbrio preventiva×corretiva por região."); add_img(doc,gcl,6.5)
    if gus: H(doc,"Usinas com Maior Demanda",2); add_img(doc,gus,6.3)
    if escopo_tipo=="cliente" and utab:
        doc.add_page_break(); H(doc,"Comparativo entre Usinas")
        body(doc,"Desempenho de manutenção por usina do portfólio no mês. % Prev. = preventiva ÷ (preventiva+corretiva); "
                "'Críticas' = corretivas de criticidade alta/muito alta. Usinas no topo concentram a demanda corretiva.")
        cols=["Usina","Tarefas","Prev.","Corr.","Emerg.","% Prev.","Críticas"]
        ut=doc.add_table(rows=1,cols=len(cols)); ut.style="Table Grid"; th_row(ut,cols)
        ranked=sorted(utab.items(),key=lambda kv:(kv[1]["corr"],kv[1]["n"]),reverse=True)
        for ufv,d in ranked:
            row=ut.add_row().cells
            td(row[0],str(ufv).split(" - ")[-1][:28]); td(row[1],d["n"]); td(row[2],d["prev"]); td(row[3],d["corr"])
            td(row[4],d["emerg"]); td(row[5],f"{d['pct_prev']:.0f}%"); td(row[6],d["crit_alta"])
        com=[r for r in ranked if (r[1]["prev"]+r[1]["corr"])>=3]
        if ranked:
            pior=ranked[0]
            melhor=max(com,key=lambda kv:kv[1]["pct_prev"]) if com else None
            pior_prev=min(com,key=lambda kv:kv[1]["pct_prev"]) if com else None
            bullet(doc,f"Maior demanda corretiva: {str(pior[0]).split(' - ')[-1]} ({pior[1]['corr']} corretivas).",cor=GRAY)
            if melhor: bullet(doc,f"Melhor índice de preventiva: {str(melhor[0]).split(' - ')[-1]} ({melhor[1]['pct_prev']:.0f}%).")
            if pior_prev and (not melhor or pior_prev[0]!=melhor[0]): bullet(doc,f"Menor índice de preventiva: {str(pior_prev[0]).split(' - ')[-1]} ({pior_prev[1]['pct_prev']:.0f}%) — priorizar plano preventivo.",cor=GRAY)

    # ----- MANUTENCOES PREVENTIVAS — dois informativos
    doc.add_page_break(); H(doc,"Manutenções Preventivas")
    body(doc,"O plano preventivo é organizado por periodicidade: MPW (semanal), MPQ (quinzenal), MPM (mensal), "
            "MPT (trimestral), MPS (semestral), MPA (anual) e MPB (bianual) a depender do escopo do cliente.")
    # INFORMATIVO 1 — mês de competência
    H(doc,f"1. Realizado no Mês — {rot}",2)
    body(doc,"Tarefas preventivas programadas para o mês de competência e quantas foram finalizadas, por periodicidade.")
    codes_m=[c for c in MP_ORDER if mpm[c]["plan"]>0]
    cols=["Periodicidade","Programadas","Finalizadas","Pendentes","% Avanço"]
    tt=doc.add_table(rows=1,cols=len(cols)); tt.style="Table Grid"; th_row(tt,cols)
    for code in codes_m+["TOTAL"]:
        d=mpm[code]; row=tt.add_row().cells
        td(row[0],(MP_LABEL.get(code,code) if code!="TOTAL" else "TOTAL"),8.5,bold=(code=="TOTAL"))
        td(row[1],d["plan"]); td(row[2],d["fin"]); td(row[3],d["pend"]); td(row[4],f"{d['pct']:.0f}%",8.5,bold=(code=="TOTAL"))
    bullet(doc,f"Avanço geral no mês: {mpm['TOTAL']['pct']:.0f}% ({mpm['TOTAL']['fin']}/{mpm['TOTAL']['plan']} tarefas finalizadas).")
    bullet(doc,f"Aderência ao cronograma: {ader['pct_prazo']:.0f}% das finalizadas concluídas até a data programada ({ader['no_prazo']}/{ader['fin']}).")
    pend=[(code,x) for code in MP_ORDER for x in mpm[code]["pendentes"][:6]]
    if pend:
        body(doc,"Preventivas programadas no mês ainda pendentes:")
        cols=["Tipo","Usina","Tarefa","Programada","Status"]
        pt=doc.add_table(rows=1,cols=len(cols)); pt.style="Table Grid"; th_row(pt,cols)
        for code,x in pend[:12]:
            row=pt.add_row().cells
            td(row[0],code); td(row[1],str(x["ufv"]).split(" - ")[-1][:24]); td(row[2],str(x["tarefa"])[:38]); td(row[3],fdate(x["dprog"])); td(row[4],x["estado"] or x["status"])
    # INFORMATIVO 2 — consolidado 12 meses
    H(doc,"2. Consolidado dos Últimos 12 Meses",2)
    body(doc,f"Cumprimento do plano preventivo no período de {_a12.strftime('%m/%Y')} a {(_b12 - dt.timedelta(days=1)).strftime('%m/%Y')}, "
            "por periodicidade.")
    codes_c=[c for c in MP_ORDER if mp12c[c]["plan"]>0]
    cols=["Periodicidade","Programadas","Finalizadas","Pendentes","% Avanço"]
    ct=doc.add_table(rows=1,cols=len(cols)); ct.style="Table Grid"; th_row(ct,cols)
    for code in codes_c+["TOTAL"]:
        d=mp12c[code]; row=ct.add_row().cells
        td(row[0],(MP_LABEL.get(code,code) if code!="TOTAL" else "TOTAL"),8.5,bold=(code=="TOTAL"))
        td(row[1],d["plan"]); td(row[2],d["fin"]); td(row[3],d["pend"]); td(row[4],f"{d['pct']:.0f}%",8.5,bold=(code=="TOTAL"))
    bullet(doc,f"Cumprimento acumulado em 12 meses: {mp12c['TOTAL']['pct']:.0f}% ({mp12c['TOTAL']['fin']}/{mp12c['TOTAL']['plan']}).")
    # (Gráfico "Cumprimento de preventivas — 12 meses" removido a pedido — 2026-07-07)

    # ----- CONFIABILIDADE DOS ATIVOS
    doc.add_page_break(); H(doc,"Confiabilidade dos Ativos")
    mes_corr=hist[-1]["corr"] if hist else 0; media_corr=(sum(h["corr"] for h in hist)/len(hist)) if hist else 0
    body(doc,f"Foram {mes_corr} corretiva(s) concluída(s) no mês, "
            + (f"abaixo da média do ano ({media_corr:.0f}/mês) — tendência de melhora. " if mes_corr<media_corr else
               (f"acima da média do ano ({media_corr:.0f}/mês) — requer atenção. " if mes_corr>media_corr else f"em linha com a média ({media_corr:.0f}/mês). "))
            + "Abaixo, indicadores de confiabilidade por tipologia de ativo e o ranking dos ativos mais demandados.")
    add_img(doc,gano,6.5)
    if tipos:
        H(doc,"MTTR, MTBF e Disponibilidade por Tipologia de Ativo",2)
        body(doc,"MTBF e MTTR desde a mobilização (base 20/10/2025), considerando tempo de operação de ~12 h/dia de geração da UFV. "
                "MTTR pondera reparos longos; MTBF = tempo de operação ÷ nº de corretivas; Disponibilidade Inerente = MTBF ÷ (MTBF + MTTR).",9.5)
        cols=["Tipologia de Ativo","Corretivas","MTTR (h)","MTBF (h)","Disponib. (%)"]
        tt=doc.add_table(rows=1,cols=len(cols)); tt.style="Table Grid"; th_row(tt,cols)
        for t in tipos:
            row=tt.add_row().cells
            td(row[0],t["tip"]); td(row[1],t["corr"]); td(row[2],f"{t['mttr']:.1f}"); td(row[3],f"{fnum(t['mtbf'],0)}"); td(row[4],f"{t['disp']:.1f}%")
        pm=max(tipos,key=lambda t:t["mttr"]); pf=tipos[0]
        bullet(doc,f"'{pf['tip']}' lidera em corretivas ({pf['corr']}); '{pm['tip']}' tem o maior MTTR ({pm['mttr']:.1f} h) — foco em sobressalentes e capacitação para reduzir o tempo de reparo.")
    # (Tabela "Corretivas por Criticidade" removida a pedido do usuário — 2026-07-07)
    # ranking de ativos
    linhas=sorted(ativos_conf,key=lambda d:(d["corr"]),reverse=True); top=[d for d in linhas if d["corr"]>0][:12]
    if top:
        H(doc,"Ranking de Ativos por Corretivas",2)
        cols=["Ativo / Equipamento","Tipologia","Corretivas","Δ vs mês ant."]
        rt=doc.add_table(rows=1,cols=len(cols)); rt.style="Table Grid"; th_row(rt,cols)
        for d in top:
            row=rt.add_row().cells; td(row[0],str(d["ativo"])[:40]); td(row[1],tipologia_ativo(d["ativo"])); td(row[2],d["corr"])
            sym="▼" if d["delta"]<0 else ("▲" if d["delta"]>0 else "—"); td(row[3],f"{sym} {d['delta']:+d}" if d["delta"]!=0 else "—")
    melhorias=sorted([d for d in linhas if d["delta"]<0],key=lambda d:d["delta"])[:3]
    pioras=sorted([d for d in linhas if d["delta"]>0],key=lambda d:-d["delta"])[:3]
    zer=[d for d in linhas if d["prev"]>0 and d["corr"]==0]
    # Aprofundamento dos Top 3 ativos com mais corretivas
    top3=top_corretivas_detalhe(conc,3,6)
    if top3:
        H(doc,"Aprofundamento — Top 3 Ativos em Corretivas",2)
        body(doc,"Para os três ativos com maior incidência corretiva no mês, detalhamos as OS/tarefas associadas e a ação recomendada.")
        for ativo,n,oss in top3:
            p=doc.add_paragraph(); r=p.add_run(f"{str(ativo)[:60]}  —  {n} corretiva(s)  ·  {tipologia_ativo(ativo)}")
            r.font.bold=True; r.font.size=Pt(10); r.font.color.rgb=hx(NAVY); r.font.name="Poppins"; p.paragraph_format.space_before=Pt(6)
            cc=["Nº OS","Tarefa","Criticidade","Finalização","Exec (h)"]
            dt2=doc.add_table(rows=1,cols=len(cc)); dt2.style="Table Grid"; th_row(dt2,cc)
            for x in oss:
                row=dt2.add_row().cells; td(row[0],x["osid"],7.5); td(row[1],str(x["tarefa"])[:46],7.5); td(row[2],x["crit"],7.5)
                td(row[3],fdt(x["dfinos"]),7.5); td(row[4],f"{x['dur']:.1f}",7.5)
            bullet(doc,"Ação: "+acao_sugerida(ativo,n))
    # (Seção "Horas Programadas × Executadas" removida a pedido do usuário — 2026-07-07)
    # Pareto + Bad actors
    if gpar:
        H(doc,"Pareto de Falhas e Bad Actors",2)
        body(doc,"Poucos equipamentos concentram a maior parte das corretivas (princípio 80/20). Atacar os 'bad actors' traz o maior ganho de confiabilidade.",9.5)
        add_img(doc,gpar,6.5)
    if bad:
        H(doc,"Bad Actors (12 meses) — Reincidência",2)
        body(doc,"Ativos com corretivas recorrentes nos últimos 12 meses — prioridade de análise de causa raiz.",9.5)
        cols=["Ativo / Equipamento","Tipologia","Corretivas (12m)"]
        bt=doc.add_table(rows=1,cols=3); bt.style="Table Grid"; th_row(bt,cols)
        for a,n in bad.most_common(8):
            row=bt.add_row().cells; td(row[0],str(a)[:42]); td(row[1],tipologia_ativo(a)); td(row[2],n)
    # Log de outliers
    outs,media_o,lim_o=outliers(conc)
    if outs:
        H(doc,"Log de Outliers — Tarefas Muito Acima da Média",2)
        body(doc,f"Tarefas cujo tempo de execução excede a média ({media_o:.1f} h) em mais de 2 desvios-padrão (> {lim_o:.1f} h) — "
                "candidatas a verificação de apontamento ou de complexidade atípica.",9.5)
        cols=["Nº OS","Tarefa","Tipo","Usina","Finalização","Exec (h)"]
        ot=doc.add_table(rows=1,cols=len(cols)); ot.style="Table Grid"; th_row(ot,cols)
        for x in outs[:12]:
            row=ot.add_row().cells; td(row[0],x["osid"],7.5); td(row[1],str(x["tarefa"])[:36],7.5); td(row[2],x["tipo"],7.5)
            td(row[3],str(x["ufv"]).split(" - ")[-1][:18],7.5); td(row[4],fdt(x["dfinos"]),7.5); td(row[5],f"{x['dur']:.1f}",7.5)
    # Insights de confiabilidade
    H(doc,"Insights de Confiabilidade",2)
    ins=[]
    for d in melhorias: ins.append(("ok",f"↓ {str(d['ativo'])[:42]}: corretivas de {d['prev']} para {d['corr']} (−{abs(d['delta'])})."))
    if zer: ins.append(("ok",f"✓ {len(zer)} ativo(s) sem corretivas neste mês após registros no anterior — melhora consolidada."))
    for d in pioras: ins.append(("bad",f"↑ {str(d['ativo'])[:42]}: corretivas de {d['prev']} para {d['corr']} (+{d['delta']}) — candidato a RCA."))
    if not ins: ins.append(("ok","Sem variações relevantes de corretivas por ativo frente ao mês anterior."))
    for tipo_i,t in ins: bullet(doc,t,cor=(LIME if tipo_i=="ok" else GRAY))

    # ----- ANEXO (paisagem): resumo + tabelas por categoria
    doc.add_section(); secA=doc.sections[-1]
    secA.orientation=WD_ORIENT.LANDSCAPE; secA.page_width,secA.page_height=Inches(11.69),Inches(8.27)
    for m in ("top_margin","bottom_margin","left_margin","right_margin"): setattr(secA,m,Inches(0.6))
    secA.top_margin=Inches(0.8); footer(secA); header_setup(secA,titulo_hdr,rot,width_in=10.3)
    H(doc,"Anexo — Ordens de Serviço do Período")
    mes_t=[x for x in regs if no_mes(x,ini,fim)]
    conc_t=[x for x in mes_t if FINALIZADO(x) or x["dfim"]]
    abert_t=[x for x in mes_t if not (FINALIZADO(x) or x["dfim"])]
    conc=conc_t; abert=abert_t; universo=mes_t
    body(doc,f"Tabela resumo e detalhamento (nível tarefa) do mês: {len(conc_t)} tarefa(s) concluída(s) e {len(abert_t)} em aberto.",9.5)
    def _grp(x):
        c=x["categoria"]
        if c=="Preventiva": return "Preventivas"
        if c=="Corretiva": return "Corretivas"
        if c=="Religamento": return "Religamento"
        if c=="Religamento Remoto": return "Religamento Remoto"
        if c=="Administrativa": return "Administrativa"
        return "Outras"
    grupos=defaultdict(list)
    for x in universo: grupos[_grp(x)].append(x)
    # tabela resumo
    H(doc,"Resumo",2)
    cols=["Categoria","Concluídas","Em aberto","Total"]
    rs=doc.add_table(rows=1,cols=len(cols)); rs.style="Table Grid"; th_row(rs,cols)
    for gnome in ["Preventivas","Corretivas","Religamento","Religamento Remoto","Administrativa","Outras"]:
        lst=grupos.get(gnome,[])
        if not lst: continue
        cc=sum(1 for x in lst if x in conc); ab=len(lst)-cc
        row=rs.add_row().cells; td(row[0],gnome); td(row[1],cc); td(row[2],ab); td(row[3],len(lst))
    row=rs.add_row().cells; td(row[0],"TOTAL",8.5,bold=True); td(row[1],len(conc),8.5,bold=True); td(row[2],len(abert),8.5,bold=True); td(row[3],len(universo),8.5,bold=True)
    # tabelas detalhadas por categoria
    acols=["Nº OS","Data Prog.","Usina","Descrição da Tarefa","Equipamento","Início OS","Fim OS","Status","Exec (h)","Observação"]
    for gnome in ["Preventivas","Corretivas","Religamento","Religamento Remoto","Administrativa","Outras"]:
        lst=grupos.get(gnome,[])
        if not lst: continue
        H(doc,f"{gnome}  ({len(lst)} OS)",2)
        at=doc.add_table(rows=1,cols=len(acols)); at.style="Table Grid"; th_row(at,acols)
        for x in sorted(lst,key=lambda r:(str(r["ufv"]),r["dprog"] or dt.datetime.min)):
            row=at.add_row().cells
            td(row[0],x["osid"],7); td(row[1],fdate(x["dprog"]),7); td(row[2],str(x["ufv"]).split(" - ")[-1][:18],7)
            td(row[3],str(x["tarefa"])[:30],7); td(row[4],str(x["ativo"])[:22],7); td(row[5],fdt(x["dini"]),7)
            td(row[6],fdt(x["dfim"]),7); td(row[7],(x["estado"] or x["status"])[:14],7); td(row[8],f"{x['dur']:.1f}",7); td(row[9],str(x["obs"])[:26],7)

    safe=re.sub(r"[^0-9A-Za-zÀ-ÿ ]+","",escopo_nome).strip().replace(" ","_"); tag=re.sub(r"[^0-9A-Za-z]+","_",rot)
    sub_per={"mensal":"Mensal","semanal":"Semanal","semestral":"Semestral","anual":"Anual"}[periodo]
    base_cli=cliente_pai if escopo_tipo=="usina" else escopo_nome
    out_dir=os.path.join(saida_base,"Relatórios",base_cli,("Usinas/"+safe+"/"+sub_per if escopo_tipo=="usina" else sub_per))
    os.makedirs(out_dir,exist_ok=True)
    metodologia(doc); aplicar_estilo_tabelas(doc)
    out=os.path.join(out_dir,f"Relatorio_{safe}_{tag}.docx"); doc.save(out)
    return out,k

def gerar_portfolio(periodo,ref,idx,rows,aux,saida_base,clientes=None):
    """Relatório gerencial de TODO o portfólio Grid Co. (todos os clientes), sem anexo."""
    ini,fim,rot,tipo=janela(periodo,ref)
    regs=coletar("grid",None,idx,rows,aux)
    if clientes:
        _sel=set(clientes); regs=[x for x in regs if x["cli"] in _sel]
    k=kpis_mes(regs,ini,fim); conc=k["conc"]; universo=conc+k["abert"]
    hist=historico_mensal(regs,fim); hp=historico_prog(regs,fim)
    mpm=mp_mes(regs,ini,fim); m12=mp_12(regs,fim); mp12c,(_a12,_b12)=mp_12_por_code(regs,fim)
    tipos=confiab_tipologia(regs,fim)
    fer=get_feriados()
    # localização modal por executor (para HH disponível com feriados municipais/estaduais)
    _rl=defaultdict(Counter)
    for x in conc:
        if x["resp"] and x["resp"]!="—": _rl[x["resp"]][(x.get("uf"),x.get("muni"))]+=1
    resp_cap={r:hh_pessoa_mes(ini,fim,fer,loc[0][0][0],loc[0][0][1]) for r,loc in
              ((r,[c.most_common(1)]) for r,c in _rl.items())}
    hhp_med=(sum(resp_cap.values())/len(resp_cap)) if resp_cap else hh_pessoa_mes(ini,fim,fer)
    g_cli=agrupa(conc,lambda x:x["cli"],resp_cap); g_eq=agrupa(conc,lambda x:x["equipe"],resp_cap); g_usi=agrupa(conc,lambda x:x["ufv"],resp_cap)
    mp_cli=mp_por_grupo(regs,ini,fim,lambda x:x["cli"]); mp_eq=mp_por_grupo(regs,ini,fim,lambda x:x["equipe"])
    # usinas por cliente (para normalização)
    uxc=defaultdict(set)
    for x in regs:
        if x["cli"] and x["cli"]!="—": uxc[x["cli"]].add(x["ufv"])
    n_cli=len([c for c in g_cli if c and c!="—"]); n_usi=len([u for u in g_usi if u and u!="—"])
    hh_total=sum(d["hh"] for d in g_cli.values()); nexec=len(resp_cap)
    cap_total=sum(resp_cap.values()); util_total=100*hh_total/cap_total if cap_total else 0
    tot_ct=sum(t["corr"] for t in tipos); disp_media=(sum(t["disp"]*t["corr"] for t in tipos)/tot_ct) if tot_ct else 0
    disp_grid=disponibilidade_grid(conc,ini,fim,max(1,n_usi))
    # preventivas NÃO realizadas (discretização)
    prev_nao=[x for x in regs if x["mp"] and mp_apos_mob(x) and mp_ref(x) and ini<=mp_ref(x)<fim and not FINALIZADO(x)]
    pn_grp=Counter((x["mp"],x["cli"]) for x in prev_nao)
    # OS de solicitações
    sol=os_de_solicitacao(universo)
    # outliers / top3 / horas
    outs,media_o,lim_o=outliers(conc); top3=top_corretivas_detalhe(conc,3,6); prog_h,exe_h=horas_prog_exec(conc)

    capa=g_capa("Portfólio Grid Co.","VISÃO GERENCIAL — TODOS OS CLIENTES",rot,"Relatório Gerencial de Portfólio","capa.png")
    don=g_donut(k,"donut.png"); gca=g_categorias(k["por_categoria"],"categorias.png")
    gh=g_hist(hist,"hist.png"); gano=g_corr_ano(hist,"corr_ano.png"); gmp=g_mp12(m12,"mp12.png")
    gcli=g_grupos({c:v for c,v in g_cli.items() if c and c!="—"},"gcli.png","OTs por cliente (preventiva × corretiva)")
    geq=g_grupos({c:v for c,v in g_eq.items() if c and c!="—"},"geq.png","OS por equipe (preventiva × corretiva)")
    gusi=g_barh(k["usinas"],"gusi.png",title="Usinas com maior demanda",maxn=15)
    ghh=g_hh(g_cli,"ghh.png","Hora-homem por cliente (h · % utilização)")
    gheq=g_hh(g_eq,"gheq.png","Hora-homem por equipe (h · % utilização)")
    gpar=g_pareto(pareto_equip(conc),"pareto.png")

    doc=Document(); st=doc.styles["Normal"]; st.font.name="Calibri"; st.font.size=Pt(10.5)
    sec=doc.sections[0]
    for m in ("top_margin","bottom_margin","left_margin","right_margin"): setattr(sec,m,Inches(0))
    doc.add_picture(capa,width=Inches(8.27))
    doc.add_section(); sec2=doc.sections[1]
    for m in ("top_margin","bottom_margin","left_margin","right_margin"): setattr(sec2,m,Inches(0.85))
    sec2.top_margin=Inches(0.95); footer(sec2); header_setup(sec2,"Portfólio Grid Co.",rot,width_in=6.5)

    # SCORECARD
    H(doc,"Scorecard Executivo — Portfólio")
    body(doc,f"Visão gerencial de {rot} consolidando {n_cli} cliente(s) e {n_usi} usina(s). "
            "Os indicadores abaixo sintetizam o desempenho do portfólio, classificados por status (Bom / Atenção / Crítico) "
            "frente a patamares de referência de O&M.")
    st_prev=status_av(k["pct_prev"],70,50); st_av=status_av(mpm["TOTAL"]["pct"],90,75)
    st_prog=status_av(k["pct_prog"],60,40); st_emg=status_av(k["emerg"],0,3,hib=False)
    st_disp=status_av(disp_grid,98,95); st_util=status_av(util_total,85,60)
    tiles=[(f"{k['pct_prev']:.0f}%","Preventiva",st_prev),(f"{mpm['TOTAL']['pct']:.0f}%","Avanço Preventivas",st_av),
           (f"{k['pct_prog']:.0f}%","Programadas",st_prog),(str(k["emerg"]),"Emergenciais",st_emg),
           (f"{disp_grid:.1f}%","Disponib. Grid",st_disp),(f"{util_total:.0f}%","Utilização HH",st_util)]
    t=doc.add_table(rows=2,cols=3); t.alignment=WD_TABLE_ALIGNMENT.CENTER; no_borders(t)
    for i,(v,l,stt) in enumerate(tiles): tile(t.cell(i//3,i%3),v,l,stt[0],stt[1])
    doc.add_paragraph()
    body(doc,f"No mês foram concluídas {k['n']} tarefas ({k['nprev']} preventivas, {k['ncorr']} corretivas), com "
            f"{fnum(hh_total,0)} horas-homem por {nexec} executor(es) — utilização média de {util_total:.0f}% da capacidade "
            f"(~{fnum(hhp_med,0)} h/mês por pessoa: {HH_DIA:.1f} h/dia × dias úteis, descontados feriados). A distribuição "
            "preventiva × corretiva e por categoria são apresentadas a seguir.")
    tg=doc.add_table(rows=1,cols=2); no_borders(tg); c1,c2=tg.rows[0].cells; c1.width=Inches(2.5); c2.width=Inches(3.1)
    rr=c1.paragraphs[0].add_run()
    if os.path.exists(don): rr.add_picture(don,width=Inches(2.3))
    rr2=c2.paragraphs[0].add_run()
    if os.path.exists(gca): rr2.add_picture(gca,width=Inches(3.0))
    p=doc.add_paragraph(); rx=p.add_run("Cada indicador é classificado em Bom, Atenção ou Crítico frente a patamares de referência de O&M. "
        "As definições de cada indicador estão no glossário ao final do relatório.")
    rx.font.size=Pt(8); rx.font.italic=True; rx.font.color.rgb=hx(MID)

    # COMPARATIVO POR CLIENTE
    doc.add_page_break(); H(doc,"Comparativo por Cliente")
    body(doc,"Volume e composição de OTs por cliente no mês. A barra evidencia o equilíbrio entre preventiva e corretiva de cada cliente.")
    add_img(doc,gcli,6.5)
    body(doc,"Tabela detalhada por cliente, incluindo horas-homem apontadas e utilização da capacidade da equipe.")
    cols=["Cliente","Tarefas","Prev.","Corr.","Emerg.","% Prev.","Críticas","HH (h)","Util.%"]
    ct=doc.add_table(rows=1,cols=len(cols)); ct.style="Table Grid"; th_row(ct,cols)
    for cli,d in sorted(g_cli.items(),key=lambda kv:kv[1]["n"],reverse=True):
        if not cli or cli=="—": continue
        row=ct.add_row().cells
        td(row[0],cli); td(row[1],d["n"]); td(row[2],d["prev"]); td(row[3],d["corr"]); td(row[4],d["emerg"])
        td(row[5],f"{d['pct_prev']:.0f}%"); td(row[6],d["crit_alta"]); td(row[7],f"{fnum(d['hh'],0)}"); td(row[8],f"{d['util']:.0f}%")
    # Normalização (por usina) — comparação justa entre clientes de portes diferentes
    H(doc,"Comparação Normalizada (por usina)",2)
    body(doc,"Como os clientes têm portes diferentes, normalizamos os indicadores pelo nº de usinas, permitindo comparação justa "
            "da intensidade de manutenção e do esforço por usina.")
    cols=["Cliente","Usinas","OTs/usina","Corretivas/usina","HH/usina","% Prev."]
    nt=doc.add_table(rows=1,cols=len(cols)); nt.style="Table Grid"; th_row(nt,cols)
    for cli,d in sorted(g_cli.items(),key=lambda kv:(kv[1]["corr"]/max(1,len(uxc.get(kv[0],[])))),reverse=True):
        if not cli or cli=="—": continue
        nu=max(1,len(uxc.get(cli,[])))
        row=nt.add_row().cells
        td(row[0],cli); td(row[1],nu); td(row[2],f"{d['n']/nu:.1f}"); td(row[3],f"{d['corr']/nu:.1f}"); td(row[4],f"{fnum(d['hh']/nu,0)}"); td(row[5],f"{d['pct_prev']:.0f}%")
    rk=sorted([(c,v) for c,v in g_cli.items() if c and c!="—" and (v["prev"]+v["corr"])>=5],key=lambda kv:kv[1]["pct_prev"])
    if rk:
        bullet(doc,f"Maior maturidade preventiva: {rk[-1][0]} ({rk[-1][1]['pct_prev']:.0f}%).")
        bullet(doc,f"Menor maturidade preventiva: {rk[0][0]} ({rk[0][1]['pct_prev']:.0f}%) — foco de plano preventivo.",cor=GRAY)

    # ANALISE POR EQUIPE (Ativo Classificação 2)
    doc.add_page_break(); H(doc,"Análise por Equipe (Ativo Classificação 2)")
    body(doc,"Como as equipes de campo estão sendo utilizadas: volume de OS, horas-homem apontadas e utilização da capacidade, "
            "cumprimento das preventivas e carga de corretivas. Permite identificar equipes sobrecarregadas, ociosas ou com baixa aderência ao plano.")
    add_img(doc,geq,6.5)
    body(doc,"Detalhamento por equipe (ordenado por volume de OS):")
    cols=["Equipe","OS","Prev.","Corr.","% Prev.","Execut.","HH (h)","Util.%","Cumpr. MP"]
    et=doc.add_table(rows=1,cols=len(cols)); et.style="Table Grid"; th_row(et,cols)
    for eq,d in sorted(g_eq.items(),key=lambda kv:kv[1]["n"],reverse=True)[:18]:
        if not eq or eq=="—": continue
        mpe=mp_eq.get(eq,{"pct":0,"plan":0})
        row=et.add_row().cells
        td(row[0],eq[:16]); td(row[1],d["n"]); td(row[2],d["prev"]); td(row[3],d["corr"]); td(row[4],f"{d['pct_prev']:.0f}%")
        td(row[5],d["nexec"]); td(row[6],f"{fnum(d['hh'],0)}"); td(row[7],f"{d['util']:.0f}%"); td(row[8],(f"{mpe['pct']:.0f}%" if mpe['plan'] else "—"))
    eqs=[(e,v) for e,v in g_eq.items() if e and e!="—" and v["nexec"]]
    if eqs:
        sob=max(eqs,key=lambda kv:kv[1]["util"]); oci=min(eqs,key=lambda kv:kv[1]["util"])
        bullet(doc,f"Equipe mais carregada: {sob[0]} (utilização {sob[1]['util']:.0f}%).",cor=(GRAY if sob[1]['util']>100 else LIME))
        bullet(doc,f"Equipe com maior folga: {oci[0]} (utilização {oci[1]['util']:.0f}%) — capacidade para antecipar preventivas.")

    # COMPARATIVO POR USINA
    doc.add_page_break(); H(doc,"Comparativo por Usina")
    body(doc,"Usinas com maior demanda de manutenção no mês — base para priorização de recursos e atenção operacional.")
    add_img(doc,gusi,6.4)

    # MANUTENCOES PREVENTIVAS — dois informativos
    doc.add_page_break(); H(doc,"Manutenções Preventivas")
    body(doc,"Plano preventivo por periodicidade — MPW (semanal), MPQ (quinzenal), MPM (mensal), MPT (trimestral), "
            "MPS (semestral), MPA (anual) e MPB (bianual). A seguir, o realizado no mês e o consolidado de 12 meses.")
    H(doc,f"1. Realizado no Mês — {rot}",2)
    body(doc,"Tarefas preventivas programadas para o mês e quantas foram finalizadas, por periodicidade.")
    codes_m=[c for c in MP_ORDER if mpm[c]["plan"]>0]
    cols=["Periodicidade","Programadas","Finalizadas","Pendentes","% Avanço"]
    tt=doc.add_table(rows=1,cols=len(cols)); tt.style="Table Grid"; th_row(tt,cols)
    for code in codes_m+["TOTAL"]:
        d=mpm[code]; row=tt.add_row().cells
        td(row[0],(MP_LABEL.get(code,code) if code!="TOTAL" else "TOTAL"),8.5,bold=(code=="TOTAL"))
        td(row[1],d["plan"]); td(row[2],d["fin"]); td(row[3],d["pend"]); td(row[4],f"{d['pct']:.0f}%",8.5,bold=(code=="TOTAL"))
    H(doc,"Avanço por Cliente",2)
    body(doc,"Cumprimento do plano preventivo por cliente no mês.")
    cols=["Cliente","Programadas","Finalizadas","% Avanço"]
    at=doc.add_table(rows=1,cols=len(cols)); at.style="Table Grid"; th_row(at,cols)
    for cli,d in sorted(mp_cli.items(),key=lambda kv:kv[1]["plan"],reverse=True):
        if not cli or cli=="—": continue
        row=at.add_row().cells; td(row[0],cli); td(row[1],d["plan"]); td(row[2],d["fin"]); td(row[3],f"{d['pct']:.0f}%")
    # discretização das NÃO realizadas
    H(doc,"Preventivas Não Realizadas — Discretização",2)
    body(doc,f"Das preventivas programadas para {rot}, {len(prev_nao)} não foram concluídas. Abaixo, a discretização por periodicidade e cliente.")
    if pn_grp:
        cols=["Periodicidade","Cliente","Pendentes"]
        pnt=doc.add_table(rows=1,cols=3); pnt.style="Table Grid"; th_row(pnt,cols)
        for (mpc,cli),n in sorted(pn_grp.items(),key=lambda kv:-kv[1]):
            row=pnt.add_row().cells; td(row[0],mpc); td(row[1],cli); td(row[2],n)
    else:
        bullet(doc,"Todas as preventivas programadas no mês foram concluídas.")
    H(doc,"2. Consolidado dos Últimos 12 Meses",2)
    body(doc,f"Cumprimento do plano preventivo de {_a12.strftime('%m/%Y')} a {(_b12 - dt.timedelta(days=1)).strftime('%m/%Y')}, "
            "por periodicidade (tabela) e a evolução mensal/acumulada (gráfico).")
    codes_c=[c for c in MP_ORDER if mp12c[c]["plan"]>0]
    cols=["Periodicidade","Programadas","Finalizadas","Pendentes","% Avanço"]
    c12=doc.add_table(rows=1,cols=len(cols)); c12.style="Table Grid"; th_row(c12,cols)
    for code in codes_c+["TOTAL"]:
        d=mp12c[code]; row=c12.add_row().cells
        td(row[0],(MP_LABEL.get(code,code) if code!="TOTAL" else "TOTAL"),8.5,bold=(code=="TOTAL"))
        td(row[1],d["plan"]); td(row[2],d["fin"]); td(row[3],d["pend"]); td(row[4],f"{d['pct']:.0f}%",8.5,bold=(code=="TOTAL"))
    bullet(doc,f"Cumprimento acumulado em 12 meses: {mp12c['TOTAL']['pct']:.0f}% ({mp12c['TOTAL']['fin']}/{mp12c['TOTAL']['plan']}).")
    add_img(doc,gmp,6.5)

    # HORA-HOMEM
    doc.add_page_break(); H(doc,"Hora-Homem — Utilização")
    body(doc,f"Hora-homem apontada no mês frente à capacidade da equipe. Capacidade por pessoa = {HH_DIA:.1f} h/dia "
            f"(turno 07:00–17:00, almoço 12:00–13:12) × dias úteis descontando feriados nacionais/estaduais/municipais ≈ {fnum(hhp_med,0)} h/mês (média). "
            f"Total: {fnum(hh_total,0)} h por {nexec} executor(es) — utilização média {util_total:.0f}%. "
            "Utilização acima de 100% (em vermelho) indica sobrecarga/horas extras; muito abaixo, capacidade ociosa.")
    add_img(doc,ghh,6.5)
    body(doc,"Mesma leitura, agora por equipe de campo:")
    add_img(doc,gheq,6.5)

    # CONFIABILIDADE
    doc.add_page_break(); H(doc,"Confiabilidade do Portfólio")
    body(doc,f"No mês houve {k['ncorr']} corretiva(s). A série abaixo mostra a evolução das corretivas no ano vigente.")
    add_img(doc,gano,6.4)
    if tipos:
        H(doc,"MTTR, MTBF e Disponibilidade por Tipologia",2)
        body(doc,f"Indicadores de confiabilidade por tipologia de ativo (tempo de operação ~{HORAS_GERACAO_DIA:.0f} h/dia de geração; "
                "MTBF desde a mobilização; Disponibilidade Inerente = MTBF ÷ (MTBF+MTTR)).")
        cols=["Tipologia de Ativo","Corretivas","MTTR (h)","MTBF (h)","Disponib. (%)"]
        tt=doc.add_table(rows=1,cols=len(cols)); tt.style="Table Grid"; th_row(tt,cols)
        for tp in tipos:
            row=tt.add_row().cells; td(row[0],tp["tip"]); td(row[1],tp["corr"]); td(row[2],f"{tp['mttr']:.1f}"); td(row[3],f"{fnum(tp['mtbf'],0)}"); td(row[4],f"{tp['disp']:.1f}%")
    if gpar:
        H(doc,"Pareto de Falhas (80/20)",2)
        body(doc,"Concentração das corretivas por equipamento — poucos ativos respondem pela maioria das falhas.")
        add_img(doc,gpar,6.5)
    # Top 3 deep dive
    if top3:
        H(doc,"Aprofundamento — Top 3 Ativos em Corretivas",2)
        body(doc,"Para os três ativos com maior incidência corretiva no portfólio, detalhamos as OS/tarefas e a ação recomendada.")
        for ativo,n,oss in top3:
            p=doc.add_paragraph(); r=p.add_run(f"{str(ativo)[:60]}  —  {n} corretiva(s)  ·  {tipologia_ativo(ativo)}")
            r.font.bold=True; r.font.size=Pt(10); r.font.color.rgb=hx(NAVY); r.font.name="Poppins"; p.paragraph_format.space_before=Pt(6)
            cc=["Nº OS","Tarefa","Usina","Criticidade","Exec (h)"]
            dt2=doc.add_table(rows=1,cols=len(cc)); dt2.style="Table Grid"; th_row(dt2,cc)
            for x in oss:
                row=dt2.add_row().cells; td(row[0],x["osid"],7.5); td(row[1],str(x["tarefa"])[:38],7.5); td(row[2],str(x["ufv"]).split(" - ")[-1][:18],7.5); td(row[3],x["crit"],7.5); td(row[4],f"{x['dur']:.1f}",7.5)
            bullet(doc,"Ação: "+acao_sugerida(ativo,n))
    # Outliers
    if outs:
        H(doc,"Log de Outliers — Tarefas Muito Acima da Média",2)
        body(doc,f"Tarefas com tempo de execução acima de {lim_o:.1f} h (média {media_o:.1f} h + 2 desvios) — verificar apontamento ou complexidade atípica.")
        cols=["Nº OS","Tarefa","Tipo","Cliente","Usina","Exec (h)"]
        ot=doc.add_table(rows=1,cols=len(cols)); ot.style="Table Grid"; th_row(ot,cols)
        for x in outs[:15]:
            row=ot.add_row().cells; td(row[0],x["osid"],7.5); td(row[1],str(x["tarefa"])[:30],7.5); td(row[2],x["tipo"],7.5); td(row[3],str(x["cli"]),7.5); td(row[4],str(x["ufv"]).split(" - ")[-1][:16],7.5); td(row[5],f"{x['dur']:.1f}",7.5)

    # HORAS PROGRAMADAS x EXECUTADAS + SOLICITACOES + CONCLUSOES
    doc.add_page_break(); H(doc,"Horas Programadas × Executadas")
    difp=(100*(exe_h-prog_h)/prog_h) if prog_h else 0
    body(doc,"Comparação entre o esforço previsto (duração estimada das tarefas) e o efetivamente apontado no portfólio — aderência do planejamento de mão de obra.")
    cols=["Indicador","Horas"]
    hpx=doc.add_table(rows=1,cols=2); hpx.style="Table Grid"; th_row(hpx,cols)
    for nome,val in [("Horas programadas (estimadas)",prog_h),("Horas executadas (apontadas)",exe_h),("Desvio (exec − prog)",exe_h-prog_h)]:
        row=hpx.add_row().cells; td(row[0],nome); td(row[1],f"{fnum(val,1)} h")
    bullet(doc,f"Execução {('acima' if difp>0 else 'abaixo')} do programado em {abs(difp):.0f}% no portfólio.")
    H(doc,"OS Originadas de Solicitações de Serviço",2)
    body(doc,f"No mês, {len(sol)} OS foram geradas a partir de solicitações de serviço (campo Número de Solicitação). "
            "A tabela lista as solicitações atendidas/abertas no período.")
    if sol:
        cols=["Nº Solicitação","Nº OS","Cliente","Usina","Tarefa","Status"]
        st=doc.add_table(rows=1,cols=len(cols)); st.style="Table Grid"; th_row(st,cols)
        for x in sorted(sol,key=lambda r:str(r.get("numsol")))[:30]:
            row=st.add_row().cells; td(row[0],str(x.get("numsol")).replace(".0",""),7.5); td(row[1],x["osid"],7.5); td(row[2],str(x["cli"]),7.5)
            td(row[3],str(x["ufv"]).split(" - ")[-1][:18],7.5); td(row[4],str(x["tarefa"])[:30],7.5); td(row[5],(x["estado"] or x["status"])[:14],7.5)
        if len(sol)>30: bullet(doc,f"Exibindo 30 de {len(sol)} solicitações.")
    H(doc,"Conclusões e Recomendações",2)
    recs=[]
    if k["pct_prev"]<70: recs.append("Reforçar plano preventivo nos clientes/usinas com menor % preventiva.")
    if mpm["TOTAL"]["pend"]>0: recs.append(f"Recuperar {mpm['TOTAL']['pend']} preventiva(s) pendente(s) do plano.")
    if util_total>100: recs.append("Avaliar dimensionamento — utilização de HH acima da capacidade (sobrecarga).")
    elif util_total<60: recs.append("Capacidade ociosa de HH — oportunidade de antecipar preventivas.")
    if k["emerg"]>0: recs.append(f"Tratar {k['emerg']} corretiva(s) emergencial(is) com RCA.")
    if top3: recs.append(f"Priorizar RCA no ativo '{str(top3[0][0])[:40]}' ({top3[0][1]} corretivas).")
    recs.append("Padronizar termografia/inspeções entre equipes para detecção precoce.")
    for r in recs: bullet(doc,r)

    out_dir=os.path.join(saida_base,"Relatórios","_Portfólio Grid",{"mensal":"Mensal","semanal":"Semanal","semestral":"Semestral","anual":"Anual"}[periodo])
    os.makedirs(out_dir,exist_ok=True)
    metodologia(doc); aplicar_estilo_tabelas(doc)
    out=os.path.join(out_dir,f"Relatorio_Portfolio_Grid_{re.sub(r'[^0-9A-Za-z]+','_',rot)}.docx"); doc.save(out)
    return out,k

# ----------------------------------------------------------------- PDF / MAIN
def _word_convert(docx_path, pdf_path):
    """Converte via Word usando LATE BINDING (win32com.client.dynamic).

    Por que não usar o docx2pdf direto: ele chama win32com.client.Dispatch, que
    consulta o cache de tipos gen_py. Havendo cache (o xlwings gera um), o
    Documents.Open passa a devolver um wrapper early-bound sem o método SaveAs
    -> 'AttributeError: Open.SaveAs' da 2ª conversão em diante. Era por isso que
    só o primeiro relatório saía em PDF. O dynamic.Dispatch ignora o cache.
    """
    import pythoncom, win32com.client
    WD_FORMAT_PDF = 17
    try: pythoncom.CoInitialize()
    except Exception: pass
    word = None
    try:
        word = win32com.client.dynamic.Dispatch("Word.Application")
        word.Visible = False
        try: word.DisplayAlerts = 0
        except Exception: pass
        doc = word.Documents.Open(os.path.abspath(docx_path), ReadOnly=True)
        try:
            doc.SaveAs(os.path.abspath(pdf_path), FileFormat=WD_FORMAT_PDF)
        finally:
            doc.Close(False)
    finally:
        if word is not None:
            try: word.Quit()
            except Exception: pass
        try: pythoncom.CoUninitialize()
        except Exception: pass


def to_pdf(docx_path):
    pdf=os.path.splitext(docx_path)[0]+".pdf"
    erros=[]
    if sys.platform=="win32":
        try:
            _word_convert(docx_path,pdf)
            if os.path.exists(pdf): return pdf
        except Exception as e:
            erros.append(f"Word: {type(e).__name__}: {e}")
    try:
        from docx2pdf import convert as _c; _c(docx_path,pdf)
        if os.path.exists(pdf): return pdf
    except Exception as e:
        erros.append(f"docx2pdf: {type(e).__name__}: {e}")
    import shutil,subprocess
    soffice=shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        try:
            subprocess.run([soffice,"--headless","--convert-to","pdf","--outdir",os.path.dirname(docx_path),docx_path],
                           check=True,timeout=240,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            if os.path.exists(pdf): return pdf
        except Exception as e:
            erros.append(f"LibreOffice: {type(e).__name__}: {e}")
    else:
        erros.append("LibreOffice: nao instalado")
    print("  [aviso] PDF indisponivel. DOCX mantido. Motivo:")
    for _e in erros: print("          - "+_e)
    return None
def _finalizar(out,formato,label):
    final=out
    if formato in ("pdf","ambos"):
        pdf=to_pdf(out)
        if pdf:
            final=pdf
            if formato=="pdf":
                try: os.remove(out)
                except Exception: pass
    print(f"[OK] {label} -> {final}")
def main():
    ap=argparse.ArgumentParser(description="Relatorios de manutencao Grid Co. (v3)")
    ap.add_argument("--periodo",required=True,choices=["semanal","mensal","semestral","anual"])
    ap.add_argument("--ref",required=True); ap.add_argument("--cliente"); ap.add_argument("--usina")
    ap.add_argument("--todos",action="store_true"); ap.add_argument("--portfolio",action="store_true"); ap.add_argument("--clientes",help="lista de clientes p/ portfólio (vírgula)"); ap.add_argument("--saida")
    ap.add_argument("--formato",choices=["pdf","docx","ambos"],default="pdf")
    a=ap.parse_args(); pasta=achar_pasta(); saida=a.saida or pasta
    idx,rows,aux,cu=carregar(pasta)
    if a.portfolio:
        cl=[c.strip() for c in a.clientes.split(",")] if a.clientes else None
        out,k=gerar_portfolio(a.periodo,a.ref,idx,rows,aux,saida,clientes=cl); _finalizar(out,a.formato,f"Portfólio Grid: {k['n']} tarefas"); return
    if a.usina:
        nome=limpa_usina(a.usina); cli=norm_cli(nome.split(" - ")[0]) if " - " in nome else norm_cli(nome)
        out,k=gerar("usina",nome,cli,a.periodo,a.ref,idx,rows,aux,saida); _finalizar(out,a.formato,f"{nome}: {k['n']} OTs"); return
    clientes=sorted({norm_cli(v["cliente"]) for v in aux.values() if v["cliente"] and v["cliente"]!="—"})
    alvo=clientes if a.todos else [a.cliente]
    if not a.todos and not a.cliente: raise SystemExit("Informe --cliente, --usina ou --todos")
    for cli in alvo:
        out,k=gerar("cliente",cli,cli,a.periodo,a.ref,idx,rows,aux,saida); _finalizar(out,a.formato,f"{cli}: {k['n']} OTs")
if __name__=="__main__": main()
