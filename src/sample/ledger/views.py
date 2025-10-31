from django.shortcuts import render, get_object_or_404
from django.db.models import F, Q, Value, CharField, Prefetch
from django.views.generic import (
    ListView,
    CreateView,
    UpdateView,
    DeleteView,
    TemplateView,
)
from django.urls import reverse_lazy
from django.db import transaction
from decimal import Decimal
from datetime import date, datetime, timedelta
from calendar import monthrange
from django.core.exceptions import ImproperlyConfigured

from ledger.models import JournalEntry, Account, Debit, Credit
from ledger.forms import JournalEntryForm, DebitFormSet, CreditFormSet
from ledger.services import calculate_monthly_balance


class JournalEntryListView(ListView):
    model = JournalEntry
    template_name = "ledger/journal_entry_list.html"
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
        if post_data:
            debit_fs = self.debit_formset_class(post_data, instance=instance)
            credit_fs = self.credit_formset_class(post_data, instance=instance)
        else:
            debit_fs = self.debit_formset_class(instance=instance)
            credit_fs = self.credit_formset_class(instance=instance)
        return debit_fs, credit_fs

    def get_context_data(self, **kwargs):
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
            form.add_error(None, "借方合計と貸方合計は一致する必要があります。")
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
    template_name = "ledger/journal_entry_form.html"
    success_url = reverse_lazy("journal_entry_list")


class JournalEntryUpdateView(JournalEntryFormMixin, UpdateView):
    model = JournalEntry
    form_class = JournalEntryForm
    template_name = "ledger/journal_entry_form.html"
    success_url = reverse_lazy("journal_entry_list")


class JournalEntryDeleteView(DeleteView):
    model = JournalEntry
    template_name = "ledger/journal_entry_confirm_delete.html"
    success_url = reverse_lazy("journal_entry_list")


class GeneralLedgerView(TemplateView):
    """
    特定の勘定科目の総勘定元帳を取得・表示するビュー。
    URL: /ledger/<str:account_name>/
    """

    template_name = "ledger/general_ledger.html"  # 使用するテンプレートファイル名

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # URLから勘定科目名を取得
        account_name = self.kwargs["account_name"]

        # 1. 勘定科目オブジェクトを取得（存在しない場合は404）
        account = get_object_or_404(Account, name=account_name)
        context["account"] = account
        target_account_id = account.id

        # 取得した勘定科目に関連する取引の科目の種類を全て取得
        # N+1問題を避けるため、prefetch_relatedを使用して関連オブジェクトを事前に取得
        journal_entries = (
            JournalEntry.objects.filter(
                Q(debits__account=account) | Q(credits__account=account)
            )
            .distinct()
            .order_by("date", "pk")
            .prefetch_related(
                Prefetch(
                    "debits",
                    queryset=Debit.objects.select_related("account"),
                    to_attr="prefetched_debits",
                ),
                Prefetch(
                    "credits",
                    queryset=Credit.objects.select_related("account"),
                    to_attr="prefetched_credits",
                ),
            )
        )

        ledger_entries = []
        running_balance = Decimal("0.00")

        for je in journal_entries:
            # 取引に含まれるすべての勘定科目（Accountオブジェクト）を収集
            all_debits = set()
            all_credits = set()

            # プリフェッチされたリレーションを利用して勘定科目を収集
            all_debits = set(debit.account for debit in je.prefetched_debits)
            all_credits = set(credit.account for credit in je.prefetched_credits)

            # 当該勘定科目に関連する明細行を特定
            is_debit_entry = target_account_id in {acc.id for acc in all_debits}

            # ターゲット勘定科目を除外した、相手勘定科目のリスト
            if is_debit_entry:
                other_accounts = all_credits
            else:
                other_accounts = all_debits

            # 3. 相手勘定科目の決定ロジック (単一 vs 諸口)
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

            # 明細タイプによって借方・貸方金額を決定

            if is_debit_entry:
                debit_amount = je.prefetched_debits[0].amount
                credit_amount = Decimal("0.00")
                running_balance += debit_amount
            else:
                debit_amount = Decimal("0.00")
                credit_amount = je.prefetched_credits[0].amount
                running_balance -= credit_amount

            entry = {
                "date": je.date,
                "summary": je.summary,
                "counter_party": counter_party_name,
                "debit_amount": debit_amount,
                "credit_amount": credit_amount,
                "running_balance": running_balance,
            }
            ledger_entries.append(entry)

        context["ledger_entries"] = ledger_entries

        return context


class AbstractCashBookView(TemplateView):
    """
    出納帳の共通処理を提供する抽象ビュー。
    サブクラスは TARGET_ACCOUNT_NAME を設定するだけで利用可能。
    戻り値のコンテキスト:
      - book_data: [{ "date", "summary", "income", "expense", "balance" }, ...]
      - account_name, current_month, next_month_carryover, error_message (必要時)
    """

    template_name = "ledger/cash_book.html"
    TARGET_ACCOUNT_NAME = None  # サブクラスで設定すること

    def _parse_year_month(self):
        try:
            year = int(self.kwargs.get("year", datetime.now().year))
            month = int(self.kwargs.get("month", datetime.now().month))
        except (ValueError, TypeError):
            now = datetime.now()
            year, month = now.year, now.month
        return year, month

    def get_context_data(self, **kwargs):
        if not self.TARGET_ACCOUNT_NAME:
            raise ImproperlyConfigured(
                "TARGET_ACCOUNT_NAME をサブクラスで設定してください。"
            )

        context = super().get_context_data(**kwargs)
        year, month = self._parse_year_month()

        # サービスに処理を委譲（サービスはdictで data/ending_balance または error を返す想定）
        result = calculate_monthly_balance(self.TARGET_ACCOUNT_NAME, year, month)

        if "error" in result:
            context["error_message"] = result["error"]
            context["book_data"] = []
            context["next_month_carryover"] = None
        else:
            # services.calculate_monthly_balance の返却スキーマに合わせて取り出す
            context["book_data"] = result.get("data", [])
            context["next_month_carryover"] = result.get("ending_balance")

        context["account_name"] = self.TARGET_ACCOUNT_NAME
        context["current_month"] = datetime(year, month, 1)
        return context


class CashBookView(AbstractCashBookView):
    """現金出納帳"""

    TARGET_ACCOUNT_NAME = "現金"


class CurrentAccountCashBookView(AbstractCashBookView):
    """当座預金出納帳"""

    TARGET_ACCOUNT_NAME = "当座預金"


class PettyCashBookView(AbstractCashBookView):
    """小口現金出納帳"""

    TARGET_ACCOUNT_NAME = "小口現金"
