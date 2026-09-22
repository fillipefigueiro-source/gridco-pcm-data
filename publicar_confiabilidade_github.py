# -*- coding: utf-8 -*-
"""
publicar_confiabilidade_github.py
---------------------------------
Publica confiabilidade.json no GitHub via API REST (mesmo padrão dos demais publishers).

Lê token do .env: GITHUB_TOKEN=ghp_xxxxx

Uso:
   py -3 publicar_confiabilidade_github.py
"""
from __future__ import annotations
import os, sys, json, base64, datetime as dt
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GITHUB_OWNER  = "fillipefigueiro-source"
GITHUB_REPO   = "gridco-pcm-data"
GITHUB_PATH   = "confiabilidade.json"
GITHUB_BRANCH = "main"


def _log(msg):
    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


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


def _carregar_env(pasta: Path) -> dict:
    env_path = pasta / ".env"
    out = {}
    if not env_path.exists():
        return out
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def publicar(token: str, payload_json: str, nusinas: int) -> None:
    import urllib.request, urllib.error

    api_url = (
        f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/contents/{GITHUB_PATH}?ref={GITHUB_BRANCH}"
    )
    req = urllib.request.Request(api_url, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "GridCo-PCM-Publisher")
    sha = None
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            sha = data.get("sha")
            _log(f"  → SHA atual: {sha[:12] if sha else '(novo)'}...")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            _log("  → Arquivo ainda não existe no repo, será criado.")
        else:
            raise

    content_b64 = base64.b64encode(payload_json.encode("utf-8")).decode("ascii")
    put_body = {
        "message": f"chore: refresh confiabilidade.json [{nusinas} usinas]",
        "content": content_b64,
        "branch":  GITHUB_BRANCH,
    }
    if sha:
        put_body["sha"] = sha

    put_req = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GITHUB_PATH}",
        data=json.dumps(put_body).encode("utf-8"),
        method="PUT",
    )
    put_req.add_header("Authorization", f"Bearer {token}")
    put_req.add_header("Accept", "application/vnd.github+json")
    put_req.add_header("X-GitHub-Api-Version", "2022-11-28")
    put_req.add_header("Content-Type", "application/json")
    put_req.add_header("User-Agent", "GridCo-PCM-Publisher")

    with urllib.request.urlopen(put_req, timeout=30) as resp:
        out = json.loads(resp.read().decode("utf-8"))
        commit = out.get("commit", {}).get("sha", "")[:12]
        _log(f"  → Publicado! Commit {commit}")


def main() -> int:
    pasta = _detectar_pasta()
    _log(f"Pasta: {pasta}")
    src = pasta / "confiabilidade.json"
    if not src.exists():
        _log(f"ERRO: {src.name} não existe. Rode gerar_confiabilidade_json.py primeiro.")
        return 2

    raw = src.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        _log(f"ERRO: confiabilidade.json corrompido: {e}")
        return 2

    nusinas = int(data.get("totalUsinas") or len(data.get("usinas", [])))

    env = _carregar_env(pasta)
    token = env.get("GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        _log("ERRO: GITHUB_TOKEN não definido no .env.")
        return 3

    try:
        publicar(token, raw, nusinas)
    except Exception as e:
        _log(f"ERRO ao publicar: {e}")
        return 1
    _log(f"OK: confiabilidade.json publicado ({nusinas} usinas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
