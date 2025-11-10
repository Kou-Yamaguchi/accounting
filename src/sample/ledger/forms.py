from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _

from ledger.models import JournalEntry, Debit, Credit
from enums.error_messages import ErrorMessages

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
                _(ErrorMessages.MESSAGE_0003.value),
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
                _(ErrorMessages.MESSAGE_0004.value),
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
                _(ErrorMessages.MESSAGE_0003.value),
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
                _(ErrorMessages.MESSAGE_0004.value),
                code="invalid",
                params={"account": account, "amount": amount},
            )
        return cleaned_data


class BaseTotalFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        total_amount = Decimal("0.00")

        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get("DELETE", False):
                amount = form.cleaned_data.get("amount")
                if amount is None or amount <= 0:
                    raise forms.ValidationError(ErrorMessages.MESSAGE_0003.value)
                total_amount += amount

        self.total_amount = total_amount


DebitFormSet = forms.inlineformset_factory(
    JournalEntry,
    Debit,
    form=DebitForm,
    formset=BaseTotalFormSet,
    extra=1,
    can_delete=True
)

CreditFormSet = forms.inlineformset_factory(
    JournalEntry,
    Credit,
    form=CreditForm,
    formset=BaseTotalFormSet,
    extra=1,
    can_delete=True
)
