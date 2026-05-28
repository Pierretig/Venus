import time
import logging
from decimal import Decimal

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class CashPayService:
    """Client minimal CashPay (Link2Pay) basé sur la doc API v3."""

    def __init__(self):
        self.client_id = getattr(settings, "CASHPAY_CLIENT_ID", "")
        if isinstance(self.client_id, str):
            self.client_id = self.client_id.strip('"').strip("'")
            
        self.client_secret = getattr(settings, "CASHPAY_CLIENT_SECRET", "")
        if isinstance(self.client_secret, str):
            self.client_secret = self.client_secret.strip('"').strip("'")
            
        self.username = getattr(settings, "CASHPAY_USERNAME", "")
        if isinstance(self.username, str):
            self.username = self.username.strip('"').strip("'")
            
        self.password = getattr(settings, "CASHPAY_PASSWORD", "")
        if isinstance(self.password, str):
            self.password = self.password.strip('"').strip("'")
            
        self.api_base_url = getattr(
            settings,
            "CASHPAY_API_BASE_URL",
            "https://api.semoa-payments.ovh/dev-v3",
        ).rstrip("/").strip('"').strip("'")
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

        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        self._token = data.get("access_token")
        expires_in = int(data.get("expires_in", 3600))
        self._token_expires_at = now + expires_in

        if not self._token:
            raise RuntimeError("CashPay OAuth: access_token manquant")
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
        access_token = self._get_access_token()
        url = f"{self.api_base_url}/orders"

        # Doc: callback_url dans le body, et client.phone en international format.
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

        resp = requests.post(url, json=body, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # Link2Pay renvoie bill_url (d'après doc)
        if data.get("status") == "success":
            return data

        raise RuntimeError(data.get("message") or "CashPay order creation failed")

