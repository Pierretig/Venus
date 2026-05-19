import logging
import jwt

logger = logging.getLogger(__name__)


def decode_cashpay_jwt(token: str, secret_key: str):
    """Décoder le JWT transmis par CashPay (doc: token signé HS256)."""
    if not token:
        return None
    # Doc ne précise pas l'algorithme mais l'exemple utilise HS256.
    return jwt.decode(token, secret_key, algorithms=["HS256"])

