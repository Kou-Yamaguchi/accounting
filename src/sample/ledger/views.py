from django.shortcuts import render
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.db import transaction

from ledger.models import JournalEntry
from ledger.forms import JournalEntryForm, DebitFormSet, CreditFormSet

# Create your views here.


class JournalEntryListView(ListView):
    model = JournalEntry
    template_name = "ledger/journal_entry_list.html"
    context_object_name = "journal_entries"


class JournalEntryCreateView(CreateView):
    model = JournalEntry
    form_class = JournalEntryForm
    template_name = "ledger/journal_entry_form.html"
    success_url = reverse_lazy("journal_entry_list")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        instance = getattr(self, "object", None) or JournalEntry()
        if self.request.POST:
            data["debit_formset"] = DebitFormSet(self.request.POST, instance=instance)
            data["credit_formset"] = CreditFormSet(self.request.POST, instance=instance)
        else:
            data["debit_formset"] = DebitFormSet(instance=instance)
            data["credit_formset"] = CreditFormSet(instance=instance)
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        instance = form.save(commit=False)
        debit_formset = context.get("debit_formset")
        credit_formset = context.get("credit_formset")

        if not (debit_formset.is_valid() and credit_formset.is_valid()):
            return super().form_invalid(form)

        # バリデーションOKならトランザクション内で保存
        with transaction.atomic():
            self.object = instance
            self.object.save()
            debit_formset.instance = self.object
            credit_formset.instance = self.object
            debit_formset.save()
            credit_formset.save()
        return super().form_valid(form)


class JournalEntryUpdateView(UpdateView):
    model = JournalEntry
    form_class = JournalEntryForm
    template_name = "ledger/journal_entry_form.html"
    success_url = reverse_lazy("journal_entry_list")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        instance = getattr(self, "object", None) or JournalEntry()
        if self.request.POST:
            data["debit_formset"] = DebitFormSet(self.request.POST, instance=instance)
            data["credit_formset"] = CreditFormSet(self.request.POST, instance=instance)
        else:
            data["debit_formset"] = DebitFormSet(instance=instance)
            data["credit_formset"] = CreditFormSet(instance=instance)
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        instance = form.save(commit=False)
        debit_formset = context.get("debit_formset")
        credit_formset = context.get("credit_formset")

        if not (debit_formset.is_valid() and credit_formset.is_valid()):
            return super().form_invalid(form)

        with transaction.atomic():
            self.object = instance
            self.object.save()
            debit_formset.instance = self.object
            credit_formset.instance = self.object
            debit_formset.save()
            credit_formset.save()
        return super().form_valid(form)


class JournalEntryDeleteView(DeleteView):
    model = JournalEntry
    template_name = "ledger/journal_entry_confirm_delete.html"
    success_url = reverse_lazy("journal_entry_list")
