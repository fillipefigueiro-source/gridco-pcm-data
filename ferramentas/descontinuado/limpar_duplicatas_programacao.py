# -*- coding: utf-8 -*-
"""
limpar_duplicatas_programacao.py
--------------------------------
Remove linhas duplicadas (mesma OSs ID + Tarefa + Dia + Hora Início) das abas
de equipe de um arquivo Programação Semana XX.xlsx. Mantém a 1ª ocorrência.

Faz backup antes em _backup_BD/<nome>_<timestamp>.xlsx.

Uso:
   py -3 limpar_duplicatas_programacao.py                          # auto-detecta semana atual
   py -3 limpar_duplicatas_programacao.py --arquivo "Programação Semana 24.xlsx"
   py -3 limpar_duplicatas_programacao.py --semana 24
   py -3 limpar_duplicatas_programacao.py --dry-run                # só conta, não modifica
"""
from __future__ import annotations
import os, sys, argparse, shutil, datetime as dt
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import openpyxl


def _detectar_pasta() -> Path:
    env = os.getenv("PCM_PROG_DIR")
    if env and Path(env).exists():
        return Path(env)
    here = Path(__file__).resolve().parent
    if (here / "atualizacao_semanal.py").exists():
        return here
    for c in [
        Path.home() / "GRID CO" / "Grid Co. - Gridco" / "4. O&M"
            / "11.Pré-Operação" / "6. PCM" / "09. Programação Semanal",
    ]:
        if c.exists():
            return c
    raise FileNotFoundError("Pasta PCM não encontrada.")


def _log(msg):
    ts = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _backup(path: Path) -> Path:
    backup_dir = path.parent / "_backup_BD"
    backup_dir.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"{path.stem}_{stamp}{path.suffix}"
    shutil.copy2(path, dest)
    return dest


def limpar(path: Path, dry_run: bool = False) -> dict:
    _log(f"Abrindo {path.name}...")
    wb = openpyxl.load_workbook(path)
    resumo = {"total_antes": 0, "total_depois": 0, "removidas": 0, "abas": {}}

    for sheet_name in wb.sheetnames:
        if sheet_name.startswith("_"):
            continue
        ws = wb[sheet_name]
        if ws.max_row < 2:
            continue
        header = [c.value for c in ws[1]]
        col = {h: i for i, h in enumerate(header) if h}

        def idx(name):
            return col.get(name)

        i_os = idx("OSs ID")
        if i_os is None:
            continue
        i_tarefa = idx("Tarefa")
        i_dia = idx("Dia")
        i_hi = idx("Hora Início")
        i_status = idx("Status Atual (BD)")
        i_estado_antes = idx("Estado Tarefa (antes)")

        # Identifica linhas duplicadas OU com status Cancelada/Finalizada
        seen = set()
        linhas_a_apagar = []  # números das linhas (1-based)
        total_linhas = 0
        for r in range(2, ws.max_row + 1):
            v_os = ws.cell(row=r, column=i_os + 1).value
            if v_os in (None, "", 0):
                continue
            total_linhas += 1
            # Marca pra apagar se Cancelada/Finalizada (em qualquer coluna de status)
            cancelada = False
            for ix_st in (i_status, i_estado_antes):
                if ix_st is not None:
                    v_st = ws.cell(row=r, column=ix_st + 1).value
                    if isinstance(v_st, str):
                        s_low = v_st.lower()
                        if "cancelad" in s_low:
                            cancelada = True
                            break
            if cancelada:
                linhas_a_apagar.append(r)
                continue
            chave_parts = [str(v_os)]
            for ix in (i_tarefa, i_dia, i_hi):
                if ix is not None:
                    val = ws.cell(row=r, column=ix + 1).value
                    chave_parts.append(str(val) if val else "")
            chave = "|".join(chave_parts)
            if chave in seen:
                linhas_a_apagar.append(r)
            else:
                seen.add(chave)

        resumo["total_antes"] += total_linhas
        resumo["total_depois"] += total_linhas - len(linhas_a_apagar)
        resumo["removidas"] += len(linhas_a_apagar)
        resumo["abas"][sheet_name] = {
            "antes": total_linhas, "depois": total_linhas - len(linhas_a_apagar),
            "removidas": len(linhas_a_apagar),
        }

        if linhas_a_apagar and not dry_run:
            # Apaga de baixo pra cima pra não invalidar índices
            for r in sorted(linhas_a_apagar, reverse=True):
                ws.delete_rows(r, 1)

        if linhas_a_apagar:
            _log(f"  {sheet_name}: {total_linhas} → {total_linhas - len(linhas_a_apagar)}  ({len(linhas_a_apagar)} removidas — duplicadas/canceladas)")

    if not dry_run and resumo["removidas"] > 0:
        bkp = _backup(path)
        _log(f"Backup criado: {bkp.name}")
        wb.save(path)
        _log(f"Salvo: {path.name}")
    elif dry_run:
        _log("DRY-RUN: nada foi salvo.")

    return resumo


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--arquivo", help="caminho ou nome do arquivo (default: semana atual)")
    p.add_argument("--semana", type=int, help="número ISO da semana (ex: 24)")
    p.add_argument("--dry-run", action="store_true", help="só conta, não modifica")
    args = p.parse_args()

    pasta = _detectar_pasta()
    _log(f"Pasta: {pasta}")

    if args.arquivo:
        path = Path(args.arquivo)
        if not path.is_absolute():
            path = pasta / path
    elif args.semana:
        path = pasta / f"Programação Semana {args.semana:02d}.xlsx"
    else:
        # Semana atual
        hoje = dt.date.today()
        mon = hoje - dt.timedelta(days=hoje.weekday())
        _, iso_w, _ = mon.isocalendar()
        path = pasta / f"Programação Semana {iso_w:02d}.xlsx"

    if not path.exists():
        _log(f"ERRO: {path} não existe.")
        return 1

    resumo = limpar(path, dry_run=args.dry_run)
    _log("=" * 60)
    _log(f"RESUMO {'(DRY-RUN)' if args.dry_run else ''}")
    _log(f"  Total antes:    {resumo['total_antes']}")
    _log(f"  Total depois:   {resumo['total_depois']}")
    _log(f"  Removidas:      {resumo['removidas']}")
    _log("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
