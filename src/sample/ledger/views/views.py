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

from ledger.models import JournalEntry, Account, Company
from ledger.forms import JournalEntryForm, DebitFormSet, CreditFormSet
from ledger.services import (
    get_all_journal_entries_for_account,
    collect_account_set_from_je,
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

        # フォームセットのバリデーション
        if not (debit_formset.is_valid() and credit_formset.is_valid()):
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

    def _determine_counter_party_name(self, other_accounts: set[Account]) -> str:
        """
        相手勘定科目の名前を決定するユーティリティメソッド。

        Args:
            other_accounts (set[Account]): 対象勘定科目以外の勘定科目のセット

        Returns:
            str: 相手勘定科目の名前
        """
        counter_party_name = ""
        if len(other_accounts) == 1:
            # 相手勘定科目が1つの場合、その名前をセット
            counter_party_name = [acc.name for acc in other_accounts][0]
        elif len(other_accounts) > 1:
            # 相手勘定科目が複数の場合
            counter_party_name = "諸口"
        else:
            # 相手勘定科目が0の場合（例：自己取引、またはデータ不備）
            counter_party_name = "取引エラー"
        return counter_party_name

    def _get_entry_record(
        self, je: JournalEntry, is_debit_entry: bool, counter_party_name: str
    ) -> dict:
        """
        総勘定元帳の1行分のレコードを作成するユーティリティメソッド。

        Args:
            je (JournalEntry): 仕訳エントリ
            is_debit_entry (bool): 対象勘定科目が借方かどうか
            counter_party_name (str): 相手勘定科目の名前

        Returns:
            dict: 総勘定元帳の1行分のデータ
        """
        if is_debit_entry:
            debit_amount = je.prefetched_debits[0].amount
            credit_amount = Decimal("0.00")
            delta_running_balance = debit_amount
        else:
            debit_amount = Decimal("0.00")
            credit_amount = je.prefetched_credits[0].amount
            delta_running_balance = -credit_amount

        entry_extract_running_balance = {
            "date": je.date,
            "summary": je.summary,
            "counter_party": counter_party_name,
            "debit_amount": debit_amount,
            "credit_amount": credit_amount,
        }
        return entry_extract_running_balance, delta_running_balance

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # URLから勘定科目名を取得
        account_name: str =self.request.GET.get("account_name","")
        # account_name: str = self.kwargs["account_name"]

        # 1. 勘定科目オブジェクトを取得（存在しない場合は404）
        account: Account = get_object_or_404(Account, name=account_name)
        context["account"] = account
        target_account_id: int = account.id

        journal_entries: list[JournalEntry] = get_all_journal_entries_for_account(
            account
        )

        ledger_entries = []
        running_balance = Decimal("0.00")

        for je in journal_entries:
            # # 取引に含まれるすべての勘定科目（Accountオブジェクト）を収集
            all_debits: set[Account] = collect_account_set_from_je(
                je, is_debit=True
            )
            all_credits: set[Account] = collect_account_set_from_je(
                je, is_debit=False
            )

            # 当該勘定科目に関連する明細行を特定
            is_debit_entry = target_account_id in {acc.id for acc in all_debits}

            # ターゲット勘定科目を除外した、相手勘定科目のリスト
            if is_debit_entry:
                other_accounts = all_credits
            else:
                other_accounts = all_debits

            counter_party_name = self._determine_counter_party_name(other_accounts)

            # 明細タイプによって借方・貸方金額を決定

            entry_extract_running_balance, delta_running_balance = (
                self._get_entry_record(je, is_debit_entry, counter_party_name)
            )

            running_balance += delta_running_balance

            entry = entry_extract_running_balance | {
                "running_balance": running_balance,
            }

            ledger_entries.append(entry)

        context["ledger_entries"] = ledger_entries

        return context
