"""
Audit définitif du flux de navigation CashPay.
Teste : est-ce que redirect_url dans le body est accepté et utilisé ?
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

# Auth
r = requests.post(f"{api_base}/auth", json={
    "client_id": client_id, "client_secret": client_secret,
    "username": username, "password": password,
}, timeout=15)
print("AUTH:", r.status_code)
token = r.json().get("access_token")
if not token:
    print("ECHEC AUTH"); exit(1)

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

RETURN_URL = "https://venus-luna.com/orders/retour/TEST999/"

print()
print("=" * 60)
print("TEST 1: body SANS redirect_url (reference: test_nav_A)")
print("=" * 60)
body_A = {
    "amount": 500, "currency": "XOF",
    "merchant_reference": "test_nav_audit_A",
    "description": "Audit navigation A",
    "callback_url": "https://venus-luna.com/orders/webhook/cashpay/",
    "client": {"phone": "+22890000000"},
}
r1 = requests.post(f"{api_base}/orders", json=body_A, headers=headers, timeout=15)
print(f"Status: {r1.status_code}")
d1 = r1.json()
print(f"redirect_url dans reponse: {d1.get('redirect_url')!r}")
print(f"bill_url: {d1.get('bill_url')!r}")
print(f"Tous les champs: {list(d1.keys())}")

print()
print("=" * 60)
print("TEST 2: body AVEC redirect_url (reference: test_nav_B)")
print("=" * 60)
body_B = {
    "amount": 500, "currency": "XOF",
    "merchant_reference": "test_nav_audit_B",
    "description": "Audit navigation B",
    "callback_url": "https://venus-luna.com/orders/webhook/cashpay/",
    "client": {"phone": "+22890000000"},
    "redirect_url": RETURN_URL,
}
r2 = requests.post(f"{api_base}/orders", json=body_B, headers=headers, timeout=15)
print(f"Status: {r2.status_code}")
d2 = r2.json()
print(f"redirect_url dans reponse: {d2.get('redirect_url')!r}")
print(f"bill_url: {d2.get('bill_url')!r}")

print()
print("=" * 60)
print("TEST 3: body AVEC return_url (reference: test_nav_C)")
print("=" * 60)
body_C = {
    "amount": 500, "currency": "XOF",
    "merchant_reference": "test_nav_audit_C",
    "description": "Audit navigation C",
    "callback_url": "https://venus-luna.com/orders/webhook/cashpay/",
    "client": {"phone": "+22890000000"},
    "return_url": RETURN_URL,
}
r3 = requests.post(f"{api_base}/orders", json=body_C, headers=headers, timeout=15)
print(f"Status: {r3.status_code}")
d3 = r3.json()
print(f"redirect_url dans reponse: {d3.get('redirect_url')!r}")
print(f"return_url dans reponse: {d3.get('return_url')!r}")
print(f"bill_url: {d3.get('bill_url')!r}")

print()
print("=" * 60)
print("TEST 4: body AVEC success_url (reference: test_nav_D)")
print("=" * 60)
body_D = {
    "amount": 500, "currency": "XOF",
    "merchant_reference": "test_nav_audit_D",
    "description": "Audit navigation D",
    "callback_url": "https://venus-luna.com/orders/webhook/cashpay/",
    "client": {"phone": "+22890000000"},
    "success_url": RETURN_URL,
}
r4 = requests.post(f"{api_base}/orders", json=body_D, headers=headers, timeout=15)
print(f"Status: {r4.status_code}")
d4 = r4.json()
print(f"redirect_url dans reponse: {d4.get('redirect_url')!r}")
print(f"success_url dans reponse: {d4.get('success_url')!r}")
print(f"bill_url: {d4.get('bill_url')!r}")

print()
print("=" * 60)
print("SYNTHESE:")
print("Test A (sans redirect_url) -> redirect_url=", d1.get('redirect_url'))
print("Test B (avec redirect_url) -> redirect_url=", d2.get('redirect_url'))
print("Test C (avec return_url)   -> redirect_url=", d3.get('redirect_url'), "| return_url=", d3.get('return_url'))
print("Test D (avec success_url)  -> redirect_url=", d4.get('redirect_url'), "| success_url=", d4.get('success_url'))
