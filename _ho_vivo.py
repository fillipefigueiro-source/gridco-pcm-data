# -*- coding: utf-8 -*-
import io, json
from collections import defaultdict
import fonte_bd_api as F

_dfr = F.df_semanal(ttl_min=2880)[['OSs ID', 'Responsável']].dropna()
RESP = {}
for _r in _dfr.to_dict('records'):
    RESP.setdefault(str(_r['OSs ID']), ' '.join(str(_r['Responsável']).split()))
g = json.load(io.open('_nuvem_gestao_pcm.json', encoding='utf-8'))
ho = [t for t in g['tarefas'] if t.get('aberta')
      and ('handover' in str(t.get('tipo', '')).lower()
           or 'handover' in str(t.get('tarefa', '')).lower())
      and 'teste' not in str(t.get('usina', '')).lower()
      and str(t.get('osStatus', '')).strip().lower() not in ('finalizados', 'finalizado')]
por = defaultdict(lambda: dict(n=0, atr=0, dias=0, oss=set(), sup=''))
for t in ho:
    e = por[t['usina']]
    e['n'] += 1
    if t.get('atrasado'):
        e['atr'] += 1
    e['dias'] = max(e['dias'], t.get('dias') or 0)
    e['oss'].add(t['os'])
    e['sup'] = t.get('responsavel', '')
rank = sorted(por.items(), key=lambda kv: -kv[1]['dias'])
oss_all = {t['os'] for t in ho}
print('HANDOVER vivo: %d tarefas, %d usinas, %d OS' % (len(ho), len(por), len(oss_all)))
out = []
for u, e in rank:
    rs = sorted({RESP.get(o, '-') for o in e['oss']})
    out.append(dict(u=u, oss=sorted(e['oss']), n=e['n'], atr=e['atr'],
                    dias=e['dias'], resp=' / '.join(rs), sup=e['sup']))
    print('%-44s | OS %-14s | %2d tarefas (%2d atr) | %3dd | %-28s | %s'
          % (u[:44], ','.join(sorted(e['oss'])[:2]), e['n'], e['atr'], e['dias'],
             ' / '.join(rs)[:28], e['sup'][:18]))
io.open('_ho_vivo.json', 'w', encoding='utf-8').write(
    json.dumps(out, ensure_ascii=False, indent=1))
