# -*- coding: utf-8 -*-
"""
atualizar_mpas.py — botão "Atualizar Gestão MPAS" do PCM_Painel
---------------------------------------------------------------
Gera o mpas.json a partir da Gerencial + Fracttal e publica no repositório,
em um passo só.

Por que existe (14/08/2026): a aba Gestão MPAS lê o `mpas.json`, cuja fonte é o
`Gerencial - PCM_2026_R00.xlsx` no OneDrive. O robô da nuvem NÃO enxerga essa
pasta, então esse arquivo nunca entrou em nenhum workflow — ficava parado até
alguém rodar à mão (estava 3 dias atrás quando isto foi escrito). Este script é
o caminho manual, porém completo: um clique gera e publica.

Custo medido: ler a planilha leva ~2 s; o Fracttal é que demora (cache de 3 h,
até ~5 min quando frio). Use --sem-api para a atualização rápida, quando só o
plano/compras mudou e o estado de execução pode esperar.

Uso:
    py -3 atualizar_mpas.py              # completo (planilha + Fracttal)
    py -3 atualizar_mpas.py --sem-api    # rápido, só a planilha
    py -3 atualizar_mpas.py --so-gerar   # gera e não publica
"""
from __future__ import annotations
import argparse, datetime as dt, os, shutil, subprocess, sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = Path(__file__).resolve().parent
CHECKOUT = Path.home() / "gridco-pcm-data"


def log(m):
    print(f"[{dt.datetime.now():%H:%M:%S}] {m}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-api", action="store_true",
                    help="pula o Fracttal (rápido; estado de execução fica o da última rodada)")
    ap.add_argument("--so-gerar", action="store_true", help="gera sem publicar")
    ap.add_argument("--claro", action="store_true",
                    help="publica SEM cifrar (ato deliberado — o repositório é público)")
    a = ap.parse_args()

    # O repositório é público. Publicar o mpas.json em claro expõe as
    # observações em texto livre da aba MPAS (inclusive nota de pessoal), então
    # a cifra é o padrão e a AUSÊNCIA de senha aborta — nunca cai para claro
    # sozinha. Foi exatamente esse silêncio que deixou o arquivo exposto: o
    # gerador sempre soube cifrar, mas este script nunca passava a flag.
    senha = None
    if not a.claro:
        senha = os.environ.get("PCM_MPAS_SENHA")
        if not senha:
            log("ERRO: a senha da cifra não está definida — NADA foi gerado nem publicado.")
            log("  Defina uma vez, na sua conta (a senha não fica em arquivo nenhum):")
            log('    setx PCM_MPAS_SENHA "sua-senha-de-admin"')
            log("  Abra um terminal novo depois do setx. Use a MESMA senha do login do")
            log("  painel — assim a aba Gestão MPAS abre sozinha, sem pedir nada.")
            log("  Para publicar em claro de propósito: py -3 atualizar_mpas.py --claro")
            return 2

    ger = AQUI / "Gerencial_atalho"          # informativo apenas
    saida = AQUI / "mpas.json"
    antes = saida.stat().st_mtime if saida.exists() else 0

    cmd = [sys.executable, "-u", str(AQUI / "gerar_mpas_json.py")]
    if a.sem_api:
        cmd.append("--sem-api")
    if not a.claro:
        cmd.append("--cifrar")          # a senha vai por env, não na linha de comando
                                        # (linha de comando aparece na lista de processos)
    log("Gerando mpas.json" + (" (sem Fracttal)" if a.sem_api else " (planilha + Fracttal)") + "...")
    env = os.environ.copy()
    env["PCM_PROG_DIR"] = str(AQUI)
    if senha:
        env["PCM_MPAS_SENHA"] = senha
    r = subprocess.run(cmd, cwd=str(AQUI), env=env)
    if r.returncode != 0:
        log("ERRO ao gerar o mpas.json — nada foi publicado.")
        return r.returncode
    if not saida.exists() or saida.stat().st_mtime == antes:
        log("AVISO: o mpas.json não foi reescrito — verifique a saída acima.")
        return 1

    if a.so_gerar:
        log("--so-gerar: arquivo atualizado localmente, sem publicar.")
        return 0
    if not (CHECKOUT / ".git").exists():
        log(f"ERRO: checkout git não encontrado em {CHECKOUT} — não publiquei.")
        return 1

    shutil.copy2(saida, CHECKOUT / "mpas.json")
    log("Publicando...")
    r = subprocess.run([sys.executable, str(CHECKOUT / "sync_repo.py")], cwd=str(CHECKOUT))
    if r.returncode != 0:
        log("ERRO no push — o arquivo está no checkout; rode sync_repo.py de novo quando resolver.")
        return r.returncode
    log("OK: Gestão MPAS atualizada e publicada" + (" EM CLARO (--claro)" if a.claro
        else " (cifrada)") + ". O painel reflete em alguns minutos "
        "(cache do GitHub Pages).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
