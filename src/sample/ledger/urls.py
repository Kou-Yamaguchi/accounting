from django.urls import path

from ledger.views import (
    JournalEntryCreateView,
    JournalEntryListView,
    JournalEntryUpdateView,
    JournalEntryDeleteView,
    GeneralLedgerView,
    CashBookView,
)

urlpatterns = [
    path("new/", JournalEntryCreateView.as_view(), name="journal_entry_new"),
    path("", JournalEntryListView.as_view(), name="journal_entry_list"),
    path("<int:pk>/edit/", JournalEntryUpdateView.as_view(), name="journal_entry_edit"),
    path("<int:pk>/delete/", JournalEntryDeleteView.as_view(), name="journal_entry_delete"),
    path("ledger/<str:account_name>/", GeneralLedgerView.as_view(), name="general_ledger"),
    path("cash_book/<int:year>/<int:month>/", CashBookView.as_view(), name="cash_book"),
    path("cash_book/", CashBookView.as_view(), name="cash_book_current"),
]
