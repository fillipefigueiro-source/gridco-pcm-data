# -*- coding: utf-8 -*-
"""
Sondagem do JSON-RPC do Fracttal — descobrir se dá para renomear classificação por API.

CONTEXTO
    A REST pública do Fracttal (app.fracttal.com/api/) é só LEITURA. A escrita vai por
    JSON-RPC em one.fracttal.com/rpc/proxy, com token de USUÁRIO — foi o que o middleware
    do App de Campo mapeou, e é como ele fecha OS.

    Os 26 métodos que o middleware usa são todos de `tasks.` e `companies.`. Nenhum de
    `inventories.` — então o nome do método para mexer em classificação é PALPITE. Esta
    sondagem existe para transformar palpite em fato, sem arriscar dado de produção.

COMO USAR
    py -3 sondar_rpc_fracttal.py            # etapa 1 — SÓ LEITURA
    py -3 sondar_rpc_fracttal.py --escrita  # etapa 2 — no-op no grupo TESTE

O TOKEN
    Vem do FRACTTAL_JWT_TOKEN do .env. O script lê e usa; NUNCA imprime. Se ele estiver
    expirado, a resposta será USER_NOT_LOGIN — e aí é reconectar a conta no Fracttal.
"""
import json, os, sys, uuid, urllib.request, urllib.error
from pathlib import Path

RPC_URL    = "https://one.fracttal.com/rpc/proxy"
RPC_ORIGIN = "https://one.fracttal.com"
X_VERSION  = "Fracttal/5.8.07 web"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")

# Grupo de TESTE, id 252610 — dado descartável, já existe no cadastro com esse nome.
# Usar ele em vez dos três de produção é o ponto inteiro desta sondagem.
GRUPO_TESTE_ID   = 252610
GRUPO_TESTE_NOME = "TESTE"


def _env(chave):
    """Lê do .env da pasta do projeto. Não imprime valor."""
    for base in (Path(__file__).parent, Path.cwd()):
        f = base / ".env"
        if not f.exists():
            continue
        for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
            ln = ln.strip()
            if ln.startswith(chave + "="):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get(chave, "")


def rpc(metodo, params, token):
    """Devolve (ok, resultado_ou_erro). Nunca levanta — sondagem não pode morrer no meio."""
    corpo = [{"id": str(uuid.uuid4()), "jsonrpc": "2.0", "method": metodo, "params": params}]
    req = urllib.request.Request(
        RPC_URL, data=json.dumps(corpo).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json",
                 "User-Agent": UA, "Accept": "application/json",
                 "x-version": X_VERSION, "Origin": RPC_ORIGIN, "Referer": RPC_ORIGIN + "/"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            bruto = r.read().decode("utf-8", "replace")
            http = r.status
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:220]}"
    except Exception as e:
        return False, f"rede: {e}"

    try:
        j = json.loads(bruto)
    except Exception:
        return False, f"resposta não-JSON (HTTP {http}): {bruto[:220]}"

    item = j[0] if isinstance(j, list) and j else j
    if isinstance(item, dict) and item.get("error"):
        return False, "erro RPC: " + json.dumps(item["error"], ensure_ascii=False)[:260]
    res = item.get("result") if isinstance(item, dict) else item
    # O Fracttal devolve {"success": false} DENTRO de lista em alguns métodos, com HTTP
    # 200. Checar só o dict deixaria isso passar calado — foi lição registrada no
    # middleware, e vale aqui igual.
    for c in (res if isinstance(res, list) else [res]):
        if isinstance(c, dict) and c.get("success") is False:
            return False, "recusado: " + str(c.get("message") or c)[:220]
    return True, res


def resumo(r):
    if isinstance(r, list):
        return f"lista com {len(r)} itens" + (f" · 1º = {json.dumps(r[0], ensure_ascii=False)[:120]}" if r else "")
    if isinstance(r, dict):
        return "dict com chaves " + str(list(r)[:8])
    return repr(r)[:120]


def main():
    token = _env("FRACTTAL_JWT_TOKEN")
    if not token:
        print("ERRO: FRACTTAL_JWT_TOKEN não encontrado no .env")
        return 1
    print(f"token carregado: {len(token)} caracteres (não impresso)\n")

    # ── ETAPA 1 — leitura pura ───────────────────────────────────────────────
    # Confirma duas coisas: que o token vale para RPC, e que o módulo `inventories`
    # existe com a convenção de nome que a MCP sugere.
    print("=" * 68)
    print("ETAPA 1 — LEITURA (não escreve nada)")
    print("=" * 68)
    candidatos_leitura = [
        ("inventories.groups_2_list",       {"limit": 1}),
        ("inventories.item_groups_2_list",  {"limit": 1}),
        ("inventories.groups_list",         {"limit": 1}),
    ]
    achou = None
    for m, p in candidatos_leitura:
        ok, r = rpc(m, p, token)
        print(f"  {'OK   ' if ok else 'FALHA'}  {m:36} {resumo(r) if ok else r[:110]}")
        if ok and achou is None:
            achou = m
    if not achou:
        print("\n  Nenhum método de leitura respondeu.")
        print("  Se todos deram USER_NOT_LOGIN, o token expirou — reconectar a conta.")
        print("  Se deram 'método não existe', a convecção de nome é outra.")
        return 2
    print(f"\n  >>> módulo confirmado: {achou}")

    if "--escrita" not in sys.argv:
        print("\n  Etapa 2 (escrita no grupo TESTE) NÃO executada.")
        print("  Para rodar:  py -3 sondar_rpc_fracttal.py --escrita")
        return 0

    # ── ETAPA 2 — escrita no-op, só no grupo TESTE ───────────────────────────
    # Gravar o MESMO valor que já está lá prova o caminho sem alterar nada. É a
    # mesma técnica que o Fabrício usou para descobrir a escrita na Observação da OS.
    print()
    print("=" * 68)
    print(f"ETAPA 2 — ESCRITA NO-OP no grupo {GRUPO_TESTE_NOME} (id {GRUPO_TESTE_ID})")
    print("=" * 68)
    print("  Grava o mesmo nome que já está lá. Se funcionar, o caminho existe.\n")
    base = achou.rsplit("_list", 1)[0]
    candidatos_escrita = [
        (base + "_update", {"id": GRUPO_TESTE_ID, "description": GRUPO_TESTE_NOME}),
        (base + "_update", [{"id": GRUPO_TESTE_ID, "description": GRUPO_TESTE_NOME}]),
        (base + "_insert", {"id": GRUPO_TESTE_ID, "description": GRUPO_TESTE_NOME}),
    ]
    for m, p in candidatos_escrita:
        forma = "dict" if isinstance(p, dict) else "lista"
        ok, r = rpc(m, p, token)
        print(f"  {'OK   ' if ok else 'FALHA'}  {m:34} params={forma:6} {resumo(r) if ok else r[:100]}")
        if ok:
            print(f"\n  >>> CAMINHO CONFIRMADO: {m} com params em {forma}")
            print("  Agora dá para renomear os três de produção:")
            print("     253625  PA LESTE 01 -> PA Leste 01")
            print("     247469  PA NORTE 01 -> PA Norte 01")
            print("     255525  MA LESTE 02 -> MA Leste 02")
            return 0
    print("\n  Nenhuma forma de escrita passou. O caminho é a interface do Fracttal.")
    return 3


if __name__ == "__main__":
    sys.exit(main())
