# -*- coding: utf-8 -*-
"""Extrai o dataset de PCM da Athon em junho/2026 e grava em JSON (scratchpad).
Reusa as regras canônicas do relatorio_clientes.py. Só lê a API — não escreve no BD."""
import os, sys, json, re, datetime as dt
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("REL_API_TTL_MIN", "180")

import relatorio_clientes as rc

PASTA = os.path.dirname(os.path.abspath(__file__))
SAIDA = r"C:\tmp\pcm\athon_junho.json"

# UFV -> código usado na apresentação de Performance (mesma nomenclatura do cliente)
COD = {
    "Athon - Timon 1": "TIM100", "Athon - Timon 2": "TIM200",
    "Athon - Matões 1": "MTS100", "Athon - Matões 2": "MTS200",
    "Athon - Marabá 1": "MAB100", "Athon - Marabá 2": "MAB200",
    "Athon - Mãe do Rio 1": "MRO100", "Athon - Jacundá 1": "JCD100",
    "Athon - Capitão Poço 1": "CPP100", "Athon - Santa Maria do Pará 1": "SMP100",
}
# ordem igual à da apresentação de Performance
ORDEM = ["TIM200", "TIM100", "MTS200", "MTS100", "MAB200", "MAB100", "MRO100", "JCD100", "CPP100", "SMP100"]

idx, rows, aux, cli_usinas = rc.carregar(PASTA)
ini, fim, rot, _ = rc.janela("mensal", "2026-06")
regs = rc.coletar("cliente", "Athon", idx, rows, aux)
k = rc.kpis_mes(regs, ini, fim)
mes = k["conc"]

# checagem: toda UFV do mês tem código?
faltando = sorted({x["ufv"] for x in mes} - set(COD))
if faltando:
    print("!! UFV sem código:", faltando)

fin = lambda x: rc.FINALIZADO(x)
out = {}
out["rotulo"] = rot
out["total"] = len(mes)
out["executadas"] = sum(1 for x in mes if fin(x))
out["aberto"] = sum(1 for x in mes if not fin(x))
out["programadas"] = k["prog"]
out["nao_programadas"] = k["nprog"]
out["pct_prog"] = k["pct_prog"]
out["pct_prev"] = k["pct_prev"]
out["emerg"] = k["emerg"]

# ---- drill-down por categoria: feitas / total
cats = {}
for c in rc.ORDER_CAT:
    grp = [x for x in mes if x["categoria"] == c]
    if not grp:
        continue
    cats[c] = dict(total=len(grp), feitas=sum(1 for x in grp if fin(x)),
                   aberto=sum(1 for x in grp if not fin(x)))
out["categorias"] = cats

# ---- programada vs não programada, feitas/total
for nome, sel in (("prog", lambda x: x["programada"]), ("nprog", lambda x: not x["programada"])):
    grp = [x for x in mes if sel(x)]
    out[nome + "_det"] = dict(total=len(grp), feitas=sum(1 for x in grp if fin(x)),
                              aberto=sum(1 for x in grp if not fin(x)))

# ---- baldes de tipo de tarefa para a matriz do slide 4
#      (Inspeção sai de Preventiva; Religamento junta presencial + remoto, com o remoto
#       destacado à parte; "Outras" garante que a soma dos baldes feche com o total)
BALDES = ["Preventiva", "Inspeção", "Corretiva", "Religamento", "Administrativa", "Outras"]


def balde(x):
    if x["categoria"] == "Zeladoria":
        return "Outras"
    t = x["tipo"]
    if t == "Preventiva":
        return "Preventiva"
    if t == "Inspeção":
        return "Inspeção"
    if t in ("Corretiva", "Corretiva Emergencial"):
        return "Corretiva"
    if t in ("Religamento", "Religamento Remoto"):
        return "Religamento"
    if t == "Administrativa":
        return "Administrativa"
    return "Outras"


def resumo_baldes(grp):
    """{balde: dict(feitas, total, sub)} — sub = emergenciais (Corretiva) ou remotos (Religamento)."""
    r = {}
    for b in BALDES:
        g = [x for x in grp if balde(x) == b]
        sub = 0
        if b == "Corretiva":
            sub = sum(1 for x in g if x["tipo"] == "Corretiva Emergencial")
        elif b == "Religamento":
            sub = sum(1 for x in g if x["tipo"] == "Religamento Remoto")
        r[b] = dict(total=len(g), feitas=sum(1 for x in g if fin(x)), sub=sub)
    assert sum(v["total"] for v in r.values()) == len(grp), "baldes não fecham com o total"
    return r


out["baldes_ordem"] = BALDES
out["baldes_total"] = resumo_baldes(mes)

# ---- por usina
usinas = {}
for ufv, cod in COD.items():
    grp = [x for x in mes if x["ufv"] == ufv]
    corr = [x for x in grp if x["categoria"] == "Corretiva"]
    prev = [x for x in grp if x["categoria"] == "Preventiva"]
    relig = [x for x in grp if x["categoria"] in ("Religamento", "Religamento Remoto")]
    base = len(prev) + len(corr)
    usinas[cod] = dict(
        ufv=ufv, total=len(grp), feitas=sum(1 for x in grp if fin(x)),
        aberto=sum(1 for x in grp if not fin(x)),
        prev=len(prev), prev_fin=sum(1 for x in prev if fin(x)),
        corr=len(corr), corr_fin=sum(1 for x in corr if fin(x)),
        emerg=sum(1 for x in corr if x["tipo"] == "Corretiva Emergencial"),
        crit_alta=sum(1 for x in corr if str(x["crit"]).strip().lower() in ("alto", "muito alto")),
        relig=len(relig),
        pct_prev=(100 * len(prev) / base if base else 0),
        pct_exec=(100 * sum(1 for x in grp if fin(x)) / len(grp) if grp else 0),
        hh=round(sum(x["tot"] for x in grp), 1),
        baldes=resumo_baldes(grp),
    )
# ---- detalhe das atividades em aberto por usina (agrupado por tarefa; a mesma tarefa
#      se repete em vários ativos — ex.: MPM - Cabine, uma OS por cabine)
_EST = {"pausado": "Pausada", "Não Iniciada": "Não iniciada", "Em progresso": "Em progresso"}
for cod, ufv in ((c, u) for u, c in COD.items()):
    ab_u = [x for x in mes if x["ufv"] == ufv and not fin(x)]
    grp = defaultdict(list)
    for x in ab_u:
        grp[x["tarefa"]].append(x)
    det = []
    for t, lst in grp.items():
        dp = [x["dprog"] for x in lst if x["dprog"]]
        det.append(dict(
            tarefa=t,
            categoria=lst[0]["categoria"],
            qtd=len(lst),
            ativos=len({x["ativo"] for x in lst}),
            prog_ini=(min(dp).strftime("%d/%m") if dp else ""),
            prog_fim=(max(dp).strftime("%d/%m") if dp else ""),
            estados=sorted({_EST.get(x["estado"], x["estado"] or "—") for x in lst}),
        ))
    det.sort(key=lambda r: (-r["qtd"], r["tarefa"]))
    usinas[cod]["aberto_det"] = det
    usinas[cod]["aberto_prev"] = sum(1 for x in ab_u if x["categoria"] == "Preventiva")
    usinas[cod]["aberto_corr"] = sum(1 for x in ab_u if x["categoria"] == "Corretiva")
    usinas[cod]["aberto_outras"] = len(ab_u) - usinas[cod]["aberto_prev"] - usinas[cod]["aberto_corr"]
    assert sum(r["qtd"] for r in det) == len(ab_u) == usinas[cod]["aberto"], f"{cod}: detalhe não fecha"

out["usinas"] = usinas
out["ordem"] = ORDEM

# ---- preventivas MP
mp = rc.mp_mes(regs, ini, fim)
out["mp"] = {c: dict(plan=d["plan"], fin=d["fin"], pend=d["pend"], pct=d["pct"])
             for c, d in mp.items() if d["plan"]}

# ---- bad actors: ativo com mais corretivas
def cod_ativo(a):
    m = re.search(r"\{\s*([A-Z0-9]+)-", str(a or ""))
    return m.group(1) if m else None

def nome_ativo(a):
    return re.sub(r"\s*\{.*?\}\s*$", "", str(a or "")).strip()

def tag_ativo(a):
    """Código completo do ativo, ex.: 'MAB200-INVR2.8' ou 'ATHN-CPP100'."""
    m = re.search(r"\{\s*([^}]+?)\s*\}", str(a or ""))
    return m.group(1) if m else None


def eh_ativo_usina(a):
    """A OS foi aberta contra a UFV inteira (ativo ATHN-XXX), não contra um equipamento."""
    return bool(re.match(r"ATHN-", str(tag_ativo(a) or "")))


corr = [x for x in mes if x["categoria"] == "Corretiva"]

# Agrupa pelo CÓDIGO do ativo, não pelo nome: "Inversor 4.2 Huawei" existe no CPP100 e no
# SMP100 e são equipamentos físicos distintos — pelo nome eles virariam uma linha só.
ba = defaultdict(lambda: dict(n=0, emerg=0, crit=0, usinas=set(), hh=0.0, tipologia="", nome=""))
for x in corr:
    if eh_ativo_usina(x["ativo"]):     # eventos de planta entram no bloco próprio, abaixo
        continue
    d = ba[tag_ativo(x["ativo"]) or nome_ativo(x["ativo"])]
    d["n"] += 1
    d["hh"] += x["tot"]
    d["tipologia"] = x["tipologia"]
    d["nome"] = nome_ativo(x["ativo"])
    if x["tipo"] == "Corretiva Emergencial":
        d["emerg"] += 1
    if str(x["crit"]).strip().lower() in ("alto", "muito alto"):
        d["crit"] += 1
    d["usinas"].add(COD.get(x["ufv"], "—"))
out["bad_actors"] = [
    dict(ativo=v["nome"], tag=k2, n=v["n"], emerg=v["emerg"], crit=v["crit"], hh=round(v["hh"], 1),
         tipologia=v["tipologia"], usinas=sorted(v["usinas"]))
    for k2, v in sorted(ba.items(), key=lambda kv: (-kv[1]["n"], kv[1]["nome"]))[:12]
]

# ---- corretivas abertas no nível da usina (ativo-usina): não são bad actor de equipamento,
#      são majoritariamente offline/comunicação — várias por evento da rede
au = [x for x in corr if eh_ativo_usina(x["ativo"])]
_kw = re.compile(r"offline|comunica|recomposi|religa", re.I)
out["ativo_usina"] = dict(
    total=len(au),
    conectividade=sum(1 for x in au if _kw.search(rc.sa(x["tarefa"]))),
    emerg=sum(1 for x in au if x["tipo"] == "Corretiva Emergencial"),
    usinas=Counter(COD.get(x["ufv"], "—") for x in au).most_common(),
)

# ---- tipologia / sistema / criticidade das corretivas
out["tipologia_corr"] = Counter(x["tipologia"] for x in corr).most_common()
out["sistema_corr"] = Counter(x["sistema"] for x in corr).most_common()
out["crit_corr"] = Counter(str(x["crit"]) for x in corr).most_common()

# ---- em aberto: por categoria e por usina + envelhecimento
ab = [x for x in mes if not fin(x)]
out["aberto_cat"] = Counter(x["categoria"] for x in ab).most_common()
out["aberto_usina"] = Counter(COD.get(x["ufv"], "—") for x in ab).most_common()
out["aberto_prev_usina"] = Counter(COD.get(x["ufv"], "—") for x in ab if x["categoria"] == "Preventiva").most_common()
out["aberto_corr_usina"] = Counter(COD.get(x["ufv"], "—") for x in ab if x["categoria"] == "Corretiva").most_common()

# ---- taxa de programação expurgando religamentos (eventos da rede, fora do controle da O&M)
#      mesma lógica do "PR GRID" da apresentação de Performance
relig_mes = [x for x in mes if x["categoria"] in ("Religamento", "Religamento Remoto")]
base_grid = len(mes) - len(relig_mes)
out["religamentos"] = len(relig_mes)
out["relig_por_usina"] = Counter(COD.get(x["ufv"], "—") for x in relig_mes).most_common()
out["base_grid"] = base_grid
out["pct_prog_grid"] = 100 * k["prog"] / base_grid if base_grid else 0
hoje = dt.datetime(2026, 7, 1)
idade = []
for x in ab:
    d = x["dprog"] or x["dini"] or x["dcri"]
    if d:
        idade.append((hoje - d).days)
out["aberto_idade_media"] = round(sum(idade) / len(idade), 1) if idade else 0
out["aberto_mais_30d"] = sum(1 for i in idade if i > 30)

# ---- histórico mensal (evolução do ano)
hm = rc.historico_mensal(regs, fim)
out["historico"] = [dict(rot=h["rot"], total=h["total"], prev=h["prev"], corr=h["corr"], pct=h["pct"]) for h in hm]
hp = rc.historico_prog(regs, fim)
out["historico_prog"] = [dict(rot=h["rot"], prog=h["prog"], nprog=h["nprog"], pct=h["pct"]) for h in hp]

os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
with open(SAIDA, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
print("gravado:", SAIDA)
print(json.dumps({kk: vv for kk, vv in out.items() if kk not in ("usinas", "bad_actors")},
                 ensure_ascii=False, indent=1, default=str))
print()
print("=== USINAS ===")
for c in ORDEM:
    u = usinas[c]
    print(f"{c:7s} tot={u['total']:4d} feitas={u['feitas']:4d} aberto={u['aberto']:3d} "
          f"prev={u['prev']:3d} corr={u['corr']:3d} emerg={u['emerg']:2d} critA={u['crit_alta']:2d} "
          f"relig={u['relig']:3d} %prev={u['pct_prev']:5.1f} %exec={u['pct_exec']:5.1f} hh={u['hh']}")
print()
print("=== BAD ACTORS ===")
for b in out["bad_actors"]:
    print(f"{b['n']:3d}  emerg={b['emerg']:2d} crit={b['crit']:2d} hh={b['hh']:6.1f}  {b['usinas']}  {b['ativo'][:60]}")
