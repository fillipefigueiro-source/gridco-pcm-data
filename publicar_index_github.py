# -*- coding: utf-8 -*-
"""
publicar_index_github.py
------------------------
Publica o painel (0. Acessos/index.html + css/ + js/) no repositório
fillipefigueiro-source/gridco-pcm-data, de onde o GitHub Pages serve.

REESCRITO em 13/08/2026 (Melhoria 0.10): o painel deixou de ser um arquivo
único — agora são index.html + 3 CSS + 2 JS. A API de contents do GitHub
faz um commit POR arquivo; publicar 6 assim deixaria o Pages servindo
versões misturadas entre commits. Por isso a publicação passou a ser feita
pelo checkout git (~/gridco-pcm-data) + sync_repo.py: UM commit atômico
com o conjunto inteiro.

Uso:
   python publicar_index_github.py
"""
from __future__ import annotations
import os, sys, shutil, subprocess, datetime as dt
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CHECKOUT = Path.home() / "gridco-pcm-data"


def _log(msg):
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def _detectar_pasta() -> Path:
    env = os.getenv("PCM_PROG_DIR")
    if env and Path(env).exists():
        return Path(env)
    here = Path(__file__).resolve().parent
    if (here / "atualizacao_semanal.py").exists():
        return here
    raise FileNotFoundError("Pasta PCM não encontrada (defina PCM_PROG_DIR).")


def main() -> int:
    pasta = _detectar_pasta()
    origem = pasta / "0. Acessos"
    idx = origem / "index.html"
    if not idx.exists():
        _log(f"ERRO: {idx} não existe.")
        return 1
    if not (CHECKOUT / ".git").exists():
        _log(f"ERRO: checkout git não encontrado em {CHECKOUT} — "
             "clone o repositório antes de publicar.")
        return 1

    # o conjunto publicado — index + pastas de estáticos (nunca os .json de
    # dados: esses são do robô, e sobrescrevê-los aqui causaria conflito)
    _log(f"Copiando painel para {CHECKOUT} ...")
    # cache-busting: cada publicação carimba os assets (?v=dev -> ?v=<stamp>).
    # Sem isso o navegador serve index.html novo com app.js VELHO do cache
    # (o Pages manda max-age=600) e o painel quebra de formas fantasmas.
    stamp = dt.datetime.now().strftime("%Y%m%d%H%M")
    html = idx.read_text(encoding="utf-8").replace("?v=dev", f"?v={stamp}")
    (CHECKOUT / "index.html").write_text(html, encoding="utf-8", newline="\n")
    n = 1
    for sub in ("css", "js"):
        d_orig = origem / sub
        if not d_orig.is_dir():
            continue
        d_dest = CHECKOUT / sub
        d_dest.mkdir(exist_ok=True)
        for f in d_orig.glob("*.*"):
            shutil.copy2(f, d_dest / f.name)
            n += 1
    _log(f"  -> {n} arquivo(s).")

    _log("Publicando via sync_repo.py (commit único)...")
    r = subprocess.run([sys.executable, str(CHECKOUT / "sync_repo.py")],
                       cwd=str(CHECKOUT))
    if r.returncode != 0:
        _log("ERRO no push — veja a saída acima. Nada foi perdido: os arquivos "
             "estão no checkout; rode sync_repo.py de novo quando resolver.")
        return r.returncode
    _log("OK: painel publicado. O Pages leva alguns minutos (às vezes ~1 h) "
         "para servir a versão nova — página velha logo após o push NÃO é bug.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
