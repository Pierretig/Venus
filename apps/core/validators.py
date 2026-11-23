import re
from django.core.exceptions import ValidationError

# Préfixes valides Togo (Moov & TMoney)
# 90-93, 96-99 : TogoCellulaire (TMoney)
# 70, 71, 72, 78, 79 : Moov Africa Togo (Moov Money)
TOGO_PHONE_VALID_PREFIXES = (
    '90', '91', '92', '93', '96', '97', '98', '99',
    '79', '70', '71', '72', '78'
)


def validate_togo_phone(phone_raw):
    """
    Nettoie, valide et normalise un numéro de téléphone togolais.

    Accepte :
      - Formats locaux à 8 chiffres : '90010203'
      - Formats internationaux avec indicatif 228 : '22890010203' ou '+22890010203'
      - Formats avec espaces, tirets, points ou parenthèses : '+228 90 01 02 03'

    Règles :
      - Supprime tous les caractères non numériques
      - Vérifie la présence de 8 chiffres utiles après l'éventuel indicatif 228
      - Vérifie que les 8 chiffres commencent par un préfixe opérateur togolais valide
        (TogoCellulaire ou Moov)

    Retourne :
      - '228XXXXXXXX' (format international standard sans le +, 11 chiffres)
        attendu en base de données et compatible avec CashPay.

    Lève :
      - ValidationError si le numéro ne comporte pas 8 chiffres utiles ou si son
        préfixe n'appartient pas à un opérateur togolais valide.
    """
    digits = re.sub(r'\D', '', str(phone_raw or ''))

    if digits.startswith('228'):
        short_phone = digits[3:]
        full_phone = digits
    else:
        short_phone = digits
        full_phone = f'228{digits}'

    if len(short_phone) != 8:
        raise ValidationError("Le numéro doit comporter 8 chiffres (ex: 90010203).")

    if not short_phone.startswith(TOGO_PHONE_VALID_PREFIXES):
        raise ValidationError("Ce numéro ne semble pas appartenir à un opérateur Togolais valide.")

    return full_phone
