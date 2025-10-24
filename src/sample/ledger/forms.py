from django import forms
from django.utils.translation import gettext_lazy as _
from decimal import Decimal

from ledger.models import JournalEntry, Debit, Credit


class JournalEntryForm(forms.ModelForm):
    class Meta:
        model = JournalEntry
        fields = ["date", "summary"]


class DebitForm(forms.ModelForm):
    class Meta:
        model = Debit
        fields = ["account", "amount"]

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is not None and amount <= Decimal("0"):
            raise forms.ValidationError(
                _("金額は正の値でなければなりません。"),
                code="invalid",
                params={"amount": amount},
            )
        return amount

    def clean(self):
        cleaned_data = super().clean()
        account = cleaned_data.get("account")
        amount = cleaned_data.get("amount")
        if (account and amount is None) or (amount and account is None):
            raise forms.ValidationError(
                _("勘定科目と金額の両方を入力してください。"),
                code="invalid",
            )
        return cleaned_data


class CreditForm(forms.ModelForm):
    class Meta:
        model = Credit
        fields = ["account", "amount"]

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is not None and amount <= Decimal("0"):
            raise forms.ValidationError(
                _("金額は正の値でなければなりません。"),
                code="invalid",
                params={"amount": amount},
            )
        return amount

    def clean(self):
        cleaned_data = super().clean()
        account = cleaned_data.get("account")
        amount = cleaned_data.get("amount")
        if (account and amount is None) or (amount and account is None):
            raise forms.ValidationError(
                _("勘定科目と金額の両方を入力してください。"),
                code="invalid",
                params={"account": account, "amount": amount},
            )
        return cleaned_data


DebitFormSet = forms.inlineformset_factory(
    JournalEntry, Debit, form=DebitForm, extra=1, can_delete=True
)

CreditFormSet = forms.inlineformset_factory(
    JournalEntry, Credit, form=CreditForm, extra=1, can_delete=True
)
