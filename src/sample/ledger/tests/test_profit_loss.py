from decimal import Decimal
from datetime import date

from django.test import TestCase, RequestFactory

# TODO: Adjust the import path as necessary based on your project structure
# from ledger.views.profit_and_loss import ProfitAndLossView
from ledger.views.financial_statement import ProfitAndLossView
from ledger.tests.utils import create_accounts, create_journal_entry
from ledger.tests.utils import AccountData


class ProfitAndLossViewTest(TestCase):
    """
    損益計算書ビューのテスト
    """

    def setUp(self):
        # テストに必要な初期データ（勘定科目）を作成
        self.factory = RequestFactory()
        self.view = ProfitAndLossView()

        self.accounts = create_accounts(
            [
                AccountData(name="現金", type="asset"),
                AccountData(name="売上", type="revenue"),
                AccountData(name="仕入", type="expense"),
                AccountData(name="消耗品費", type="expense"),
            ]
        )

        # テスト対象のビューにアクセスするためのURLを準備
        self.url = "/ledger/profit_and_loss_by_year/?year=2025"

    def test_profit_and_loss_view_access(self):
        """
        損益計算書ビューにアクセスできることを確認するテストケース
        """
        request = self.factory.get(self.url)
        request.GET = {"year": "2025"}
        response = ProfitAndLossView.as_view()(request)

        self.assertEqual(response.status_code, 200)

    def test_profit_and_loss_account_classification(self):
        """
        損益計算書の勘定科目が収益・費用に正しく分類されていることを確認するテストケース
        """
        # いくつかの取引を作成して、損益計算書にデータが存在するようにする
        create_journal_entry(
            date(2025, 1, 10),
            "売上",
            [(self.accounts["現金"], Decimal("50000.00"))],
            [(self.accounts["売上"], Decimal("50000.00"))],
        )
        create_journal_entry(
            date(2025, 2, 15),
            "仕入",
            [(self.accounts["仕入"], Decimal("30000.00"))],
            [(self.accounts["現金"], Decimal("30000.00"))],
        )
        create_journal_entry(
            date(2025, 3, 20),
            "消耗品費",
            [(self.accounts["消耗品費"], Decimal("5000.00"))],
            [(self.accounts["現金"], Decimal("5000.00"))],
        )

        request = self.factory.get(self.url)
        request.GET = {"year": "2025"}
        self.view.request = request
        data_dict = self.view.get_data(2025)

        # 収益勘定が含まれていることを確認
        revenue_accounts = data_dict["credit_accounts"]
        revenue_names = {item.name for item in revenue_accounts}
        self.assertIn("売上", revenue_names)

        # 費用勘定が含まれていることを確認
        expense_accounts = data_dict["debit_accounts"]
        expense_names = {item.name for item in expense_accounts}
        self.assertIn("仕入", expense_names)
        self.assertIn("消耗品費", expense_names)

    def test_profit_and_loss_account_totals(self):
        """
        損益計算書の各勘定科目の残高が正しく計算されていることを確認するテストケース
        """
        # いくつかの取引を作成
        create_journal_entry(
            date(2025, 1, 10),
            "売上1",
            [(self.accounts["現金"], Decimal("50000.00"))],
            [(self.accounts["売上"], Decimal("50000.00"))],
        )
        create_journal_entry(
            date(2025, 2, 15),
            "売上2",
            [(self.accounts["現金"], Decimal("30000.00"))],
            [(self.accounts["売上"], Decimal("30000.00"))],
        )
        create_journal_entry(
            date(2025, 3, 20),
            "仕入",
            [(self.accounts["仕入"], Decimal("40000.00"))],
            [(self.accounts["現金"], Decimal("40000.00"))],
        )

        request = self.factory.get(self.url)
        request.GET = {"year": "2024"}
        self.view.request = request
        data_dict = self.view.get_data(2024)

        # 売上の残高を確認 (50000 + 30000 = 80000)
        revenue_accounts = data_dict["credit_accounts"]
        sales_balance = next(
            item.total for item in revenue_accounts if item.name == "売上"
        )
        self.assertEqual(sales_balance, Decimal("80000.00"))

        # 仕入の残高を確認
        expense_accounts = data_dict["debit_accounts"]
        purchase_balance = next(
            item.total for item in expense_accounts if item.name == "仕入"
        )
        self.assertEqual(purchase_balance, Decimal("40000.00"))

    def test_profit_and_loss_totals(self):
        """
        損益計算書の収益合計と費用合計を確認するテストケース
        """
        # いくつかの取引を作成
        create_journal_entry(
            date(2025, 1, 10),
            "売上",
            [(self.accounts["現金"], Decimal("100000.00"))],
            [(self.accounts["売上"], Decimal("100000.00"))],
        )
        create_journal_entry(
            date(2025, 2, 15),
            "仕入",
            [(self.accounts["仕入"], Decimal("60000.00"))],
            [(self.accounts["現金"], Decimal("60000.00"))],
        )
        create_journal_entry(
            date(2025, 3, 20),
            "消耗品費",
            [(self.accounts["消耗品費"], Decimal("10000.00"))],
            [(self.accounts["現金"], Decimal("10000.00"))],
        )

        request = self.factory.get(self.url)
        request.GET = {"year": "2024"}
        self.view.request = request
        data_dict = self.view.get_data(2024)
        context = self.view.build_context(2024, data_dict)

        total_revenue = context["total_credits"]
        total_expense = context["total_debits"]

        # 収益合計を確認
        self.assertEqual(total_revenue, Decimal("100000.00"))

        # 費用合計を確認 (60000 + 10000 = 70000)
        self.assertEqual(total_expense, Decimal("70000.00"))

    def test_profit_and_loss_net_income(self):
        """
        当期純利益が正しく計算されていることを確認するテストケース
        """
        # 収益 > 費用 の場合
        create_journal_entry(
            date(2025, 1, 10),
            "売上",
            [(self.accounts["現金"], Decimal("100000.00"))],
            [(self.accounts["売上"], Decimal("100000.00"))],
        )
        create_journal_entry(
            date(2025, 2, 15),
            "仕入",
            [(self.accounts["仕入"], Decimal("60000.00"))],
            [(self.accounts["現金"], Decimal("60000.00"))],
        )

        request = self.factory.get(self.url)
        request.GET = {"year": "2024"}
        self.view.request = request
        data_dict = self.view.get_data(2024)
        context = self.view.build_context(2024, data_dict)

        # 当期純利益を確認 (100000 - 60000 = 40000)
        self.assertIn("net_income", context)
        self.assertEqual(context["net_income"], Decimal("40000.00"))
        self.assertNotIn("net_loss", context)

    def test_profit_and_loss_net_loss(self):
        """
        当期純損失が正しく計算されていることを確認するテストケース
        """
        # 費用 > 収益 の場合
        create_journal_entry(
            date(2025, 1, 10),
            "売上",
            [(self.accounts["現金"], Decimal("30000.00"))],
            [(self.accounts["売上"], Decimal("30000.00"))],
        )
        create_journal_entry(
            date(2025, 2, 15),
            "仕入",
            [(self.accounts["仕入"], Decimal("50000.00"))],
            [(self.accounts["現金"], Decimal("50000.00"))],
        )

        request = self.factory.get(self.url)
        request.GET = {"year": "2024"}
        self.view.request = request
        data_dict = self.view.get_data(2024)
        context = self.view.build_context(2024, data_dict)

        # 当期純損失を確認 (50000 - 30000 = 20000)
        self.assertIn("net_loss", context)
        self.assertEqual(context["net_loss"], Decimal("20000.00"))
        self.assertNotIn("net_income", context)

    def test_profit_and_loss_no_transactions(self):
        """
        取引が存在しない場合の損益計算書ビューの動作を確認するテストケース
        """
        request = self.factory.get(self.url)
        request.GET = {"year": "2025"}
        self.view.request = request
        data_dict = self.view.get_data(2025)
        context = self.view.build_context(2025, data_dict)

        # 全ての勘定科目の残高が0であることを確認
        for data in context["profit_data"]:
            self.assertEqual(data.total, Decimal("0.00"))
        for data in context["loss_data"]:
            self.assertEqual(data.total, Decimal("0.00"))

        # 収益・費用合計が0であることを確認
        self.assertEqual(context["total_revenue"], Decimal("0.00"))
        self.assertEqual(context["total_expense"], Decimal("0.00"))

    def test_profit_and_loss_paired_columns(self):
        """
        損益計算書の表示用転置処理が正しく行われていることを確認するテストケース
        """
        # テスト用の取引を作成
        create_journal_entry(
            date(2025, 1, 10),
            "売上",
            [(self.accounts["現金"], Decimal("100000.00"))],
            [(self.accounts["売上"], Decimal("100000.00"))],
        )
        create_journal_entry(
            date(2025, 2, 15),
            "仕入",
            [(self.accounts["仕入"], Decimal("60000.00"))],
            [(self.accounts["現金"], Decimal("60000.00"))],
        )

        request = self.factory.get(self.url)
        request.GET = {"year": "2025"}
        self.view.request = request
        data_dict = self.view.get_data(2025)
        context = self.view.build_context(2025, data_dict)

        # paired_columnsが存在することを確認
        self.assertIn("paired_columns", context)
        paired_columns = context["paired_columns"]

        # paired_columnsが正しい構造であることを確認
        self.assertIsInstance(paired_columns, list)
        if len(paired_columns) > 0:
            self.assertIsInstance(paired_columns[0], tuple)
            self.assertEqual(len(paired_columns[0]), 2)
