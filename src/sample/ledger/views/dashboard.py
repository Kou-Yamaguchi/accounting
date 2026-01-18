from datetime import datetime, timedelta
from decimal import Decimal
import json
from operator import attrgetter

from django.shortcuts import render
from django.views.generic import TemplateView

from ledger.structures import DayRange, YearMonth, AccountWithTotal
# TODO: 以下のimportは，煩雑になったら整理して有効にする
# from ledger.models.date_utils.day_range import DayRange
# from ledger.models.date_utils.year_month import YearMonth
from ledger.services import (
    get_last_year_month,
    list_decimal_to_int,
    get_month_range,
    calc_each_account_totals,
    calc_monthly_sales,
    calc_recent_half_year_sales,
    calc_monthly_profit,
    calc_recent_half_year_profits,
    get_company_sales_last_month,
    prepare_pareto_chart_data,
)

# TODO: 以下のimportは，煩雑になったら整理して有効にする
# from ledger.services.calculations.dashboard_calculations import (
#     calc_monthly_profit,
#     calc_monthly_sales,
#     calc_recent_half_year_profits,
#     calc_recent_half_year_sales,
#     calc_each_account_totals,
# )
# from ledger.services.calculations.pareto_chart_calculations import (
#     prepare_pareto_chart_data,
# )
# from ledger.services.data_fetchers.company_sales_fetcher import (
#     get_company_sales_last_month,
# )
# from ledger.services.date_utils.date_utilities import (
#     get_last_year_month,
#     get_month_range,
# )
# from ledger.services.type_definitions.account_with_total import (
#     AccountWithTotal,
# )
# from ledger.services.utils.decimal_utils import list_decimal_to_int


class DashboardView(TemplateView):
    """ダッシュボードビュー"""

    template_name = "ledger/dashboard/page.html"

    PARTIAL_CONFIG: dict = {
        "sales_chart": {
            "template": "ledger/dashboard/sales_chart.html",
            "context": "get_sales_chart_context",
        },
        "cost_chart": {
            "template": "ledger/dashboard/expense_breakdown_chart.html",
            "context": "get_expense_breakdown_context",
        },
        "pareto_sales_chart": {
            "template": "ledger/dashboard/pareto_sales_chart.html",
            "context": "get_pareto_sales_context",
        },
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current_year_month: YearMonth = YearMonth(
            year=datetime.now().year, month=datetime.now().month
        )
        context["monthly_sales"] = calc_monthly_sales(current_year_month)
        context["monthly_profit"] = calc_monthly_profit(current_year_month)

        context.update(self.get_sales_chart_context())
        context.update(self.get_expense_breakdown_context())
        context.update(self.get_pareto_sales_context())
        return context

    def get(self, request, *args, **kwargs):
        """AJAXリクエストに対してJSONデータを返す処理を追加"""
        partial = request.GET.get("partial")
        span = request.GET.get("span", "6months")
        # 部分テンプレートのレンダリング

        if request.headers.get("HX-Request") and partial in self.PARTIAL_CONFIG:
            cfg = self.PARTIAL_CONFIG[partial]
            context = getattr(self, cfg["context"])()
            return render(request, cfg["template"], context)
        return super().get(request, *args, **kwargs)

    def _get_sales_chart_data(
        self, span: int = 6
    ) -> tuple[list[str], list[int], list[int]]:
        labels = [
            f"{(datetime.now() - timedelta(days=30*i)).strftime('%Y-%m')}"
            for i in range(span - 1, -1, -1)
        ]
        sales_data = list_decimal_to_int(calc_recent_half_year_sales())
        profit_data = list_decimal_to_int(calc_recent_half_year_profits())
        return labels, sales_data, profit_data

    def get_sales_chart_context(self, span: int = 6) -> dict:
        labels, sales_data, profit_data = self._get_sales_chart_data(span)
        return {
            "sales_chart_labels": json.dumps(labels),
            "sales_chart_sales_data": json.dumps(sales_data),
            "sales_chart_profit_data": json.dumps(profit_data),
        }

    def _get_expense_breakdown_data(self) -> tuple[list[str], list[int]]:
        last_month_range: DayRange = get_month_range(get_last_year_month())
        list_total_expense_by_account: list[AccountWithTotal] = (
            calc_each_account_totals(last_month_range, ["expense"])
        )
        sorted_list_total_expense_by_account = sorted(
            list_total_expense_by_account, key=attrgetter("total_amount"), reverse=True
        )
        labels = [
            account_total.account_object.name
            for account_total in sorted_list_total_expense_by_account
        ]
        expense_data = [
            account_total.total_amount
            for account_total in sorted_list_total_expense_by_account
        ]
        expense_data_int = list_decimal_to_int(expense_data)
        return labels, expense_data_int

    def get_expense_breakdown_context(self) -> dict:
        labels, expense_data = self._get_expense_breakdown_data()
        return {
            "expense_breakdown_labels": json.dumps(labels),
            "expense_breakdown_data": json.dumps(expense_data),
        }

    def get_pareto_sales_context(self) -> dict:
        company_sales: dict[str, Decimal] = get_company_sales_last_month()
        labels, sales_data, list_cumulative_sales = prepare_pareto_chart_data(
            company_sales
        )
        return {
            "pareto_sales_labels": json.dumps(labels),
            "pareto_sales_data": json.dumps(sales_data),
            "pareto_sales_cumulative_data": json.dumps(list_cumulative_sales),
        }
