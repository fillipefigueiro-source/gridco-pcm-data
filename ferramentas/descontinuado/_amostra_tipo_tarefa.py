# -*- coding: utf-8 -*-
"""
_amostra_tipo_tarefa.py
-----------------------
Lê BD_Relatório Semanal.xlsx e amostra valores únicos das colunas:
  - Tipo de tarefa
  - Estado da Tarefa
Plus: distribuição de "Tipo de tarefa" pra OSs com "religamento" na Tarefa.

Uso:
   py -3 _amostra_tipo_tarefa.py > tipos.txt
   notepad tipos.txt
"""
from __future__ import annotations
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import openpyxl

BASE = Path(__file__).resolve().parent
xlsx = BASE / "BD_Relatório Semanal.xlsx"
if not xlsx.exists():
    print(f"ERRO: {xlsx} não encontrado")
    sys.exit(1)

print(f"Lendo {xlsx.name}...")
wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
ws = wb["Semanal"]
rows_iter = ws.iter_rows(values_only=True)
header = list(next(rows_iter))
print(f"Colunas do header: {len(header)}")

def idx(name):
    try:
        return header.index(name)
    except ValueError:
        return None

idx_tt = idx("Tipo de tarefa")
idx_tarefa = idx("Tarefa")
idx_estado = idx("Estado da Tarefa")

if idx_tt is None:
    print("ERRO: coluna 'Tipo de tarefa' não encontrada")
    print(f"Header: {header}")
    sys.exit(1)

cnt_tt = Counter()
cnt_estado = Counter()
cnt_tt_relig = Counter()  # tipo de tarefa entre OSs com 'religamento' no texto

total = 0
for r in rows_iter:
    total += 1
    v_tt = r[idx_tt] if idx_tt < len(r) else None
    if v_tt:
        cnt_tt[str(v_tt).strip()] += 1
    v_est = r[idx_estado] if idx_estado is not None and idx_estado < len(r) else None
    if v_est:
        cnt_estado[str(v_est).strip()] += 1
    if idx_tarefa is not None:
        v_t = r[idx_tarefa] if idx_tarefa < len(r) else None
        if v_t and "religamento" in str(v_t).lower():
            cnt_tt_relig[str(v_tt or "(sem)")] += 1

print(f"\nTotal linhas: {total}")
print()
print("=" * 70)
print("VALORES ÚNICOS DE 'Tipo de tarefa' (ordenados por frequência)")
print("=" * 70)
for k, n in cnt_tt.most_common(50):
    print(f"  {n:7d}  {k!r}")

print()
print("=" * 70)
print("VALORES ÚNICOS DE 'Estado da Tarefa'")
print("=" * 70)
for k, n in cnt_estado.most_common(20):
    print(f"  {n:7d}  {k!r}")

print()
print("=" * 70)
print("Tipo de tarefa das OSs com 'religamento' na descrição (top 15)")
print("=" * 70)
for k, n in cnt_tt_relig.most_common(15):
    print(f"  {n:7d}  {k!r}")
