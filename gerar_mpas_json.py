# -*- coding: utf-8 -*-
"""
gerar_mpas_json.py
------------------
Gera `mpas.json` para a aba "Gestão MPAS" do painel (gridco-pcm-data).

Reusa a coleta já existente do site MPAS (Site_Gestao_MPAS/gerar_calendario_mpas.py):
  1. Gerencial - PCM_2026_R00.xlsx, aba "MPAS"  -> a linha de cada MPA/MPS
  2. API Fracttal -> tarefas de cada OS + Estado da Tarefa (badge 23/25 e o modal)

CIFRAGEM — opcional, desligada por padrão
-----------------------------------------
O que este arquivo carrega (cliente, usina, cluster, datas, equipe, observação)
é do MESMO nível do que o painel já publica aberto em banco_dados.json e
gestao_pcm.json. Não há custo, cotação, fornecedor nem contrato aqui. Cifrar
isso só criaria atrito (uma senha a mais) sem proteger nada de novo — por isso
o padrão é gravar em claro, e a aba fica restrita ao admin no painel.

Se um dia entrarem dados sensíveis de verdade (Fornecedores, Cotações, custos),
use --cifrar: AES-GCM com chave PBKDF2-SHA256 da senha do admin. O painel decifra
no navegador com a senha do login; quem baixar o arquivo vê bytes aleatórios.

Uso:
    py -3 gerar_mpas_json.py              # padrão: claro
    py -3 gerar_mpas_json.py --sem-api    # só Excel (rápido, p/ testar layout)
    py -3 gerar_mpas_json.py --cifrar     # pede senha e cifra
"""
import os
import sys
import json
import base64
import hashlib
import getpass
import argparse
import datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.join(AQUI, "Site_Gestao_MPAS")
SAIDA = os.path.join(AQUI, "mpas.json")

PBKDF2_ITER = 210_000          # mesmo patamar recomendado p/ PBKDF2-SHA256
SALT_BYTES, IV_BYTES = 16, 12


def log(m):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {m}", flush=True)


def _cifrar(texto: str, senha: str) -> dict:
    """AES-GCM com chave PBKDF2-SHA256. Formato pronto p/ Web Crypto no browser."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        log("ERRO: falta a lib 'cryptography'. Rode: pip install cryptography")
        raise
    salt = os.urandom(SALT_BYTES)
    iv = os.urandom(IV_BYTES)
    chave = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, PBKDF2_ITER, 32)
    ct = AESGCM(chave).encrypt(iv, texto.encode("utf-8"), None)
    b64 = lambda b: base64.b64encode(b).decode("ascii")
    return {
        "cifrado": True, "alg": "AES-GCM", "kdf": "PBKDF2-SHA256",
        "iter": PBKDF2_ITER, "salt": b64(salt), "iv": b64(iv), "ct": b64(ct),
    }


def _enriquecer(manut, G):
    """O coletor do site guarda só o supervisor (derivado da Equipe) e trunca
    Apoio/Observação na 1ª linha. A aba Gestão MPAS mostra esses campos como
    coluna, então relemos a planilha e trazemos o texto completo."""
    import openpyxl
    # A aba e a linha do cabeçalho vêm do coletor — em 24/08/2026 a "MPAS" virou
    # "Zeladoria e MPAS" e o cabeçalho subiu da linha 4 para a 1. Esta função
    # ficou de fora do primeiro conserto e foi o terceiro ponto a quebrar.
    _aba = getattr(G, "ABA_MPAS", "MPAS")
    _lin = getattr(G, "LINHA_CAB", 4)             # 1-based
    wb = openpyxl.load_workbook(G.XLSX, read_only=True, data_only=True)
    ws = wb[_aba]
    todas = list(ws.iter_rows(values_only=True))
    cab = todas[_lin - 1] if len(todas) >= _lin else ()
    linhas = todas[_lin:]

    # ⚠ O MESMO filtro do ler_mpas, e não é zelo: o pareamento abaixo é POR
    # POSIÇÃO (brutos[i] <-> manut[i]). A aba nova traz 140 linhas de zeladoria
    # misturadas; sem filtrar seriam 312 brutos contra 172 coletadas, e cada
    # observação cairia num registro DIFERENTE. Dado trocado, sem erro nenhum.
    _tipos = getattr(G, "TIPOS_MPAS", None)
    def _linha_vale(r):
        def _c(i):
            return r[i] if (isinstance(i, int) and 0 <= i < len(r)) else None
        if not (_c(G.C_CLI) or _c(G.C_USINA)):
            return False
        if _tipos:
            v = _c(G.C_TIPO)
            return str(v or "").strip().upper() in _tipos
        return True

    brutos = [r for r in linhas if _linha_vale(r)]
    if len(brutos) != len(manut):
        log(f"  ! ATENÇÃO: {len(brutos)} linhas na planilha x {len(manut)} coletadas. "
            f"O pareamento é por posição, então esta diferença DESALINHA equipe, "
            f"apoio e observação entre registros. Confira o filtro antes de confiar "
            f"nesses campos.")
    # As colunas são achadas pelo NOME no cabeçalho (linha 4): a planilha já
    # ganhou coluna nova antes ("Nº do lote do relatório"), o que deslocou a
    # Observação e deixou o índice fixo do coletor antigo apontando p/ vazio.
    hdr = [("" if h is None else str(h)).strip().lower() for h in cab]
    def col(*nomes, padrao=None):
        for n in nomes:
            n = n.lower()
            for i, h in enumerate(hdr):
                if h == n:
                    return i
        for n in nomes:                      # 2ª passada: começa com
            n = n.lower()
            for i, h in enumerate(hdr):
                if h.startswith(n):
                    return i
        return padrao
    i_eq = col("equipe", padrao=G.C_EQUIPE)
    i_ap = col("apoio na equipe", "apoio", padrao=G.C_APOIO)
    i_ob = col("observação", "observacao", "obs", padrao=G.C_OBS)
    # 19/08/2026 — as colunas de PENDÊNCIA. A coluna "Observação" conta a
    # história ("aguardando e-mail da Renata"); estas quatro dizem o MOTIVO
    # concreto de a manutenção não ter andado, e é o que o gerente operacional
    # procura. Ficavam só no Excel: a aba mostrava o atraso sem a causa.
    i_fe = col("equipamentos do escopo faltantes?", "equipamentos do escopo faltantes")
    i_ff = col("equipamentos/ferramentas auxiliares faltantes?",
               "equipamentos/ferramentas auxiliares faltantes")
    i_cp = col("compra de equipamentos principais")
    i_dl = col("desligamentos programados")
    log(f"  colunas: Equipe=[{i_eq}] Apoio=[{i_ap}] Observação=[{i_ob}]")
    log(f"  pendência: EscopoFalta=[{i_fe}] FerrFalta=[{i_ff}] Compra=[{i_cp}] Deslig=[{i_dl}]")
    if None in (i_fe, i_ff, i_cp, i_dl):
        log("  ! alguma coluna de pendência não foi achada pelo nome — o campo "
            "sai vazio e a aba mostra '—' (não quebra)")

    # Células com fórmula quebrada chegam como "#N/A", "#REF!"… — viram vazio,
    # senão aparecem como texto na coluna Equipe da aba.
    import re as _re
    import datetime as _dt
    ERRO_XL = _re.compile(r"^#(N/A|REF!|VALUE!|DIV/0!|NAME\?|NULL!|NUM!)$", _re.I)

    def txt(v):
        # datas chegam como datetime e viram "2026-08-17 00:00:00" no str()
        if isinstance(v, (_dt.datetime, _dt.date)):
            return v.strftime("%d/%m/%Y")
        s = ("" if v is None else str(v)).strip()
        return "" if ERRO_XL.match(s) else s

    lim = min(len(brutos), len(manut))
    for i in range(lim):
        r = brutos[i]
        g = lambda j: txt(r[j]) if (j is not None and j < len(r)) else ""
        manut[i]["equipe"] = g(i_eq)          # Equipe (texto completo)
        manut[i]["apoio"] = g(i_ap)           # Apoio na equipe (completo)
        manut[i]["obs"] = g(i_ob)             # Observação (completa)
        # Cru, sem normalizar: "Não" (respondido: nada falta) é informação
        # diferente de "" (ninguém preencheu). Quem decide é a tela.
        manut[i]["falta_eq"] = g(i_fe)        # equipamentos do escopo faltantes
        manut[i]["falta_fer"] = g(i_ff)       # ferramentas auxiliares faltantes
        manut[i]["compra_princ"] = g(i_cp)    # compra de equipamentos principais
        manut[i]["deslig"] = g(i_dl)          # desligamentos programados
    return manut


def _xlsx_legivel(caminho):
    """Devolve um caminho que dá para abrir mesmo com a planilha aberta no Excel.

    O Excel trava o arquivo enquanto está aberto (PermissionError) e o usuário
    edita a Gerencial justamente para alimentar este bloco. Copiar para o temp
    antes de ler resolve — e a cópia é descartável."""
    import shutil, tempfile
    try:
        with open(caminho, "rb"):
            return caminho
    except PermissionError:
        dst = os.path.join(tempfile.gettempdir(), "_pcm_" + os.path.basename(caminho))
        try:
            shutil.copy2(caminho, dst)
            log("  (planilha aberta no Excel — lendo de uma cópia temporária)")
            return dst
        except Exception as e:
            log(f"  ! não consegui copiar a planilha travada: {e}")
            return caminho


def _remapear_colunas(G):
    """Reancora os índices C_* do coletor pelos NOMES do cabeçalho.

    O `gerar_calendario_mpas` fixa as colunas por posição (C_PREV = 14 etc.).
    Em 11/08/2026 a coluna "Relatório" saiu da aba MPAS e tudo depois dela
    andou uma casa: 203 de 219 registros ficaram SEM Data Prevista e o painel
    teria mostrado dado trocado sem nenhum erro. Mapear por nome imuniza o
    coletor a inserção/remoção/reordenação de colunas."""
    import openpyxl
    ALVOS = {
        # Os segundos nomes vieram da reestruturação de 24/08/2026, quando a aba
        # MPAS virou "Zeladoria e MPAS". Ficam como APELIDOS, não substitutos: se
        # a Gerencial voltar aos nomes antigos, os dois continuam casando.
        "C_OS": ["os", "numero da os"], "C_CLI": ["cliente"], "C_USINA": ["usina"],
        "C_CLUSTER": ["cluster"],
        "C_TIPO": ["tipo de manutencao", "tipo", "supressao lavagem"],
        "C_HA": ["hectare"], "C_MOD": ["n de modulos", "no de modulos", "modulos"],
        "C_SEMANAS": ["semanas de mobilizacao"], "C_STATUS": ["status"],
        "C_RELAT": ["relatorio"], "C_CICLO": ["ciclo"], "C_PRIOR": ["prioridade"],
        "C_ATUALIZ": ["ultima atualizacao"], "C_PREV": ["data prevista"],
        "C_INI": ["data inicio"], "C_FIM": ["data termino"],
        "C_EQUIPE": ["equipe", "empresa contratada nome equipe"],
        "C_APOIO": ["apoio na equipe"],
        "C_TRAFOS_OLEO": ["quantidade de transformadores a oleo"],
        "C_OLEO": ["analise de oleo solicitada para a mpa"],
        "C_OBS": ["observacao"],
        # colunas novas, usadas pelo bloco de compras
        "C_TENSAO": ["tensao da usina para aterramento temporario"],
        "C_COMPRA": ["compra de equipamentos principais"],
        "C_FALTANTES": ["equipamentos do escopo faltantes",
                        "equipamentos faltantes data do registro"],
    }
    import re as _re, unicodedata as _ud

    def nz(s):
        s = _ud.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
        return _re.sub(r"[^a-z0-9 ]+", " ", s).strip()

    try:
        aba = getattr(G, "ABA_MPAS", "MPAS")
        lin = getattr(G, "LINHA_CAB", 4)
        wb = openpyxl.load_workbook(G.XLSX, read_only=True, data_only=True)
        cab = [nz(c) for c in next(wb[aba].iter_rows(min_row=lin, max_row=lin, values_only=True))]
        wb.close()
    except Exception as e:
        # ⚠ Este `return` devolvia {} — um dicionário VAZIO — enquanto quem chama
        # faz `_, _perdidas = _remapear_colunas(G)`. O resultado era
        # "ValueError: not enough values to unpack (expected 2, got 0)": o plano B
        # escrito para degradar com elegância DERRUBAVA o script. Descoberto em
        # 24/08/2026, quando a aba mudou de nome e este caminho rodou pela
        # primeira vez desde que foi escrito.
        log(f"  ! não consegui ler o cabeçalho da aba {getattr(G, 'ABA_MPAS', 'MPAS')} "
            f"({e}); mantendo índices fixos")
        return {}, []
    achadas, perdidas, mudou = {}, [], []
    for const, nomes in ALVOS.items():
        idx = next((i for i, c in enumerate(cab) if c in nomes), None)
        if idx is None:
            idx = next((i for i, c in enumerate(cab)
                        if c and any(c.startswith(n[:14]) for n in nomes)), None)
        if idx is None:
            perdidas.append(const)
            # Zerar é essencial, não cosmético: o índice antigo continuaria
            # apontando para ALGUMA coluna da aba nova. C_MOD=7 pousaria em
            # "Relatório enviado ao cliente" e gravaria esse texto no campo
            # "módulos" — errado e silencioso. None faz o _cel devolver vazio.
            setattr(G, const, None)
            continue
        achadas[const] = idx
        antigo = getattr(G, const, None)
        if antigo is not None and antigo != idx:
            mudou.append(f"{const}: {antigo}->{idx}")
        setattr(G, const, idx)
    if mudou:
        log(f"  ! cabeçalho mudou de lugar — reancorado por nome ({len(mudou)}): "
            + ", ".join(mudou[:6]) + (" ..." if len(mudou) > 6 else ""))
    if perdidas:
        log(f"  ! coluna(s) não encontrada(s) na aba MPAS: {', '.join(perdidas)}"
            " — os campos correspondentes saem vazios (melhor vazio que trocado)")
    return achadas, perdidas


# Constante de coluna -> campo do registro, p/ esvaziar o que não existe mais
_CONST_CAMPO = {"C_RELAT": "relatorio", "C_CICLO": "ciclo", "C_PRIOR": "prioridade",
                "C_TRAFOS_OLEO": "trafos_oleo", "C_OLEO": "oleo", "C_OBS": "obs"}


def coletar(sem_api: bool):
    """Chama o coletor do site MPAS (planilha + Fracttal)."""
    if SITE_DIR not in sys.path:
        sys.path.insert(0, SITE_DIR)
    import gerar_calendario_mpas as G
    G.XLSX = _xlsx_legivel(G.XLSX)
    _, _perdidas = _remapear_colunas(G)

    log("Lendo a planilha Gerencial (aba MPAS)...")
    manut = G.ler_mpas(G.XLSX)
    # Coluna que sumiu da planilha: o índice antigo aponta para a vizinha e o
    # campo sairia com o valor errado. Esvaziar é o comportamento honesto.
    for _c in _perdidas:
        _campo = _CONST_CAMPO.get(_c)
        if _campo:
            for _m in manut:
                _m[_campo] = ""
    manut = _enriquecer(manut, G)
    log(f"  -> {len(manut)} manutenções (MPA/MPS)")

    bd = {}
    if sem_api:
        log("--sem-api: pulando o Fracttal (cluster e situação vêm da planilha)")
    else:
        log("Consultando o Fracttal (tarefas + Estado da Tarefa)...")
        bd = G.carregar_bd_fracttal(manut, ttl_min=180) or {}
        log(f"  -> {len(bd)} OS cruzadas")
        _cluster_do_fracttal(manut, G)
    return manut, bd


def _cluster_do_fracttal(manut, G):
    """A Equipe Cluster vem da CLASSIFICAÇÃO 2 do Fracttal (fonte viva), não da
    coluna Cluster da planilha — que fica desatualizada e tem linhas em branco.
    Casa por usina (Classificação 1); a planilha entra só como reserva."""
    try:
        df = G._df_tarefas(180)
    except Exception as e:
        log(f"  ! não consegui ler a classificação 2 ({e}); mantendo o cluster da planilha")
        return
    c1 = "Ativo Classificação 1"
    c2 = "Ativo Classificação 2"
    if c1 not in df.columns or c2 not in df.columns:
        log(f"  ! colunas de classificação ausentes na API; mantendo o cluster da planilha")
        return
    # Os nomes divergem entre as fontes: a API traz " - UF" no fim
    # ("2C - Araputanga 1 - MT") e a planilha numera de 100 em 100
    # ("Athon - Marabá 200" = "Athon - Marabá 2" na API).
    import re as _re
    import unicodedata as _ud
    import difflib as _dl

    def norm(s):
        s = _ud.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
        s = _re.sub(r"\s+-\s+[a-z]{2}\s*$", "", s)      # tira " - UF"
        s = _re.sub(r"[^a-z0-9]+", " ", s).strip()
        s = _re.sub(r"\b(\d)00\b", r"\1", s)            # 100->1, 200->2
        return s

    mapa = {}
    for u, c in zip(df[c1], df[c2]):
        k, c = norm(u), str(c or "").strip()
        if k and c:
            mapa.setdefault(k, {})
            mapa[k][c] = mapa[k].get(c, 0) + 1
    # por usina, o cluster mais frequente (o Fracttal tem grafias divergentes)
    melhor = {k: max(v.items(), key=lambda kv: kv[1])[0] for k, v in mapa.items()}
    chaves = list(melhor)

    exato = aprox = semcasar = trocados = 0
    for m in manut:
        k1, k2 = norm(m.get("usina")), norm(m.get("usina_curta"))
        alvo = melhor.get(k1) or melhor.get(k2)
        if alvo:
            exato += 1
        else:
            p = _dl.get_close_matches(k1, chaves, n=1, cutoff=0.86)
            if p:
                alvo = melhor[p[0]]; aprox += 1
            else:
                semcasar += 1        # apelido ambíguo: fica o cluster da planilha
                continue
        if (m.get("cluster") or "").strip() != alvo:
            trocados += 1
        m["cluster"] = alvo
    log(f"  -> cluster pela Classificação 2: {exato} exatas + {aprox} aproximadas "
        f"= {exato + aprox}/{len(manut)} ({trocados} corrigidas); "
        f"{semcasar} mantiveram o cluster da planilha")

    # O Fracttal tem o mesmo cluster com grafias diferentes ("PA Norte 01" e
    # "PA NORTE 01") — sem unificar, a árvore mostra dois nós para a mesma equipe.
    freq = {}
    for m in manut:
        c = (m.get("cluster") or "").strip()
        if c:
            freq.setdefault(c.lower(), {})
            freq[c.lower()][c] = freq[c.lower()].get(c, 0) + 1
    canon = {k: max(v.items(), key=lambda kv: kv[1])[0] for k, v in freq.items()}
    unif = sum(1 for k, v in freq.items() if len(v) > 1)
    if unif:
        for m in manut:
            c = (m.get("cluster") or "").strip()
            if c:
                m["cluster"] = canon[c.lower()]
        log(f"  -> {unif} cluster(s) com grafia divergente unificado(s)")


# ---------------------------------------------------------------- COMPRAS
# Aba "Compra Equip MPA 2026" da Gerencial: quantidades e abatimentos são
# JULGAMENTO do PCM (o que cada cluster já tem, auxílio do cliente, faixa de
# tensão) e ficam no Excel. O que é VIVO — a âncora, o prazo e a frente — sai
# das datas reais das MPAs (planilha + Fracttal), recalculado a cada rodada.
ABA_COMPRA = "Compra Equip MPA 2026"
JANELA_INI, JANELA_FIM = "2026-06-01", "2026-12-31"


def _frente_de(data_iso):
    """Frente pela data da âncora — mesma régua da aba, mas recalculada."""
    if not data_iso:
        return "Sem data"
    d = str(data_iso)[:10]
    if d <= "2026-08-31":
        return "Frente 1 – Imediata"
    if d <= "2026-09-30":
        return "Frente 2 – Setembro"
    if d <= "2026-10-31":
        return "Frente 3 – Outubro"
    return "Frente 4 – Nov/Dez"


def ler_compras(manut, G):
    """Lê a aba de compra e cruza com as MPAs da janela. Devolve None se a aba
    não existir (o painel simplesmente não mostra o bloco)."""
    import openpyxl
    try:
        wb = openpyxl.load_workbook(G.XLSX, read_only=True, data_only=True)
    except Exception as e:
        log(f"  ! não consegui abrir a Gerencial p/ compras ({e})")
        return None
    if ABA_COMPRA not in wb.sheetnames:
        log(f"  ! aba '{ABA_COMPRA}' não existe — bloco de compras desligado")
        return None
    rows = list(wb[ABA_COMPRA].iter_rows(values_only=True))

    def num(v):
        try:
            return float(str(v).replace("R$", "").replace(".", "").replace(",", ".").strip())
        except Exception:
            return 0.0

    premissas = []
    for r in rows[4:14]:
        if r and r[0] and isinstance(r[1], (int, float)):
            premissas.append({"item": str(r[0]).strip(), "valor": float(r[1])})

    # MPAs da janela, por cluster — a fonte viva da urgência
    jan = [m for m in manut
           if (m.get("tipo") or "").upper() == "MPA"
           and JANELA_INI <= str(m.get("prevista") or "") <= JANELA_FIM]
    por_cluster = {}
    for m in jan:
        por_cluster.setdefault(_norm_cluster(m.get("cluster")), []).append(m)

    itens, vistos = [], set()
    for r in rows[16:47]:
        if not r or not r[0] or str(r[0]).strip().upper().startswith("TOTAL"):
            continue
        nome = str(r[0]).strip()
        ch = _norm_cluster(nome)
        vistos.add(ch)
        mpas = sorted(por_cluster.get(ch, []), key=lambda m: str(m.get("prevista") or "9"))
        ancora = mpas[0] if mpas else None
        data_anc = str(ancora.get("prevista"))[:10] if ancora else None
        itens.append({
            "cluster": nome,
            "cliente": str(r[2] or "").strip(),
            "qtd": {"megometro": r[3] or 0, "microhmimetro": r[4] or 0, "terrometro": r[5] or 0,
                    "chave_impacto": r[6] or 0, "lanterna": r[7] or 0},
            "faixa": str(r[8] or "").strip(),
            "aterramento": num(r[9]),
            "valorA": num(r[10]), "valorB": num(r[11]),
            "obs": str(r[12] or "").strip(),
            # VIVO: âncora, prazo e frente vêm das MPAs, não da célula do Excel
            "ancora": data_anc,
            "ancoraUsina": (ancora.get("usina") if ancora else None),
            "frente": _frente_de(data_anc),
            "mpas": len(mpas),
            "pendencia": "tensão" if "PENDENTE" in str(r[8] or "").upper() else "",
        })

    # Cluster com MPA na janela e SEM linha de dimensionamento = buraco no plano
    faltando, sem_cluster = [], 0
    for ch, ms in por_cluster.items():
        if not ch:                      # MPA sem cluster: outro problema, conta à parte
            sem_cluster += len(ms)
            continue
        if ch in vistos:
            continue
        ms = sorted(ms, key=lambda m: str(m.get("prevista") or "9"))
        faltando.append({"cluster": ms[0].get("cluster"), "mpas": len(ms),
                         "ancora": str(ms[0].get("prevista"))[:10],
                         "usina": ms[0].get("usina")})
    if faltando:
        log(f"  ! {len(faltando)} cluster(s) com MPA na janela e SEM linha de compra: "
            + ", ".join(f["cluster"] for f in faltando))

    log(f"  -> compras: {len(itens)} clusters | A=R$ {sum(i['valorA'] for i in itens):,.0f}"
        .replace(",", "."))
    if sem_cluster:
        log(f"  ! {sem_cluster} MPA(s) na janela sem cluster — ficam fora do rateio")
    return {"janela": [JANELA_INI, JANELA_FIM], "premissas": premissas,
            "clusters": itens, "semDimensionamento": faltando,
            "semCluster": sem_cluster, "totalMpas": len(jan)}


def _norm_cluster(s):
    import re as _re
    import unicodedata as _ud
    s = _ud.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return _re.sub(r"[^a-z0-9]+", " ", s).strip()


def resumir(manut, bd):
    """Contadores que o painel mostra nos cards (Total/Concluídas/... )."""
    def sit(m):
        os_id = str(m.get("os") or "").strip()
        b = bd.get(os_id) if os_id else None
        if b and b.get("sit"):
            return b["sit"]
        st = (m.get("status") or "").strip().lower()
        if st.startswith("finaliz"):
            return "Concluída"
        if st.startswith("em execu"):
            return "Em andamento"
        return "Não iniciada"
    cont = {}
    for m in manut:
        cont[sit(m)] = cont.get(sit(m), 0) + 1
    return cont


def main():
    ap = argparse.ArgumentParser(description="Gera mpas.json p/ a aba Gestão MPAS")
    ap.add_argument("--sem-api", action="store_true", help="Só Excel, sem consultar o Fracttal")
    ap.add_argument("--cifrar", action="store_true",
                    help="Cifra o conteúdo (só faz sentido com dados sensíveis)")
    ap.add_argument("--claro", action="store_true", help="(compat) grava em claro — é o padrão")
    ap.add_argument("--senha", default=None, help="Senha p/ --cifrar (ou env PCM_MPAS_SENHA)")
    a = ap.parse_args()

    manut, bd = coletar(a.sem_api)
    try:
        if SITE_DIR not in sys.path:
            sys.path.insert(0, SITE_DIR)
        import gerar_calendario_mpas as _G
        compras = ler_compras(manut, _G)
    except Exception as e:
        log(f"  ! bloco de compras não gerado: {type(e).__name__}: {e}")
        compras = None
    payload = {
        "geradoEm": datetime.datetime.now(datetime.timezone.utc)
                    .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fonte": "Gerencial - PCM_2026_R00.xlsx (abas MPAS + Compra Equip MPA 2026) + API Fracttal",
        "manut": manut,
        "bd": bd,
        "compras": compras,
    }
    resumo = resumir(manut, bd)
    log("Situação: " + " | ".join(f"{k}={v}" for k, v in sorted(resumo.items())))

    texto = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    log(f"payload: {len(texto)/1024:.0f} KB")

    if a.cifrar:
        senha = a.senha or os.environ.get("PCM_MPAS_SENHA")
        if not senha:
            try:
                senha = getpass.getpass("Senha do admin (p/ cifrar): ")
            except Exception:
                senha = None
        if not senha:
            log("ERRO: --cifrar exige senha (--senha ou PCM_MPAS_SENHA).")
            return 1
        saida = _cifrar(texto, senha)
        saida["geradoEm"] = payload["geradoEm"]      # fora do cofre: só a data
        saida["itens"] = len(manut)                  # e a contagem (não é sigiloso)
        log(f"cifrado: AES-GCM + PBKDF2 ({PBKDF2_ITER:,} iterações)".replace(",", "."))
        log("   a aba vai PEDIR a senha — use a mesma do login p/ ela abrir sozinha")
    else:
        saida = payload   # padrão: mesmo nível dos demais JSONs do painel

    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
    log(f"OK: {os.path.basename(SAIDA)} ({os.path.getsize(SAIDA)/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
