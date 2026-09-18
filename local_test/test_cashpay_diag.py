import os
import requests
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"

def clean_val(v):
    if not v:
        return ""
    for _ in range(5):
        v = v.strip().rstrip(',').strip().strip('"').strip("'")
    return v

env = {}
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    for sep in ("=", ":"):
        if sep in line:
            k, v = line.split(sep, 1)
            env[clean_val(k)] = clean_val(v)
            break

auth_url = "https://api.semoa-payments.ovh/sandbox-v3/auth"
auth_payload = {
    "client_id": env.get("client_id") or env.get("CASHPAY_CLIENT_ID"),
    "client_secret": env.get("client_secret") or env.get("CASHPAY_CLIENT_SECRET"),
    "username": env.get("username") or env.get("CASHPAY_USERNAME"),
    "password": env.get("password") or env.get("CASHPAY_PASSWORD")
}

res = requests.post(auth_url, json=auth_payload, timeout=10)
print("AUTH Status:", res.status_code)
token = res.json().get("access_token")

orders_url = "https://api.semoa-payments.ovh/sandbox-v3/orders"
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Test 1: with return_url
body1 = {
    "amount": 100,
    "currency": "XOF",
    "merchant_reference": "diag_test_01",
    "description": "Diagnostic test 1",
    "callback_url": "https://venus-luna.com/orders/webhook/cashpay/",
    "client": {"phone": "+22890000000"},
    "return_url": "https://venus-luna.com/orders/cashpay/return/999/"
}
res1 = requests.post(orders_url, json=body1, headers=headers, timeout=10)
print("ORDER res1 (with return_url):", res1.status_code, res1.text)

# Let's inspect the order details if created:
if res1.status_code in (200, 201):
    data = res1.json()
    order_ref = data.get("order_reference")
    if order_ref:
        res_get = requests.get(f"{orders_url}/{order_ref}", headers=headers, timeout=10)
        print("ORDER GET details:", res_get.status_code, res_get.text)
