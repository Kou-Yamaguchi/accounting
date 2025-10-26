from django.shortcuts import render, get_object_or_404
from django.db.models import F, Value, CharField
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView
from django.urls import reverse_lazy
from django.db import transaction
from decimal import Decimal

from ledger.models import JournalEntry, Account, Debit, Credit
from ledger.forms import JournalEntryForm, DebitFormSet, CreditFormSet


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
        # 親クラスのコンテキストデータを取得
        context = super().get_context_data(**kwargs)

        # URLから勘定科目名を取得
        account_name = self.kwargs["account_name"]

        # 1. 勘定科目オブジェクトを取得（存在しない場合は404）
        account = get_object_or_404(Account, name=account_name)
        context["account"] = account
        target_account_id = account.id

        # 取得した勘定科目に関連する取引の科目の種類を全て取得
        # N+1問題を避けるため、prefetch_relatedを使用して関連オブジェクトを事前に取得
        prefetch_args = ["journal_entry__debits__account", "journal_entry__credits__account"]
        debit_lines = Debit.objects.filter(account_id=target_account_id).prefetch_related(*prefetch_args)
        credit_lines = Credit.objects.filter(account_id=target_account_id).prefetch_related(*prefetch_args)
        all_lines = sorted(
            list(debit_lines) + list(credit_lines), key=lambda x: x.journal_entry.date
        )
        ledger_entries = []
        running_balance = Decimal("0.00")

        for line in all_lines:
            je = line.journal_entry
            # 取引に含まれるすべての勘定科目（Accountオブジェクト）を収集
            all_accounts = set()

            # プリフェッチされたリレーションを利用して勘定科目を収集
            # ここでの .all() はデータベースにクエリを発行せず、メモリ上のプリフェッチデータを利用します。
            for debit in je.debits.all():
                all_accounts.add(debit.account)
            for credit in je.credits.all():
                all_accounts.add(credit.account)

            # ターゲット勘定科目を除外した、相手勘定科目のリスト
            other_accounts = [
                acc for acc in all_accounts if acc.id != target_account_id
            ]

            # 3. 相手勘定科目の決定ロジック (単一 vs 諸口)
            counter_party_name = ""
            if len(other_accounts) == 1:
                # 相手勘定科目が1つの場合、その名前をセット
                counter_party_name = other_accounts[0].name
            elif len(other_accounts) > 1:
                # 相手勘定科目が複数の場合
                counter_party_name = "諸口"
            else:
                # 相手勘定科目が0の場合（例：自己取引、またはデータ不備）
                counter_party_name = "取引エラー"

            # 明細タイプによって借方・貸方金額を決定
            is_debit_entry = isinstance(line, Debit)

            if is_debit_entry:
                running_balance += line.amount
            else:
                running_balance -= line.amount

            entry = {
                "date": je.date,
                "summary": je.summary,
                "counter_party": counter_party_name,
                "debit_amount": line.amount if is_debit_entry else 0,
                "credit_amount": line.amount if not is_debit_entry else 0,
                "running_balance": running_balance,
            }
            ledger_entries.append(entry)

        context["ledger_entries"] = ledger_entries

        return context
