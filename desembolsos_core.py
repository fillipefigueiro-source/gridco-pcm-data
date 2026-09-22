# -*- coding: utf-8 -*-
"""
Nucleo de leitura/gravacao da aba "Equipamentos - Desembolsos"
do arquivo financeiro (Tabela Excel "Desembolso_de_equipamentos").

- Leitura da lista de usinas: aba AUXILIAR, coluna UFV (via openpyxl, read-only).
- Gravacao: via xlwings (o proprio Excel salva), preservando validacoes,
  formulas de tabela (Cliente/Cluster/MWp/Codigo da compra sao automaticos)
  e demais recursos do workbook.

As parcelas sao gravadas uma por linha, na PRIMEIRA linha vazia da tabela,
mantendo os dados contiguos.
"""
from __future__ import annotations
import calendar
import contextlib
import datetime as _dt
from dataclasses import dataclass, field

SHEET = "Equipamentos - Desembolsos"
TABLE = "Desembolso_de_equipamentos"
AUX_SHEET = "AUXILIAR"
FORN_SHEET = "Fornecedores"
FERR_SHEET = "Ferramentas"

# Mapeamento de colunas (indice relativo dentro da tabela; col 1 = 1a coluna = B)
# Fornecedores (Tabela18): B Fornecedor | C Nome dos vendedores | D Email | E Telefone
#                          | F Atualizado em | G Estado | H Servico | I Avaliacao
FORN_COLS = {"fornecedor": 1, "vendedor": 2, "email": 3, "telefone": 4,
             "atualizado": 5, "estado": 6, "servico": 7, "avaliacao": 8}
FORN_DATE_COL = 5
# Ferramentas (Tabela1820): B Ferramenta | C Nome Vendedores | D Email | E Telefone
#                           | F Atualizado em | G Estado | H Servico | I Avaliacao
FERR_COLS = {"ferramenta": 1, "vendedor": 2, "email": 3, "telefone": 4,
             "atualizado": 5, "estado": 6, "servico": 7, "avaliacao": 8}
FERR_DATE_COL = 5

# Colunas da tabela (indice relativo dentro da tabela; col 1 = coluna B da planilha)
COL_NUM_COMPRA = 1   # B
COL_CLIENTE    = 2   # C  (formula - nao escrever)
COL_USINA      = 3   # D
COL_CLUSTER    = 4   # E  (formula - nao escrever)
COL_MWP        = 5   # F  (formula - nao escrever)
COL_ITEM       = 6   # G
COL_FORNECEDOR = 7   # H
COL_VALOR_TOT  = 8   # I
COL_VALOR_PARC = 9   # J
COL_NUM_PARC   = 10  # K
COL_DATA_PREV  = 11  # L
COL_STATUS     = 12  # M
COL_DATA_PAGTO = 13  # N  (deixar vazio)
COL_CODIGO     = 14  # O
COL_CLASSE     = 15  # P
COL_NF         = 16  # Q  (deixar vazio)
COL_COD_COMPRA = 17  # R  (formula - nao escrever)

STATUS_PADRAO = "Pagamento previsto"


@dataclass
class Parcela:
    numero: int
    valor: float
    data: _dt.date


@dataclass
class Desembolso:
    usina: str
    item: str
    fornecedor: str
    valor_total: float
    codigo: str
    classe: str
    parcelas: list = field(default_factory=list)
    num_compra: int | None = None
    status: str = STATUS_PADRAO
    # preenchidos a partir da AUXILIAR (o app escreve direto, sem depender de formula)
    cliente: str | None = None
    cluster: str | None = None
    mwp: object = None


# --------------------------------------------------------------------------
# Utilidades de data / parcelas
# --------------------------------------------------------------------------
def add_months(d: _dt.date, n: int) -> _dt.date:
    """Soma n meses mantendo o dia (ajusta p/ ultimo dia do mes quando preciso)."""
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    last_day = calendar.monthrange(y, m)[1]
    return _dt.date(y, m, min(d.day, last_day))


def gerar_parcelas_iguais(valor_total: float, n: int, data_inicial: _dt.date) -> list:
    """Divide o total em n parcelas iguais (ajustando centavos na ultima),
    com datas mensais a partir de data_inicial."""
    if n <= 0:
        raise ValueError("Numero de parcelas deve ser >= 1")
    base = round(valor_total / n, 2)
    parcelas = []
    acumulado = 0.0
    for i in range(n):
        if i == n - 1:
            valor = round(valor_total - acumulado, 2)  # ultima absorve o residuo
        else:
            valor = base
            acumulado = round(acumulado + base, 2)
        parcelas.append(Parcela(numero=i + 1, valor=valor, data=add_months(data_inicial, i)))
    return parcelas


def validar_soma(parcelas: list, valor_total: float, tol: float = 0.01) -> bool:
    return abs(sum(p.valor for p in parcelas) - valor_total) <= tol


_EPOCH_EXCEL = _dt.date(1899, 12, 30)  # base serial do Excel (Windows)


def data_para_serial(d: _dt.date) -> int:
    """Converte uma data no numero serial do Excel (inteiro, sem hora).
    Evita qualquer conversao de fuso horario ao gravar via COM."""
    return (d - _EPOCH_EXCEL).days


# --------------------------------------------------------------------------
# Leitura (openpyxl, read-only)
# --------------------------------------------------------------------------
def carregar_usinas(path: str) -> list:
    """Retorna lista ordenada de usinas (UFV) da aba AUXILIAR."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[AUX_SHEET]
        usinas = set()
        # UFV = coluna B (2); dados a partir da linha 5
        for row in ws.iter_rows(min_row=5, min_col=2, max_col=2, values_only=True):
            v = row[0]
            if v is not None and str(v).strip():
                usinas.add(str(v).strip())
        return sorted(usinas, key=lambda s: s.lower())
    finally:
        wb.close()


def proximo_num_compra(path: str) -> int:
    """Le a aba de desembolsos e devolve (max Nº da compra) + 1."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[SHEET]
        maxc = 0
        # coluna B (Nº da compra) = 2; dados a partir da linha 5
        for row in ws.iter_rows(min_row=5, min_col=2, max_col=2, values_only=True):
            v = row[0]
            try:
                maxc = max(maxc, int(v))
            except (TypeError, ValueError):
                pass
        return maxc + 1
    finally:
        wb.close()


def _carregar_coluna(path: str, sheet: str, col: int = 2, start_row: int = 5) -> list:
    """Lista ordenada de valores nao vazios de uma coluna de uma aba."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[sheet]
        vals = set()
        for row in ws.iter_rows(min_row=start_row, min_col=col, max_col=col, values_only=True):
            v = row[0]
            if v is not None and str(v).strip():
                vals.add(str(v).strip())
        return sorted(vals, key=lambda s: s.lower())
    finally:
        wb.close()


def carregar_fornecedores(path: str) -> list:
    """Lista de fornecedores (aba Fornecedores, coluna B)."""
    return _carregar_coluna(path, FORN_SHEET, col=2)


def carregar_ferramentas(path: str) -> list:
    """Lista de ferramentas (aba Ferramentas, coluna B)."""
    return _carregar_coluna(path, FERR_SHEET, col=2)


def valores_distintos(path: str, coluna_letra: str) -> list:
    """Valores distintos ja usados numa coluna (p/ sugerir Codigo/Classe)."""
    import openpyxl
    from openpyxl.utils import column_index_from_string
    col = column_index_from_string(coluna_letra)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[SHEET]
        vistos = []
        for row in ws.iter_rows(min_row=5, min_col=col, max_col=col, values_only=True):
            v = row[0]
            if v is not None and str(v).strip() and str(v) not in vistos:
                vistos.append(str(v))
        return vistos
    finally:
        wb.close()


# --------------------------------------------------------------------------
# Gravacao (xlwings)
# --------------------------------------------------------------------------
@contextlib.contextmanager
def _com():
    """Inicializa o COM na thread atual (necessario p/ xlwings fora da main thread)."""
    try:
        import pythoncom
    except Exception:
        pythoncom = None
    if pythoncom is not None:
        pythoncom.CoInitialize()
    try:
        yield
    finally:
        if pythoncom is not None:
            pythoncom.CoUninitialize()


def _com_thread(fn):
    """Decorator: garante COM inicializado na thread (p/ xlwings em worker threads)."""
    import functools

    @functools.wraps(fn)
    def wrapper(*a, **k):
        with _com():
            return fn(*a, **k)
    return wrapper


def _ler_coluna(bk, sheet, col=2, start=5):
    """Le uma coluna inteira (valores nao vazios) de uma aba do workbook aberto (xlwings)."""
    if sheet not in [s.name for s in bk.sheets]:
        return []
    sht = bk.sheets[sheet]
    api = sht.api
    last = api.Cells(api.Rows.Count, col).End(-4162).Row  # -4162 = xlUp
    if last < start:
        return []
    vals = sht.range((start, col), (last, col)).value
    if not isinstance(vals, list):
        vals = [vals]
    out = []
    for v in vals:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            out.append(s)
    return out


def _coluna_openpyxl(wb, sheet, col=2, start=5):
    if sheet not in wb.sheetnames:
        return []
    ws = wb[sheet]
    out = []
    for row in ws.iter_rows(min_row=start, min_col=col, max_col=col, values_only=True):
        v = row[0]
        if v is not None and str(v).strip():
            out.append(str(v).strip())
    return out


def _mapa_openpyxl(wb):
    """Mapa usina -> (cliente, cluster, mwp) lido da AUXILIAR
    (B=UFV, E=Cliente, F=Equipe Cluster, H=Capacidade MWp)."""
    m = {}
    if AUX_SHEET not in wb.sheetnames:
        return m
    ws = wb[AUX_SHEET]
    for row in ws.iter_rows(min_row=5, min_col=2, max_col=8, values_only=True):
        ufv = row[0]  # B
        if ufv is not None and str(ufv).strip():
            cliente = row[3]  # E
            cluster = row[4]  # F
            mwp = row[6]      # H
            m[str(ufv).strip()] = (cliente, cluster, mwp)
    return m


def _carregar_tudo_openpyxl(path):
    """Leitura rapida via openpyxl (funciona com o arquivo FECHADO)."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        usinas = sorted(set(_coluna_openpyxl(wb, AUX_SHEET)), key=lambda s: s.lower())
        forns = sorted(set(_coluna_openpyxl(wb, FORN_SHEET)), key=lambda s: s.lower())
        ferrs = sorted(set(_coluna_openpyxl(wb, FERR_SHEET)), key=lambda s: s.lower())
        mapa = _mapa_openpyxl(wb)
        maxc = 0
        for v in _coluna_openpyxl(wb, SHEET):
            try:
                maxc = max(maxc, int(float(v)))
            except (ValueError, TypeError):
                pass
        return {"usinas": usinas, "fornecedores": forns,
                "ferramentas": ferrs, "proximo": maxc + 1, "mapa": mapa}
    finally:
        wb.close()


def _carregar_tudo_xlwings(path):
    """Leitura anexando ao Excel aberto (usada quando o openpyxl falha por lock)."""
    with _com():
        app, bk, we_opened = _abrir_ou_anexar(path, read_only=True)
        try:
            usinas = sorted(set(_ler_coluna(bk, AUX_SHEET, 2)), key=lambda s: s.lower())
            forns = sorted(set(_ler_coluna(bk, FORN_SHEET, 2)), key=lambda s: s.lower())
            ferrs = sorted(set(_ler_coluna(bk, FERR_SHEET, 2)), key=lambda s: s.lower())
            maxc = 0
            for v in _ler_coluna(bk, SHEET, 2):
                try:
                    maxc = max(maxc, int(float(v)))
                except (ValueError, TypeError):
                    pass
            mapa = {}
            aux = bk.sheets[AUX_SHEET].api
            last = aux.Cells(aux.Rows.Count, 2).End(-4162).Row
            if last >= 5:
                dados = bk.sheets[AUX_SHEET].range((5, 2), (last, 8)).value
                if not isinstance(dados, list):
                    dados = [dados]
                for lin in dados:
                    if isinstance(lin, list) and lin and lin[0] and str(lin[0]).strip():
                        mapa[str(lin[0]).strip()] = (lin[3], lin[4], lin[6])
            return {"usinas": usinas, "fornecedores": forns,
                    "ferramentas": ferrs, "proximo": maxc + 1, "mapa": mapa}
        finally:
            if we_opened:
                try:
                    bk.close()
                    app.quit()
                except Exception:
                    pass


def _copia_temp(path):
    """Copia o arquivo p/ uma pasta temp (funciona mesmo com o Excel aberto,
    pois o Excel compartilha leitura). Retorna o caminho da copia."""
    import shutil, tempfile, os
    tmp = os.path.join(tempfile.gettempdir(), "_pcm_leitura" + os.path.splitext(path)[1])
    shutil.copy2(path, tmp)
    return tmp


def carregar_tudo(path):
    """Le usinas, fornecedores, ferramentas e o proximo Nº da compra, sem travar
    mesmo com o arquivo ABERTO no Excel:
    1) openpyxl direto (rapido, arquivo fechado);
    2) copia p/ temp + openpyxl (arquivo aberto — nao toca no Excel);
    3) ultimo recurso: anexa a instancia aberta via xlwings."""
    try:
        return _carregar_tudo_openpyxl(path)
    except Exception:
        pass
    try:
        return _carregar_tudo_openpyxl(_copia_temp(path))
    except Exception:
        pass
    return _carregar_tudo_xlwings(path)


def _lista_openpyxl(path, sheet, col=2):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        return sorted(set(_coluna_openpyxl(wb, sheet, col)), key=lambda s: s.lower())
    finally:
        wb.close()


def carregar_lista(path, sheet, col=2):
    """Le uma unica coluna (p/ atualizar dropdown apos cadastro)."""
    try:
        return _lista_openpyxl(path, sheet, col)
    except Exception:
        pass
    try:
        return _lista_openpyxl(_copia_temp(path), sheet, col)
    except Exception:
        pass
    with _com():
        app, bk, we_opened = _abrir_ou_anexar(path, read_only=True)
        try:
            return sorted(set(_ler_coluna(bk, sheet, col)), key=lambda s: s.lower())
        finally:
            if we_opened:
                try:
                    bk.close()
                    app.quit()
                except Exception:
                    pass


def _abrir_ou_anexar(path, read_only=False):
    """Se o arquivo ja estiver aberto no Excel, anexa a essa instancia;
    senao abre uma instancia invisivel. Retorna (app, bk, we_opened).

    Casa primeiro pelo NOME do arquivo (robusto p/ arquivos do SharePoint/OneDrive,
    cujo FullName vem como URL e nao bate com o caminho local).
    read_only: ao abrir por conta propria, abre em somente-leitura (mais rapido e
    evita travar em avisos de 'arquivo bloqueado')."""
    import os
    import xlwings as xw
    alvo_nome = os.path.basename(path).lower()
    alvo_full = os.path.normcase(os.path.abspath(path))
    def _silenciar(a):
        # evita dialogos que travam o COM (avisos de link externo, etc.)
        for prop, val in (("DisplayAlerts", False), ("AskToUpdateLinks", False),
                          ("EnableEvents", False)):
            try:
                setattr(a.api, prop, val)
            except Exception:
                pass

    for app in xw.apps:
        for bk in app.books:
            try:
                if bk.name.lower() == alvo_nome:
                    _silenciar(app)
                    return app, bk, False
            except Exception:
                pass
            try:
                if os.path.normcase(os.path.abspath(bk.fullname)) == alvo_full:
                    _silenciar(app)
                    return app, bk, False
            except Exception:
                pass
    app = xw.App(visible=False)
    app.display_alerts = False
    app.screen_updating = False
    try:
        app.api.AskToUpdateLinks = False
    except Exception:
        pass
    bk = app.books.open(path, update_links=False, read_only=read_only)
    return app, bk, True


def _finalizar(app, bk, we_opened):
    """Salva. Com AutoSave (OneDrive) o save do COM pode falhar — nesse caso o
    AutoSave ja persiste as celulas, entao o erro e ignorado. Fecha/encerra so
    se fomos nos que abrimos o arquivo."""
    try:
        bk.save()
    except Exception:
        pass
    if we_opened:
        try:
            bk.close()
            app.quit()
        except Exception:
            pass


def _primeira_linha_vazia(sht, tbl, key_rel_col: int = 1):
    """(linha, base_col) da 1a linha vazia da tabela (pela coluna-chave).
    Se nao houver, adiciona uma nova ListRow."""
    nrows = tbl.ListRows.Count
    first = tbl.HeaderRowRange.Row + 1
    last = first + nrows - 1
    base_col = tbl.HeaderRowRange.Column
    key_abs = base_col + key_rel_col - 1
    vals = sht.range((first, key_abs), (last, key_abs)).value
    if not isinstance(vals, list):
        vals = [vals]
    for i, v in enumerate(vals):
        if v is None or str(v).strip() == "":
            return first + i, base_col
    nova = tbl.ListRows.Add()
    return nova.Range.Row, base_col


@_com_thread
def cadastrar_em_tabela(path: str, sheet: str, campos: dict, date_rel_col: int | None = None) -> dict:
    """Insere um registro na (unica) tabela de 'sheet', na 1a linha vazia.
    campos: {rel_col: valor}. date_rel_col: coluna a preencher com a data de hoje
    (formato serial), se ainda nao vier em 'campos'."""
    app, bk, we_opened = _abrir_ou_anexar(path)
    try:
        sht = bk.sheets[sheet]
        tbl = sht.api.ListObjects(1)
        linha, base_col = _primeira_linha_vazia(sht, tbl, key_rel_col=1)
        if date_rel_col is not None and date_rel_col not in campos:
            campos = dict(campos)
            campos[date_rel_col] = _dt.date.today()
        for rel_col, valor in campos.items():
            if valor is None or valor == "":
                continue
            cel = sht.api.Cells(linha, base_col + rel_col - 1)
            if isinstance(valor, _dt.date):
                fmt = cel.NumberFormat
                cel.Value = data_para_serial(valor)
                if not fmt or fmt in ("General", "Geral"):
                    cel.NumberFormat = "dd/mm/yyyy"
            else:
                cel.Value = valor
        _finalizar(app, bk, we_opened)
        return {"sheet": sheet, "linha": linha}
    except Exception:
        if we_opened:
            try:
                bk.close(); app.quit()
            except Exception:
                pass
        raise


def cadastrar_fornecedor(path, fornecedor, vendedor="", email="", telefone="", estado="", servico="", avaliacao=""):
    campos = {
        FORN_COLS["fornecedor"]: fornecedor, FORN_COLS["vendedor"]: vendedor,
        FORN_COLS["email"]: email, FORN_COLS["telefone"]: telefone,
        FORN_COLS["estado"]: estado, FORN_COLS["servico"]: servico,
        FORN_COLS["avaliacao"]: avaliacao,
    }
    return cadastrar_em_tabela(path, FORN_SHEET, campos, date_rel_col=FORN_DATE_COL)


def cadastrar_ferramenta(path, ferramenta, vendedor="", email="", telefone="", estado="", servico="", avaliacao=""):
    campos = {
        FERR_COLS["ferramenta"]: ferramenta, FERR_COLS["vendedor"]: vendedor,
        FERR_COLS["email"]: email, FERR_COLS["telefone"]: telefone,
        FERR_COLS["estado"]: estado, FERR_COLS["servico"]: servico,
        FERR_COLS["avaliacao"]: avaliacao,
    }
    return cadastrar_em_tabela(path, FERR_SHEET, campos, date_rel_col=FERR_DATE_COL)


@_com_thread
def gravar_desembolso(path: str, d: Desembolso) -> dict:
    """
    Grava as parcelas do desembolso 'd' na tabela, na primeira linha vazia.
    Retorna dict com resumo. Preserva o workbook (Excel faz o save).
    """
    if not d.parcelas:
        raise ValueError("Nenhuma parcela para gravar.")
    if not validar_soma(d.parcelas, d.valor_total):
        raise ValueError("A soma das parcelas nao confere com o Valor previsto total.")

    app, bk, we_opened = _abrir_ou_anexar(path)
    try:
        if True:
            sht = bk.sheets[SHEET]
            tbl = sht.api.ListObjects(TABLE)
            nrows = tbl.ListRows.Count
            first_body_row = tbl.HeaderRowRange.Row + 1  # normalmente 5
            last_body_row = first_body_row + nrows - 1

            # le colunas B (Nº compra) e D (Usina) de todo o corpo em uma chamada
            # para achar a primeira linha realmente vazia
            colB = tbl.ListColumns(COL_NUM_COMPRA).Range.Column
            colD = tbl.ListColumns(COL_USINA).Range.Column
            b_vals = sht.range((first_body_row, colB), (last_body_row, colB)).value
            d_vals = sht.range((first_body_row, colD), (last_body_row, colD)).value
            if not isinstance(b_vals, list):
                b_vals = [b_vals]
                d_vals = [d_vals]

            free_rows = []
            for i in range(nrows):
                bv = b_vals[i]
                dv = d_vals[i]
                vazio = (bv is None or str(bv).strip() == "") and \
                        (dv is None or str(dv).strip() == "")
                if vazio:
                    free_rows.append(first_body_row + i)

            necessarias = len(d.parcelas)
            # garante linhas suficientes (senao adiciona ao final da tabela)
            while len(free_rows) < necessarias:
                nova = tbl.ListRows.Add()
                free_rows.append(nova.Range.Row)

            alvo = sorted(free_rows)[:necessarias]

            base_col = tbl.HeaderRowRange.Column  # coluna da 1a coluna da tabela (B=2)
            # formato de data usado nas linhas existentes (p/ manter padrao da planilha)
            try:
                date_fmt = sht.api.Cells(first_body_row, base_col + COL_DATA_PREV - 1).NumberFormat
                if not date_fmt or date_fmt in ("General", "Geral"):
                    date_fmt = "dd/mm/yyyy"
            except Exception:
                date_fmt = "dd/mm/yyyy"

            for parc, linha in zip(d.parcelas, alvo):

                def put(rel_col, value):
                    sht.api.Cells(linha, base_col + rel_col - 1).Value = value

                put(COL_NUM_COMPRA, d.num_compra)
                put(COL_USINA, d.usina)
                # Cliente/Cluster/MWp/Codigo-da-compra escritos direto (a planilha
                # oficial nao tem as formulas XLOOKUP funcionando)
                if d.cliente is not None:
                    put(COL_CLIENTE, d.cliente)
                if d.cluster is not None:
                    put(COL_CLUSTER, d.cluster)
                if d.mwp is not None:
                    put(COL_MWP, d.mwp)
                put(COL_COD_COMPRA, f"{d.num_compra} - {d.usina}")
                put(COL_ITEM, d.item)
                put(COL_FORNECEDOR, d.fornecedor)
                put(COL_VALOR_TOT, d.valor_total)
                put(COL_VALOR_PARC, parc.valor)
                put(COL_NUM_PARC, parc.numero)
                # data como serial + formato de data (imune a fuso horario)
                cel_data = sht.api.Cells(linha, base_col + COL_DATA_PREV - 1)
                cel_data.Value = data_para_serial(parc.data)
                cel_data.NumberFormat = date_fmt
                put(COL_STATUS, d.status)
                put(COL_CODIGO, d.codigo)
                put(COL_CLASSE, d.classe)

            _finalizar(app, bk, we_opened)
            return {
                "num_compra": d.num_compra,
                "usina": d.usina,
                "parcelas": necessarias,
                "linhas": alvo,
                "valor_total": d.valor_total,
            }
    except Exception:
        if we_opened:
            try:
                bk.close(); app.quit()
            except Exception:
                pass
        raise
