import os
import sys
import requests
from pathlib import Path

# Force loading the .env file in the parent directory
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"

print("=== DIAGNOSTIC CASHPAY AUTH ===")
print(f"Base Directory: {BASE_DIR}")
print(f"Fichier .env trouve: {env_path.exists()}")

# Simuler la lecture du fichier .env
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
        
        # Nettoyer
        for _ in range(5):
            v = v.strip().rstrip(',').strip().strip('"').strip("'")
            
        mapping = {
            'client_id': 'CASHPAY_CLIENT_ID',
            'client_secret': 'CASHPAY_CLIENT_SECRET',
            'username': 'CASHPAY_USERNAME',
            'password': 'CASHPAY_PASSWORD'
        }
        if k in mapping:
            target_key = mapping[k]
            if target_key not in os.environ:
                os.environ[target_key] = v
                print(f"[.env] Charge et mappe: {k} -> {target_key} = '{v}'")
            else:
                print(f"[System ENV] {target_key} deja present dans l'OS: '{os.environ[target_key]}'")
        
        if k not in os.environ:
            os.environ[k] = v
            print(f"[.env] Charge: {k} = '{v}'")
        else:
            print(f"[System ENV] Deja defini dans l'OS: {k} = '{os.environ[k]}'")

load_env_manually(env_path)

# Nettoyer les valeurs
def clean_val(val):
    if not val:
        return ""
    for _ in range(5):
        val = val.strip().rstrip(',').strip().strip('"').strip("'")
    return val

# Recuperer les variables (avec fallback minuscules)
client_id = clean_val(os.getenv("CASHPAY_CLIENT_ID") or os.getenv("client_id"))
client_secret = clean_val(os.getenv("CASHPAY_CLIENT_SECRET") or os.getenv("client_secret"))
username = clean_val(os.getenv("CASHPAY_USERNAME") or os.getenv("username"))
password = clean_val(os.getenv("CASHPAY_PASSWORD") or os.getenv("password"))
base_url = clean_val(os.getenv("CASHPAY_API_BASE_URL") or "https://api.semoa-payments.ovh/sandbox-v3")

def analyze_value(name, val):
    if not val:
        print(f"[ERROR] {name} est VIDE ou NON DEFINI.")
        return False
    
    print(f"[INFO] {name} :")
    print(f"   - Longueur : {len(val)} caracteres")
    print(f"   - Premier caractere : {repr(val[0])}")
    print(f"   - Dernier caractere : {repr(val[-1])}")
    return True

ok = True
ok &= analyze_value("CASHPAY_CLIENT_ID", client_id)
ok &= analyze_value("CASHPAY_CLIENT_SECRET", client_secret)
ok &= analyze_value("CASHPAY_USERNAME", username)
ok &= analyze_value("CASHPAY_PASSWORD", password)

if not ok:
    print("\n[ERROR] Arret du diagnostic: Certaines variables sont manquantes.")
    sys.exit(1)

# Tester l'authentification avec les valeurs nettoyees
print("\n--- Test d'Authentification avec l'API CashPay (valeurs nettoyees) ---")
payload_clean = {
    "client_id": client_id,
    "client_secret": client_secret,
    "username": username,
    "password": password
}
url = f"{base_url.rstrip('/')}/auth"
print(f"POST {url}")
try:
    resp = requests.post(url, json=payload_clean, timeout=15)
    print(f"Statut HTTP : {resp.status_code}")
    if resp.status_code in (200, 201):
        print("[SUCCESS] AUTHENTIFICATION REUSSIE avec les valeurs nettoyees !")
        data = resp.json()
        print(f"Token recu: {data.get('access_token')[:15]}... (Expire dans {data.get('expires_in')}s)")
    else:
        print(f"[ERROR] Echec de l'authentification. Statut {resp.status_code}")
        print(f"Reponse du serveur : {resp.text}")
except Exception as e:
    print(f"[ERROR] Erreur de connexion : {e}")
