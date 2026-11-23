from django.test import SimpleTestCase
from django.core.exceptions import ValidationError
from apps.core.validators import validate_togo_phone, TOGO_PHONE_VALID_PREFIXES


class TogoPhoneValidatorTests(SimpleTestCase):
    """
    Tests exhaustifs du validateur centralisé des numéros togolais.
    """

    def test_local_8_digits_formats(self):
        """Formats locaux à 8 chiffres pour TMoney et Moov."""
        self.assertEqual(validate_togo_phone('90010203'), '22890010203')
        self.assertEqual(validate_togo_phone('70112233'), '22870112233')
        self.assertEqual(validate_togo_phone('99887766'), '22899887766')
        self.assertEqual(validate_togo_phone('79123456'), '22879123456')

    def test_international_formats_with_228(self):
        """Formats avec indicatif 228 (avec ou sans signe +)."""
        self.assertEqual(validate_togo_phone('22890010203'), '22890010203')
        self.assertEqual(validate_togo_phone('+22890010203'), '22890010203')

    def test_formats_with_separators(self):
        """Formats bruités avec espaces, tirets, points et parenthèses."""
        self.assertEqual(validate_togo_phone('+228 90 01 02 03'), '22890010203')
        self.assertEqual(validate_togo_phone('90-01-02-03'), '22890010203')
        self.assertEqual(validate_togo_phone('(228) 90.01.02.03'), '22890010203')

    def test_all_valid_operator_prefixes(self):
        """Vérifie tous les préfixes agréés TogoCellulaire et Moov."""
        for prefix in TOGO_PHONE_VALID_PREFIXES:
            with self.subTest(prefix=prefix):
                num = f"{prefix}123456"
                self.assertEqual(validate_togo_phone(num), f"228{num}")

    def test_invalid_length_too_short(self):
        """Rejet d'un numéro à 7 chiffres."""
        with self.assertRaises(ValidationError) as ctx:
            validate_togo_phone('9001020')
        self.assertIn("8 chiffres", str(ctx.exception))

    def test_invalid_length_too_long(self):
        """Rejet d'un numéro à 9 chiffres."""
        with self.assertRaises(ValidationError) as ctx:
            validate_togo_phone('900102030')
        self.assertIn("8 chiffres", str(ctx.exception))

    def test_invalid_prefix(self):
        """Rejet de préfixes non reconnus au Togo."""
        with self.assertRaises(ValidationError) as ctx:
            validate_togo_phone('80010203')
        self.assertIn("opérateur Togolais valide", str(ctx.exception))

        with self.assertRaises(ValidationError) as ctx:
            validate_togo_phone('01020304')
        self.assertIn("opérateur Togolais valide", str(ctx.exception))

    def test_empty_and_non_numeric_values(self):
        """Rejet de chaîne vide, None ou texte alphabétique."""
        with self.assertRaises(ValidationError):
            validate_togo_phone('')
        with self.assertRaises(ValidationError):
            validate_togo_phone(None)
        with self.assertRaises(ValidationError):
            validate_togo_phone('abcdefgh')

    def test_cashpay_compatibility_format(self):
        """Vérifie que la sortie 11 chiffres '228XXXXXXXX' est directement convertible pour CashPay."""
        res = validate_togo_phone('90 01 02 03')
        self.assertEqual(len(res), 11)
        self.assertTrue(res.startswith('228'))
        cashpay_fmt = f"+{res}"
        self.assertEqual(cashpay_fmt, '+22890010203')
