# -*- coding: utf-8 -*-
"""
gerar_supervisores_json.py
--------------------------
Lê BD_Operacoes.xlsx (aba 'Supervisores') e gera supervisores.json
no formato esperado pelo index.html — mapa cluster → supervisor.

Saída: supervisores.json
{
  "geradoEm": "...",
  "porCluster": {"MA Leste 02": "Pedro Candido", "MT Sul 01": "Tiago Nascimento", ...},
  "lista": ["Pedro Candido", "Tiago Nascimento", ...]
}

Uso:
   py -3 gerar_supervisores_json.py
"""
from __future__ import annotations
import os, sys, json, datetime as dt
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import openpyxl


def _log(msg):
    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _detectar_pasta_prog() -> Path:
    env = os.getenv("PCM_PROG_DIR")
    if env and Path(env).exists():
        return Path(env)
    here = Path(__file__).resolve().parent
    if (here / "gerar_pcm_json.py").exists():
        return here
    for c in [
        Path.home() / "GRID CO" / "Grid Co. - Gridco" / "4. O&M"
            / "11.Pré-Operação" / "6. PCM" / "09. Programação Semanal",
    ]:
        if c.exists():
            return c
    raise FileNotFoundError("Pasta 09. Programação Semanal não encontrada.")


def _detectar_bd_operacoes() -> Path:
    # 15/09/2026: o BD mudou para `17. Backoffice`. O antigo continua no disco com uma
    # cópia velha — por isso o Backoffice vem PRIMEIRO, e o 6.Gerencial fica só como recuo.
    candidates = [
        Path(os.environ["BD_OPERACOES_PATH"]) if os.environ.get("BD_OPERACOES_PATH") else None,
        Path.home() / "GRID CO" / "Grid Co. - Gridco" / "4. O&M"
            / "17. Backoffice" / "4. Gestão à vista" / "1. Banco de Dados" / "BD_Operacoes.xlsx",
        Path.home() / "GRID CO" / "Grid Co. - Gridco" / "4. O&M"
            / "6.Gerencial" / "4. Gestão à vista" / "1. Banco de Dados" / "BD_Operacoes.xlsx",
        Path("/sessions/happy-keen-galileo/mnt/1. Banco de Dados/BD_Operacoes.xlsx"),
    ]
    for c in candidates:
        if c and c.exists():
            return c
    raise FileNotFoundError("BD_Operacoes.xlsx não encontrado.")


def main():
    pasta_out = _detectar_pasta_prog()
    bd_op = _detectar_bd_operacoes()
    _log(f"Pasta saida: {pasta_out}")
    _log(f"BD_Operacoes: {bd_op}")

    wb = openpyxl.load_workbook(bd_op, read_only=True, data_only=True)
    if "Operações" not in wb.sheetnames:
        _log("ERRO: aba 'Operações' nao existe em BD_Operacoes.xlsx")
        sys.exit(1)
    ws = wb["Operações"]

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        _log("ERRO: aba vazia")
        sys.exit(1)

    # Cabeçalho: col 40=CLUSTER, col 41=Equipe Cluster, col 45=RESPONSÁVEL O&M
    header = [str(c).strip() if c is not None else "" for c in rows[0]]
    _log(f"Colunas usadas: [{40}]={header[40]}  [{41}]={header[41]}  [{45}]={header[45]}")
    try:
        idx_cluster  = header.index("CLUSTER")           # Ativo Classificação 2
        idx_equipe   = header.index("Equipe Cluster")    # Ativo Classificação 1
        idx_sup      = header.index("RESPONSÁVEL O&M")   # supervisor
    except ValueError as e:
        _log(f"ERRO: coluna não encontrada: {e}")
        _log(f"  Cabeçalho: {header[:50]}")
        sys.exit(1)

    por_cluster: dict[str, str] = {}   # chave completa (Equipe Cluster = r.cluster no dashboard)
    por_equipe:  dict[str, str] = {}   # mesmo mapa, alias para compatibilidade
    for r in rows[1:]:
        if not r:
            continue
        sup    = str(r[idx_sup]   or "").strip()
        equipe = str(r[idx_equipe] or "").strip()  # "SP Leste 05" — chave usada no dashboard
        if not sup or not equipe:
            continue
        if equipe not in por_cluster:
            por_cluster[equipe] = sup
        if equipe not in por_equipe:
            por_equipe[equipe] = sup

    lista = sorted(set(por_cluster.values()) | set(por_equipe.values()))

    out = {
        "geradoEm":   dt.datetime.now().isoformat(timespec="seconds"),
        "porCluster": por_cluster,   # Ativo Classificação 2 → supervisor
        "porEquipe":  por_equipe,    # Ativo Classificação 1 → supervisor
        "lista":      lista,
    }

    out_path = pasta_out / "supervisores.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"OK: {out_path}")
    _log(f"   {len(por_cluster)} clusters | {len(por_equipe)} equipes | {len(lista)} supervisores únicos")
    _log(f"   Supervisores: {', '.join(lista)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log(f"FALHA: {e}")
        sys.exit(1)
