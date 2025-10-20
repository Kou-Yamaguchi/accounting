from django import forms

from ledger.models import JournalEntry, Debit, Credit

class JournalEntryForm(forms.ModelForm):
    class Meta:
        model = JournalEntry
        fields = ['date', 'summary']


class DebitForm(forms.ModelForm):
    class Meta:
        model = Debit
        fields = ['account', 'amount']


class CreditForm(forms.ModelForm):
    class Meta:
        model = Credit
        fields = ['account', 'amount']


DebitFormSet = forms.inlineformset_factory(
    JournalEntry, Debit, form=DebitForm, extra=1, can_delete=True
)

CreditFormSet = forms.inlineformset_factory(
    JournalEntry, Credit, form=CreditForm, extra=1, can_delete=True
)