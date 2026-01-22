"""
決算整理仕訳入力画面のビュー
"""

from decimal import Decimal
from django.views.generic import CreateView
from django.urls import reverse_lazy
from django.db import transaction

from ledger.models import JournalEntry, FiscalPeriod
from ledger.forms import (
    AdjustmentJournalEntryForm,
    DebitFormSet,
    CreditFormSet,
)
from ledger.services_temp import AdjustmentCalculator
from enums.error_messages import ErrorMessages


class AdjustmentEntryCreateView(CreateView):
    """決算整理仕訳入力ビュー"""

    model = JournalEntry
    form_class = AdjustmentJournalEntryForm
    template_name = "ledger/adjustment_entry/form.html"
    success_url = reverse_lazy("journal_entry_list")

    debit_formset_class = DebitFormSet
    credit_formset_class = CreditFormSet

    def get_formsets(self, post_data=None, instance=None):
        """フォームセットを取得"""
        if post_data:
            debit_fs = self.debit_formset_class(post_data, instance=instance)
            credit_fs = self.credit_formset_class(post_data, instance=instance)
        else:
            debit_fs = self.debit_formset_class(instance=instance)
            credit_fs = self.credit_formset_class(instance=instance)
        return debit_fs, credit_fs

    def get_context_data(self, **kwargs):
        """コンテキストデータにフォームセットと参考情報を追加"""
        data = super().get_context_data(**kwargs)
        instance = getattr(self, "object", None) or JournalEntry()
        post = self.request.POST if self.request.method == "POST" else None
        debit_fs, credit_fs = self.get_formsets(post, instance)
        data["debit_formset"] = debit_fs
        data["credit_formset"] = credit_fs

        # 会計期間が選択されている場合、参考情報を計算
        fiscal_period_id = None
        if post:
            fiscal_period_id = post.get("fiscal_period")
        elif self.request.method == "GET":
            fiscal_period_id = self.request.GET.get("fiscal_period")

        if fiscal_period_id:
            try:
                fiscal_period = FiscalPeriod.objects.get(id=fiscal_period_id)
                # 参考情報を計算
                adjustment_info = AdjustmentCalculator.get_all_adjustment_info(
                    fiscal_period
                )
                data.update(adjustment_info)
            except FiscalPeriod.DoesNotExist:
                pass

        return data

    def form_valid(self, form):
        """フォームのバリデーションと保存処理"""
        context = self.get_context_data()
        instance = form.save(commit=False)
        debit_formset = context.get("debit_formset")
        credit_formset = context.get("credit_formset")

        # フォームセットのバリデーション
        if not (debit_formset.is_valid() and credit_formset.is_valid()):
            return self.form_invalid(form)

        # 借方・貸方合計チェック
        total_debit = getattr(debit_formset, "total_amount", Decimal("0.00"))
        total_credit = getattr(credit_formset, "total_amount", Decimal("0.00"))
        if total_debit != total_credit:
            form.add_error(None, ErrorMessages.MESSAGE_0001.value)
            return self.form_invalid(form)

        # 会計期間から期末日を取得して設定
        fiscal_period = form.cleaned_data["fiscal_period"]
        instance.date = fiscal_period.end_date
        instance.fiscal_period = fiscal_period
        instance.entry_type = "adjustment"  # 決算整理仕訳として設定

        # トランザクション内で保存
        with transaction.atomic():
            self.object = instance
            self.object.save()
            debit_formset.instance = self.object
            credit_formset.instance = self.object
            debit_formset.save()
            credit_formset.save()

        return super().form_valid(form)
