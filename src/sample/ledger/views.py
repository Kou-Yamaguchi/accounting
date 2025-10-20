from django.shortcuts import render
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from ledger.models import JournalEntry
from ledger.forms import JournalEntryForm, DebitFormSet, CreditFormSet
# Create your views here.

class JournalEntryListView(ListView):
    model = JournalEntry
    template_name = "journal_entry_list.html"
    context_object_name = "journal_entries"


class JournalEntryCreateView(CreateView):
    model = JournalEntry
    form_class = JournalEntryForm
    template_name = "journal_entry_form.html"
    success_url = "/ledger/journal-entries/"

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['debit_formset'] = DebitFormSet(self.request.POST)
            data['credit_formset'] = CreditFormSet(self.request.POST)
        else:
            data['debit_formset'] = DebitFormSet()
            data['credit_formset'] = CreditFormSet()
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        debit_formset = context['debit_formset']
        credit_formset = context['credit_formset']
        if debit_formset.is_valid() and credit_formset.is_valid():
            self.object = form.save()
            debit_formset.instance = self.object
            credit_formset.instance = self.object
            debit_formset.save()
            credit_formset.save()
            return super().form_valid(form)
        else:
            return self.form_invalid(form)
        

class JournalEntryUpdateView(UpdateView):
    model = JournalEntry
    form_class = JournalEntryForm
    template_name = "journal_entry_form.html"
    success_url = "/ledger/journal-entries/"

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['debit_formset'] = DebitFormSet(self.request.POST, instance=self.object)
            data['credit_formset'] = CreditFormSet(self.request.POST, instance=self.object)
        else:
            data['debit_formset'] = DebitFormSet(instance=self.object)
            data['credit_formset'] = CreditFormSet(instance=self.object)
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        debit_formset = context['debit_formset']
        credit_formset = context['credit_formset']
        if debit_formset.is_valid() and credit_formset.is_valid():
            self.object = form.save()
            debit_formset.instance = self.object
            credit_formset.instance = self.object
            debit_formset.save()
            credit_formset.save()
            return super().form_valid(form)
        else:
            return self.form_invalid(form)
        

class JournalEntryDeleteView(DeleteView):
    model = JournalEntry
    template_name = "journal_entry_confirm_delete.html"
    success_url = "/ledger/journal-entries/"