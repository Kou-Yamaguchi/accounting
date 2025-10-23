from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ledger.models import JournalEntry, Debit, Credit, Account

# Create your tests here.
class JournalEntryViewTest(TestCase):
    """
    journal_entryテーブルに対するCRUD操作のテスト
    1. 一覧表示
    2. 作成
    3. 更新
    4. 削除
    それぞれの操作に対して、ビューが正しく動作することを確認する
    ためのテストケースを実装する。
    """
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='testuser',
            password='testpass'
        )
        self.client.force_login(self.user)
        self.cash = Account.objects.create(name="現金", type="asset")
        self.sales = Account.objects.create(name="売上", type="revenue")
        self.entry = JournalEntry.objects.create(
            date="2024-01-01",
            summary="初期取引",
            created_by=self.user
        )
        Debit.objects.create(
            journal_entry=self.entry,
            account=self.cash,
            amount=1000.00,
            created_by=self.user
        )
        Credit.objects.create(
            journal_entry=self.entry,
            account=self.sales,
            amount=1000.00,
            created_by=self.user
        )

    def test_journal_entry_list_view(self):
        response = self.client.get(reverse("journal_entry_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "初期取引")

    def test_create_journal_entry(self):
        data = {
            'date': '2024-01-01',
            'summary': 'テスト取引',
            'debits-TOTAL_FORMS': '1',
            'debits-INITIAL_FORMS': '0',
            'debits-MIN_NUM_FORMS': '0',
            'debits-MAX_NUM_FORMS': '1000',
            'debits-0-account': self.cash.id,
            'debits-0-amount': '100.00',
            'credits-TOTAL_FORMS': '1',
            'credits-INITIAL_FORMS': '0',
            'credits-MIN_NUM_FORMS': '0',
            'credits-MAX_NUM_FORMS': '1000',
            'credits-0-account': self.sales.id,
            'credits-0-amount': '100.00',
        }
        response = self.client.post('/ledger/new/', data)
        self.assertEqual(response.status_code, 302)  # リダイレクトを確認
        journal_entries = JournalEntry.objects.all()
        self.assertEqual(journal_entries.count(), 2)
        self.assertEqual(journal_entries.filter(summary="テスト取引").first().debits.first().amount, 100.00)
        self.assertEqual(journal_entries.filter(summary="テスト取引").first().credits.first().amount, 100.00)

    def test_update_journal_entry(self):
        data = {
            'date': '2024-01-02',
            'summary': '更新取引',
            'debits-TOTAL_FORMS': '1',
            'debits-INITIAL_FORMS': '1',
            'debits-MIN_NUM_FORMS': '0',
            'debits-MAX_NUM_FORMS': '1000',
            'debits-0-id': self.entry.debits.first().id,
            'debits-0-account': self.cash.id,
            'debits-0-amount': '200.00',
            'credits-TOTAL_FORMS': '1',
            'credits-INITIAL_FORMS': '1',
            'credits-MIN_NUM_FORMS': '0',
            'credits-MAX_NUM_FORMS': '1000',
            'credits-0-id': self.entry.credits.first().id,
            'credits-0-account': self.sales.id,
            'credits-0-amount': '200.00',
        }
        response = self.client.post(f'/ledger/{self.entry.id}/edit/', data)
        self.assertEqual(response.status_code, 302)  # リダイレクトを確認
        updated_entry = JournalEntry.objects.get(id=self.entry.id)
        self.assertEqual(updated_entry.summary, "更新取引")
        self.assertEqual(updated_entry.debits.first().amount, 200.00)
        self.assertEqual(updated_entry.credits.first().amount, 200.00)

    def test_delete_journal_entry(self):
        response = self.client.post(f'/ledger/{self.entry.id}/delete/')
        self.assertEqual(response.status_code, 302)  # リダイレクトを確認
        journal_entries = JournalEntry.objects.all()
        self.assertEqual(journal_entries.count(), 0)
        self.assertEqual(Debit.objects.count(), 0)
        self.assertEqual(Credit.objects.count(), 0)
