from datetime import date, datetime
from decimal import Decimal
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.http import HttpRequest, HttpResponse

from ledger.models import (
    JournalEntry,
    Debit,
    Credit,
    Account,
    InitialBalance,
    Item,
    SalesDetail,
    PurchaseDetail,
    Company,
)
from ledger.views import (
    GeneralLedgerView,
    PurchaseBookView,
    PurchaseBookEntry,
    TrialBalanceView,
    TrialBalanceEntry,
    BalanceSheetView,
    ProfitAndLossView,
    DashboardView,
)
from ledger.services import calculate_monthly_balance
from enums.error_messages import ErrorMessages


@dataclass
class AccountData:
    name: str
    type: str


def create_accounts(list_account: list[AccountData]) -> dict[str, Account]:
    """
    テスト用の勘定科目を作成するヘルパー関数
    Args:
        list_account (list[AccountData]): 作成する勘定科目データのリスト

    Returns:
        dict {勘定科目名: Accountオブジェクト, ...}
    """
    accounts = {}
    for acc_data in list_account:
        account = Account.objects.create(name=acc_data.name, type=acc_data.type)
        accounts[acc_data.name] = account
    return accounts


def create_journal_entry(
    entry_date: date,
    summary: str,
    debits_data: list[tuple[Account, Decimal]],
    credits_data: list[tuple[Account, Decimal]],
    company: Company = None,
    created_by=None,
) -> JournalEntry:
    """
    取引 (JournalEntry) とその明細 (Debit/Credit) を作成するヘルパー関数
    debits_data/credits_data は [(Accountオブジェクト, Decimal金額), ...] のリスト
    Args:
        entry_date (date): 取引日
        summary (str): 摘要
        debits_data (list[tuple[Account, Decimal]]): 借方明細データ
        credits_data (list[tuple[Account, Decimal]]): 貸方明細データ
        company (Company, optional): 会社情報。指定しない場合はNone。
        created_by (User, optional): 作成者情報。指定しない場合はNone。

    Returns:
        JournalEntry: 作成された取引オブジェクト
    """
    entry = JournalEntry.objects.create(
        date=entry_date, summary=summary, company=company, created_by=created_by
    )

    for account, amount in debits_data:
        Debit.objects.create(
            journal_entry=entry, account=account, amount=amount, created_by=created_by
        )

    for account, amount in credits_data:
        Credit.objects.create(
            journal_entry=entry, account=account, amount=amount, created_by=created_by
        )

    return entry


class JournalEntryViewTest(TestCase):
    """
    journal_entryテーブルに対するCRUD操作のテスト
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="testuser", password="testpass"
        )
        self.client.force_login(self.user)
        self.accounts: dict[str, Account] = create_accounts(
            [
                AccountData(name="現金", type="asset"),
                AccountData(name="売上", type="revenue"),
            ]
        )
        self.entry = create_journal_entry(
            entry_date=date(2024, 1, 1),
            summary="初期取引",
            debits_data=[(self.accounts["現金"], Decimal("1000.00"))],
            credits_data=[(self.accounts["売上"], Decimal("1000.00"))],
            created_by=self.user,
        )

        self.base_post = {
            "date": "2024-01-01",
            "summary": "",
            "debits-TOTAL_FORMS": "0",
            "debits-INITIAL_FORMS": "0",
            "debits-MIN_NUM_FORMS": "0",
            "debits-MAX_NUM_FORMS": "1000",
            "credits-TOTAL_FORMS": "0",
            "credits-INITIAL_FORMS": "0",
            "credits-MIN_NUM_FORMS": "0",
            "credits-MAX_NUM_FORMS": "1000",
        }

    def build_post(self, date=None, summary=None, debit_items=None, credit_items=None):
        """
        debit_items / credit_items はリスト。各要素は
        {'account': account_id, 'amount': '123.45', 'id': existing_id (optional)}
        を想定する。id がある要素は INITIAL_FORMS のカウントに含める。
        """
        data = self.base_post.copy()
        if date is not None:
            data["date"] = date
        if summary is not None:
            data["summary"] = summary

        # デビット
        if debit_items is not None:
            data["debits-TOTAL_FORMS"] = str(len(debit_items))
            initial_count = sum(1 for it in debit_items if it.get("id") is not None)
            data["debits-INITIAL_FORMS"] = str(initial_count)
            for i, item in enumerate(debit_items):
                if "id" in item:
                    data[f"debits-{i}-id"] = str(item["id"])
                data[f"debits-{i}-account"] = str(item["account"])
                data[f"debits-{i}-amount"] = str(item["amount"])

        # クレジット
        if credit_items is not None:
            data["credits-TOTAL_FORMS"] = str(len(credit_items))
            initial_count = sum(1 for it in credit_items if it.get("id") is not None)
            data["credits-INITIAL_FORMS"] = str(initial_count)
            for i, item in enumerate(credit_items):
                if "id" in item:
                    data[f"credits-{i}-id"] = str(item["id"])
                data[f"credits-{i}-account"] = str(item["account"])
                data[f"credits-{i}-amount"] = str(item["amount"])

        return data

    def test_journal_entry_list_view(self):
        response = self.client.get(reverse("journal_entry_list"))
        self.assertTemplateUsed(response, "ledger/journal_entry_list.html")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "初期取引")

    def test_create_journal_entry(self):
        data = self.build_post(
            date="2024-01-01",
            summary="テスト取引",
            debit_items=[{"account": self.accounts["現金"].id, "amount": "100.00"}],
            credit_items=[{"account": self.accounts["売上"].id, "amount": "100.00"}],
        )
        response = self.client.post("/ledger/new/", data)
        self.assertEqual(response.status_code, 302)
        journal_entries = JournalEntry.objects.all()
        self.assertEqual(journal_entries.count(), 2)
        self.assertEqual(
            float(
                journal_entries.filter(summary="テスト取引")
                .first()
                .debits.first()
                .amount
            ),
            100.00,
        )
        self.assertEqual(
            float(
                journal_entries.filter(summary="テスト取引")
                .first()
                .credits.first()
                .amount
            ),
            100.00,
        )

    def test_update_journal_entry(self):
        data = self.build_post(
            date="2024-01-02",
            summary="更新取引",
            debit_items=[
                {
                    "id": self.entry.debits.first().id,
                    "account": self.accounts["現金"].id,
                    "amount": "200.00",
                }
            ],
            credit_items=[
                {
                    "id": self.entry.credits.first().id,
                    "account": self.accounts["売上"].id,
                    "amount": "200.00",
                }
            ],
        )
        response = self.client.post(f"/ledger/{self.entry.id}/edit/", data)
        self.assertEqual(response.status_code, 302)
        updated_entry = JournalEntry.objects.get(id=self.entry.id)
        self.assertEqual(updated_entry.summary, "更新取引")
        self.assertEqual(float(updated_entry.debits.first().amount), 200.00)
        self.assertEqual(float(updated_entry.credits.first().amount), 200.00)

    def test_delete_journal_entry(self):
        response = self.client.post(f"/ledger/{self.entry.id}/delete/")
        self.assertEqual(response.status_code, 302)
        journal_entries = JournalEntry.objects.all()
        self.assertEqual(journal_entries.count(), 0)
        self.assertEqual(Debit.objects.count(), 0)
        self.assertEqual(Credit.objects.count(), 0)


class JournalEntryValidationTest(TestCase):
    """
    journal_entryのバリデーションテスト
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="testuser", password="testpass"
        )
        self.client.force_login(self.user)
        self.accounts: dict[str, Account] = create_accounts(
            [
                AccountData(name="現金", type="asset"),
                AccountData(name="売上", type="revenue"),
            ]
        )
        # self.accounts["現金"] = Account.objects.create(name="現金", type="asset")
        # self.accounts["売上"] = Account.objects.create(name="売上", type="revenue")

        self.base_post = {
            "date": "2024-01-01",
            "summary": "",
            "debits-TOTAL_FORMS": "0",
            "debits-INITIAL_FORMS": "0",
            "debits-MIN_NUM_FORMS": "0",
            "debits-MAX_NUM_FORMS": "1000",
            "credits-TOTAL_FORMS": "0",
            "credits-INITIAL_FORMS": "0",
            "credits-MIN_NUM_FORMS": "0",
            "credits-MAX_NUM_FORMS": "1000",
        }

    def build_post(self, date=None, summary=None, debit_items=None, credit_items=None):
        # 同上のヘルパー
        data = self.base_post.copy()
        if date is not None:
            data["date"] = date
        if summary is not None:
            data["summary"] = summary

        if debit_items is not None:
            data["debits-TOTAL_FORMS"] = str(len(debit_items))
            initial_count = sum(1 for it in debit_items if it.get("id") is not None)
            data["debits-INITIAL_FORMS"] = str(initial_count)
            for i, item in enumerate(debit_items):
                if "id" in item:
                    data[f"debits-{i}-id"] = str(item["id"])
                data[f"debits-{i}-account"] = str(item["account"])
                data[f"debits-{i}-amount"] = str(item["amount"])

        if credit_items is not None:
            data["credits-TOTAL_FORMS"] = str(len(credit_items))
            initial_count = sum(1 for it in credit_items if it.get("id") is not None)
            data["credits-INITIAL_FORMS"] = str(initial_count)
            for i, item in enumerate(credit_items):
                if "id" in item:
                    data[f"credits-{i}-id"] = str(item["id"])
                data[f"credits-{i}-account"] = str(item["account"])
                data[f"credits-{i}-amount"] = str(item["amount"])

        return data

    def test_empty_journal_entry(self):
        data = self.build_post(date="", summary="", debit_items=[], credit_items=[])
        response = self.client.post("/ledger/new/", data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ErrorMessages.REQUIRED.value)

    def test_negative_amount_debit(self):
        data = self.build_post(
            date="2024-01-01",
            summary="負の金額取引",
            debit_items=[{"account": self.accounts["現金"].id, "amount": "-100.00"}],
            credit_items=[{"account": self.accounts["売上"].id, "amount": "100.00"}],
        )
        response = self.client.post("/ledger/new/", data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ErrorMessages.MESSAGE_0003.value)

    def test_unbalanced_journal_entry(self):
        data = self.build_post(
            date="2024-01-01",
            summary="不均衡取引",
            debit_items=[{"account": self.accounts["現金"].id, "amount": "100.00"}],
            credit_items=[{"account": self.accounts["売上"].id, "amount": "50.00"}],
        )
        response = self.client.post("/ledger/new/", data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ErrorMessages.MESSAGE_0001.value)


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
        self.url_template = "/ledger/{account_name}/"

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

        trial_balance_data, total_debits, total_credits = self.view.get_data(year=2025)
        context = self.view._form_to_html_rows(
            trial_balance_data, 2025, total_debits, total_credits
        )

        self.assertEqual(response.status_code, 200)

        # 全ての勘定科目がresponseに含まれていることを確認
        trial_balance_data: list[TrialBalanceEntry] = context["trial_balance_data"]
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

        trial_balance_data, total_debits, total_credits = self.view.get_data(year=2025)
        context = self.view._form_to_html_rows(
            trial_balance_data, 2025, total_debits, total_credits
        )

        self.assertEqual(response.status_code, 200)
        trial_balance_data: list[TrialBalanceEntry] = context["trial_balance_data"]

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

        trial_balance_data, total_debits, total_credits = self.view.get_data(year=2025)
        context = self.view._form_to_html_rows(
            trial_balance_data, 2025, total_debits, total_credits
        )

        self.assertEqual(response.status_code, 200)
        trial_balance_data: list[TrialBalanceEntry] = context["trial_balance_data"]

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

        trial_balance_data, total_debits, total_credits = self.view.get_data(year=2025)
        context = self.view._form_to_html_rows(
            trial_balance_data, 2025, total_debits, total_credits
        )

        self.assertEqual(response.status_code, 200)
        trial_balance_data: list[TrialBalanceEntry] = context["trial_balance_data"]

        # 取引がない場合、全ての勘定科目の合計が0であることを確認
        for entry in trial_balance_data:
            self.assertEqual(
                entry.total, Decimal("0.00"), f"{entry.name}の合計が0であること"
            )


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
            item.total
            for item in equity_accounts
            if item.name == "資本金"
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
            item.total
            for item in revenue_accounts
            if item.name == "売上"
        )
        self.assertEqual(sales_balance, Decimal("80000.00"))

        # 仕入の残高を確認
        expense_accounts = data_dict["debit_accounts"]
        purchase_balance = next(
            item.total
            for item in expense_accounts
            if item.name == "仕入"
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


class CashBookCalculationTest(TestCase):

    # テスト開始前に必要なマスタデータ（勘定科目）を作成
    @classmethod
    def setUpTestData(cls):
        cls.accounts = create_accounts(
            [
                AccountData(name="現金", type="Asset"),
                AccountData(name="売上", type="Revenue"),
                AccountData(name="消耗品費", type="Expense"),
                AccountData(name="雑収入", type="Revenue"),
            ]
        )
        # 現金出納帳の対象科目
        cls.cash_account = cls.accounts["現金"]
        # 相手勘定科目
        cls.sales_account = cls.accounts["売上"]
        cls.supplies_account = cls.accounts["消耗品費"]
        cls.unknown_account = cls.accounts["雑収入"]

    # --- ユーザーが要求したケース ---

    ## 1. 初期残高がある場合とない場合
    def test_initial_balance_cases(self):
        """初期残高がある場合（前月繰越あり）とない場合（0）のテスト"""

        # 【ケースA: 初期残高設定なし = 0】
        # InitialBalanceを作成しない状態
        result_no_initial = calculate_monthly_balance("現金", 2025, 1)
        self.assertEqual(
            result_no_initial["data"][0]["summary"],
            "前月繰越",
            "前月繰越の行が存在すること",
        )
        # InitialBalanceがない場合は「期首残高が設定されていません。」という警告を出す仕様としている。(エラーは出さない)
        # 今回はテスト用に、InitialBalanceをあえて作らずにテストする。
        result_no_initial = calculate_monthly_balance("現金", 2025, 1)
        self.assertEqual(result_no_initial["data"][0]["balance"], 0)
        self.assertEqual(result_no_initial["ending_balance"], 0)

        # --- ここから、InitialBalanceが設定されていることを前提とする ---

        # 【ケースB: 初期残高あり (2025/01/01期首)】
        # 2025/01/01を会計期間開始日とし、残高50000を設定
        InitialBalance.objects.create(
            account=self.cash_account, balance=50000, start_date=date(2025, 1, 1)
        )

        # 1月の取引は作成しない
        result_with_initial = calculate_monthly_balance("現金", 2025, 1)

        # 前月繰越が50000であること
        self.assertEqual(result_with_initial["data"][0]["balance"], 50000)
        # 次月繰越（最終行）の残高が50000であること
        self.assertEqual(result_with_initial["ending_balance"], 50000)

    ## 2. 1ヶ月分の集計が正しくできるかどうか
    def test_single_month_calculation(self):
        """1ヶ月内の収入と支出が正しく計算されるか"""
        InitialBalance.objects.create(
            account=self.cash_account, balance=10000, start_date=date(2025, 4, 1)
        )

        # 4月10日: 収入 (売上) 5000
        je1 = create_journal_entry(
            date(2025, 4, 10),
            "売上入金",
            [(self.cash_account, Decimal("5000"))],
            [(self.sales_account, Decimal("5000"))],
            None,  # Company is None for this test
        )

        # 4月20日: 支出 (消耗品費) 2000
        je2 = create_journal_entry(
            date(2025, 4, 20),
            "文房具購入",
            [(self.supplies_account, Decimal("2000"))],
            [(self.cash_account, Decimal("2000"))],
            None,  # Company is None for this test
        )

        result = calculate_monthly_balance("現金", 2025, 4)
        data = result["data"]

        # 前月繰越: 10000 (0行目)
        self.assertEqual(data[0]["balance"], 10000)

        # 収入取引: 5000 (1行目)
        self.assertEqual(data[1]["income"], 5000)
        self.assertEqual(data[1]["balance"], 10000 + 5000)  # 15000
        self.assertEqual(
            data[1]["summary"], "売上"
        )  # 相手勘定科目が摘要になっていること

        # 支出取引: 2000 (2行目)
        self.assertEqual(data[2]["expense"], 2000)
        self.assertEqual(data[2]["balance"], 15000 - 2000)  # 13000
        self.assertEqual(
            data[2]["summary"], "消耗品費"
        )  # 相手勘定科目が摘要になっていること

        # 次月繰越（最終行）
        self.assertEqual(result["ending_balance"], 13000)

    ## 3. 2ヶ月分の集計が正しくできるかどうか (繰越残高の検証)
    def test_two_month_carryover(self):
        """前月の残高が次月へ正しく繰り越されるか（前月繰越残高の計算ロジック検証）"""

        # 2025/03/01期首、残高 50000
        InitialBalance.objects.create(
            account=self.cash_account, balance=50000, start_date=date(2025, 3, 1)
        )

        # 3月取引: 収入 +10000
        je3 = create_journal_entry(
            date(2025, 3, 15),
            "3月入金",
            [(self.cash_account, Decimal("10000"))],
            [(self.unknown_account, Decimal("10000"))],
            None,  # Company is None for this test
        )

        # --- 3月集計結果確認 ---
        result_march = calculate_monthly_balance("現金", 2025, 3)
        self.assertEqual(
            result_march["ending_balance"],
            60000,
            "3月残高が正しく計算されていること (50000 + 10000)",
        )

        # --- 4月集計結果確認 (3月の残高が前月繰越になっていること) ---

        # 4月取引: 支出 -5000
        je4 = create_journal_entry(
            date(2025, 4, 10),
            "4月出金",
            [(self.supplies_account, Decimal("5000"))],
            [(self.cash_account, Decimal("5000"))],
            None,  # Company is None for this test
        )

        result_april = calculate_monthly_balance("現金", 2025, 4)
        data_april = result_april["data"]

        # 4月の前月繰越（0行目）が3月の最終残高(60000)と一致すること
        self.assertEqual(
            data_april[0]["balance"],
            60000,
            "4月の前月繰越が3月の最終残高と一致すること",
        )

        # 4月の最終残高 (60000 - 5000)
        self.assertEqual(
            result_april["ending_balance"],
            55000,
            "4月の最終残高が正しく計算されていること",
        )

    ## 4. 仕訳の入力内容が変更になった場合の集計
    def test_recalculation_after_change(self):
        """過去の取引を変更した場合に集計し直せるか"""
        # (ロジックがキャッシュを使用していないため、関数を再実行するだけで実現可能)

        # 2025/05/01期首、残高 10000
        InitialBalance.objects.create(
            account=self.cash_account, balance=10000, start_date=date(2025, 5, 1)
        )

        # 5月取引: 収入 (売上) 5000
        je5 = create_journal_entry(
            date(2025, 5, 10),
            "売上入金",
            [(self.cash_account, Decimal("5000"))],
            [(self.sales_account, Decimal("5000"))],
            None,  # Company is None for this test
        )

        # 5月最終残高: 10000 + 5000 = 15000
        result_initial = calculate_monthly_balance("現金", 2025, 5)
        self.assertEqual(result_initial["ending_balance"], 15000)

        # 過去の仕訳（je5）の金額を修正
        Debit.objects.filter(journal_entry=je5, account=self.cash_account).update(
            amount=8000
        )
        Credit.objects.filter(journal_entry=je5, account=self.sales_account).update(
            amount=8000
        )

        # 再集計
        result_recalculated = calculate_monthly_balance("現金", 2025, 5)

        # 修正後の最終残高: 10000 + 8000 = 18000
        self.assertEqual(
            result_recalculated["ending_balance"],
            18000,
            "仕訳変更後、残高が正しく再計算されること",
        )

    # --- 追加テストケース ---

    ## 5. 月末日と月初日の取引処理
    def test_month_boundary_transactions(self):
        """集計期間の境界（前月末日、当月1日、当月末日、翌月1日）の取引が正しく含まれるか/除外されるか"""

        # 2025/06/01期首、残高 5000
        InitialBalance.objects.create(
            account=self.cash_account, balance=5000, start_date=date(2025, 6, 1)
        )

        # 7月集計

        # 6月30日 (前月末): 収入 1000 -> 7月の集計に含めない (前月繰越に影響)
        je_prev = create_journal_entry(
            date(2025, 6, 30),
            "6月取引",
            [(self.cash_account, Decimal("1000"))],
            [(self.sales_account, Decimal("1000"))],
            None,  # Company is None for this test
        )

        # 7月1日 (月初): 支出 500 -> 7月の集計に含める
        je_start = create_journal_entry(
            date(2025, 7, 1),
            "7月1日取引",
            [(self.supplies_account, Decimal("500"))],
            [(self.cash_account, Decimal("500"))],
            None,  # Company is None for this test
        )

        # 7月31日 (月末): 収入 2000 -> 7月の集計に含める
        je_end = create_journal_entry(
            date(2025, 7, 31),
            "7月31日取引",
            [(self.cash_account, Decimal("2000"))],
            [(self.sales_account, Decimal("2000"))],
            None,  # Company is None for this test
        )

        # 8月1日 (翌月): 支出 3000 -> 7月の集計に含めない
        je_next = create_journal_entry(
            date(2025, 8, 1),
            "8月1日取引",
            [(self.supplies_account, Decimal("3000"))],
            [(self.cash_account, Decimal("3000"))],
            None,  # Company is None for this test
        )

        result_july = calculate_monthly_balance("現金", 2025, 7)
        data_july = result_july["data"]

        # 前月繰越の確認: 初期残高5000 + 6月30日の取引1000 = 6000
        self.assertEqual(
            data_july[0]["balance"],
            6000,
            "前月繰越に残月取引が正しく反映されていること",
        )

        # 7月の取引件数（前月繰越、月初、月末、次月繰越の計4行）
        self.assertEqual(
            len(data_july), 4, "当月取引（月初、月末の2件）のみが抽出されていること"
        )

        # 最終残高の確認: 6000 (繰越) - 500 (月初) + 2000 (月末) = 7500
        self.assertEqual(result_july["ending_balance"], 7500)

    ## 6. 仕訳ヘッダーの摘要 (summary) が空欄の場合のフォールバック
    def test_summary_fallback(self):
        """仕訳に総合摘要がない場合でも相手勘定科目が摘要として使われるか"""

        # 2025/08/01期首、残高 10000
        InitialBalance.objects.create(
            account=self.cash_account, balance=10000, start_date=date(2025, 8, 1)
        )

        # 8月取引: 収入 (売上) 5000、summaryは空欄
        je6 = create_journal_entry(
            date(2025, 8, 15),
            "",
            [(self.cash_account, Decimal("5000"))],
            [(self.sales_account, Decimal("5000"))],
            None,  # Company is None for this test
        )

        result = calculate_monthly_balance("現金", 2025, 8)
        data = result["data"]

        # 収入取引の摘要が相手勘定（売上）になっていること
        self.assertEqual(
            data[1]["summary"],
            "売上",
            "summaryが空欄でも相手勘定科目が摘要になること",
        )


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


class PurchaseBookViewTest(TestCase):
    """
    PurchaseBookViewのテスト
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="testuser", password="testpass"
        )
        self.client.force_login(self.user)

    # 必要なマスタデータを作成
    @classmethod
    def setUpTestData(cls):
        cls.accounts = create_accounts(
            [
                AccountData(name="仕入", type="Expense"),
                AccountData(name="買掛金", type="Liability"),
                AccountData(name="現金", type="Asset"),
            ]
        )
        cls.purchase = cls.accounts["仕入"]
        cls.accounts_payable = cls.accounts["買掛金"]
        cls.cash = cls.accounts["現金"]

        cls.co_a = Company.objects.create(name="甲社")
        cls.co_b = Company.objects.create(name="乙社")

        cls.item_y = Item.objects.create(name="Y商品")
        cls.item_z = Item.objects.create(name="Z商品")

    # --- ユーザーが要求した基本的なケースのテスト ---

    def test_basic_purchase_and_total(self):
        """1ヶ月分の正常な仕入と総仕入高の集計テスト"""

        # 2025/4/10: 甲社から掛仕入 (仕入 3000 / 買掛金 3000)
        je1 = create_journal_entry(
            date(2025, 4, 10),
            "掛仕入",
            [(self.purchase, 3000)],
            [(self.accounts_payable, 3000)],
            self.co_a,
        )
        PurchaseDetail.objects.create(
            journal_entry=je1, item=self.item_y, quantity=10, unit_price=300
        )

        # 2025/4/20: 乙社から現金仕入 (仕入 5000 / 現金 5000)
        je2 = create_journal_entry(
            date(2025, 4, 20),
            "現金仕入",
            [(self.purchase, 5000)],
            [(self.cash, 5000)],
            self.co_b,
        )
        PurchaseDetail.objects.create(
            journal_entry=je2, item=self.item_z, quantity=5, unit_price=1000
        )

        response = self.client.get(reverse("purchase_book", args=[2025, 4]))

        closing_entry = response.context["purchase_book"].closing_entry

        # 総仕入高の確認 (3000 + 5000 = 8000)
        self.assertEqual(
            closing_entry.total_purchase, 8000, "総仕入高が正しく集計されていること"
        )
        # 純仕入高の確認 (戻しがないため8000)
        self.assertEqual(
            closing_entry.net_purchase, 8000, "純仕入高が正しく集計されていること"
        )
        # データ件数 (取引2件, 明細2件 + 総仕入高/戻し/純仕入高の行はサービス側で集計) -> 2つの取引ヘッダー行と2つの明細行
        # self.assertEqual(
        #     len(response.context["book_entries"]["details"]), 4, "取引2件のヘッダーと明細が正しく作成されていること"
        # )

        # 明細行の内訳金額の確認
        # self.assertEqual(
        #     response.context["book_entries"]["details"][1]["total_amount"], 3000, "Y商品の内訳金額が正しいこと"
        # )

    # --- 追加ケース A: 仕入戻し・値引き取引の処理 ---
    def test_purchase_returns(self):
        """仕入戻し（貸方 仕入）が正しくマイナスとして処理され、純仕入高に反映されること"""

        je3 = create_journal_entry(
            date(2025, 5, 5),
            "掛仕入",
            [(self.purchase, 10000)],
            [(self.accounts_payable, 10000)],
            self.co_a,
        )
        PurchaseDetail.objects.create(
            journal_entry=je3, item=self.item_y, quantity=20, unit_price=500
        )

        # 2025/5/15: 仕入戻し (買掛金 2000 / 仕入 2000) -> 貸方に仕入が来る
        je4 = create_journal_entry(
            date(2025, 5, 15),
            "品違いによる返品",
            [(self.accounts_payable, 2000)],
            [(self.purchase, 2000)],
            self.co_a,
        )
        PurchaseDetail.objects.create(
            journal_entry=je4, item=self.item_y, quantity=4, unit_price=500
        )  # 明細もマイナス分を作成

        # response = self.client.get("/ledger/purchase_book/2025/5/")
        response = self.client.get(reverse("purchase_book", args=[2025, 5]))

        closing_entry = response.context["purchase_book"].closing_entry

        # 総仕入高の確認
        self.assertEqual(
            closing_entry.total_purchase,
            10000,
            "総仕入高には通常仕入のみが計上されること",
        )
        # 仕入戻し高の確認
        self.assertEqual(
            closing_entry.total_returns, 2000, "仕入戻し高が正しく計上されること"
        )
        # 純仕入高の確認 (10000 - 2000 = 8000)
        self.assertEqual(
            closing_entry.net_purchase, 8000, "純仕入高が正しく計算されていること"
        )

        # 仕入戻し取引の表示内容確認
        return_header: PurchaseBookEntry = response.context[
            "purchase_book"
        ].book_entries[
            1
        ]  # 2件目の取引が戻し
        self.assertTrue(
            return_header.is_return, "仕入戻し取引であると識別されていること"
        )
        # self.assertEqual(
        #     return_header["main_summary"], "掛戻し", "仕入戻しの摘要が正しいこと"
        # )

    # --- 追加ケース B: 仕訳と明細の不一致 ---
    def test_mismatch_validation(self):
        """仕訳の金額と明細の合計金額が一致しない場合にエラーが記録されること"""

        # 2025/6/01: 不一致仕入 (仕入 10000 / 買掛金 10000)
        je5 = create_journal_entry(
            date(2025, 6, 1),
            "金額不一致テスト",
            [(self.purchase, 10000)],
            [(self.accounts_payable, 10000)],
            self.co_b,
        )
        # 明細の合計は 10個 * 500 = 5000 (仕訳金額10000と不一致)
        PurchaseDetail.objects.create(
            journal_entry=je5, item=self.item_z, quantity=10, unit_price=500
        )

        response = self.client.get(reverse("purchase_book", args=[2025, 6]))

        # エラーメッセージがヘッダー行に記録されていること
        # header_line = response.context["data"][0]
        # self.assertIsNotNone(
        #     header_line["error"],
        #     "金額不一致の場合、エラーメッセージが記録されていること",
        # )
        self.assertIn(
            "内訳金額合計が仕訳金額と一致しません。",
            response.context["error"],
            "エラーメッセージに'金額不一致'が含まれていること",
        )

    # --- 追加ケース C: 複数商品取引の処理 ---
    # def test_multi_item_transaction(self):
    #     """一つの仕訳で複数の商品を扱った場合、複数行として正しく表示されること"""

    #     # 2025/7/01: 複数商品仕入 (仕入 760 / 買掛金 760) -> 添付画像と同じ金額
    #     je6 = self.create_journal_entry(
    #         "2025-07-01",
    #         self.co_b,
    #         "複数商品仕入",
    #         self.purchase,
    #         760,
    #         self.accounts_payable,
    #         760,
    #     )
    #     PurchaseDetail.objects.create(
    #         journal_entry=je6, item=self.item_y, quantity=8, unit_price=50
    #     )  # 内訳 400
    #     PurchaseDetail.objects.create(
    #         journal_entry=je6, item=self.item_z, quantity=6, unit_price=60
    #     )  # 内訳 360

    #     response = self.client.get(reverse("purchase_book", args=[2025, 7]))
    #     data = response.context["data"]

    #     # データ件数 (ヘッダー1行 + 明細2行 + 総仕入/戻し/純仕入の集計行)
    #     self.assertEqual(
    #         len(data), 3 + 3, "取引1件（明細2件）で3行のデータが作成されていること"
    #     )

    #     # ヘッダー行 (0行目)
    #     self.assertEqual(data[0]["type"], "header")
    #     self.assertEqual(data[0]["company_name"], "乙社")
    #     self.assertEqual(data[0]["total_amount"], 760)

    #     # 明細1行目 (1行目)
    #     self.assertEqual(data[1]["type"], "detail")
    #     self.assertEqual(data[1]["item_name"], "Y商品")
    #     self.assertEqual(data[1]["sub_total"], 400)

    #     # 明細2行目 (2行目)
    #     self.assertEqual(data[2]["type"], "detail")
    #     self.assertEqual(data[2]["item_name"], "Z商品")
    #     self.assertEqual(data[2]["sub_total"], 360)
