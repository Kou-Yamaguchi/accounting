from decimal import Decimal

from django.shortcuts import render, get_object_or_404

# from django.db.models import F, Q, Value, CharField, Prefetch, Sum
from django.http import HttpResponse, HttpRequest
from django.views.generic import (
    View,
    ListView,
    CreateView,
    UpdateView,
    DeleteView,
    TemplateView,
)
from django.urls import reverse_lazy
from django.db import transaction

from ledger.models import JournalEntry, Account, Company, FixedAsset, FiscalPeriod
from ledger.structures import DayRange, YearMonth
from ledger.forms import (
    JournalEntryForm,
    DebitFormSet,
    CreditFormSet,
    FixedAssetInlineForm,
)
from ledger.services import (
    get_list_general_ledger_row,
    get_month_range,
    get_year_month_from_string,
)
from enums.error_messages import ErrorMessages


class AccountCreateView(CreateView):
    model = Account
    fields = ["name", "type"]
    template_name = "ledger/account/form.html"
    success_url = reverse_lazy("account_list")


class AccountListView(ListView):
    model = Account
    template_name = "ledger/account/list.html"
    context_object_name = "accounts"


class AccountUpdateView(UpdateView):
    model = Account
    fields = ["name", "type"]
    template_name = "ledger/account/form.html"
    success_url = reverse_lazy("account_list")


class AccountDeleteView(DeleteView):
    model = Account
    template_name = "ledger/account/confirm_delete.html"
    success_url = reverse_lazy("account_list")


class CompanyCreateView(CreateView):
    model = Company
    fields = ["name"]
    template_name = "ledger/company/form.html"
    success_url = reverse_lazy("company_list")


class CompanyListView(ListView):
    model = Company
    template_name = "ledger/company/list.html"
    context_object_name = "companies"


class CompanyUpdateView(UpdateView):
    model = Company
    fields = ["name"]
    template_name = "ledger/company/form.html"
    success_url = reverse_lazy("company_list")


class CompanyDeleteView(DeleteView):
    model = Company
    template_name = "ledger/company/confirm_delete.html"
    success_url = reverse_lazy("company_list")


class FiscalPeriodListView(ListView):
    model = FiscalPeriod
    template_name = "ledger/fiscal_period_list.html"
    context_object_name = "fiscal_periods"


class FiscalPeriodCreateView(CreateView):
    model = FiscalPeriod
    fields = ["name", "start_date", "end_date", "is_closed"]
    template_name = "ledger/fiscal_period_form.html"
    success_url = reverse_lazy("fiscal_period_list")


class FiscalPeriodUpdateView(UpdateView):
    model = FiscalPeriod
    fields = ["name", "start_date", "end_date", "is_closed"]
    template_name = "ledger/fiscal_period_form.html"
    success_url = reverse_lazy("fiscal_period_list")


# class FiscalPeriodDeleteView(DeleteView):
#     model = FiscalPeriod
#     template_name = "ledger/fiscal_period_confirm_delete.html"
#     success_url = reverse_lazy("fiscal_period_list")


class JournalEntryListView(ListView):
    model = JournalEntry
    template_name = "ledger/journal_entry/list.html"
    context_object_name = "journal_entries"


class JournalEntryFormMixin:
    """
    JournalEntryCreateView / JournalEntryUpdateView の共通処理を切り出すミックスイン。
    - フォームセットの生成（POST の場合はバインド）
    - バリデーション（個別＋借貸合計の一致チェック）
    - トランザクションを使った保存
    """

    debit_formset_class = DebitFormSet
    credit_formset_class = CreditFormSet

    def get_formsets(self, post_data=None, instance=None):
        """
        フォームセットを取得するユーティリティメソッド。
        Args:
            post_data (QueryDict, optional): POSTデータ。デフォルトはNone。
            instance (JournalEntry, optional): JournalEntryインスタンス。デフォルトはNone。
        Returns:
            tuple: (debit_formset, credit_formset)
        """
        if post_data:
            debit_fs = self.debit_formset_class(post_data, instance=instance)
            credit_fs = self.credit_formset_class(post_data, instance=instance)
        else:
            debit_fs = self.debit_formset_class(instance=instance)
            credit_fs = self.credit_formset_class(instance=instance)
        return debit_fs, credit_fs

    def get_context_data(self, **kwargs):
        """
        コンテキストデータにフォームセットを追加する。
        """
        data = super().get_context_data(**kwargs)
        instance = getattr(self, "object", None) or JournalEntry()
        post = self.request.POST if self.request.method == "POST" else None
        debit_fs, credit_fs = self.get_formsets(post, instance)
        data["debit_formset"] = debit_fs
        data["credit_formset"] = credit_fs

        # 固定資産フォームを追加
        if post:
            data["fixed_asset_form"] = FixedAssetInlineForm(post)
        else:
            data["fixed_asset_form"] = FixedAssetInlineForm()

        return data

    def form_valid(self, form):
        """
        親フォームは commit=False でインスタンスを作成し、フォームセットを先に検証。
        検証OKならトランザクション内で保存。
        """
        context = self.get_context_data()
        instance = form.save(commit=False)
        debit_formset = context.get("debit_formset")
        credit_formset = context.get("credit_formset")
        fixed_asset_form = context.get("fixed_asset_form")

        # フォームセットのバリデーション（早期リターンせず両方チェック）
        debit_valid = debit_formset.is_valid()
        credit_valid = credit_formset.is_valid()

        if not debit_valid:
            print("Debit formset errors:", debit_formset.non_form_errors())
        if not credit_valid:
            print("Credit formset errors:", credit_formset.non_form_errors())

        # どちらかが無効なら早期リターン
        if not (debit_valid and credit_valid):
            return self.form_invalid(form)

        is_register_checked = self.request.POST.get("register_as_fixed_asset") in [
            "on",
            "True",
            "true",
            "1",
        ]

        if is_register_checked:
            if not fixed_asset_form.is_valid():
                return self.form_invalid(form)

        # 借方・貸方合計チェック（フォームセット内で合計を保持している前提）
        total_debit = getattr(debit_formset, "total_amount", Decimal("0.00"))
        total_credit = getattr(credit_formset, "total_amount", Decimal("0.00"))
        if total_debit != total_credit:
            form.add_error(None, ErrorMessages.MESSAGE_0001.value)
            return self.form_invalid(form)

        # トランザクション内で親子を保存
        with transaction.atomic():
            self.object = instance
            self.object.save()
            debit_formset.instance = self.object
            credit_formset.instance = self.object
            debit_formset.save()
            credit_formset.save()

            if not is_register_checked:
                return super().form_valid(form)

            # 固定資産登録処理
            fixed_asset = fixed_asset_form.save(commit=False)
            fixed_asset.acquisition_journal_entry = self.object
            fixed_asset.acquisition_date = self.object.date

            # 取得価額は借方明細の該当勘定科目の金額から取得
            target_account = fixed_asset.account
            debit_amount = Decimal("0")
            for debit in self.object.debits.filter(account=target_account):
                debit_amount += debit.amount

            if debit_amount <= 0:
                # 借方に該当勘定科目の金額がない場合はエラー
                form.add_error(
                    None,
                    f"固定資産登録エラー: 仕訳の借方に勘定科目「{target_account.name}」の金額が存在しません。",
                )
                return self.form_invalid(form)

            fixed_asset.acquisition_cost = debit_amount
            fixed_asset.save()

        return super().form_valid(form)


class JournalEntryCreateView(JournalEntryFormMixin, CreateView):
    model = JournalEntry
    form_class = JournalEntryForm
    template_name = "ledger/journal_entry/form.html"
    success_url = reverse_lazy("journal_entry_list")


class JournalEntryUpdateView(JournalEntryFormMixin, UpdateView):
    model = JournalEntry
    form_class = JournalEntryForm
    template_name = "ledger/journal_entry/form.html"
    success_url = reverse_lazy("journal_entry_list")


class JournalEntryDeleteView(DeleteView):
    model = JournalEntry
    template_name = "ledger/journal_entry/confirm_delete.html"
    success_url = reverse_lazy("journal_entry_list")


class LedgerSelectView(TemplateView):
    """帳票選択ビュー"""

    template_name = "ledger/ledger_select.html"


class GeneralLedgerView(TemplateView):
    """
    特定の勘定科目の総勘定元帳を取得・表示するビュー。
    URL: /ledger/general_ledger/<str:account_name>/
    """

    template_name = (
        "ledger/general_ledger_partial.html"  # 使用するテンプレートファイル名
    )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # URLから勘定科目名を取得
        account_name: str = self.request.GET.get("account_name", "")
        year_month: str = self.request.GET.get("year_month", "")
        if year_month == "":
            # TODO: 指定がない場合は当月をデフォルトにする。将来的には会計期間の選択も必要かもしれない。
            raise ValueError("year_month is required")
        day_range: DayRange = get_month_range(get_year_month_from_string(year_month))
        
        # account_name: str = self.kwargs["account_name"]

        # 1. 勘定科目オブジェクトを取得（存在しない場合は404）
        account: Account = get_object_or_404(Account, name=account_name)
        context["account"] = account

        ledger_rows = get_list_general_ledger_row(account, day_range=day_range)

        context["ledger_entries"] = ledger_rows

        return context
