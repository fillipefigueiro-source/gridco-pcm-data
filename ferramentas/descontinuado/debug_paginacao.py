"""Debug paginacao Fracttal: testa varios parametros."""
import sys
sys.path.insert(0, '.')
from gerar_bd_via_api import FracttalClient, CLIENT_ID, CLIENT_SECRET, BASE_URL

client = FracttalClient(CLIENT_ID, CLIENT_SECRET, BASE_URL)
client.autenticar()
client._resolver_path("work_orders")
url = client.base_url + "work_orders"

def test(rotulo, params):
    r = client.session.get(url, headers=client._headers(), params=params, timeout=15)
    payload = r.json()
    items = payload.get("data", [])
    folios = [str(it.get("wo_folio")) for it in items]
    print(f"{rotulo:>30}: {len(items)} items, folios: {folios}")

print("\nTestando varios padroes de paginacao...\n")

# Padrao atual (page nao funciona)
test("page=1", {"limit": 5, "page": 1})
test("page=2", {"limit": 5, "page": 2})

# Tentar start (offset)
test("start=0", {"limit": 5, "start": 0})
test("start=5", {"limit": 5, "start": 5})
test("start=10", {"limit": 5, "start": 10})
test("start=100", {"limit": 5, "start": 100})

# Tentar offset
test("offset=0", {"limit": 5, "offset": 0})
test("offset=5", {"limit": 5, "offset": 5})

# Tentar skip
test("skip=5", {"limit": 5, "skip": 5})

# Tentar combinacao
test("page=2 start=5", {"limit": 5, "page": 2, "start": 5})
