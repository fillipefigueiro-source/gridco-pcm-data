# -*- coding: utf-8 -*-
"""Recorte "só time de campo" dos relatórios do PCM (decisão do Fabricio, 09/11/2026).

OS cujo responsável no Fracttal é uma das pessoas de NAO_CAMPO não aparece em
nada: some de gestao_pcm (tarefas) e do banco_dados (linhas e pendentes da
programação). OS com responsáveis mistos (campo + fora) continua.
"""
import io
import json
import os
import re
import unicodedata

NAO_CAMPO = ['singrid vieira', 'lara fortes', 'aury albuquerque', 'tionardo santos',
             'ana patricia barros', 'levi maia', 'roger lelis', 'hebert rabelo',
             'joao vieira', 'luis otavio lima de sousa']

_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_os_nao_campo.json')


def _norm(s):
    s = unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', s.lower()).strip()


def fora_do_campo(resp):
    n = _norm(resp)
    if not n:
        return False
    pal = n.split()
    for x in NAO_CAMPO:
        p = x.split()
        # nome completo, ou primeiro + último nome ("Ana Barros" = Ana Patrícia Barros)
        if x in n or (p[0] in pal and p[-1] in pal):
            return True
    return False


def _os(x):
    v = x.get('os', x.get('os_id'))
    return str(v) if v is not None else ''


def os_fora(banco=None):
    """Conjunto de OS só com responsáveis fora do campo. Fonte: API do Fracttal
    (fonte_bd_api) + resp_os da programação; sem API, usa a última lista salva."""
    resp = {}
    try:
        import fonte_bd_api as F
        df = F.df_semanal(ttl_min=720)[['OSs ID', 'Responsável']].dropna()
        for r in df.to_dict('records'):
            k = str(r['OSs ID']).strip()
            if k.endswith('.0'):
                k = k[:-2]
            resp.setdefault(k, set()).add(' '.join(str(r['Responsável']).split()))
    except Exception as e:
        if os.path.exists(_CACHE):
            print('AVISO filtro_campo: API indisponível (%s); usando a última lista salva' % e)
            return set(json.load(io.open(_CACHE, encoding='utf-8'))['os'])
        print('AVISO filtro_campo: API indisponível (%s) e sem lista salva; filtro só pela programação' % e)
    for w in (banco or {}).get('semanas', []):
        for r in w.get('rows', []):
            k = str(r.get('os_id'))
            if r.get('resp_os') and k not in resp:
                resp[k] = {' '.join(str(r['resp_os']).split())}
    fora = {k for k, rs in resp.items() if rs and all(fora_do_campo(r) for r in rs)}
    if resp:
        io.open(_CACHE, 'w', encoding='utf-8').write(
            json.dumps({'nomes': NAO_CAMPO, 'os': sorted(fora)}, ensure_ascii=False))
    return fora


def aplicar(gestao, banco):
    """Tira as OS fora do campo de gestao['tarefas'] e das semanas do banco, no lugar."""
    fora = os_fora(banco)
    antes = len(gestao.get('tarefas', []))
    gestao['tarefas'] = [t for t in gestao.get('tarefas', []) if _os(t) not in fora]
    for w in banco.get('semanas', []):
        for k in ('rows', 'pendentes'):
            if isinstance(w.get(k), list):
                w[k] = [r for r in w[k] if _os(r) not in fora]
    print('filtro_campo: %d OS fora do campo · %d tarefas removidas' % (len(fora), antes - len(gestao['tarefas'])))
    return fora
