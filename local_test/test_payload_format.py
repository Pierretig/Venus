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
base_url = "https://api.semoa-payments.ovh/sandbox-v3/auth"

tests = [
    {
        "name": "JSON Payload",
        "post_kwargs": {
            "json": {
                "client_id": client_id,
                "client_secret": client_secret,
                "username": username,
                "password": password
            }
        }
    },
    {
        "name": "Form Data (x-www-form-urlencoded)",
        "post_kwargs": {
            "data": {
                "client_id": client_id,
                "client_secret": client_secret,
                "username": username,
                "password": password
            }
        }
    },
    {
        "name": "JSON with grant_type",
        "post_kwargs": {
            "json": {
                "client_id": client_id,
                "client_secret": client_secret,
                "username": username,
                "password": password,
                "grant_type": "password"
            }
        }
    },
    {
        "name": "Form Data with grant_type",
        "post_kwargs": {
            "data": {
                "client_id": client_id,
                "client_secret": client_secret,
                "username": username,
                "password": password,
                "grant_type": "password"
            }
        }
    },
    {
        "name": "JSON trailing slash",
        "url": "https://api.semoa-payments.ovh/sandbox-v3/auth/",
        "post_kwargs": {
            "json": {
                "client_id": client_id,
                "client_secret": client_secret,
                "username": username,
                "password": password
            }
        }
    }
]

print("Running payload format tests...")
for test in tests:
    url = test.get("url", base_url)
    kwargs = test["post_kwargs"]
    try:
        resp = requests.post(url, timeout=10, **kwargs)
        print(f"Test: {test['name']} -> Status: {resp.status_code} -> {resp.text.strip()}")
    except Exception as e:
        print(f"Test: {test['name']} -> Error: {e}")
