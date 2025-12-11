from django.urls import path

from ledger.views import (
    AccountListView,
    AccountCreateView,
    AccountUpdateView,
    AccountDeleteView,
    JournalEntryCreateView,
    JournalEntryListView,
    JournalEntryUpdateView,
    JournalEntryDeleteView,
    LedgerSelectView,
    GeneralLedgerView,
    CashBookView,
    CurrentAccountCashBookView,
    PettyCashBookView,
    PurchaseBookView
)

urlpatterns = [
    path("new/", JournalEntryCreateView.as_view(), name="journal_entry_new"),
    path("", JournalEntryListView.as_view(), name="journal_entry_list"),
    path("<int:pk>/edit/", JournalEntryUpdateView.as_view(), name="journal_entry_edit"),
    path("<int:pk>/delete/", JournalEntryDeleteView.as_view(), name="journal_entry_delete"),
    path("accounts/", AccountListView.as_view(), name="account_list"),
    path("accounts/new/", AccountCreateView.as_view(), name="account_create"),
    path("accounts/<int:pk>/edit/", AccountUpdateView.as_view(), name="account_edit"),
    path("accounts/<int:pk>/delete/", AccountDeleteView.as_view(), name="account_delete"),
    path("select/", LedgerSelectView.as_view(), name="ledger_select"),
    path("<str:account_name>/", GeneralLedgerView.as_view(), name="general_ledger"),
    path("cash_book/cash/<int:year>/<int:month>/", CashBookView.as_view(), name="cash_book"),
    path("cash_book/cash/", CashBookView.as_view(), name="cash_book_current"),
    path("cash_book/current/<int:year>/<int:month>/", CurrentAccountCashBookView.as_view(), name="current_account_cash_book"),
    path("cash_book/current/", CurrentAccountCashBookView.as_view(), name="current_account_cash_book_current"),
    path("cash_book/petty/<int:year>/<int:month>/", PettyCashBookView.as_view(), name="petty_cash_book"),
    path("cash_book/petty/", PettyCashBookView.as_view(), name="petty_cash_book_current"),
    path("purchase_book/<int:year>/<int:month>/", PurchaseBookView.as_view(), name="purchase_book"),
    path("purchase_book/", PurchaseBookView.as_view(), name="purchase_book_current"),
]
