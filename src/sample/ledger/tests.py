from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ledger.models import JournalEntry, Debit, Credit, Account


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
