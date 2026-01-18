from datetime import date, datetime
from decimal import Decimal

from django.test import TestCase, RequestFactory

from ledger.tests.utils import create_accounts, create_journal_entry, AccountData
from ledger.views import DashboardView


class DashboardViewTest(TestCase):
    """
    DashboardViewのテスト
    """

    def setUp(self):
        self.factory = RequestFactory()
        # テストに必要な勘定科目を作成
        self.accounts = create_accounts(
            [
                AccountData(name="現金", type="asset"),
                AccountData(name="売上", type="revenue"),
                AccountData(name="仕入", type="expense"),
                AccountData(name="消耗品費", type="expense"),
            ]
        )

    def test_dashboard_view_access(self):
        """ダッシュボードビューにアクセスできることを確認"""
        # from ledger.views import DashboardView

        request = self.factory.get("/ledger/dashboard/")
        response = DashboardView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("monthly_sales", response.context_data)
        self.assertIn("monthly_profit", response.context_data)
        self.assertIn("sales_chart_labels", response.context_data)
        self.assertIn("sales_chart_sales_data", response.context_data)
        self.assertIn("sales_chart_profit_data", response.context_data)

    def test_monthly_sales_calculation(self):
        """月次売上が正しく計算されることを確認"""
        # from ledger.views import DashboardView

        # 現在月の取引を作成
        current_year = datetime.now().year
        current_month = datetime.now().month

        # 売上取引1: 10000円
        create_journal_entry(
            date(current_year, current_month, 5),
            "売上取引1",
            [(self.accounts["現金"], Decimal("10000.00"))],
            [(self.accounts["売上"], Decimal("10000.00"))],
        )

        # 売上取引2: 5000円
        create_journal_entry(
            date(current_year, current_month, 15),
            "売上取引2",
            [(self.accounts["現金"], Decimal("5000.00"))],
            [(self.accounts["売上"], Decimal("5000.00"))],
        )

        request = self.factory.get("/ledger/dashboard/")
        response = DashboardView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        # 月次売上が15000円であること
        self.assertEqual(response.context_data["monthly_sales"], Decimal("15000.00"))

    def test_monthly_profit_calculation(self):
        """月次利益が正しく計算されることを確認"""
        # from ledger.views import DashboardView

        # 現在月の取引を作成
        current_year = datetime.now().year
        current_month = datetime.now().month

        # 売上取引: 20000円
        create_journal_entry(
            date(current_year, current_month, 5),
            "売上取引",
            [(self.accounts["現金"], Decimal("20000.00"))],
            [(self.accounts["売上"], Decimal("20000.00"))],
        )

        # 仕入取引: 8000円
        create_journal_entry(
            date(current_year, current_month, 10),
            "仕入取引",
            [(self.accounts["仕入"], Decimal("8000.00"))],
            [(self.accounts["現金"], Decimal("8000.00"))],
        )

        # 消耗品費: 2000円
        create_journal_entry(
            date(current_year, current_month, 15),
            "消耗品購入",
            [(self.accounts["消耗品費"], Decimal("2000.00"))],
            [(self.accounts["現金"], Decimal("2000.00"))],
        )

        request = self.factory.get("/ledger/dashboard/")
        response = DashboardView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        # 月次利益が10000円（売上20000 - 費用10000）であること
        self.assertEqual(response.context_data["monthly_profit"], Decimal("10000.00"))

    def test_sales_chart_data_structure(self):
        """売上・利益推移グラフ用データの構造が正しいことを確認"""
        from ledger.views import DashboardView
        import json

        request = self.factory.get("/ledger/dashboard/")
        response = DashboardView.as_view()(request)

        self.assertEqual(response.status_code, 200)

        # JSONデータがパース可能であることを確認
        labels = json.loads(response.context_data["sales_chart_labels"])
        sales_data = json.loads(response.context_data["sales_chart_sales_data"])
        profit_data = json.loads(response.context_data["sales_chart_profit_data"])

        # labelsが6ヶ月分のリストであること
        self.assertEqual(len(labels), 6)
        # sales_dataが6ヶ月分のリストであること
        self.assertEqual(len(sales_data), 6)
        # profit_dataが6ヶ月分のリストであること
        self.assertEqual(len(profit_data), 6)

        # labelsの各要素が"YYYY-MM"形式であること
        for label in labels:
            self.assertRegex(label, r"^\d{4}-\d{2}$")

        # sales_dataとprofit_dataの各要素が数値であること
        for sales in sales_data:
            self.assertIsInstance(sales, int)
        for profit in profit_data:
            self.assertIsInstance(profit, int)

    def test_recent_half_year_sales_and_profit_trend(self):
        """直近半年間の売上・利益推移が正しく計算されることを確認"""
        from ledger.views import DashboardView
        import json
        from dateutil.relativedelta import relativedelta

        # 過去6ヶ月分のデータを作成
        today = date.today()

        for i in range(6):
            target_date = today - relativedelta(months=i)
            year = target_date.year
            month = target_date.month

            # 各月に売上と費用を作成
            # 売上: (6-i) * 10000円（古い月ほど少ない）
            sales_amount = Decimal((6 - i) * 10000)
            create_journal_entry(
                date(year, month, 10),
                f"{year}年{month}月の売上",
                [(self.accounts["現金"], sales_amount)],
                [(self.accounts["売上"], sales_amount)],
            )

            # 費用: (6-i) * 3000円
            expense_amount = Decimal((6 - i) * 3000)
            create_journal_entry(
                date(year, month, 15),
                f"{year}年{month}月の仕入",
                [(self.accounts["仕入"], expense_amount)],
                [(self.accounts["現金"], expense_amount)],
            )

        request = self.factory.get("/ledger/dashboard/")
        response = DashboardView.as_view()(request)

        self.assertEqual(response.status_code, 200)

        sales_data = json.loads(response.context_data["sales_chart_sales_data"])
        profit_data = json.loads(response.context_data["sales_chart_profit_data"])

        # sales_dataが昇順（古い月から新しい月）になっていることを確認
        self.assertEqual(sales_data[0], 10000)  # 6ヶ月前
        self.assertEqual(sales_data[1], 20000)  # 5ヶ月前
        self.assertEqual(sales_data[2], 30000)  # 4ヶ月前
        self.assertEqual(sales_data[3], 40000)  # 3ヶ月前
        self.assertEqual(sales_data[4], 50000)  # 2ヶ月前
        self.assertEqual(sales_data[5], 60000)  # 1ヶ月前

        # profit_dataも正しく計算されていることを確認（売上 - 費用）
        self.assertEqual(profit_data[0], 7000)  # 10000 - 3000
        self.assertEqual(profit_data[1], 14000)  # 20000 - 6000
        self.assertEqual(profit_data[2], 21000)  # 30000 - 9000
        self.assertEqual(profit_data[3], 28000)  # 40000 - 12000
        self.assertEqual(profit_data[4], 35000)  # 50000 - 15000
        self.assertEqual(profit_data[5], 42000)  # 60000 - 18000

    def test_no_transactions_scenario(self):
        """取引が存在しない場合でもエラーなく動作することを確認"""
        # from ledger.views import DashboardView

        request = self.factory.get("/ledger/dashboard/")
        response = DashboardView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        # 月次売上が0であること
        self.assertEqual(response.context_data["monthly_sales"], Decimal("0.00"))
        # 月次利益が0であること
        self.assertEqual(response.context_data["monthly_profit"], Decimal("0.00"))
