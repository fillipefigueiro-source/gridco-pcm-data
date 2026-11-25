# -*- coding: utf-8 -*-
"""
backoffice.py — quem é do backoffice (não é time de campo). Lista ÚNICA.

OS cujo Responsável (campo `user_assigned` da OS no Fracttal) é alguém desta
lista não é trabalho de campo: fica FORA dos relatórios (Gerar_Relatorios e
Relatório Executivo / Semana do painel). Pedido do PCM em 09/11/2026 — caso
Marabá (Singrid/Lara) e as 40 "Administrativas" da Athon na S44.

Quem usa:
  - relatorio_clientes.py   -> pula a OS na coleta
  - gerar_gestao_pcm_json.py -> marca a tarefa com "bo": true; o
                                js/relatorio_exec.js tira essas OS das contas

Mudou o time? Edite na tela do Nexus (PCM → Gerar a semana → Backoffice): desde 24/11/2026 a lista que vale
é a do Nexus, que ele publica no Fora_da_programacao.json (a mesma que tira essas OS da geração). A lista daqui
embaixo é só a RESERVA, para quando o arquivo faltar: em 24/11 o Nexus já tinha 12 nomes e esta, 11, e os
relatórios mostravam OS de quem o programador já tirava.
"""
import io
import json
import os
import re
import unicodedata

RESP_BACKOFFICE = [
    "Singrid Vieira", "Lara Fortes", "Aury Albuquerque", "Tionardo Santos",
    "Ana Patrícia Barros", "Levi Maia", "Roger Lélis", "Hebert Rabelo",
    "João Vieira", "Luis Otávio Lima de Sousa",
    "Luana Pereira",   # incluída em 23/11/2026: só OS Administrativas
]


def _sa(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


ARQ_NEXUS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Fora_da_programacao.json")
_BO = None


def lista() -> list:
    """A lista do backoffice que vale: a do Nexus (o "backoffice" do Fora_da_programacao.json); sem o arquivo
    ou com ele vazio, a reserva RESP_BACKOFFICE, com aviso."""
    try:
        with io.open(ARQ_NEXUS, encoding="utf-8") as f:
            nomes = [str(n) for n in (json.load(f).get("backoffice") or []) if str(n).strip()]
        if nomes:
            return nomes
    except Exception:                       # noqa: BLE001 — sem o arquivo, vale a reserva
        pass
    print("AVISO backoffice: sem a lista do Nexus (Fora_da_programacao.json); usando a reserva do codigo")
    return list(RESP_BACKOFFICE)


def _bo() -> list:
    global _BO
    if _BO is None:
        _BO = [_sa(n).split() for n in lista() if _sa(n)]
    return _BO


def eh_backoffice(resp) -> bool:
    """Mesmo primeiro nome E (último nome do Fracttal está no nome da lista, ou
    o último da lista está no do Fracttal). Assim 'Luis Otavio' e 'Luis Otávio
    Lima de Sousa' casam, e 'João Neves' / 'Luis Moura' (campo) NÃO casam."""
    t = _sa(resp).split()
    return bool(t) and any(t[0] == b[0] and (t[-1] in b[1:] or b[-1] in t[1:]) for b in _bo())
