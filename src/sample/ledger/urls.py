from django.urls import path

from ledger.views import (
    JournalEntryCreateView,
    JournalEntryListView,
    JournalEntryUpdateView,
    JournalEntryDeleteView,
)

urlpatterns = [
    path("new/", JournalEntryCreateView.as_view(), name="journal_entry_new"),
    path("", JournalEntryListView.as_view(), name="journal_entry_list"),
    path("<int:pk>/edit/", JournalEntryUpdateView.as_view(), name="journal_entry_edit"),
    path("<int:pk>/delete/", JournalEntryDeleteView.as_view(), name="journal_entry_delete"),
]
