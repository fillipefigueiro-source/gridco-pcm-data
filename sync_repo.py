# -*- coding: utf-8 -*-
"""
sync_repo.py — commit + push deste checkout sem gravar o token no git config.

    py -3 sync_repo.py "mensagem do commit"

O que faz, nesta ordem:
  1. git add -A (respeitando o .gitignore)
  2. commit (se houver algo)
  3. fetch + rebase — o robô da nuvem commita JSONs a cada ~15-60 min,
     então SEMPRE pode haver commit remoto novo entre o clone e o push
  4. push, injetando o GITHUB_TOKEN só no comando (não fica em .git/config)

Token: env GITHUB_TOKEN, ou o .env da pasta de dados do PCM (OneDrive).
"""
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
OWNER_REPO = "fillipefigueiro-source/gridco-pcm-data"
ENV_PCM = os.path.join(
    os.path.expanduser("~"),
    "GRID CO", "GRID CO. - Gridco", "4. O&M", "11.Pré-Operação",
    "6. PCM", "09. Programação Semanal", ".env")


def token():
    t = os.environ.get("GITHUB_TOKEN")
    if t:
        return t
    if os.path.exists(ENV_PCM):
        for ln in open(ENV_PCM, encoding="utf-8"):
            if ln.strip().startswith("GITHUB_TOKEN"):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def git(*args, ok_codes=(0,)):
    r = subprocess.run(["git", "-C", AQUI, *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode not in ok_codes:
        print(r.stdout); print(r.stderr)
        raise SystemExit(f"git {' '.join(args[:2])} falhou ({r.returncode})")
    return r.stdout.strip()


def main():
    msg = sys.argv[1] if len(sys.argv) > 1 else "chore: atualiza scripts do PCM"
    tok = token()
    if not tok:
        print("ERRO: GITHUB_TOKEN não encontrado (env ou .env da pasta do PCM).")
        return 1
    url = f"https://x-access-token:{tok}@github.com/{OWNER_REPO}.git"

    git("add", "-A")
    pend = git("status", "--porcelain")
    if pend:
        git("-c", "user.name=PCM Grid Co.",
            "-c", "user.email=fabricio.barreto@gridco.com.br",
            "commit", "-m", msg)
        print("commit: " + git("log", "--oneline", "-1"))
    else:
        print("nada a commitar — só sincronizando")

    # o robô pode ter commitado nesse meio-tempo: rebase antes do push.
    # Identidade explícita: o rebase também cria commits, e sem user.name
    # configurado ele morre com 128 (aconteceu na primeira execução).
    git("config", "user.name", "PCM Grid Co.")
    git("config", "user.email", "fabricio.barreto@gridco.com.br")
    git("fetch", url, "main")
    git("rebase", "FETCH_HEAD")
    git("push", url, "HEAD:main")
    print("push OK -> " + git("log", "--oneline", "-1"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
