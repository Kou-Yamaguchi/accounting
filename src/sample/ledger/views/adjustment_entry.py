"""
決算整理仕訳入力画面のビュー
"""

import json
from dataclasses import dataclass, field
from decimal import Decimal
from django.views.generic import CreateView
from django.urls import reverse_lazy
from django.db import transaction
from django.shortcuts import redirect

from ledger.models import JournalEntry, FiscalPeriod, Account
from ledger.forms import (
    AdjustmentJournalEntryForm,
    DebitFormSet,
    CreditFormSet,
)
from ledger.services_temp import AdjustmentCalculator
from enums.error_messages import ErrorMessages


@dataclass
class EntryBlock:
    """仕訳入力の1ブロック（1仕訳分）"""

    key: str
    title: str
    form: AdjustmentJournalEntryForm
    debit_formset: DebitFormSet
    credit_formset: CreditFormSet
    debit_initial_json: str = "[]"
    credit_initial_json: str = "[]"


class AdjustmentEntryCreateView(CreateView):
    """決算整理仕訳入力ビュー"""

    model = JournalEntry
    form_class = AdjustmentJournalEntryForm
    template_name = "ledger/adjustment_entry/form.html"
    success_url = reverse_lazy("journal_entry_list")

    debit_formset_class = DebitFormSet
    credit_formset_class = CreditFormSet

    @staticmethod
    def _get_account_or_none(name):
        """勘定科目名で検索し、存在しない場合はNoneを返す"""
        try:
            return Account.objects.get(name=name)
        except Account.DoesNotExist:
            return None

    def _create_formset(self, formset_class, post_data, prefix, initial=[]):
        """フォームセットを生成するヘルパー"""
        if post_data is not None:
            return formset_class(post_data, prefix=prefix)
        return formset_class(prefix=prefix, initial=initial)

    @staticmethod
    def _initial_to_json(initial_list):
        """initial リストを data-* 属性用の JSON 文字列に変換する"""
        if not initial_list:
            return "[]"
        result = []
        for item in initial_list:
            account = item.get("account")
            result.append({
                "account": account.pk if account else "",
                "amount": str(item.get("amount", "")),
            })
        return json.dumps(result)

    def _build_entry_blocks(self, fiscal_period, adjustment_info, post_data=None):
        """計算結果をもとにEntryBlockのリストを生成する"""
        blocks = []
        depreciation = adjustment_info.get("depreciation", {})
        allowance = adjustment_info.get("allowance", {})

        # 減価償却費ブロック（未計上の資産がある場合のみ）
        if depreciation.get("has_unrecorded"):
            total = depreciation["total_depreciation"]
            prefix = "depreciation"

            if post_data is None:
                debit_account = self._get_account_or_none("減価償却費")
                credit_account = self._get_account_or_none("減価償却累計額")
                debit_initial = [{"account": debit_account, "amount": total}]
                credit_initial = [{"account": credit_account, "amount": total}]
                debit_initial_json = self._initial_to_json(debit_initial)
                credit_initial_json = self._initial_to_json(credit_initial)
                form_initial = {"summary": "減価償却費の計上"}
            else:
                debit_initial_json = credit_initial_json = "[]"
                form_initial = None

            form = AdjustmentJournalEntryForm(
                post_data, prefix=prefix, initial=form_initial
            )
            debit_fs = self._create_formset(
                self.debit_formset_class,
                post_data,
                prefix=f"{prefix}-debit",
            )
            credit_fs = self._create_formset(
                self.credit_formset_class,
                post_data,
                prefix=f"{prefix}-credit",
            )
            blocks.append(
                EntryBlock(
                    key=prefix,
                    title="減価償却費",
                    form=form,
                    debit_formset=debit_fs,
                    credit_formset=credit_fs,
                    debit_initial_json=debit_initial_json,
                    credit_initial_json=credit_initial_json,
                )
            )

        # 貸倒引当金ブロック（計上額がある場合のみ）
        entry_amount = allowance.get("entry_amount", Decimal("0"))
        if entry_amount > 0:
            is_reversal = allowance.get("is_reversal", False)
            prefix = "allowance"

            if post_data is None:
                if is_reversal:
                    debit_account = self._get_account_or_none("貸倒引当金")
                    credit_account = self._get_account_or_none("貸倒引当金戻入")
                    form_initial = {"summary": "貸倒引当金の戻入"}
                else:
                    debit_account = self._get_account_or_none("貸倒引当金繰入")
                    credit_account = self._get_account_or_none("貸倒引当金")
                    form_initial = {"summary": "貸倒引当金繰入額の計上"}
                debit_initial = [{"account": debit_account, "amount": entry_amount}]
                credit_initial = [{"account": credit_account, "amount": entry_amount}]
                debit_initial_json = self._initial_to_json(debit_initial)
                credit_initial_json = self._initial_to_json(credit_initial)
            else:
                debit_initial_json = credit_initial_json = "[]"
                form_initial = None

            form = AdjustmentJournalEntryForm(
                post_data, prefix=prefix, initial=form_initial
            )
            debit_fs = self._create_formset(
                self.debit_formset_class,
                post_data,
                prefix=f"{prefix}-debit",
            )
            credit_fs = self._create_formset(
                self.credit_formset_class,
                post_data,
                prefix=f"{prefix}-credit",
            )
            blocks.append(
                EntryBlock(
                    key=prefix,
                    title="貸倒引当金",
                    form=form,
                    debit_formset=debit_fs,
                    credit_formset=credit_fs,
                    debit_initial_json=debit_initial_json,
                    credit_initial_json=credit_initial_json,
                )
            )

        return blocks

    def get_context_data(
        self, entry_blocks=None, adjustment_info=None, fiscal_period=None, **kwargs
    ):
        """コンテキストデータにEntryBlockリストと参考情報を追加"""
        data = super().get_context_data(**kwargs)

        # GETパラメータからfiscal_periodを解決
        if fiscal_period is None and self.request.method == "GET":
            fiscal_period_id = self.request.GET.get("fiscal_period")
            if fiscal_period_id:
                try:
                    fiscal_period = FiscalPeriod.objects.get(id=fiscal_period_id)
                except FiscalPeriod.DoesNotExist:
                    pass

        data["fiscal_periods"] = FiscalPeriod.objects.filter(is_closed=False)

        if fiscal_period:
            data["fiscal_period"] = fiscal_period

            if adjustment_info is None:
                adjustment_info = AdjustmentCalculator.get_all_adjustment_info(
                    fiscal_period
                )
            data.update(adjustment_info)

            if entry_blocks is None:
                entry_blocks = self._build_entry_blocks(fiscal_period, adjustment_info)

        data["entry_blocks"] = entry_blocks or []
        return data

    def post(self, request, *args, **kwargs):
        """POST処理：複数ブロックを一括バリデーション・保存"""
        fiscal_period_id = request.POST.get("fiscal_period")
        try:
            fiscal_period = FiscalPeriod.objects.get(id=fiscal_period_id)
        except (FiscalPeriod.DoesNotExist, TypeError, ValueError):
            return redirect(self.success_url)

        adjustment_info = AdjustmentCalculator.get_all_adjustment_info(fiscal_period)
        entry_blocks = self._build_entry_blocks(
            fiscal_period, adjustment_info, post_data=request.POST
        )

        all_valid = True
        for block in entry_blocks:
            form_valid = block.form.is_valid()
            debit_valid = block.debit_formset.is_valid()
            credit_valid = block.credit_formset.is_valid()

            # 借方・貸方合計チェック（両フォームセットが有効な場合のみ）
            if debit_valid and credit_valid:
                total_debit = getattr(
                    block.debit_formset, "total_amount", Decimal("0.00")
                )
                total_credit = getattr(
                    block.credit_formset, "total_amount", Decimal("0.00")
                )
                if total_debit != total_credit:
                    block.form.add_error(None, ErrorMessages.MESSAGE_0001.value)
                    form_valid = False

            if not (form_valid and debit_valid and credit_valid):
                all_valid = False

        if all_valid:
            with transaction.atomic():
                for block in entry_blocks:
                    instance = block.form.save(commit=False)
                    instance.date = fiscal_period.end_date
                    instance.fiscal_period = fiscal_period
                    instance.entry_type = "adjustment"
                    instance.save()
                    block.debit_formset.instance = instance
                    block.credit_formset.instance = instance
                    block.debit_formset.save()
                    block.credit_formset.save()
            return redirect(self.success_url)

        context = self.get_context_data(
            entry_blocks=entry_blocks,
            adjustment_info=adjustment_info,
            fiscal_period=fiscal_period,
        )
        return self.render_to_response(context)
