from django.urls import path
from django.views.generic import TemplateView

from ledger.views.dashboard import DashboardView
from ledger.views.financial_statement import (
    BalanceSheetView,
    ProfitAndLossView,
    TrialBalanceView,
)
from ledger.views.cashbook import (
    CashBookView,
    CurrentAccountCashBookView,
    PettyCashBookView,
)
from ledger.views.purchasebook import PurchaseBookView
from ledger.views.views import (
    AccountListView,
    AccountCreateView,
    AccountUpdateView,
    AccountDeleteView,
    CompanyListView,
    CompanyCreateView,
    CompanyUpdateView,
    CompanyDeleteView,
    FiscalPeriodListView,
    FiscalPeriodCreateView,
    FiscalPeriodUpdateView,
    # FiscalPeriodDeleteView,
    JournalEntryCreateView,
    JournalEntryListView,
    JournalEntryUpdateView,
    JournalEntryDeleteView,
    LedgerSelectView,
    GeneralLedgerView,
)
from ledger.views.adjustment_entry import AdjustmentEntryCreateView
from ledger.views.pdf.journal_pdf import journal_pdf

urlpatterns = [
    path("new/", JournalEntryCreateView.as_view(), name="journal_entry_new"),
    path(
        "adjustment/new/",
        AdjustmentEntryCreateView.as_view(),
        name="adjustment_entry_new",
    ),
    path("", JournalEntryListView.as_view(), name="journal_entry_list"),
    path("<int:pk>/edit/", JournalEntryUpdateView.as_view(), name="journal_entry_edit"),
    path(
        "<int:pk>/delete/",
        JournalEntryDeleteView.as_view(),
        name="journal_entry_delete",
    ),
    path("pdf/", journal_pdf, name="journal_pdf"),
    path("accounts/", AccountListView.as_view(), name="account_list"),
    path("accounts/new/", AccountCreateView.as_view(), name="account_create"),
    path("accounts/<int:pk>/edit/", AccountUpdateView.as_view(), name="account_edit"),
    path(
        "accounts/<int:pk>/delete/", AccountDeleteView.as_view(), name="account_delete"
    ),
    path("companies/", CompanyListView.as_view(), name="company_list"),
    path("companies/new/", CompanyCreateView.as_view(), name="company_create"),
    path("companies/<int:pk>/edit/", CompanyUpdateView.as_view(), name="company_edit"),
    path(
        "companies/<int:pk>/delete/", CompanyDeleteView.as_view(), name="company_delete"
    ),
    path("fiscal_periods/", FiscalPeriodListView.as_view(), name="fiscal_period_list"),
    path(
        "fiscal_periods/new/",
        FiscalPeriodCreateView.as_view(),
        name="fiscal_period_create",
    ),
    path(
        "fiscal_periods/<int:pk>/edit/",
        FiscalPeriodUpdateView.as_view(),
        name="fiscal_period_edit",
    ),
    path("select/", LedgerSelectView.as_view(), name="ledger_select"),
    path(
        "trial_balance/",
        TemplateView.as_view(template_name="ledger/trial_balance.html"),
        name="trial_balance",
    ),
    path(
        "trial_balance_by_year/",
        TrialBalanceView.as_view(),
        name="trial_balance_by_year",
    ),
    path(
        "general_ledger/",
        TemplateView.as_view(template_name="ledger/general_ledger.html"),
        name="general_ledger",
    ),
    path(
        "balance_sheet/",
        TemplateView.as_view(template_name="ledger/balance_sheet/balance_sheet.html"),
        name="balance_sheet",
    ),
    path(
        "balance_sheet_by_year/",
        BalanceSheetView.as_view(),
        name="balance_sheet_by_year",
    ),
    path(
        "profit_and_loss/",
        TemplateView.as_view(
            template_name="ledger/profit_and_loss/profit_and_loss.html"
        ),
        name="profit_and_loss",
    ),
    path(
        "profit_and_loss_by_year/",
        ProfitAndLossView.as_view(),
        name="profit_and_loss_by_year",
    ),
    path(
        "general_ledger/content",
        GeneralLedgerView.as_view(),
        name="general_ledger_by_account",
    ),
    path(
        "cash_book/cash/<int:year>/<int:month>/",
        CashBookView.as_view(),
        name="cash_book",
    ),
    path("cash_book/cash/", CashBookView.as_view(), name="cash_book_current"),
    path(
        "cash_book/current/<int:year>/<int:month>/",
        CurrentAccountCashBookView.as_view(),
        name="current_account_cash_book",
    ),
    path(
        "cash_book/current/",
        CurrentAccountCashBookView.as_view(),
        name="current_account_cash_book_current",
    ),
    path(
        "cash_book/petty/<int:year>/<int:month>/",
        PettyCashBookView.as_view(),
        name="petty_cash_book",
    ),
    path(
        "cash_book/petty/", PettyCashBookView.as_view(), name="petty_cash_book_current"
    ),
    path(
        "purchase_book/<int:year>/<int:month>/",
        PurchaseBookView.as_view(),
        name="purchase_book",
    ),
    path("purchase_book/", PurchaseBookView.as_view(), name="purchase_book_current"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
]
