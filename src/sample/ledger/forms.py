from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _

from ledger.models import (
    Account,
    Company,
    JournalEntry,
    Debit,
    Credit,
    FixedAsset,
    FiscalPeriod,
)
from enums.error_messages import ErrorMessages

ACCOUNT = "account"
AMOUNT = "amount"


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ["name", "type", "is_default"]


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ["name"]


class JournalEntryForm(forms.ModelForm):
    class Meta:
        model = JournalEntry
        fields = ["date", "summary", "company"]
        widgets = {
            "summary": forms.TextInput(attrs={"class": "form-control"}),
        }


class DebitForm(forms.ModelForm):
    class Meta:
        model = Debit
        fields = [ACCOUNT, AMOUNT]

    def clean_amount(self):
        amount = self.cleaned_data.get(AMOUNT)
        if amount is None:
            raise forms.ValidationError(
                _(ErrorMessages.MESSAGE_0004.value),
                code="invalid",
                params={f"{AMOUNT}": amount},
            )

        if amount <= Decimal("0"):
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
        if amount is None:
            raise forms.ValidationError(
                _(ErrorMessages.MESSAGE_0004.value),
                code="invalid",
                params={f"{AMOUNT}": amount},
            )

        if amount <= Decimal("0"):
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

        # 非フォームエラーのリストを初期化（まだ存在しない場合）
        if not hasattr(self, "_non_form_errors") or self._non_form_errors is None:
            self._non_form_errors = []

        total_amount = Decimal("0.00")
        has_errors = False

        for i, form in enumerate(self.forms):
            if form.cleaned_data.get("DELETE", False):
                continue

            amount = form.cleaned_data.get(AMOUNT)
            if amount is None:
                # フォームセット全体のエラーとして追加（早期リターンしない）
                # self.add_error(None, f"{i+1}行目: {ErrorMessages.MESSAGE_0004.value}")
                # has_errors = True
                self._non_form_errors.append(
                    forms.ValidationError(
                        f"{i+1}行目: {ErrorMessages.MESSAGE_0004.value}"
                    )
                )
                continue

            if amount <= 0:
                # self.add_error(None, f"{i+1}行目: {ErrorMessages.MESSAGE_0003.value}")
                # has_errors = True
                self._non_form_errors.append(
                    forms.ValidationError(
                        f"{i+1}行目: {ErrorMessages.MESSAGE_0003.value}"
                    )
                )
                continue

            total_amount += amount

        self.total_amount = total_amount


DebitFormSet = forms.inlineformset_factory(
    JournalEntry,
    Debit,
    form=DebitForm,
    formset=BaseTotalFormSet,
    extra=0,
    can_delete=True,
)

CreditFormSet = forms.inlineformset_factory(
    JournalEntry,
    Credit,
    form=CreditForm,
    formset=BaseTotalFormSet,
    extra=0,
    can_delete=True,
)


class FixedAssetInlineForm(forms.ModelForm):
    """
    固定資産情報の入力フォーム（仕訳入力と同時に登録）
    """

    register_as_fixed_asset = forms.BooleanField(
        required=False, label="固定資産として登録", initial=False
    )

    class Meta:
        model = FixedAsset
        fields = [
            "register_as_fixed_asset",
            "name",
            "asset_number",
            "account",
            "useful_life",
            "depreciation_method",
            "residual_value",
        ]
        widgets = {
            "residual_value": forms.NumberInput(attrs={"value": 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 固定資産科目のみを選択肢に
        self.fields["account"].queryset = Account.objects.filter(type="asset")
        # 登録フラグがOFFの場合は他のフィールドは必須ではない
        for field_name in ["name", "asset_number", "account", "useful_life"]:
            self.fields[field_name].required = False

    def clean(self):
        cleaned_data = super().clean()
        register_flag = cleaned_data.get("register_as_fixed_asset")

        if register_flag:
            # 固定資産として登録する場合、必須フィールドをチェック
            required_fields = ["name", "asset_number", "account", "useful_life"]
            for field_name in required_fields:
                if not cleaned_data.get(field_name):
                    self.add_error(
                        field_name,
                        f"固定資産登録時は{self.fields[field_name].label}が必須です。",
                    )

        return cleaned_data


class AdjustmentJournalEntryForm(forms.ModelForm):
    """決算整理仕訳用フォーム"""

    fiscal_period = forms.ModelChoiceField(
        queryset=FiscalPeriod.objects.filter(is_closed=False),
        label="会計期間",
        required=True,
    )

    class Meta:
        model = JournalEntry
        fields = ["fiscal_period", "summary", "company"]
        widgets = {
            "summary": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 日付フィールドは表示しない（期末日で自動設定）
        # entry_typeも自動設定するため除外


class FiscalPeriodForm(forms.ModelForm):
    class Meta:
        model = FiscalPeriod
        fields = ["name", "start_date", "end_date", "is_closed"]
