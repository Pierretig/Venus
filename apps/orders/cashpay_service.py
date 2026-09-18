import time
import logging
from decimal import Decimal

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class CashPayService:
    """Client minimal CashPay (Link2Pay) basé sur la doc API v3."""

    def __init__(self):
        def _clean(val):
            if not isinstance(val, str):
                return val
            for _ in range(5):
                val = val.strip().rstrip(',').strip().strip('"').strip("'")
            return val

        self.client_id = _clean(getattr(settings, "CASHPAY_CLIENT_ID", ""))
        self.client_secret = _clean(getattr(settings, "CASHPAY_CLIENT_SECRET", ""))
        self.username = _clean(getattr(settings, "CASHPAY_USERNAME", ""))
        self.password = _clean(getattr(settings, "CASHPAY_PASSWORD", ""))

        self.api_base_url = _clean(getattr(
            settings,
            "CASHPAY_API_BASE_URL",
            "https://api.semoa-payments.ovh/sandbox-v3",
        )).rstrip("/")
        self._token = None
        self._token_expires_at = 0

    def is_configured(self) -> bool:
        return all([self.client_id, self.client_secret, self.username, self.password])

    def _get_access_token(self) -> str:
        now = int(time.time())
        if self._token and now < self._token_expires_at - 30:
            return self._token

        url = f"{self.api_base_url}/auth"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "username": self.username,
            "password": self.password,
        }

        try:
            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code not in (200, 201):
                try:
                    error_detail = resp.json()
                except Exception:
                    error_detail = resp.text
                raise RuntimeError(
                    f"Authentification CashPay échouée ({resp.status_code}) : {error_detail} "
                    f"(Vérifiez vos identifiants CASHPAY_* dans .env)"
                )
            data = resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f"Erreur de connexion à l'API CashPay : {e}")

        self._token = data.get("access_token")
        expires_in = int(data.get("expires_in", 3600))
        self._token_expires_at = now + expires_in

        if not self._token:
            raise RuntimeError("CashPay OAuth: access_token manquant dans la réponse")
        return self._token

    def create_link2pay_order(
        self,
        amount: Decimal,
        currency: str,
        merchant_reference: str,
        description: str,
        callback_url: str,
        phone: str,
        type_notif=None,
    ):
        """
        Crée une commande Link2Pay sur CashPay et retourne la réponse complète.

        Champs utiles dans la réponse :
          - bill_url       : URL de la facture CashPay (rediriger le client ici)
          - order_reference: référence interne CashPay (pour get_order_status)
          - merchant_reference: référence merchant (= order.id Venus Luna)

        NB : return_url n'est PAS documenté dans l'API Link2Pay CashPay v3.
        La redirection navigateur après paiement est gérée côté Venus Luna via
        la page cashpay_payment_page + polling de cashpay_return.
        """
        access_token = self._get_access_token()
        url = f"{self.api_base_url}/orders"

        # Normalisation du numéro de téléphone en format international
        if phone:
            phone = phone.strip()
            if not phone.startswith('+'):
                if phone.startswith('228') and len(phone) == 11:
                    phone = f"+{phone}"
                elif len(phone) == 8:
                    phone = f"+228{phone}"
                else:
                    phone = f"+{phone}"

        body = {
            "amount": int(amount),
            "currency": currency,
            "merchant_reference": merchant_reference,
            "description": description,
            "callback_url": callback_url,
            "client": {"phone": phone},
        }
        if type_notif:
            body["type_notif"] = type_notif

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            resp = requests.post(url, json=body, headers=headers, timeout=30)
            if resp.status_code not in (200, 201):
                try:
                    error_detail = resp.json()
                except Exception:
                    error_detail = resp.text
                raise RuntimeError(
                    f"Création de commande CashPay échouée ({resp.status_code}) : {error_detail}"
                )
            data = resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f"Erreur lors de la création de la commande CashPay : {e}")

        # Link2Pay renvoie bill_url et order_reference (d'après doc)
        if data.get("status") == "success":
            return data

        raise RuntimeError(data.get("message") or "CashPay order creation failed")

    def get_order_status(self, order_reference: str) -> dict:
        """
        Interroge directement l'API CashPay pour connaître le statut d'une commande.

        Mécanisme de fallback au webhook :
        si le webhook n'arrive pas (réseau, config), le polling frontend appelle
        cette méthode via cashpay_return pour confirmer le paiement côté serveur.

        Retourne le dict de réponse CashPay (champs : state, amount, bill_url, …)
        ou lève RuntimeError en cas d'erreur.

        États possibles : Pending, Paid, Partial, Excess, Canceled, Error, Expired
        """
        access_token = self._get_access_token()
        url = f"{self.api_base_url}/orders/{order_reference}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 404:
                raise RuntimeError(f"Commande CashPay introuvable : {order_reference}")
            if resp.status_code not in (200, 201):
                raise RuntimeError(
                    f"Erreur API CashPay get_order_status ({resp.status_code}) : {resp.text[:300]}"
                )
            return resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f"Erreur réseau CashPay get_order_status : {e}")
