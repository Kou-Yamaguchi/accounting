from datetime import date
from decimal import Decimal

from django.test import TestCase, RequestFactory

from ledger.models import Account
from ledger.views.views import GeneralLedgerView
from ledger.tests.utils import create_accounts, create_journal_entry, AccountData


class GeneralLedgerViewTest(TestCase):
    """
    GeneralLedgerViewが返す総勘定元帳のデータ内容をテストする
    """

    def setUp(self):
        # テストに必要な初期データ（勘定科目）を作成
        self.factory = RequestFactory()

        self.accounts = create_accounts(
            [
                AccountData(name="現金", type="Asset"),
                AccountData(name="売上", type="Revenue"),
                AccountData(name="仕入", type="Expense"),
                AccountData(name="買掛金", type="Liability"),
                AccountData(name="消耗品", type="Asset"),
            ]
        )

        self.cash = self.accounts["現金"]
        self.sales = self.accounts["売上"]
        self.purchases = self.accounts["仕入"]
        self.accounts_payable = self.accounts["買掛金"]
        self.supplies = self.accounts["消耗品"]
        # テスト対象のビューにアクセスするためのURLを準備
        self.url_template = "/ledger/general_ledger/content/?account_name={account_name}"

    # ----------------------------------------------------
    # 1. 1 vs 1 (単純仕訳) のテスト
    # ----------------------------------------------------

    def test_single_vs_single_entry_debit_side(self):
        """
        現金勘定をテスト対象とし、相手科目が1つの場合の借方（Debit）エントリを検証
        仕訳: 現金 100 / 売上 100
        """
        create_journal_entry(
            date(2025, 10, 1),
            "商品売上（現金）",
            [(self.cash, Decimal("100.00"))],  # 現金が借方
            [(self.sales, Decimal("100.00"))],  # 売上が貸方
        )

        request = self.factory.get(self.url_template.format(account_name="現金"))
        response = GeneralLedgerView.as_view()(request, account_name="現金")

        self.assertEqual(response.status_code, 200)

        ledger_entries = response.context_data["ledger_entries"]
        self.assertEqual(len(ledger_entries), 1)

        entry = ledger_entries[0]
        # チェック項目
        self.assertEqual(
            entry["counter_party"], "売上"
        )  # 相手勘定が単一科目名であること
        self.assertEqual(entry["debit_amount"], Decimal("100.00"))
        self.assertEqual(entry["credit_amount"], Decimal("0"))

    def test_single_vs_single_entry_credit_side(self):
        """
        買掛金勘定をテスト対象とし、相手科目が1つの場合の貸方（Credit）エントリを検証
        仕訳: 仕入 50 / 買掛金 50
        """
        create_journal_entry(
            date(2025, 10, 2),
            "商品仕入（掛）",
            [(self.purchases, Decimal("50.00"))],
            [(self.accounts_payable, Decimal("50.00"))],  # 買掛金が貸方
        )

        request = self.factory.get(self.url_template.format(account_name="買掛金"))
        response = GeneralLedgerView.as_view()(request, account_name="買掛金")

        ledger_entries = response.context_data["ledger_entries"]
        self.assertEqual(len(ledger_entries), 1)

        entry = ledger_entries[0]
        # チェック項目
        self.assertEqual(
            entry["counter_party"], "仕入"
        )  # 相手勘定が単一科目名であること
        self.assertEqual(entry["debit_amount"], Decimal("0"))
        self.assertEqual(entry["credit_amount"], Decimal("50.00"))

    # ----------------------------------------------------
    # 2. 1 vs 多 (複合仕訳) のテスト
    # ----------------------------------------------------

    def test_multiple_entry_debit_side(self):
        """
        現金勘定をテスト対象とし、相手科目が複数の場合の借方エントリを検証
        仕訳: 現金 150 / 売上 100, 消耗品 50 （売上と消耗品が相手）
        """
        create_journal_entry(
            date(2025, 10, 3),
            "売上と備品の一部を現金受領",
            [(self.cash, Decimal("150.00"))],  # 相手が1つ
            [
                (self.sales, Decimal("100.00")),
                (self.supplies, Decimal("50.00")),
            ],  # 現金が借方
        )

        request = self.factory.get(self.url_template.format(account_name="売上"))
        response = GeneralLedgerView.as_view()(request, account_name="売上")

        ledger_entries = response.context_data["ledger_entries"]
        self.assertEqual(len(ledger_entries), 1)

        entry = ledger_entries[0]
        # チェック項目
        self.assertEqual(
            entry["counter_party"], "現金"
        )  # 相手勘定が単一科目名であること
        self.assertEqual(entry["debit_amount"], Decimal("0.00"))
        self.assertEqual(entry["credit_amount"], Decimal("100.00"))

    def test_multiple_entry_credit_side(self):
        """
        現金勘定をテスト対象とし、相手科目が複数の場合の貸方エントリを検証
        仕訳: 現金 80, 買掛金 20 / 売上 100 （現金と買掛金が相手）
        """
        create_journal_entry(
            date(2025, 10, 4),
            "商品売上（一部現金、一部掛）",
            [
                (self.cash, Decimal("80.00")),
                (self.accounts_payable, Decimal("20.00")),
            ],  # 相手が2科目
            [(self.sales, Decimal("100.00"))],  # 売上が貸方
        )

        request = self.factory.get(self.url_template.format(account_name="現金"))
        response = GeneralLedgerView.as_view()(request, account_name="現金")

        ledger_entries = response.context_data["ledger_entries"]
        self.assertEqual(len(ledger_entries), 1)

        entry = ledger_entries[0]
        # チェック項目
        self.assertEqual(entry["counter_party"], "売上")  # 相手勘定が売上であること
        self.assertEqual(entry["debit_amount"], Decimal("80.00"))
        self.assertEqual(entry["credit_amount"], Decimal("0.00"))

    def test_single_vs_multiple_entry_debit_side(self):
        """
        現金勘定をテスト対象とし、相手科目が複数の場合の借方エントリを検証
        仕訳: 現金 150 / 売上 100, 消耗品 50 （売上と消耗品が相手）
        """
        create_journal_entry(
            date(2025, 10, 3),
            "売上と備品の一部を現金受領",
            [(self.cash, Decimal("150.00"))],  # 現金が借方
            [
                (self.sales, Decimal("100.00")),
                (self.supplies, Decimal("50.00")),
            ],  # 相手が2科目
        )

        request = self.factory.get(self.url_template.format(account_name="現金"))
        response = GeneralLedgerView.as_view()(request, account_name="現金")

        ledger_entries = response.context_data["ledger_entries"]
        self.assertEqual(len(ledger_entries), 1)

        entry = ledger_entries[0]
        # チェック項目
        self.assertEqual(entry["counter_party"], "諸口")  # 相手勘定が諸口であること
        self.assertEqual(entry["debit_amount"], Decimal("150.00"))
        self.assertEqual(entry["credit_amount"], Decimal("0"))

    def test_single_vs_multiple_entry_credit_side(self):
        """
        売上勘定をテスト対象とし、相手科目が複数の場合の貸方エントリを検証
        仕訳: 現金 80, 買掛金 20 / 売上 100 （現金と買掛金が相手）
        """
        create_journal_entry(
            date(2025, 10, 4),
            "商品売上（一部現金、一部掛）",
            [
                (self.cash, Decimal("80.00")),
                (self.accounts_payable, Decimal("20.00")),
            ],  # 相手が2科目
            [(self.sales, Decimal("100.00"))],  # 売上が貸方
        )

        request = self.factory.get(self.url_template.format(account_name="売上"))
        response = GeneralLedgerView.as_view()(request, account_name="売上")

        ledger_entries = response.context_data["ledger_entries"]
        self.assertEqual(len(ledger_entries), 1)

        entry = ledger_entries[0]
        # チェック項目
        self.assertEqual(entry["counter_party"], "諸口")  # 相手勘定が諸口であること
        self.assertEqual(entry["debit_amount"], Decimal("0"))
        self.assertEqual(entry["credit_amount"], Decimal("100.00"))

    # ----------------------------------------------------
    # 3. 残高計算の検証
    # ----------------------------------------------------

    def test_balance_calculation(self):
        """
        複数の取引を通じた総勘定元帳の残高計算が正しいか検証（スタート残高は0と仮定）
        勘定科目: 現金（資産：借方残高）
        """

        # 1. 現金 / 売上 100 (残高: 借方 100)
        create_journal_entry(
            date(2025, 10, 10),
            "売上1",
            [(self.cash, Decimal("100"))],
            [(self.sales, Decimal("100"))],
        )

        # 2. 仕入 / 現金 40 (残高: 借方 60)
        create_journal_entry(
            date(2025, 10, 11),
            "仕入1",
            [(self.purchases, Decimal("40"))],
            [(self.cash, Decimal("40"))],
        )

        # 3. 現金 / 買掛金 50 (残高: 借方 110)
        create_journal_entry(
            date(2025, 10, 12),
            "買掛金支払い",
            [(self.cash, Decimal("50"))],
            [(self.accounts_payable, Decimal("50"))],
        )

        request = self.factory.get(self.url_template.format(account_name="現金"))
        response = GeneralLedgerView.as_view()(request, account_name="現金")

        ledger_entries = response.context_data["ledger_entries"]
        self.assertEqual(len(ledger_entries), 3)

        # エントリは日付順にソートされていることを前提とする
        # 現金は資産 (Asset) のため、借方が増加、貸方が減少

        # 1. 借方 100
        self.assertEqual(ledger_entries[0]["running_balance"], Decimal("100"))

        # 2. 貸方 40 (100 - 40 = 60)
        self.assertEqual(ledger_entries[1]["running_balance"], Decimal("60"))

        # 3. 借方 50 (60 + 50 = 110)
        self.assertEqual(ledger_entries[2]["running_balance"], Decimal("110"))
