import os
import sys
import requests
from pathlib import Path

# Force loading the .env file in the parent directory
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"

print("=== DIAGNOSTIC CASHPAY AUTH ===")
print(f"Base Directory: {BASE_DIR}")
print(f"Fichier .env trouvé: {env_path.exists()}")

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
        # On n'écrase pas si déjà dans os.environ
        if k not in os.environ:
            os.environ[k] = v
            print(f"[.env] Chargé: {k} (brut dans fichier: '{v}')")
        else:
            print(f"[System ENV] Déjà défini dans l'OS: {k} = '{os.environ[k]}'")

load_env_manually(env_path)

# Récupérer les variables
client_id = os.getenv("CASHPAY_CLIENT_ID")
client_secret = os.getenv("CASHPAY_CLIENT_SECRET")
username = os.getenv("CASHPAY_USERNAME")
password = os.getenv("CASHPAY_PASSWORD")
base_url = os.getenv("CASHPAY_API_BASE_URL", "https://api.semoa-payments.ovh/sandbox-v3")

def analyze_value(name, val):
    if not val:
        print(f"❌ {name} est VIDE ou NON DÉFINI.")
        return False
    
    has_quotes = val.startswith('"') and val.endswith('"') or val.startswith("'") and val.endswith("'")
    double_quotes_count = val.count('"')
    
    print(f"🔍 {name} :")
    print(f"   - Longueur : {len(val)} caractères")
    print(f"   - Entouré de guillemets : {has_quotes}")
    print(f"   - Nombre de guillemets doubles : {double_quotes_count}")
    print(f"   - Premier caractère : {repr(val[0])}")
    print(f"   - Dernier caractère : {repr(val[-1])}")
    
    if has_quotes or double_quotes_count > 0:
        print(f"   ⚠️ WARNING: Il y a des guillemets dans la valeur de {name}. Supprimez-les de votre configuration/fichier .env.")
    return True

ok = True
ok &= analyze_value("CASHPAY_CLIENT_ID", client_id)
ok &= analyze_value("CASHPAY_CLIENT_SECRET", client_secret)
ok &= analyze_value("CASHPAY_USERNAME", username)
ok &= analyze_value("CASHPAY_PASSWORD", password)

if not ok:
    print("\n❌ Arrêt du diagnostic: Certaines variables sont manquantes.")
    sys.exit(1)

# Nettoyer les guillemets pour le test d'API
clean_client_id = client_id.strip('"').strip("'")
clean_client_secret = client_secret.strip('"').strip("'")
clean_username = username.strip('"').strip("'")
clean_password = password.strip('"').strip("'")

# Tester l'authentification avec les valeurs brutes (telles qu'elles sont lues actuellement)
print("\n--- Test 1: Authentification avec les valeurs actuelles (brutes) ---")
payload_raw = {
    "client_id": client_id,
    "client_secret": client_secret,
    "username": username,
    "password": password
}
url = f"{base_url.rstrip('/')}/auth"
print(f"POST {url}")
try:
    resp = requests.post(url, json=payload_raw, timeout=15)
    print(f"Statut HTTP : {resp.status_code}")
    if resp.status_code == 201:
        print("✅ AUTHENTIFICATION RÉUSSIE avec les valeurs brutes !")
    else:
        print(f"❌ Échec de l'authentification. Réponse du serveur : {resp.text}")
except Exception as e:
    print(f"❌ Erreur de connexion : {e}")

# Tester l'authentification avec les valeurs nettoyées de tout guillemet
print("\n--- Test 2: Authentification après avoir retiré les guillemets ---")
payload_clean = {
    "client_id": clean_client_id,
    "client_secret": clean_client_secret,
    "username": clean_username,
    "password": clean_password
}
try:
    resp = requests.post(url, json=payload_clean, timeout=15)
    print(f"Statut HTTP : {resp.status_code}")
    if resp.status_code == 201:
        print("✅ AUTHENTIFICATION RÉUSSIE avec les valeurs nettoyées !")
        print("👉 Conseil : Retirez les guillemets de vos variables d'environnement dans votre fichier .env ou sur votre interface Dokploy.")
    else:
        print(f"❌ Échec même avec les valeurs nettoyées. Réponse du serveur : {resp.text}")
except Exception as e:
    print(f"❌ Erreur de connexion : {e}")
