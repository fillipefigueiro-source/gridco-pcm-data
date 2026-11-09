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

Mudou o time? Edite SÓ esta lista.
"""
import re
import unicodedata

RESP_BACKOFFICE = [
    "Singrid Vieira", "Lara Fortes", "Aury Albuquerque", "Tionardo Santos",
    "Ana Patrícia Barros", "Levi Maia", "Roger Lélis", "Hebert Rabelo",
    "João Vieira", "Luis Otávio Lima de Sousa",
]


def _sa(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


_BO = [_sa(n).split() for n in RESP_BACKOFFICE]


def eh_backoffice(resp) -> bool:
    """Mesmo primeiro nome E (último nome do Fracttal está no nome da lista, ou
    o último da lista está no do Fracttal). Assim 'Luis Otavio' e 'Luis Otávio
    Lima de Sousa' casam, e 'João Neves' / 'Luis Moura' (campo) NÃO casam."""
    t = _sa(resp).split()
    return bool(t) and any(t[0] == b[0] and (t[-1] in b[1:] or b[-1] in t[1:]) for b in _BO)
