# -*- coding: utf-8 -*-
"""
publicar_observacoes_github.py
------------------------------
Envia os arquivos de observação para o repo gridco-pcm-data via API do GitHub,
pra o robô da nuvem (semanal.yml) enxergar as intervenções do usuário.

Publica (se existirem):
  - Observacoes_Semana_Atual.txt  (override da semana atual)
  - Observacoes_Semana.txt         (plano da sexta)

Token: GITHUB_TOKEN no .env (mesmo dos outros publicadores).
Uso:  python publicar_observacoes_github.py            # publica os dois
      python publicar_observacoes_github.py --atual    # só o da semana atual
"""
from __future__ import annotations
import os, sys, json, base64, datetime as dt
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GITHUB_OWNER = "fillipefigueiro-source"
GITHUB_REPO  = "gridco-pcm-data"
GITHUB_BRANCH = "main"
ARQUIVOS = ["Observacoes_Semana_Atual.txt", "Observacoes_Semana.txt"]


def _log(m):
    print(f"[{dt.datetime.now():%H:%M:%S}] {m}", flush=True)


def _detectar_pasta() -> Path:
    env = os.getenv("PCM_PROG_DIR")
    if env and Path(env).exists():
        return Path(env)
    here = Path(__file__).resolve().parent
    if (here / "atualizacao_semanal.py").exists():
        return here
    c = (Path.home() / "GRID CO" / "Grid Co. - Gridco" / "4. O&M"
         / "11.Pré-Operação" / "6. PCM" / "09. Programação Semanal")
    if c.exists():
        return c
    raise FileNotFoundError("Pasta PCM não encontrada.")


def _carregar_env(pasta: Path) -> dict:
    out = {}
    p = pasta / ".env"
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def publicar_arquivo(token: str, pasta: Path, nome: str) -> bool:
    import urllib.request, urllib.error
    fp = pasta / nome
    if not fp.exists():
        _log(f"  (pulado: {nome} não existe)")
        return True
    conteudo = fp.read_text(encoding="utf-8")
    base = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{nome}"
    hdr = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
           "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "GridCo-PCM-Obs"}
    # SHA atual (se já existe)
    sha = None
    req = urllib.request.Request(base + f"?ref={GITHUB_BRANCH}", method="GET")
    for k, v in hdr.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            sha = json.loads(r.read().decode()).get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    body = {"message": f"chore: observações do painel ({nome})",
            "content": base64.b64encode(conteudo.encode("utf-8")).decode("ascii"),
            "branch": GITHUB_BRANCH}
    if sha:
        body["sha"] = sha
    put = urllib.request.Request(base, data=json.dumps(body).encode("utf-8"), method="PUT")
    for k, v in hdr.items():
        put.add_header(k, v)
    put.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(put, timeout=60) as r:
        commit = json.loads(r.read().decode()).get("commit", {}).get("sha", "")[:12]
        _log(f"  → {nome} publicado (commit {commit})")
    return True


def main() -> int:
    pasta = _detectar_pasta()
    env = _carregar_env(pasta)
    token = env.get("GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        _log("ERRO: GITHUB_TOKEN não definido no .env.")
        return 3
    arquivos = ["Observacoes_Semana_Atual.txt"] if "--atual" in sys.argv else ARQUIVOS
    _log(f"Publicando observações em {GITHUB_OWNER}/{GITHUB_REPO}...")
    try:
        for nome in arquivos:
            publicar_arquivo(token, pasta, nome)
    except Exception as e:
        _log(f"ERRO ao publicar: {type(e).__name__}: {e}")
        return 4
    _log("OK: observações enviadas. A nuvem aplica no próximo ciclo (~15 min).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
