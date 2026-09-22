# -*- coding: utf-8 -*-
"""
aplicar_overrides_classificacao.py
----------------------------------
Aplica overrides de "Ativo Classificação 2" (cluster correto) no
BD_Relatório Semanal.xlsx, baseado no nome do "Ativo" (coluna B).

Útil quando o Fracttal está com groups_2_description vazio ou errado.
Pode rodar:
  - Direto pelo usuário (após editar o BD)
  - Como pós-processamento depois de gerar_bd_via_api.py
  - Via GUI (botão dedicado)

Regra: match case-insensitive + espaços normalizados.

Uso:
   py -3 aplicar_overrides_classificacao.py
   py -3 aplicar_overrides_classificacao.py --dry-run
"""
from __future__ import annotations
import os, sys, argparse, datetime as dt
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import openpyxl

# ════════════════════════════════════════════════════════════════════
# REGRA PADRÃO — Mapa "Ativo" → cluster correto
# ════════════════════════════════════════════════════════════════════
OVERRIDE_CLASSIFICACAO_2 = {
    "nova xavantina 1 - mt":       "MT Leste 01",
    "nova xavantina 2 - mt":       "MT Leste 01",
    "são josé do egito 1 - pe":    "PE Oeste 01",
    "sao jose do egito 1 - pe":    "PE Oeste 01",
    "são bento 5 - rj":            "RJ Sul 01",
    "sao bento 5 - rj":            "RJ Sul 01",
    "rodrigues 1 - rn":            "RN Sul 01",
    "aparecida 3 - sp":            "SP Leste 01",
    "guaratinguetá 5 - sp":        "SP Leste 01",
    "guaratingueta 5 - sp":        "SP Leste 01",
    "santo inácio 12 - sp":        "SP Leste 04",
    "santo inacio 12 - sp":        "SP Leste 04",
    "salto pirapora 3 - sp":       "SP Leste 02",
    "barretos 1 - sp":             "SP Norte 02",
    "santa bárbara 1 - sp":        "SP Leste 05",
    "santa barbara 1 - sp":        "SP Leste 05",
    "araçoiaba da serra 1 - sp":   "SP Leste 02",
    "aracoiaba da serra 1 - sp":   "SP Leste 02",
    "araçoiaba da serra 2 - sp":   "SP Leste 02",
    "aracoiaba da serra 2 - sp":   "SP Leste 02",
    "elias fausto 1 - sp":         "SP Leste 07",
    "demerval lobão":              "PI Oeste 01",
    "demerval lobao":              "PI Oeste 01",
    "2c - ipixuna do pará 1":     "PA Norte 03",
    "2c - ipixuna do para 1":     "PA Norte 03",
    "axis - linhares 1":          "ES Norte 02",
    "renogrid - elias fausto":    "SP Leste 07",
    "thopen - alto paraná 1":     "PR Oeste 01",
    "thopen - alto parana 1":     "PR Oeste 01",
    "thopen - alto paraná 2":     "PR Oeste 01",
    "thopen - alto parana 2":     "PR Oeste 01",
    "thopen - ipixuna 1 e 2":     "PA Norte 03",
    "thopen - guaratinguetá":              "SP Leste 01",
    "thopen - guaratingueta":              "SP Leste 01",
    # Variantes com prefixo de cliente (formato completo do BD)
    "renogrid - nova xavantina 1 - mt":    "MT Leste 01",
    "renogrid - nova xavantina 2 - mt":    "MT Leste 01",
    "axis - são josé do egito 1 - pe":     "PE Oeste 01",
    "axis - sao jose do egito 1 - pe":     "PE Oeste 01",
    "thopen - são bento 5 - rj":           "RJ Sul 01",
    "thopen - sao bento 5 - rj":           "RJ Sul 01",
    "thopen - rodrigues 1 - rn":           "RN Sul 01",
    "thopen - aparecida 3 - sp":           "SP Leste 01",
    "thopen - guaratinguetá 5 - sp":       "SP Leste 01",
    "thopen - guaratingueta 5 - sp":       "SP Leste 01",
    "thopen - santo inácio 12 - sp":       "SP Leste 04",
    "thopen - santo inacio 12 - sp":       "SP Leste 04",
    "thopen - salto pirapora 3 - sp":      "SP Leste 02",
    "thopen - barretos 1 - sp":            "SP Norte 02",
    "thopen - santa bárbara 1 - sp":       "SP Leste 05",
    "thopen - santa barbara 1 - sp":       "SP Leste 05",
    "thopen - araçoiaba da serra 1 - sp":  "SP Leste 02",
    "thopen - aracoiaba da serra 1 - sp":  "SP Leste 02",
    "thopen - araçoiaba da serra 2 - sp":  "SP Leste 02",
    "thopen - aracoiaba da serra 2 - sp":  "SP Leste 02",
    "renogrid - elias fausto 1 - sp":      "SP Leste 07",
    "greenyellow - demerval lobão 1 - pi": "PI Oeste 01",
    "greenyellow - demerval lobao 1 - pi": "PI Oeste 01",
    "2c - ipixuna do pará 1 - pa":         "PA Norte 03",
    "2c - ipixuna do para 1 - pa":         "PA Norte 03",
    "axis - linhares 1 - es":              "ES Norte 02",
    "thopen - alto paraná 1 - pr":         "PR Oeste 01",
    "thopen - alto parana 1 - pr":         "PR Oeste 01",
    "thopen - alto paraná 2 - pr":         "PR Oeste 01",
    "thopen - alto parana 2 - pr":         "PR Oeste 01",
    "thopen - ipixuna 1 e 2 - pa":         "PA Norte 03",
}


def _log(msg):
    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _norm(s) -> str:
    """Normaliza string pra match: minúsculo, espaços colapsados."""
    if s is None:
        return ""
    return " ".join(str(s).strip().lower().split())


def _detectar_pasta() -> Path:
    env = os.getenv("PCM_PROG_DIR")
    if env and Path(env).exists():
        return Path(env)
    here = Path(__file__).resolve().parent
    if (here / "BD_Relatório Semanal.xlsx").exists():
        return here
    for c in [
        Path.home() / "GRID CO" / "Grid Co. - Gridco" / "4. O&M"
            / "11.Pré-Operação" / "6. PCM" / "09. Programação Semanal",
    ]:
        if c.exists():
            return c
    raise FileNotFoundError("Pasta 09. Programação Semanal não encontrada.")


def aplicar_overrides(path_bd: Path, dry_run: bool = False) -> int:
    """Abre BD, aplica overrides, salva. Retorna número de linhas alteradas."""
    _log(f"Lendo {path_bd.name}...")
    wb = openpyxl.load_workbook(path_bd)
    ws = wb.active   # primeira aba (BD principal)
    _log(f"   Aba: {ws.title} | {ws.max_row} linhas x {ws.max_column} colunas")

    # Descobre índices das colunas pelo cabeçalho da linha 1
    header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    header = [str(c).strip() if c else "" for c in header_row]
    try:
        col_ativo  = header.index("Ativo") + 1                   # 1-based
        col_cls1   = header.index("Ativo Classificação 1") + 1   # fallback
        col_cls2   = header.index("Ativo Classificação 2") + 1
    except ValueError:
        _log(f"ERRO: cabeçalho não tem 'Ativo' ou 'Ativo Classificação 2'.")
        _log(f"   Cabeçalho lido: {header[:15]}...")
        return -1
    _log(f"   Coluna 'Ativo' = {col_ativo}  |  'Ativo Classificação 1' = {col_cls1}  |  'Ativo Classificação 2' = {col_cls2}")

    alteradas = 0
    contagem_por_ativo = {}
    for ridx in range(2, ws.max_row + 1):
        ativo  = ws.cell(row=ridx, column=col_ativo).value
        chave  = _norm(ativo)
        # Fallback: se o Ativo é equipamento (não bateu no dict), tenta Classificação 1
        if not chave or chave not in OVERRIDE_CLASSIFICACAO_2:
            cls1  = ws.cell(row=ridx, column=col_cls1).value
            chave = _norm(cls1)
            if not chave or chave not in OVERRIDE_CLASSIFICACAO_2:
                continue
            label = cls1   # usa Classificação 1 como rótulo no log
        else:
            label = ativo
        novo_valor = OVERRIDE_CLASSIFICACAO_2[chave]
        valor_atual = ws.cell(row=ridx, column=col_cls2).value
        if str(valor_atual or "").strip() == novo_valor:
            continue
        if not dry_run:
            ws.cell(row=ridx, column=col_cls2).value = novo_valor
        alteradas += 1
        contagem_por_ativo[str(label)] = contagem_por_ativo.get(str(label), 0) + 1

    _log(f"   Linhas alteradas: {alteradas}")
    if contagem_por_ativo:
        for at, n in sorted(contagem_por_ativo.items()):
            novo = OVERRIDE_CLASSIFICACAO_2.get(_norm(at), '?')
            _log(f"      {at}: {n} linhas -> {novo}")

    if dry_run:
        _log("DRY-RUN: nada foi salvo.")
        return alteradas

    if alteradas:
        _log("Salvando...")
        wb.save(path_bd)
        _log(f"OK: {path_bd.name} salvo com {alteradas} alterações.")
    else:
        _log("Nenhuma alteração necessária — tudo já está correto.")
    return alteradas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Apenas mostra o que mudaria, sem salvar.")
    parser.add_argument("--arquivo", default="BD_Relatório Semanal.xlsx",
                        help="Nome do arquivo (default: BD_Relatório Semanal.xlsx).")
    args = parser.parse_args()

    pasta = _detectar_pasta()
    _log(f"Pasta: {pasta}")
    path_bd = pasta / args.arquivo
    if not path_bd.exists():
        _log(f"ERRO: {path_bd} não existe.")
        return 2

    _log(f"Overrides configurados: {len(set(OVERRIDE_CLASSIFICACAO_2.keys()))} ativos "
         f"({len(set(OVERRIDE_CLASSIFICACAO_2.values()))} clusters únicos)")
    try:
        n = aplicar_overrides(path_bd, dry_run=args.dry_run)
        return 0 if n >= 0 else 4
    except Exception as e:
        import traceback
        _log(f"FALHA: {type(e).__name__}: {e}")
        _log(traceback.format_exc())
        return 3


if __name__ == "__main__":
    sys.exit(main())
