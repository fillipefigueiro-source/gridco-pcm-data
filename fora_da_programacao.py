"""O que fica fora da programação (16/10/2026): o Fora_da_programacao.json que o Nexus publica.

O PCM e os supervisores marcam no Nexus o MOTIVO de cada tarefa (Engenharia, Aguardando Material, Sinistro...; um por
tarefa). Os motivos que "tiram da programação" (no cadastro de 16/10: os quatro Aguardando, Condições Climáticas
Adversas e Pendente recurso) deixam a tarefa fora da semana: o programacao_v7 não a programa, e na semana em curso o
atualizacao_semanal apaga as linhas dela e não a inclui de novo como OS nova. E a OS cujo responsável no Fracttal é
alguém da lista do backoffice (mantida no Nexus, no Gerar a semana) fica fora da geração, e o robô não a inclui como OS
nova no meio da semana.

O arquivo (o Nexus grava na raiz deste repositório, ao lado do banco_dados.json, e na pasta de cada rodada que ele
gera; o servidor do App de Campo lê da mesma pasta do PROG_URL):
  {"versao": 1, "gerado_em": "...", "hash": "...",
   "motivos": [{"id", "nome", "descricao", "tira_da_programacao", "ativo"}],
   "tarefas": [{"os", "codigo", "tarefa", "usina", "cluster", "data_prog", "motivo", "tira_da_programacao", "desde"}],
   "backoffice": ["Nome Como No Fracttal", ...]}
É o estado de AGORA (a tarefa desmarcada sai); os, codigo e tarefa vão como nas linhas do banco_dados.json; o motivo é
o id.
A tarefa é OS + código do ativo + nome. Código vazio = a marca vale para a tarefa daquele nome em todos os ativos da OS
(a marca feita no Nexus pelo número da OS: a Gestão PCM não traz o código); a marca do ativo vence a da OS.

As comparações são as do Nexus (nexus/pcm/motivos.py, o teste de contrato lá roda este arquivo): a OS como inteiro, o
código maiúsculo e sem espaço, o nome da tarefa e o do responsável sem acento, sem caixa e com espaço único.

Sem o arquivo, ou com ele ilegível, NADA fica de fora (e o motivo vai para o log): a programação segue como antes.
"""
import json
import os
import re
import unicodedata

ARQUIVO = "Fora_da_programacao.json"


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def canon(codigo) -> str:
    return re.sub(r"\s+", "", str(codigo or "").strip()).upper()


def os_de(v) -> str:
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return str(v or "").strip()


def vazio() -> dict:
    return {"marcas": {}, "backoffice": set(), "n_tarefas": 0, "erro": "", "gerado_em": ""}


def carregar(pasta: str) -> dict:
    """{"marcas": {(os, código, nome): (motivo, tira)}, "backoffice": {nome}, ...}: todas as tarefas com motivo (a do
    ativo que NÃO tira ainda vence a da OS que tira) e os nomes do backoffice, já normalizados; `n_tarefas` conta as que
    tiram. `erro` diz por que veio vazio (sem arquivo não é erro)."""
    out = vazio()
    caminho = os.path.join(pasta, ARQUIVO)
    if not os.path.exists(caminho):
        return out
    try:
        with open(caminho, encoding="utf-8") as f:
            d = json.load(f)
        nomes = {m.get("id"): str(m.get("nome") or "") for m in d.get("motivos") or [] if isinstance(m, dict)}
        for t in d.get("tarefas") or []:
            if not isinstance(t, dict):
                continue
            chave = (os_de(t.get("os")), canon(t.get("codigo")), norm(t.get("tarefa")))
            if chave[0] and chave[2]:
                out["marcas"][chave] = (nomes.get(t.get("motivo")) or "motivo", bool(t.get("tira_da_programacao")))
        out["backoffice"] = {norm(n) for n in d.get("backoffice") or [] if norm(n)}
        out["n_tarefas"] = sum(1 for _m, tira in out["marcas"].values() if tira)
        out["gerado_em"] = str(d.get("gerado_em") or "")
    except Exception as e:      # noqa: BLE001 — arquivo quebrado não derruba a programação
        out = vazio()
        out["erro"] = f"{ARQUIVO} ilegível ({type(e).__name__}: {e})"
    return out


def motivo_que_tira(fora: dict, os_id, codigo, tarefa) -> str | None:
    """O motivo que tira esta tarefa da programação, ou None. A marca do ativo vence a da OS (código vazio)."""
    marcas = fora.get("marcas") or {}
    if not marcas:
        return None
    o, t = os_de(os_id), norm(tarefa)
    m = marcas.get((o, canon(codigo), t)) or marcas.get((o, "", t))
    return m[0] if m and m[1] else None


def do_backoffice(fora: dict, responsavel) -> bool:
    """A OS cujo responsável no Fracttal é alguém da lista do backoffice."""
    n = norm(responsavel)
    return bool(n) and n in (fora.get("backoffice") or set())
