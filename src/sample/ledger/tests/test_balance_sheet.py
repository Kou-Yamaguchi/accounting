from datetime import date
from decimal import Decimal

from django.test import TestCase, RequestFactory

from ledger.models import Account
# TODO: Adjust import according to your project structure
# from ledger.views.balance_sheet import BalanceSheetView
from ledger.views.views import BalanceSheetView
from ledger.tests.utils import create_journal_entry, create_accounts, AccountData


class BalanceSheetViewTest(TestCase):
    """
    貸借対照表ビューのテスト
    """

    def setUp(self):
        # テストに必要な初期データ（勘定科目）を作成
        self.factory = RequestFactory()
        self.view = BalanceSheetView()

        self.accounts = create_accounts(
            [
                AccountData(name="現金", type="asset"),
                AccountData(name="売掛金", type="asset"),
                AccountData(name="買掛金", type="liability"),
                AccountData(name="資本金", type="equity"),
            ]
        )

        # テスト対象のビューにアクセスするためのURLを準備
        self.url = "/ledger/balance_sheet_by_year/?year=2025"

    def test_balance_sheet_view_access(self):
        """
        貸借対照表ビューにアクセスできることを確認するテストケース
        """
        request = self.factory.get(self.url)
        request.GET = {"year": "2025"}
        response = BalanceSheetView.as_view()(request)

        self.assertEqual(response.status_code, 200)

    def test_balance_sheet_account_classification(self):
        """
        貸借対照表の勘定科目が資産・負債・純資産に正しく分類されていることを確認するテストケース
        """
        # いくつかの取引を作成して、貸借対照表にデータが存在するようにする
        create_journal_entry(
            date(2025, 1, 10),
            "開業資本金",
            [(self.accounts["現金"], Decimal("100000.00"))],
            [(self.accounts["資本金"], Decimal("100000.00"))],
        )
        create_journal_entry(
            date(2025, 2, 15),
            "掛売上",
            [(self.accounts["売掛金"], Decimal("50000.00"))],
            [
                (
                    Account.objects.create(name="売上", type="revenue"),
                    Decimal("50000.00"),
                )
            ],
        )
        create_journal_entry(
            date(2025, 3, 20),
            "掛仕入",
            [
                (
                    Account.objects.create(name="仕入", type="expense"),
                    Decimal("30000.00"),
                )
            ],
            [(self.accounts["買掛金"], Decimal("30000.00"))],
        )

        request = self.factory.get(self.url)
        request.GET = {"year": "2024"}
        self.view.request = request
        data_dict = self.view.get_data(2024)

        # 資産勘定が含まれていることを確認
        asset_accounts = data_dict["debit_accounts"]
        asset_names = {item.name for item in asset_accounts}
        self.assertIn("現金", asset_names)
        self.assertIn("売掛金", asset_names)

        # 負債勘定が含まれていることを確認
        liability_accounts = data_dict["credit_accounts"]
        liability_names = {item.name for item in liability_accounts}
        self.assertIn("買掛金", liability_names)

        # 純資産勘定が含まれていることを確認
        equity_accounts = data_dict["credit_accounts"]
        equity_names = {item.name for item in equity_accounts}
        self.assertIn("資本金", equity_names)

    def test_balance_sheet_account_totals(self):
        """
        貸借対照表の各勘定科目の残高が正しく計算されていることを確認するテストケース
        """
        # いくつかの取引を作成
        create_journal_entry(
            date(2025, 1, 10),
            "開業資本金",
            [(self.accounts["現金"], Decimal("100000.00"))],
            [(self.accounts["資本金"], Decimal("100000.00"))],
        )
        create_journal_entry(
            date(2025, 2, 15),
            "現金支払",
            [
                (
                    Account.objects.create(name="消耗品費", type="expense"),
                    Decimal("5000.00"),
                )
            ],
            [(self.accounts["現金"], Decimal("5000.00"))],
        )

        request = self.factory.get(self.url)
        request.GET = {"year": "2024"}
        self.view.request = request
        data_dict = self.view.get_data(2024)

        # 現金の残高を確認 (100000 - 5000 = 95000)
        asset_accounts = data_dict["debit_accounts"]
        cash_balance = next(
            item.total for item in asset_accounts if item.name == "現金"
        )
        self.assertEqual(cash_balance, Decimal("95000.00"))

        # 資本金の残高を確認
        equity_accounts = data_dict["credit_accounts"]
        capital_balance = next(
            item.total for item in equity_accounts if item.name == "資本金"
        )
        self.assertEqual(capital_balance, Decimal("100000.00"))

    def test_balance_sheet_totals(self):
        """
        貸借対照表の借方合計と貸方合計を確認するテストケース
        （純資産には損益が含まれるため、借方合計=貸方合計とはならない場合がある）
        """
        # いくつかの取引を作成
        create_journal_entry(
            date(2025, 1, 10),
            "開業資本金",
            [(self.accounts["現金"], Decimal("100000.00"))],
            [(self.accounts["資本金"], Decimal("100000.00"))],
        )
        create_journal_entry(
            date(2025, 2, 15),
            "掛仕入",
            [
                (
                    Account.objects.create(name="仕入", type="expense"),
                    Decimal("30000.00"),
                )
            ],
            [(self.accounts["買掛金"], Decimal("30000.00"))],
        )

        request = self.factory.get(self.url)
        request.GET = {"year": "2024"}
        self.view.request = request
        data_dict = self.view.get_data(2024)
        context = self.view.build_context(2024, data_dict)

        # 資産合計を確認 (現金100000)
        self.assertEqual(context["total_debits"], Decimal("100000.00"))

        # 負債+純資産合計を確認 (買掛金30000 + 資本金100000)
        self.assertEqual(context["total_credits"], Decimal("130000.00"))

    def test_balance_sheet_no_transactions(self):
        """
        取引が存在しない場合の貸借対照表ビューの動作を確認するテストケース
        """
        request = self.factory.get(self.url)
        request.GET = {"year": "2025"}
        self.view.request = request
        data_dict = self.view.get_data(2025)

        # 全ての勘定科目の残高が0であることを確認
        for item in data_dict["debit_accounts"] + data_dict["credit_accounts"]:
            self.assertEqual(item.total, Decimal("0.00"))

    def test_balance_sheet_paired_columns(self):
        """
        貸借対照表の表示用転置処理が正しく行われていることを確認するテストケース
        """
        # テスト用の取引を作成
        create_journal_entry(
            date(2025, 1, 10),
            "開業資本金",
            [(self.accounts["現金"], Decimal("100000.00"))],
            [(self.accounts["資本金"], Decimal("100000.00"))],
        )

        request = self.factory.get(self.url)
        request.GET = {"year": "2025"}
        self.view.request = request
        data_dict = self.view.get_data(2025)
        context = self.view.build_context(2025, data_dict)
        paired_columns = context["paired_columns"]
        # # paired_columnsが存在することを確認
        self.assertIsNotNone(paired_columns)

        # paired_columnsが正しい構造であることを確認
        self.assertIsInstance(paired_columns, list)
        if len(paired_columns) > 0:
            self.assertIsInstance(paired_columns[0], tuple)
            self.assertEqual(len(paired_columns[0]), 2)
