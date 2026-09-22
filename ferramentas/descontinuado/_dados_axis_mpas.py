# -*- coding: utf-8 -*-
"""Consolida a situação de MPA/MPS/Supressão/Limpeza das usinas Axis para o deck de
alinhamento com o cliente. Fontes:
  - Gerencial - PCM_2026_R00.xlsx, aba 'Zeladoria e MPAS' (status oficial: OS, datas, classificação)
  - API Fracttal (avanço das sub-tarefas da MPA por componente)
Escopo: Ponto Belo, São José do Egito (PE I), Petrolina 2 (PE II), Petrolina 3 (PE III), Marialva.
Só lê. Grava C:\\tmp\\pcm\\axis_mpas.json."""
import os, sys, re, json, datetime as dt
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("REL_API_TTL_MIN", "180")
import relatorio_clientes as rc
from python_calamine import CalamineWorkbook

HOJE = dt.datetime(2026, 7, 21)
GER = r"C:\Users\Fabricio Barreto\GRID CO\GRID CO. - Gridco\4. O&M\11.Pré-Operação\1. Gerencial\4. Gerencial - MPAS e Zeladoria\Gerencial - PCM_2026_R00.xlsx"
SAIDA = r"C:\tmp\pcm\axis_mpas.json"

PLANTS = [
    dict(cod="PB",  display="Ponto Belo",              sheet="Axis - Ponto Belo 1", api="Axis - Ponto Belo 1"),
    dict(cod="SJE", display="São José do Egito (PE I)", sheet="Axis - PE 1",         api="Axis - São José do Egito 1"),
    dict(cod="PE2", display="Petrolina 2 (PE II)",      sheet="Axis - PE 2",         api="Axis - Petrolina 2"),
    dict(cod="PE3", display="Petrolina 3 (PE III)",     sheet="Axis - PE 3",         api="Axis - Petrolina 3"),
    dict(cod="MAR", display="Marialva",                 sheet="Axis - Marialva 1",   api="Axis - Marialva 1"),
]

# ---------------- 1) planilha gerencial (status oficial) ----------------
wb = CalamineWorkbook.from_path(GER)
data = wb.get_sheet_by_name("Zeladoria e MPAS").to_python(skip_empty_area=False)
hdr = [str(c).strip() for c in data[3]]
H = {h: i for i, h in enumerate(hdr)}


def g(row, name):
    i = H.get(name)
    v = row[i] if i is not None and i < len(row) else ""
    return "" if v is None else (v if isinstance(v, dt.date) else str(v).strip())


def dfmt(v):
    if isinstance(v, dt.date):
        return v.strftime("%d/%m/%Y")
    return str(v)[:10] if v else ""


linhas_sheet = defaultdict(list)
for r in data[4:]:
    u = g(r, "Usina")
    if "axis" in u.lower():
        linhas_sheet[u].append(r)


def melhor(rows, atividade):
    """Linha mais relevante da atividade: prioriza Em Execução/Atrasado; senão maior ciclo."""
    cand = [r for r in rows if g(r, "Atividades").lower() == atividade.lower()]
    if not cand:
        return None
    def rank(r):
        cls = g(r, "Classificação")
        pr = {"Atrasado": 3, "Em Execução": 2, "Programar": 1, "Finalizado": 0}.get(cls, 0)
        try:
            ci = float(g(r, "Ciclo") or 0)
        except Exception:
            ci = 0
        return (pr, ci)
    return sorted(cand, key=rank, reverse=True)[0]


def linha_dict(r):
    if r is None:
        return None
    return dict(
        os=g(r, "Número da OS"), ciclo=g(r, "Ciclo"),
        status=g(r, "Status Facttal"), classificacao=g(r, "Classificação"),
        prevista=dfmt(g(r, "Data Prevista")), inicio=dfmt(g(r, "Data Inicio")),
        termino=dfmt(g(r, "Data Término")), obs=g(r, "Observação"),
    )


# ---------------- 2) API (avanço das sub-tarefas da MPA) ----------------
idx, rows, aux, _ = rc.carregar(os.path.dirname(os.path.abspath(__file__)))
regs = rc.coletar("cliente", "Axis", idx, rows, aux)
BLOQ = re.compile(r"cabine|transformador|qgbt|qdmt|cabos? ca|cabos? cc|média tensão|media tensao|relé|rele", re.I)


def mpa_api(api_nome):
    g_ = [x for x in regs if x["ufv"] == api_nome and x["mp"] == "MPA"]
    if not g_:
        return None
    fin = [x for x in g_ if rc.FINALIZADO(x)]
    pend = [x for x in g_ if not rc.FINALIZADO(x)]
    # componentes pendentes que dependem de desligamento (média tensão)
    bloq = sorted({re.sub(r"^\[Axis\]\s*-\s*MPA\s*-\s*", "", x["tarefa"]).split("apenas")[0].strip()
                   for x in pend if BLOQ.search(rc.sa(x["tarefa"]))})
    return dict(total=len(g_), fin=len(fin), pend=len(pend),
                pct=round(100 * len(fin) / len(g_), 0),
                bloqueados=bloq)


# ---------------- 3) consolida por usina ----------------
out = {"hoje": HOJE.strftime("%d/%m/%Y"), "plants": []}
for p in PLANTS:
    rws = linhas_sheet.get(p["sheet"], [])
    rec = dict(cod=p["cod"], display=p["display"])
    rec["mpa"] = linha_dict(melhor(rws, "MPA"))
    rec["mps"] = linha_dict(melhor(rws, "MPS"))
    rec["supressao"] = linha_dict(melhor(rws, "Supressão Vegetal"))
    rec["limpeza"] = linha_dict(melhor(rws, "Limpeza de Módulos"))
    rec["poda"] = linha_dict(melhor(rws, "Poda Química"))
    rec["mpa_api"] = mpa_api(p["api"])
    out["plants"].append(rec)

os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
with open(SAIDA, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
print("gravado:", SAIDA)
print()
for p in out["plants"]:
    print("=" * 72)
    print(p["display"])
    a = p["mpa_api"]
    print(f"  MPA  sheet={p['mpa']['classificacao'] if p['mpa'] else '—':12s} "
          f"api={(str(a['fin'])+'/'+str(a['total'])+' ('+str(int(a['pct']))+'%)') if a else '—':14s} "
          f"bloq={a['bloqueados'] if a else []}")
    print(f"  MPS  {p['mps']['classificacao'] if p['mps'] else '—':12s} prevista={p['mps']['prevista'] if p['mps'] else '—'}")
    for k in ("supressao", "limpeza", "poda"):
        v = p[k]
        if v:
            print(f"  {k:10s} {v['classificacao'] or v['status']:12s} prevista={v['prevista']}  os={v['os']}")
