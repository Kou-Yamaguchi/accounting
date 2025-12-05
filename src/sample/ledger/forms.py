from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _

from ledger.models import Account, JournalEntry, Debit, Credit
from enums.error_messages import ErrorMessages

ACCOUNT = "account"
AMOUNT = "amount"


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ["name", "type", "is_default"]


class JournalEntryForm(forms.ModelForm):
    class Meta:
        model = JournalEntry
        fields = ["date", "summary"]


class DebitForm(forms.ModelForm):
    class Meta:
        model = Debit
        fields = [ACCOUNT, AMOUNT]

    def clean_amount(self):
        amount = self.cleaned_data.get(AMOUNT)
        if amount is not None and amount <= Decimal("0"):
            raise forms.ValidationError(
                _(ErrorMessages.MESSAGE_0003.value),
                code="invalid",
                params={f"{AMOUNT}": amount},
            )
        return amount

    def clean(self):
        cleaned_data = super().clean()
        account = cleaned_data.get(ACCOUNT)
        amount = cleaned_data.get(AMOUNT)
        if (account and amount is None) or (amount and account is None):
            raise forms.ValidationError(
                _(ErrorMessages.MESSAGE_0004.value),
                code="invalid",
            )
        return cleaned_data


class CreditForm(forms.ModelForm):
    class Meta:
        model = Credit
        fields = [ACCOUNT, AMOUNT]

    def clean_amount(self):
        amount = self.cleaned_data.get(AMOUNT)
        if amount is not None and amount <= Decimal("0"):
            raise forms.ValidationError(
                _(ErrorMessages.MESSAGE_0003.value),
                code="invalid",
                params={f"{AMOUNT}": amount},
            )
        return amount

    def clean(self):
        cleaned_data = super().clean()
        account = cleaned_data.get(ACCOUNT)
        amount = cleaned_data.get(AMOUNT)

        # if (account and amount):
        #     return cleaned_data
        
        # raise forms.ValidationError(
        #     _(ErrorMessages.MESSAGE_0004.value),
        #     code="invalid",
        # )

        if (account and amount is None) or (amount and account is None):
            raise forms.ValidationError(
                _(ErrorMessages.MESSAGE_0004.value),
                code="invalid",
                params={ACCOUNT: account, AMOUNT: amount},
            )
        return cleaned_data


class BaseTotalFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        total_amount = Decimal("0.00")

        for form in self.forms:
            # if (form.cleaned_data) and not form.cleaned_data.get("DELETE", False):
            amount = form.cleaned_data.get(AMOUNT)
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
