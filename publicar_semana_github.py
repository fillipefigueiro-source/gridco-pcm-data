# -*- coding: utf-8 -*-
"""
publicar_semana_github.py
-------------------------
Envia a Programação Semana XX.xlsx + as observações da sexta para o repo
gridco-pcm-data, pro robô da nuvem (semanal.yml) usar como base da semana.

Sem argumentos: publica a `Programação Semana *.xlsx` MAIS RECENTE (a que você
acabou de gerar) + `Observacoes_Semana.txt` + `Observacoes_Semana_Atual.txt`.
Com argumento: `python publicar_semana_github.py "Programação Semana 29.xlsx"`.

Token: GITHUB_TOKEN no .env.
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


def publicar_arquivo(token: str, pasta: Path, nome: str) -> None:
    """PUT binário-safe (lê bytes) — serve p/ xlsx e txt."""
    import urllib.request, urllib.error, urllib.parse
    fp = pasta / nome
    if not fp.exists():
        _log(f"  (pulado: {nome} não existe)")
        return
    dados = fp.read_bytes()
    nome_url = urllib.parse.quote(nome)   # espaços/acentos no nome do arquivo
    base = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{nome_url}"
    hdr = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
           "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "GridCo-PCM-Semana"}
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
    body = {"message": f"chore: painel envia {nome}",
            "content": base64.b64encode(dados).decode("ascii"),
            "branch": GITHUB_BRANCH}
    if sha:
        body["sha"] = sha
    put = urllib.request.Request(base, data=json.dumps(body).encode("utf-8"), method="PUT")
    for k, v in hdr.items():
        put.add_header(k, v)
    put.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(put, timeout=90) as r:
        commit = json.loads(r.read().decode()).get("commit", {}).get("sha", "")[:12]
        _log(f"  → {nome} publicado (commit {commit})")


def main() -> int:
    pasta = _detectar_pasta()
    env = _carregar_env(pasta)
    token = env.get("GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        _log("ERRO: GITHUB_TOKEN não definido no .env.")
        return 3

    # Excel: arg explícito ou o mais recente
    args_files = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args_files:
        excels = args_files
    else:
        import re
        def _wk(p):
            m = re.search(r"Semana\s+(\d+)", p.name)
            return int(m.group(1)) if m else -1
        cands = [c for c in pasta.glob("Programação Semana *.xlsx") if not c.name.startswith("~")]
        cands = sorted(cands, key=_wk, reverse=True)   # maior nº de semana = a mais nova
        if not cands:
            _log("ERRO: nenhuma 'Programação Semana *.xlsx' encontrada.")
            return 2
        excels = [cands[0].name]

    alvos = excels + ["Observacoes_Semana.txt", "Observacoes_Semana_Atual.txt"]
    _log(f"Publicando no repo: {excels[0]} + observações...")
    try:
        for nome in alvos:
            publicar_arquivo(token, pasta, nome)
    except Exception as e:
        _log(f"ERRO ao publicar: {type(e).__name__}: {e}")
        return 4
    _log("OK: semana enviada. O robô usa esse Excel como base da semana.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
