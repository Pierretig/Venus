"""
Test de connexion CashPay avec les variables du .env propre.
Lit les clés au format KEY=value (sans virgules ni deux-points).
"""
import requests
from pathlib import Path

env_path = Path(__file__).resolve().parent.parent / ".env"

env = {}
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    if "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

client_id     = env.get("CASHPAY_CLIENT_ID", "")
client_secret = env.get("CASHPAY_CLIENT_SECRET", "")
username      = env.get("CASHPAY_USERNAME", "")
password      = env.get("CASHPAY_PASSWORD", "")
api_base      = env.get("CASHPAY_API_BASE_URL", "https://api.semoa-payments.ovh/sandbox-v3")
webhook_key   = env.get("CASHPAY_SECRET_WEBHOOK", "")

print("=== Configuration CashPay ===")
print(f"  CLIENT_ID  : {client_id!r}")
print(f"  USERNAME   : {username!r}")
print(f"  API_BASE   : {api_base!r}")
print(f"  WEBHOOK KEY: {webhook_key[:8]}... (len={len(webhook_key)})")
print()

# --- STEP 1: Authentification ---
auth_url = f"{api_base}/auth"
auth_payload = {
    "client_id": client_id,
    "client_secret": client_secret,
    "username": username,
    "password": password,
}
print("1) AUTH POST", auth_url)
r = requests.post(auth_url, json=auth_payload, timeout=15)
print(f"   Status: {r.status_code}")
if r.status_code not in (200, 201):
    print(f"   ERREUR: {r.text}")
    exit(1)

token = r.json().get("access_token")
print(f"   Token: {token[:30]}..." if token else "   Token: ABSENT")
print()

if not token:
    print("ECHEC: pas de token")
    exit(1)

# --- STEP 2: Créer une commande Link2Pay de test ---
orders_url = f"{api_base}/orders"
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}
body = {
    "amount": 500,
    "currency": "XOF",
    "merchant_reference": "test_retour_marchand_001",
    "description": "Test retour marchand Venus Luna",
    "callback_url": "https://venus-luna.com/orders/webhook/cashpay/",
    "client": {"phone": "+22890000000"},
}
print("2) ORDER POST", orders_url)
r2 = requests.post(orders_url, json=body, headers=headers, timeout=15)
print(f"   Status: {r2.status_code}")
data = r2.json()
print(f"   Response: {data}")
print()

bill_url = data.get("bill_url")
order_ref = data.get("order_reference")
print(f"   bill_url       : {bill_url}")
print(f"   order_reference: {order_ref}")

if bill_url:
    print()
    print("✅ SUCCESS: bill_url obtenu. Le paiement peut être initié.")
    print(f"   Ouvrir: {bill_url}")
else:
    print()
    print("❌ ECHEC: pas de bill_url dans la réponse.")

# --- STEP 3: Vérifier le statut de la commande ---
if order_ref:
    print()
    print(f"3) GET order status: {api_base}/orders/{order_ref}")
    r3 = requests.get(f"{api_base}/orders/{order_ref}", headers=headers, timeout=15)
    print(f"   Status: {r3.status_code}")
    print(f"   Response: {r3.json()}")

# --- STEP 4: Vérifier que le webhook JWT est décodable ---
print()
print("4) Test décodage JWT webhook avec CASHPAY_SECRET_WEBHOOK...")
try:
    import jwt
    # Token de test (exemple de la doc CashPay page 33)
    test_token_payload = {
        "order_reference": "TEST-001",
        "amount": 500,
        "state": "Paid",
        "merchant_reference": "test_retour_marchand_001",
        "client": {"phone": "+22890000000"},
        "received_amount": 500,
    }
    encoded = jwt.encode(test_token_payload, webhook_key, algorithm="HS256")
    decoded = jwt.decode(encoded, webhook_key, algorithms=["HS256"])
    print(f"   ✅ JWT encode/decode OK: state={decoded.get('state')}")
except Exception as e:
    print(f"   ❌ Erreur JWT: {e}")
