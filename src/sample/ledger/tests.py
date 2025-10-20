from django.contrib.auth import get_user_model
from django.test import TestCase

from ledger.models import JournalEntry, Debit, Credit, Account

# Create your tests here.
class CreateJournalEntryTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='testuser',
            password='testpass'
        )
        self.client.force_login(self.user)
        self.cash = Account.objects.create(name="現金", type="asset")
        self.sales = Account.objects.create(name="売上", type="revenue")

    def test_create_journal_entry(self):
        data = {
            'date': '2024-01-01',
            'summary': 'Test Journal Entry',
            'debit_formset-TOTAL_FORMS': '1',
            'debit_formset-INITIAL_FORMS': '0',
            'debit_formset-MIN_NUM_FORMS': '0',
            'debit_formset-MAX_NUM_FORMS': '1000',
            'debit_formset-0-account': self.cash.id,
            'debit_formset-0-amount': '100.00',
            'credit_formset-TOTAL_FORMS': '1',
            'credit_formset-INITIAL_FORMS': '0',
            'credit_formset-MIN_NUM_FORMS': '0',
            'credit_formset-MAX_NUM_FORMS': '1000',
            'credit_formset-0-account': self.sales.id,
            'credit_formset-0-amount': '100.00',
        }
        self.client.post('/ledger/journal-entries/new/', data)
        journal_entries = JournalEntry.objects.filter(summary='Test Journal Entry').first()
        debit = Debit.objects.filter(journal_entries_id=journal_entries.id)
        credit = Credit.objects.filter(journal_entries_id=journal_entries.id)
        self.assertEqual(journal_entries.count(), 1)
        self.assertEqual(debit.first().amount, 100.00)
        self.assertEqual(credit.first().amount, 100.00)


# class ReadJournalEntryTest(TestCase):
#     def setUp(self):
#         self.user = get_user_model().objects.create_user(
#             username='testuser',
#             password='testpass'
#         )
#         self.client.force_login(self.user)

#     def test_read_journal_entry(self):
#         # テスト用のコードをここに追加してください
#         self.assertTrue(True)  # 仮のアサーション


# class UpdateJournalEntryTest(TestCase):
#     def test_update_journal_entry(self):
#         # テスト用のコードをここに追加してください
#         self.assertTrue(True)  # 仮のアサーション


# class DeleteJournalEntryTest(TestCase):
#     def test_delete_journal_entry(self):
#         # テスト用のコードをここに追加してください
#         self.assertTrue(True)  # 仮のアサーション
