from datetime import datetime

from django.core.exceptions import ImproperlyConfigured
from django.views.generic import TemplateView

# TODO: 以下のimportは，煩雑になったら整理して有効にする
# from ledger.services.cash_book_services import calculate_monthly_balance
from ledger.services import calculate_monthly_balance
from enums.error_messages import ErrorMessages


class AbstractCashBookView(TemplateView):
    """
    出納帳の共通処理を提供する抽象ビュー。
    サブクラスは TARGET_ACCOUNT_NAME を設定するだけで利用可能。
    戻り値のコンテキスト:
      - book_data: [{ "date", "summary", "income", "expense", "balance" }, ...]
      - account_name, current_month, next_month_carryover, error_message (必要時)
    """

    template_name = "ledger/cash_book.html"
    TARGET_ACCOUNT_NAME = None  # サブクラスで設定すること

    def _parse_year_month(self):
        try:
            year = int(self.kwargs.get("year", datetime.now().year))
            month = int(self.kwargs.get("month", datetime.now().month))
        except (ValueError, TypeError):
            now = datetime.now()
            year, month = now.year, now.month
        return year, month

    def get_context_data(self, **kwargs):
        if not self.TARGET_ACCOUNT_NAME:
            raise ImproperlyConfigured(ErrorMessages.MESSAGE_0002.value)

        context = super().get_context_data(**kwargs)
        year, month = self._parse_year_month()

        # サービスに処理を委譲（サービスはdictで data/ending_balance または error を返す想定）
        result = calculate_monthly_balance(self.TARGET_ACCOUNT_NAME, year, month)

        if "error" in result:
            context["error_message"] = result["error"]
            context["book_data"] = []
            context["next_month_carryover"] = None
        else:
            # services.calculate_monthly_balance の返却スキーマに合わせて取り出す
            context["book_data"] = result.get("data", [])
            context["next_month_carryover"] = result.get("ending_balance")

        context["account_name"] = self.TARGET_ACCOUNT_NAME
        context["current_month"] = datetime(year, month, 1)
        return context


class CashBookView(AbstractCashBookView):
    """現金出納帳"""

    TARGET_ACCOUNT_NAME = "現金"


class CurrentAccountCashBookView(AbstractCashBookView):
    """当座預金出納帳"""

    TARGET_ACCOUNT_NAME = "当座預金"


class PettyCashBookView(AbstractCashBookView):
    """小口現金出納帳"""

    TARGET_ACCOUNT_NAME = "小口現金"
