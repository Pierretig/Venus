import requests

client_id = "tchen.tigube"
client_secret = "yPzj1GiSjChO9HaahvunjYxQymh205B0"
username = "overn.tigube"
password = "[QmsXmRcERQAs#Y3"
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
