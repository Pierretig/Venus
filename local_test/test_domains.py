import os
from pathlib import Path
import requests

# Load the .env file in the parent directory
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"

def load_env_manually(path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
        elif ":" in line:
            k, v = line.split(":", 1)
        else:
            continue
        k = k.strip()
        v = v.strip()
        for _ in range(5):
            v = v.strip().rstrip(',').strip().strip('"').strip("'")
        os.environ[k] = v

load_env_manually(env_path)

client_id = os.getenv("CASHPAY_CLIENT_ID") or os.getenv("client_id")
client_secret = os.getenv("CASHPAY_CLIENT_SECRET") or os.getenv("client_secret")
username = os.getenv("CASHPAY_USERNAME") or os.getenv("username")
password = os.getenv("CASHPAY_PASSWORD") or os.getenv("password")

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
