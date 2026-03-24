"""金額の HTML 表示用テンプレートフィルタ（円・整数・カンマ区切り）。"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import template
from django.contrib.humanize.templatetags.humanize import intcomma

register = template.Library()


@register.filter
def yen(value) -> str:
    """
    金額を「¥123,456」形式で表示する。負数は「-¥1,234」。
    DB の Decimal（小数2桁）を四捨五入で整数円にまとめる。
    """
    if value is None or value == "":
        return ""
    if value == "-":
        return "-"
    try:
        s = str(value).strip().replace(",", "")
        d = Decimal(s)
    except (InvalidOperation, ValueError, TypeError):
        return str(value)

    rounded = d.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    negative = rounded < 0
    abs_part = int(abs(rounded))
    formatted = intcomma(abs_part, use_l10n=False)
    body = f"¥{formatted}"
    return f"-{body}" if negative else body
