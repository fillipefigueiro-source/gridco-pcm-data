# -*- coding: utf-8 -*-
"""
publicar_sugestoes_github.py
-----------------------------
Lê Sugestoes_PCM.xlsx (aba "Sugestões"), monta o mesmo JSON que o Office Script
Acumulador_Sugestoes produziria, e publica em
   https://github.com/fillipefigueiro-source/gridco-pcm-data/sugestoes.json
via API REST do GitHub (PUT contents).

Lê o token do .env:
   GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

Roda silencioso. Saída segue convenção do projeto (logs em _log_semanal/).

Uso:
   python publicar_sugestoes_github.py
   python publicar_sugestoes_github.py --dry-run    # mostra JSON, não publica
"""
from __future__ import annotations
import os
import sys
import json
import base64
import argparse
import datetime as dt
from pathlib import Path

import openpyxl

# Força UTF-8 no stdout/stderr (PowerShell padrão é cp1252 e quebra com → / acentos)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------- Configuração ----------
GITHUB_OWNER  = "fillipefigueiro-source"
GITHUB_REPO   = "gridco-pcm-data"
GITHUB_PATH   = "sugestoes.json"
GITHUB_BRANCH = "main"

# Mesmas colunas que o Office Script
COLS_DATA = {"Criado em", "Última Avaliação", "OS Criada no Sistema", "Dia Sugerido"}
COLS_NUM  = {"RPN", "Score", "Duração (h)"}

STATUS_EXCLUIR = (
    "os criada",
    "não mais aberta",
    "nao mais aberta",
    "cancelad",
    "rejeitad",
)


def _log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _detectar_pasta() -> Path:
    """Detecta a pasta '09. Programação Semanal' (igual aos outros scripts)."""
    env = os.getenv("PCM_PROG_DIR")
    if env and Path(env).exists():
        return Path(env)
    here = Path(__file__).resolve().parent
    if (here / "atualizacao_semanal.py").exists():
        return here
    candidates = [
        Path.home() / "GRID CO" / "Grid Co. - Gridco" / "4. O&M"
            / "11.Pré-Operação" / "6. PCM" / "09. Programação Semanal",
        Path.home() / "OneDrive - Grid Co" / "4. O&M"
            / "11.Pré-Operação" / "6. PCM" / "09. Programação Semanal",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        "Não consegui localizar '09. Programação Semanal'. "
        "Defina PCM_PROG_DIR no ambiente."
    )


def _carregar_env(pasta: Path) -> dict:
    """Lê chaves=valor do .env (formato simples). Não usa python-dotenv."""
    env_path = pasta / ".env"
    out: dict = {}
    if not env_path.exists():
        return out
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _serial_excel_para_iso(serial: float) -> str:
    """Converte serial date do Excel (anchor 1899-12-30) para ISO 8601 UTC."""
    if not serial or serial <= 0:
        return ""
    epoch = dt.datetime(1899, 12, 30)
    d = epoch + dt.timedelta(days=float(serial))
    return d.isoformat(timespec="seconds") + "Z"


def _normalizar(val, key: str):
    """Normaliza um valor de célula do openpyxl pro JSON final."""
    if val is None or val == "":
        return ""
    # Dates do openpyxl podem vir como datetime nativo
    if isinstance(val, (dt.datetime, dt.date)):
        if isinstance(val, dt.datetime):
            return val.isoformat(timespec="seconds") + "Z"
        return val.isoformat()
    if key in COLS_DATA and isinstance(val, (int, float)):
        return _serial_excel_para_iso(float(val))
    if key in COLS_NUM:
        if isinstance(val, str):
            try:
                return float(val.replace(",", "."))
            except ValueError:
                return val
        return val
    if isinstance(val, str):
        return val.strip()
    return val


def ler_sugestoes(xlsx_path: Path) -> list[dict]:
    """Lê a aba 'Sugestões' e devolve lista de dicts (já filtrada)."""
    if not xlsx_path.exists():
        _log(f"AVISO: {xlsx_path.name} não existe ainda. Devolvendo lista vazia.")
        return []

    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    if "Sugestões" not in wb.sheetnames:
        _log("AVISO: aba 'Sugestões' não encontrada.")
        return []

    ws = wb["Sugestões"]
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return []

    header = [str(c or "").strip() for c in rows[0]]
    out: list[dict] = []

    for row in rows[1:]:
        obj: dict = {}
        tem_conteudo = False
        for j, key in enumerate(header):
            if not key:
                continue
            val = row[j] if j < len(row) else None
            if val not in (None, ""):
                tem_conteudo = True
            obj[key] = _normalizar(val, key)
        if not tem_conteudo:
            continue
        num = obj.get("Nº Solicitação")
        if num in (None, "", 0):
            continue
        out.append(obj)

    # Mesma regra de filtro do Office Script e do index.html
    def _ativa(s: dict) -> bool:
        if str(s.get("OS Criada no Sistema") or "").strip():
            return False
        st = str(s.get("Status no PCM") or "").lower()
        return not any(t in st for t in STATUS_EXCLUIR)

    total_raw = len(out)
    ativas = [s for s in out if _ativa(s)]
    ativas.sort(key=lambda s: -(s.get("Score") or 0))
    _log(f"  → {total_raw} linhas na planilha, {len(ativas)} ativas após filtro")
    return ativas, total_raw  # type: ignore


def montar_payload(ativas: list[dict], total_raw: int) -> dict:
    pendentes = sum(
        1 for s in ativas
        if "aguardando" in str(s.get("Status no PCM") or "").lower()
    )
    return {
        "geradoEm": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fonte": "Sugestoes_PCM.xlsx → Sugestões (publicado por publicar_sugestoes_github.py)",
        "totalNaPlanilha": total_raw,
        "total": len(ativas),
        "pendentes": pendentes,
        "sugestoes": ativas,
    }


def publicar_no_github(token: str, payload: dict) -> None:
    import urllib.request
    import urllib.error

    api_url = (
        f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
        f"/contents/{GITHUB_PATH}?ref={GITHUB_BRANCH}"
    )

    # 1) GET pra pegar o SHA atual
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
            _log(f"  → SHA atual: {sha[:12] if sha else '(sem)'}...")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            _log("  → Arquivo ainda não existe no repo, será criado.")
        else:
            raise

    # 2) PUT com novo conteúdo
    body_json = json.dumps(payload, ensure_ascii=False, indent=2)
    content_b64 = base64.b64encode(body_json.encode("utf-8")).decode("ascii")

    put_body = {
        "message": f"chore: refresh sugestoes.json [{payload['total']} ativas]",
        "content": content_b64,
        "branch": GITHUB_BRANCH,
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Monta o JSON e imprime, mas não publica")
    args = parser.parse_args()

    pasta = _detectar_pasta()
    _log(f"Pasta: {pasta}")

    xlsx = pasta / "Sugestoes_PCM.xlsx"
    ativas, total_raw = ler_sugestoes(xlsx)
    payload = montar_payload(ativas, total_raw)

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        _log(f"DRY-RUN: {payload['total']} ativas, {payload['pendentes']} pendentes")
        return 0

    env = _carregar_env(pasta)
    token = env.get("GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        _log("ERRO: GITHUB_TOKEN não definido no .env nem no ambiente.")
        return 2

    try:
        publicar_no_github(token, payload)
    except Exception as e:
        _log(f"ERRO ao publicar: {type(e).__name__}: {e}")
        return 3

    _log(f"OK: {payload['total']} ativas publicadas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
