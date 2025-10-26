from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.urls import reverse
from datetime import date
from decimal import Decimal

from ledger.models import JournalEntry, Debit, Credit, Account
from ledger.views import GeneralLedgerView


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
        self.assertContains(response, "このフィールドは必須です")

    def test_negative_amount_debit(self):
        data = self.build_post(
            date="2024-01-01",
            summary="負の金額取引",
            debit_items=[{"account": self.cash.id, "amount": "-100.00"}],
            credit_items=[{"account": self.sales.id, "amount": "100.00"}],
        )
        response = self.client.post("/ledger/new/", data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "金額は正の値でなければなりません。")

    def test_unbalanced_journal_entry(self):
        data = self.build_post(
            date="2024-01-01",
            summary="不均衡取引",
            debit_items=[{"account": self.cash.id, "amount": "100.00"}],
            credit_items=[{"account": self.sales.id, "amount": "50.00"}],
        )
        response = self.client.post("/ledger/new/", data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "借方合計と貸方合計は一致する必要があります。")


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

    def create_transaction(self, entry_date, summary, debits_data, credits_data):
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
        self.create_transaction(
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
        self.create_transaction(
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

    def test_single_vs_multiple_entry_debit_side(self):
        """
        現金勘定をテスト対象とし、相手科目が複数の場合の借方エントリを検証
        仕訳: 現金 150 / 売上 100, 消耗品 50 （売上と消耗品が相手）
        """
        self.create_transaction(
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
        self.create_transaction(
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
        self.create_transaction(
            date(2025, 10, 10),
            "売上1",
            [(self.cash, Decimal("100"))],
            [(self.sales, Decimal("100"))],
        )

        # 2. 仕入 / 現金 40 (残高: 借方 60)
        self.create_transaction(
            date(2025, 10, 11),
            "仕入1",
            [(self.purchases, Decimal("40"))],
            [(self.cash, Decimal("40"))],
        )

        # 3. 現金 / 買掛金 50 (残高: 借方 110)
        self.create_transaction(
            date(2025, 10, 12),
            "買掛金支払い",
            [(self.cash, Decimal("50"))],
            [(self.accounts_payable, Decimal("50"))],
        )

        request = self.factory.get(self.url_template.format(account_name="現金"))
        response = GeneralLedgerView.as_view()(request, account_name="現金")

        ledger_entries = response.context_data["ledger_entries"]
        self.assertEqual(len(ledger_entries), 3)

        # 残高計算ロジックをテストコード側で実行
        current_balance = Decimal("0")

        # エントリは日付順にソートされていることを前提とする
        # 現金は資産 (Asset) のため、借方が増加、貸方が減少

        # 1. 借方 100
        current_balance += (
            ledger_entries[0]["debit_amount"] - ledger_entries[0]["credit_amount"]
        )
        self.assertEqual(current_balance, Decimal("100"))

        # 2. 貸方 40 (100 - 40 = 60)
        current_balance += (
            ledger_entries[1]["debit_amount"] - ledger_entries[1]["credit_amount"]
        )
        self.assertEqual(current_balance, Decimal("60"))

        # 3. 借方 50 (60 + 50 = 110)
        current_balance += (
            ledger_entries[2]["debit_amount"] - ledger_entries[2]["credit_amount"]
        )
        self.assertEqual(current_balance, Decimal("110"))

        # 注意: view.pyで残高フィールドを付与していないため、テストコード側で計算して検証しています。
        # もしview.py側で残高フィールド (e.g., 'running_balance') を付与していれば、
        # self.assertEqual(ledger_entries[2]['running_balance'], Decimal('110')) のように検証できます。
