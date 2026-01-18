from datetime import date
from decimal import Decimal

from django.test import TestCase, RequestFactory
from django.http import HttpResponse

from ledger.views.views import TrialBalanceView
from ledger.tests.utils import create_accounts, create_journal_entry, AccountData
from ledger.structures import FinancialStatementEntry


class TrialBalanceViewTest(TestCase):
    """
    試算表ビューのテスト
    """

    def setUp(self):
        # テストに必要な初期データ（勘定科目）を作成
        self.factory = RequestFactory()
        self.view = TrialBalanceView()

        self.accounts = create_accounts(
            [
                AccountData(name="現金", type="asset"),
                AccountData(name="売上", type="revenue"),
                AccountData(name="仕入", type="expense"),
                AccountData(name="買掛金", type="liability"),
            ]
        )

        # テスト対象のビューにアクセスするためのURLを準備
        self.url = "/ledger/trial_balance/?year=2025"

    # ここに試算表ビューのテストケースを追加していく
    def test_trial_balance_view_access(self):
        """
        試算表ビューにアクセスできることを確認するテストケース
        """
        request = self.factory.get(self.url)
        response: HttpResponse = TrialBalanceView.as_view()(request)

        self.view = TrialBalanceView()

        data_dict = self.view.get_data(year=2025)
        context = self.view.build_context(2025, data_dict)
        self.assertEqual(response.status_code, 200)

        # 全ての勘定科目がresponseに含まれていることを確認
        trial_balance_data: list[FinancialStatementEntry] = context[
            "trial_balance_data"
        ]
        account_names_in_response = {entry.name for entry in trial_balance_data}
        for account in self.accounts.values():
            self.assertIn(account.name, account_names_in_response)

    def test_trial_balance_entry_totals(self):
        """
        試算表の各勘定科目の借方・貸方合計が正しく計算されていることを確認するテストケース
        """
        # いくつかの取引を作成して、試算表にデータが存在するようにする
        create_journal_entry(
            date(2025, 5, 5),
            "売上取引",
            [(self.accounts["現金"], Decimal("2000.00"))],
            [(self.accounts["売上"], Decimal("2000.00"))],
        )
        create_journal_entry(
            date(2025, 5, 6),
            "売上取引2",
            [(self.accounts["現金"], Decimal("300.00"))],
            [(self.accounts["売上"], Decimal("300.00"))],
        )
        create_journal_entry(
            date(2025, 5, 8),
            "仕入取引",
            [(self.accounts["仕入"], Decimal("800.00"))],
            [(self.accounts["買掛金"], Decimal("800.00"))],
        )

        request = self.factory.get(self.url)
        response = TrialBalanceView.as_view()(request)

        data_dict = self.view.get_data(year=2025)
        context = self.view.build_context(2025, data_dict)

        self.assertEqual(response.status_code, 200)
        trial_balance_data: list[FinancialStatementEntry] = context[
            "trial_balance_data"
        ]

        # 各勘定科目の合計を検証
        for entry in trial_balance_data:
            if entry.name == "現金":
                self.assertEqual(entry.total, Decimal("2300.00"))
            elif entry.name == "売上":
                self.assertEqual(entry.total, Decimal("2300.00"))
            elif entry.name == "仕入":
                self.assertEqual(entry.total, Decimal("800.00"))
            elif entry.name == "買掛金":
                self.assertEqual(entry.total, Decimal("800.00"))

    def test_trial_balance_totals(self):
        """
        試算表の借方合計と貸方合計が一致することを確認するテストケース
        """
        # いくつかの取引を作成して、試算表にデータが存在するようにする
        create_journal_entry(
            date(2025, 5, 10),
            "売上取引",
            [(self.accounts["現金"], Decimal("1000.00"))],
            [(self.accounts["売上"], Decimal("1000.00"))],
        )
        create_journal_entry(
            date(2025, 5, 15),
            "仕入取引",
            [(self.accounts["仕入"], Decimal("500.00"))],
            [(self.accounts["買掛金"], Decimal("500.00"))],
        )

        request = self.factory.get(self.url)
        response = TrialBalanceView.as_view()(request)

        data_dict = self.view.get_data(year=2025)
        context = self.view.build_context(2025, data_dict)

        self.assertEqual(response.status_code, 200)
        trial_balance_data: list[FinancialStatementEntry] = context[
            "trial_balance_data"
        ]

        total_debit = sum(
            entry.total
            for entry in trial_balance_data
            if entry.type in ["asset", "expense"]
        )
        total_credit = sum(
            entry.total
            for entry in trial_balance_data
            if not entry.type in ["asset", "expense"]
        )

        self.assertEqual(total_debit, total_credit, "借方合計と貸方合計が一致すること")

    def test_trial_balance_no_transactions(self):
        """
        取引が存在しない場合の試算表ビューの動作を確認するテストケース
        """
        request = self.factory.get(self.url)
        response = TrialBalanceView.as_view()(request)

        data_dict = self.view.get_data(year=2025)
        context = self.view.build_context(2025, data_dict)

        self.assertEqual(response.status_code, 200)
        trial_balance_data: list[FinancialStatementEntry] = context[
            "trial_balance_data"
        ]

        # 取引がない場合、全ての勘定科目の合計が0であることを確認
        for entry in trial_balance_data:
            self.assertEqual(
                entry.total, Decimal("0.00"), f"{entry.name}の合計が0であること"
            )
