from decimal import Decimal
from typing import Optional

from django.template import Context, Template
from django.test import SimpleTestCase


class YenFilterTest(SimpleTestCase):
    def _render(self, template_str: str, context: Optional[dict] = None) -> str:
        t = Template("{% load ledger_money %}" + template_str)
        return t.render(Context(context or {})).strip()

    def test_positive_integer(self):
        self.assertEqual(self._render("{{ n|yen }}", {"n": 1234567}), "¥1,234,567")

    def test_positive_decimal_rounds_half_up(self):
        self.assertEqual(
            self._render("{{ amount|yen }}", {"amount": Decimal("1234.56")}),
            "¥1,235",
        )

    def test_negative(self):
        self.assertEqual(
            self._render("{{ amount|yen }}", {"amount": Decimal("-1234.56")}),
            "-¥1,235",
        )

    def test_zero(self):
        self.assertEqual(
            self._render("{{ amount|yen }}", {"amount": Decimal("0.00")}),
            "¥0",
        )

    def test_none_empty(self):
        self.assertEqual(self._render("{{ n|yen }}", {"n": None}), "")
        self.assertEqual(self._render("{{ e|yen }}", {"e": ""}), "")

    def test_string_amount(self):
        self.assertEqual(self._render("{{ s|yen }}", {"s": "100.00"}), "¥100")
