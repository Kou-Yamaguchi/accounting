from django.shortcuts import render
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy

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
        if self.request.POST:
            data['debits'] = DebitFormSet(self.request.POST)
            data['credits'] = CreditFormSet(self.request.POST)
        else:
            data['debits'] = DebitFormSet()
            data['credits'] = CreditFormSet()
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        debit_formset = context['debits']
        credit_formset = context['credits']
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
    template_name = "ledger/journal_entry_form.html"
    success_url = reverse_lazy("journal_entry_list")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['debits'] = DebitFormSet(self.request.POST, instance=self.object)
            data['credits'] = CreditFormSet(self.request.POST, instance=self.object)
        else:
            data['debits'] = DebitFormSet(instance=self.object)
            data['credits'] = CreditFormSet(instance=self.object)
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        debit_formset = context['debits']
        credit_formset = context['credits']
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
    template_name = "ledger/journal_entry_confirm_delete.html"
    success_url = reverse_lazy("journal_entry_list")