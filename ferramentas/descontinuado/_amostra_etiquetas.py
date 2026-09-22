# -*- coding: utf-8 -*-
"""
_amostra_etiquetas.py
---------------------
Lê BD_Relatório Semanal.xlsx, aba Semanal, coluna Etiquetas, e imprime
um resumo: valores únicos + contagem por valor + tabela cruzada com
Estado da Tarefa (status).

Cole o output completo no chat pra eu mapear as 5 tipologias.

Uso:
   py -3 _amostra_etiquetas.py
"""
from __future__ import annotations
import os, sys, json, collections
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
print("Abas disponíveis:", wb.sheetnames)
ws = wb["Semanal"] if "Semanal" in wb.sheetnames else wb[wb.sheetnames[0]]

# Header
rows_iter = ws.iter_rows(values_only=True)
header = list(next(rows_iter))
print(f"Aba: '{ws.title}', cols: {len(header)}")

def idx_of(name):
    try:
        return header.index(name)
    except ValueError:
        return None

idx_etq = idx_of("Etiquetas")
idx_est = idx_of("Estado da Tarefa")
idx_cls = idx_of("Cluster") or idx_of("Equipe PCM") or idx_of("Equipe")
print(f"Etiquetas col idx = {idx_etq}")
print(f"Estado da Tarefa col idx = {idx_est}")
print(f"Equipe/Cluster col idx = {idx_cls}")
print()

if idx_etq is None:
    print("ERRO: coluna 'Etiquetas' não encontrada no header.")
    print("Header completo:", header)
    sys.exit(1)

# Conta valores brutos
brutos = collections.Counter()
# Tabela cruzada etiqueta x estado
cruzada = collections.defaultdict(lambda: collections.Counter())
# Por equipe
por_equipe = collections.defaultdict(lambda: collections.Counter())

total = 0
for r in rows_iter:
    total += 1
    raw = r[idx_etq] if idx_etq is not None else None
    if not raw:
        continue
    s = str(raw).strip()
    if not s:
        continue
    # A coluna pode vir como JSON list ou string simples
    valores = []
    if s.startswith("[") and s.endswith("]"):
        try:
            j = json.loads(s)
            if isinstance(j, list):
                valores = [str(x).strip() for x in j if x]
            else:
                valores = [str(j).strip()]
        except Exception:
            valores = [s]
    elif "," in s:
        valores = [v.strip() for v in s.split(",") if v.strip()]
    elif ";" in s:
        valores = [v.strip() for v in s.split(";") if v.strip()]
    else:
        valores = [s]

    estado = (r[idx_est] if idx_est is not None else "") or ""
    equipe = (r[idx_cls] if idx_cls is not None else "") or ""
    for v in valores:
        brutos[v] += 1
        cruzada[v][estado] += 1
        por_equipe[v][equipe] += 1

print(f"Total de linhas no BD: {total}")
print(f"Linhas com Etiquetas preenchidas: {sum(brutos.values())}")
print()
print("=" * 70)
print("VALORES ÚNICOS DE ETIQUETAS (ordenados por frequência):")
print("=" * 70)
for tag, n in brutos.most_common():
    print(f"  {n:6d}  {tag!r}")

print()
print("=" * 70)
print("TABELA CRUZADA: Etiqueta x Estado da Tarefa")
print("=" * 70)
estados_todos = sorted({e for c in cruzada.values() for e in c.keys()})
print(f"{'Etiqueta':40s}  " + "  ".join(f"{e[:14]:>14s}" for e in estados_todos))
print("-" * (42 + 16 * len(estados_todos)))
for tag, _ in brutos.most_common(30):
    row = [f"{cruzada[tag].get(e, 0):14d}" for e in estados_todos]
    print(f"{tag[:40]:40s}  " + "  ".join(row))

print()
print("=" * 70)
print("TOP 5 EQUIPES por etiqueta (Top 10 etiquetas):")
print("=" * 70)
for tag, _ in brutos.most_common(10):
    print(f"\n{tag}:")
    for eq, n in por_equipe[tag].most_common(5):
        print(f"  {n:5d}  {eq}")
