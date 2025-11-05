from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.urls import reverse

from ledger.models import JournalEntry, Debit, Credit, Account, InitialBalance
from ledger.views import GeneralLedgerView
from ledger.services import calculate_monthly_balance
from enums.error_messages import ErrorMessages


class JournalEntryViewTest(TestCase):
    """
    journal_entryテーブルに対するCRUD操作のテスト
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="testuser", password="testpass"
        )
        self.client.force_login(self.user)
        self.cash = Account.objects.create(name="現金", type="asset")
        self.sales = Account.objects.create(name="売上", type="revenue")
        self.entry = JournalEntry.objects.create(
            date="2024-01-01", summary="初期取引", created_by=self.user
        )
        Debit.objects.create(
            journal_entry=self.entry,
            account=self.cash,
            amount=1000.00,
            created_by=self.user,
        )
        Credit.objects.create(
            journal_entry=self.entry,
            account=self.sales,
            amount=1000.00,
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
            debit_items=[{"account": self.cash.id, "amount": "100.00"}],
            credit_items=[{"account": self.sales.id, "amount": "100.00"}],
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
                    "account": self.cash.id,
                    "amount": "200.00",
                }
            ],
            credit_items=[
                {
                    "id": self.entry.credits.first().id,
                    "account": self.sales.id,
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
        self.cash = Account.objects.create(name="現金", type="asset")
        self.sales = Account.objects.create(name="売上", type="revenue")

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
            debit_items=[{"account": self.cash.id, "amount": "-100.00"}],
            credit_items=[{"account": self.sales.id, "amount": "100.00"}],
        )
        response = self.client.post("/ledger/new/", data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ErrorMessages.MESSAGE_0003.value)

    def test_unbalanced_journal_entry(self):
        data = self.build_post(
            date="2024-01-01",
            summary="不均衡取引",
            debit_items=[{"account": self.cash.id, "amount": "100.00"}],
            credit_items=[{"account": self.sales.id, "amount": "50.00"}],
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

        self.cash = Account.objects.create(name="現金", type="Asset")
        self.sales = Account.objects.create(name="売上", type="Revenue")
        self.purchases = Account.objects.create(name="仕入", type="Expense")
        self.accounts_payable = Account.objects.create(name="買掛金", type="Liability")
        self.supplies = Account.objects.create(name="消耗品", type="Asset")

        # テスト対象のビューにアクセスするためのURLを準備
        self.url_template = "/ledger/{account_name}/"

    def create_journal_entry(self, entry_date, summary, debits_data, credits_data):
        """
        取引 (JournalEntry) とその明細 (Debit/Credit) を作成するヘルパー関数
        debits_data/credits_data は [(Accountオブジェクト, Decimal金額), ...] のリスト
        """
        entry = JournalEntry.objects.create(date=entry_date, summary=summary)

        for account, amount in debits_data:
            Debit.objects.create(journal_entry=entry, account=account, amount=amount)

        for account, amount in credits_data:
            Credit.objects.create(journal_entry=entry, account=account, amount=amount)

        return entry

    # ----------------------------------------------------
    # 1. 1 vs 1 (単純仕訳) のテスト
    # ----------------------------------------------------

    def test_single_vs_single_entry_debit_side(self):
        """
        現金勘定をテスト対象とし、相手科目が1つの場合の借方（Debit）エントリを検証
        仕訳: 現金 100 / 売上 100
        """
        self.create_journal_entry(
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
        self.create_journal_entry(
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
        self.create_journal_entry(
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
        self.create_journal_entry(
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
        self.create_journal_entry(
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
        self.create_journal_entry(
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
        self.create_journal_entry(
            date(2025, 10, 10),
            "売上1",
            [(self.cash, Decimal("100"))],
            [(self.sales, Decimal("100"))],
        )

        # 2. 仕入 / 現金 40 (残高: 借方 60)
        self.create_journal_entry(
            date(2025, 10, 11),
            "仕入1",
            [(self.purchases, Decimal("40"))],
            [(self.cash, Decimal("40"))],
        )

        # 3. 現金 / 買掛金 50 (残高: 借方 110)
        self.create_journal_entry(
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


class CashBookCalculationTest(TestCase):

    # テスト開始前に必要なマスタデータ（勘定科目）を作成
    @classmethod
    def setUpTestData(cls):
        # 現金出納帳の対象科目
        cls.cash_account = Account.objects.create(name="現金")
        # 相手勘定科目
        cls.sales_account = Account.objects.create(name="売上")
        cls.supplies_account = Account.objects.create(name="消耗品費")
        cls.unknown_account = Account.objects.create(name="雑収入")

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
        je1 = JournalEntry.objects.create(date=date(2025, 4, 10), summary="売上入金")
        Debit.objects.create(journal_entry=je1, account=self.cash_account, amount=5000)
        Credit.objects.create(
            journal_entry=je1, account=self.sales_account, amount=5000
        )

        # 4月20日: 支出 (消耗品費) 2000
        je2 = JournalEntry.objects.create(date=date(2025, 4, 20), summary="文房具購入")
        Debit.objects.create(
            journal_entry=je2, account=self.supplies_account, amount=2000
        )
        Credit.objects.create(journal_entry=je2, account=self.cash_account, amount=2000)

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
        je3 = JournalEntry.objects.create(date=date(2025, 3, 15), summary="3月入金")
        Debit.objects.create(journal_entry=je3, account=self.cash_account, amount=10000)
        Credit.objects.create(
            journal_entry=je3, account=self.unknown_account, amount=10000
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
        je4 = JournalEntry.objects.create(date=date(2025, 4, 10), summary="4月出金")
        Debit.objects.create(
            journal_entry=je4, account=self.supplies_account, amount=5000
        )
        Credit.objects.create(journal_entry=je4, account=self.cash_account, amount=5000)

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
        je5 = JournalEntry.objects.create(date=date(2025, 5, 10), summary="売上入金")
        Debit.objects.create(journal_entry=je5, account=self.cash_account, amount=5000)
        Credit.objects.create(
            journal_entry=je5, account=self.sales_account, amount=5000
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
        je_prev = JournalEntry.objects.create(date=date(2025, 6, 30), summary="6月取引")
        Debit.objects.create(
            journal_entry=je_prev, account=self.cash_account, amount=1000
        )
        Credit.objects.create(
            journal_entry=je_prev, account=self.sales_account, amount=1000
        )

        # 7月1日 (月初): 支出 500 -> 7月の集計に含める
        je_start = JournalEntry.objects.create(
            date=date(2025, 7, 1), summary="7月1日取引"
        )
        Debit.objects.create(
            journal_entry=je_start, account=self.supplies_account, amount=500
        )
        Credit.objects.create(
            journal_entry=je_start, account=self.cash_account, amount=500
        )

        # 7月31日 (月末): 収入 2000 -> 7月の集計に含める
        je_end = JournalEntry.objects.create(
            date=date(2025, 7, 31), summary="7月31日取引"
        )
        Debit.objects.create(
            journal_entry=je_end, account=self.cash_account, amount=2000
        )
        Credit.objects.create(
            journal_entry=je_end, account=self.sales_account, amount=2000
        )

        # 8月1日 (翌月): 支出 3000 -> 7月の集計に含めない
        je_next = JournalEntry.objects.create(
            date=date(2025, 8, 1), summary="8月1日取引"
        )
        Debit.objects.create(
            journal_entry=je_next, account=self.supplies_account, amount=3000
        )
        Credit.objects.create(
            journal_entry=je_next, account=self.cash_account, amount=3000
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
        je6 = JournalEntry.objects.create(
            date=date(2025, 8, 15), summary=""
        )  # summaryを空欄にする
        Debit.objects.create(journal_entry=je6, account=self.cash_account, amount=5000)
        Credit.objects.create(
            journal_entry=je6, account=self.sales_account, amount=5000
        )

        result = calculate_monthly_balance("現金", 2025, 8)
        data = result["data"]

        # 収入取引の摘要が相手勘定（売上）になっていること
        self.assertEqual(
            data[1]["summary"],
            "売上",
            "summaryが空欄でも相手勘定科目が摘要になること",
        )
