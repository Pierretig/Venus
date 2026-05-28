import requests

client_id = "tchen.tigube"
client_secret = "yPzj1GiSjChO9HaahvunjYxQymh205B0"
username = "overn.tigube"
password = "[QmsXmRcERQAs#Y3"

payload = {
    "client_id": client_id,
    "client_secret": client_secret,
    "username": username,
    "password": password
}

domains = [
    "https://api.sandbox-v3.cashpay.tg/auth",
    "https://api.sandbox.cashpay.tg/v3/auth",
    "https://api.cashpay.tg/sandbox-v3/auth",
    "https://api.semoa-payments.com/sandbox-v3/auth",
    "https://api.semoa-payments.ovh/sandbox-v3/auth"
]

print("Testing alternative domains...")
for url in domains:
    try:
        resp = requests.post(url, json=payload, timeout=5)
        print(f"URL: {url} -> Status: {resp.status_code} -> {resp.text.strip()[:100]}")
    except Exception as e:
        print(f"URL: {url} -> Error: {e}")
