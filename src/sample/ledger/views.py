from decimal import Decimal
from datetime import date, datetime, timedelta
from calendar import monthrange
from dataclasses import dataclass
from itertools import zip_longest
import json

from django.shortcuts import render, get_object_or_404
from django.db.models import F, Q, Value, CharField, Prefetch, Sum
from django.http import HttpResponse
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
from django.core.exceptions import ImproperlyConfigured
from openpyxl import Workbook

from ledger.models import JournalEntry, Account, Entry, Debit, Credit, PurchaseDetail
from ledger.forms import JournalEntryForm, DebitFormSet, CreditFormSet
from ledger.services import (
    decimal_to_int,
    list_decimal_to_int,
    calculate_monthly_balance,
    get_fiscal_range,
    calculate_account_total,
    calc_monthly_sales,
    calc_recent_half_year_sales,
    calc_monthly_profit,
    calc_recent_half_year_profits,
)
from enums.error_messages import ErrorMessages

@dataclass
class YearMonth:
    year: int
    month: int


@dataclass
class ClosingEntry:
    total_purchase: int
    total_returns: int
    net_purchase: int


@dataclass
class PurchaseItem:
    name: str
    quantity: int
    unit_price: int


@dataclass
class PurchaseBookEntry:
    date: date
    company: str
    items: list[PurchaseItem]
    counter_account: str
    is_return: bool
    total_amount: int


@dataclass
class PurchaseBook:
    date: YearMonth
    book_entries: list[PurchaseBookEntry]  # List of PurchaseBookEntry instances
    closing_entry: ClosingEntry = None
    error: str = None


class AccountCreateView(CreateView):
    model = Account
    fields = ["name", "type"]
    template_name = "ledger/account_form.html"
    success_url = reverse_lazy("account_list")


class AccountListView(ListView):
    model = Account
    template_name = "ledger/account_list.html"
    context_object_name = "accounts"


class AccountUpdateView(UpdateView):
    model = Account
    fields = ["name", "type"]
    template_name = "ledger/account_form.html"
    success_url = reverse_lazy("account_list")


class AccountDeleteView(DeleteView):
    model = Account
    template_name = "ledger/account_confirm_delete.html"
    success_url = reverse_lazy("account_list")


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


class LedgerSelectView(TemplateView):
    """帳票選択ビュー"""
    template_name = "ledger/ledger_select.html"


class GeneralLedgerView(TemplateView):
    """
    特定の勘定科目の総勘定元帳を取得・表示するビュー。
    URL: /ledger/general_ledger/<str:account_name>/
    """

    template_name = "ledger/general_ledger_partial.html"  # 使用するテンプレートファイル名

    def _get_all_journal_entries_for_account(self, account: Account) -> list[JournalEntry]:
        """
        指定された勘定科目に関連する全ての仕訳を取得するユーティリティメソッド。
        N+1問題を避けるため、prefetch_relatedを使用して関連オブジェクトを事前に取得

        Args:
            account (Account): 対象の勘定科目

        Returns:
            QuerySet: 指定された勘定科目に関連する全ての仕訳のクエリセット
        """
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
        return journal_entries

    def _collect_account_set_from_je(self, je: JournalEntry, is_debit: bool) -> set[Account]:
        """
        取引に含まれる勘定科目をEntryごとに収集するユーティリティメソッド。
        """
        if is_debit:
            return set(debit.account for debit in je.prefetched_debits)
        else:
            return set(credit.account for credit in je.prefetched_credits)

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

    def _get_entry_record(self, je: JournalEntry, is_debit_entry: bool, counter_party_name: str) -> dict:
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
        account_name: str = self.kwargs["account_name"]

        # 1. 勘定科目オブジェクトを取得（存在しない場合は404）
        account: Account = get_object_or_404(Account, name=account_name)
        context["account"] = account
        target_account_id: int = account.id

        journal_entries: list[JournalEntry] = self._get_all_journal_entries_for_account(account)

        ledger_entries = []
        running_balance = Decimal("0.00")

        for je in journal_entries:
            # # 取引に含まれるすべての勘定科目（Accountオブジェクト）を収集
            all_debits: set[Account] = self._collect_account_set_from_je(je, is_debit=True)
            all_credits: set[Account] = self._collect_account_set_from_je(je, is_debit=False)

            # 当該勘定科目に関連する明細行を特定
            is_debit_entry = target_account_id in {acc.id for acc in all_debits}

            # ターゲット勘定科目を除外した、相手勘定科目のリスト
            if is_debit_entry:
                other_accounts = all_credits
            else:
                other_accounts = all_debits

            counter_party_name = self._determine_counter_party_name(other_accounts)

            # 明細タイプによって借方・貸方金額を決定

            entry_extract_running_balance, delta_running_balance = self._get_entry_record(
                je, is_debit_entry, counter_party_name
            )

            running_balance += delta_running_balance

            entry = entry_extract_running_balance | {
                "running_balance": running_balance,
            }

            ledger_entries.append(entry)

        context["ledger_entries"] = ledger_entries

        return context


@dataclass
class TrialBalanceEntry:
    name: str
    type: str
    total: Decimal


class TrialBalanceView(TemplateView):
    """
    試算表ビュー
    該当年度の試算表を表示する。
    URL: /ledger/trial_balance_by_year/
    """
    template_name = "ledger/trial_balance_partial.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # HACK: excel出力時と同じロジックなので共通化したい
        year = int(self.request.GET.get("year"))

        start_date, end_date = get_fiscal_range(year)

        # 全勘定科目を取得
        accounts = Account.objects.all().order_by("type", "name")

        trial_balance_data: list[TrialBalanceEntry] = []

        total_debits = Decimal("0.00")
        total_credits = Decimal("0.00")

        for account in accounts:
            total = calculate_account_total(account, start_date, end_date)

            # html表示時特有の処理 ===========================
            trial_balance_data_entry = TrialBalanceEntry(
                name=account.name,
                type=account.type,
                total=total,
            )

            trial_balance_data.append(trial_balance_data_entry)

            if account.type in ['asset', 'expense']:
                total_debits += total
            else:
                total_credits += total
        context["total_debits"] = total_debits
        context["total_credits"] = total_credits
        context["year"] = year
        context["trial_balance_data"] = trial_balance_data

        return context


class ExportTrialBalanceView(View):
    """試算表エクスポートビュー"""
    def get(self, request, *args, **kwargs):
        wb = Workbook()
        ws = wb.active

        ws.append(["借方", "勘定科目", "貸方"])

        year = int(self.request.GET.get("year"))
        start_date, end_date = get_fiscal_range(year)

        total_debits = Decimal("0.00")
        total_credits = Decimal("0.00")

        accounts = Account.objects.all().order_by("type", "name")

        for account in accounts:
            total = calculate_account_total(account, start_date, end_date)

            # エクスポート時特有の処理 ===========================
            if account.type in ['asset', 'expense']:
                ws.append([total, account.name, ""])
                total_debits += total
            else:
                ws.append(["", account.name, total])
                total_credits += total

        ws.append([total_debits, "合計", total_credits])

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename=trial_balance_{year}.xlsx'
        wb.save(response)
        return response


class BalanceSheetView(TemplateView):
    """貸借対照表ビュー"""
    template_name = "ledger/balance_sheet_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 貸借対照表のデータ取得ロジックをここに実装
        year = int(self.request.GET.get("year", datetime.now().year))
        context["year"] = year
        start_date, end_date = get_fiscal_range(year)

        total_debits = Decimal("0.00")
        total_credits = Decimal("0.00")

        for account_type in ['asset', 'liability', 'equity']:
            accounts = Account.objects.filter(type=account_type).order_by("name")
            account_data = []

            for account in accounts:
                total = calculate_account_total(account, start_date, end_date)

                account_data.append({
                    "account": account,
                    "type": account_type,
                    "balance": total,
                })

            context[f"{account_type}_accounts"] = account_data

            total_debits += sum(item["balance"] for item in account_data if item["type"] == "asset")
            total_credits += sum(item["balance"] for item in account_data if item["type"] in ["liability", "equity"])
        context["total_debits"] = total_debits
        context["total_credits"] = total_credits


        # HACK: 貸借差額を繰越利益剰余金or繰越欠損金を直接計算している
        # 本来は損益振替・資本振替をした決算整理仕訳を経由して反映させるべき
        if total_debits > total_credits:
            context["rebf"] = total_debits - total_credits
        else:
            context["debfb"] = total_credits - total_debits

        # htmlのtableで貸借対照表を表示するための転置処理
        debit_columns = context['asset_accounts']
        credit_columns = context['liability_accounts'] + context['equity_accounts']

        paired_columns = [(debit, credit) for debit, credit in zip_longest(debit_columns, credit_columns, fillvalue=None)]

        context['paired_columns'] = paired_columns

        return context


class ExportBalanceSheetView(View):
    """貸借対照表エクスポートビュー"""
    def get(self, request, *args, **kwargs):
        # TODO: エクスポート処理の実装
        pass


class ProfitAndLossView(TemplateView):
    """損益計算書ビュー"""
    template_name = "ledger/profit_and_loss_table.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 損益計算書のデータ取得ロジックをここに実装
        year = int(self.request.GET.get("year", datetime.now().year))
        context["year"] = year
        start_date, end_date = get_fiscal_range(year)

        total_revenue = Decimal("0.00")
        total_expense = Decimal("0.00")

        for account_type in ['revenue', 'expense']:
            accounts = Account.objects.filter(type=account_type).order_by("name")
            account_data = []

            for account in accounts:
                total = calculate_account_total(account, start_date, end_date)

                account_data.append({
                    "account": account,
                    "type": account_type,
                    "balance": total,
                })

            context[f"{account_type}_accounts"] = account_data

            if account_type == 'revenue':
                total_revenue += sum(item["balance"] for item in account_data)
            else:
                total_expense += sum(item["balance"] for item in account_data)

        context["total_revenue"] = total_revenue
        context["total_expense"] = total_expense

        # HACK: 当期純利益・純損失を直接計算している
        # 本来は損益振替仕訳を経由して反映させるべき
        if total_revenue >= total_expense:
            context["net_income"] = total_revenue - total_expense
        else:
            context["net_loss"] = total_expense - total_revenue

        # htmlのtableで貸借対照表を表示するための転置処理
        debit_columns = context["expense_accounts"]
        credit_columns = context["revenue_accounts"]

        paired_columns = [
            (debit, credit)
            for debit, credit in zip_longest(
                debit_columns, credit_columns, fillvalue=None
            )
        ]

        context["paired_columns"] = paired_columns

        return context


class ExportProfitAndLossView(View):
    """損益計算書エクスポートビュー"""
    def get(self, request, *args, **kwargs):
        # TODO: エクスポート処理の実装
        pass


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
                ErrorMessages.MESSAGE_0002.value
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


class PurchaseBookView(TemplateView):
    """仕入帳ビュー"""
    template_name = "ledger/purchase_book.html"

    def _parse_year_month(self):
        try:
            year = int(self.kwargs.get("year", datetime.now().year))
            month = int(self.kwargs.get("month", datetime.now().month))
        except (ValueError, TypeError):
            now = datetime.now()
            year, month = now.year, now.month
        return YearMonth(year=year, month=month)

    def get_context_data(self, **kwargs):
        """仕入帳データを取得してコンテキストに追加する。

        Args:
            year (int): 対象年
            month (int): 対象月

        Returns:
            PurchaseBook: 仕入帳データのコンテキスト
        """
        context = super().get_context_data(**kwargs)
        target_year_month = self._parse_year_month()

        # 勘定科目「仕入」のIDを取得（事前にAccountテーブルに「仕入」を登録しておく）
        try:
            purchase_account = Account.objects.get(name="仕入")
        except Account.DoesNotExist:
            context["error"] = "勘定科目「仕入」が見つかりません。"
            return context

        # 1. JournalEntryの取得とprefetch_related
        # 勘定科目の片方が「仕入」となっている取引を抽出
        # 仕入は費用なので、増加（純仕入）は借方（Debit）、減少（仕入戻し・値引）は貸方（Credit）

        # Prefetchオブジェクトを使用して、関連データを効率的に取得
        credit_prefetch = Prefetch(
            "credits",
            queryset=Credit.objects.select_related("account"),
            to_attr="prefetched_credits",
        )
        debit_prefetch = Prefetch(
            "debits",
            queryset=Debit.objects.select_related("account"),
            to_attr="prefetched_debits",
        )
        # purchase_prefetch = Prefetch(
        #     "purchase_details",
        #     queryset=PurchaseDetail.objects.select_related("item"),
        #     to_attr="prefetched_purchase_details",
        # )

        # 「仕入」勘定を含む取引、かつ対象年月内の取引をフィルタリング
        # Qオブジェクトを使ってOR検索 (仕入が借方 OR 仕入が貸方)
        purchase_journals = (
            JournalEntry.objects.filter(
                Q(debits__account=purchase_account)
                | Q(credits__account=purchase_account),
                date__year=target_year_month.year,
                date__month=target_year_month.month,
            )
            .prefetch_related(
                credit_prefetch,
                debit_prefetch,
                "purchase_details",
                "company",  # 取引先情報も取得
            )
            .order_by("date")
        )

        # 5. 整形済みリストの作成と 6. 合計の計算
        book_entries: list[PurchaseBookEntry] = []
        total_purchase = 0  # 総仕入高
        total_returns_allowances = 0  # 仕入値引戻し高 (純額で計算)

        # 仕入戻し/値引の勘定科目を定義 (日商簿記3級では「仕入」勘定を直接減らす処理が多いですが、
        # 仕訳の**相手勘定**の名称として仕訳摘要を生成するため、今回は借方の相手科目が純仕入、貸方の相手科目が戻し/値引と判断します。
        # または、仕入戻し等の場合はCredit/Debitテーブルの相手勘定を判断します)

        for entry in purchase_journals:
            # 仕入の取引金額と、仕入の相手勘定を特定
            is_purchase_increase = any(
                d.account_id == purchase_account.id for d in entry.prefetched_debits
            )
            is_purchase_decrease = any(
                c.account_id == purchase_account.id for c in entry.prefetched_credits
            )

            # 仕入の増減と金額の特定
            if is_purchase_increase:
                # 純仕入 (仕入が借方)
                amount = sum(
                    d.amount
                    for d in entry.prefetched_debits
                    if d.account_id == purchase_account.id
                )
                # 仕入の相手勘定（貸方）を特定。ここでは買掛金など1つに絞れる前提
                counter_entry = next((c for c in entry.prefetched_credits), None)
                transaction_type = "仕入"
                total_purchase += amount
            elif is_purchase_decrease:
                # 仕入戻し・値引 (仕入が貸方)
                amount = sum(
                    c.amount
                    for c in entry.prefetched_credits
                    if c.account_id == purchase_account.id
                )
                # 仕入の相手勘定（借方）を特定。ここでは買掛金など1つに絞れる前提
                counter_entry = next((d for d in entry.prefetched_debits), None)
                transaction_type = "仕入引戻し"
                total_returns_allowances += amount  # 戻し・値引として加算
            else:
                continue  # 万一「仕入」がない場合はスキップ

            counter_account_name = (
                counter_entry.account.name if counter_entry else "不明"
            )
            company_name = entry.company.name if entry.company else "不明"

            # 2. 取引ごとの摘要文字列を生成 & 3. 内訳フィールドの計算
            total_detail_amount = 0

            # 1行目: 会社名と相手勘定
            # 摘要の1行目は会社名と「掛」「掛戻し」など
            abstract_line1 = f"{company_name} "
            if transaction_type == "仕入":
                # 買掛金/現金など
                if counter_account_name == "買掛金":
                    abstract_line1 += "掛"
                elif counter_account_name == "現金":
                    abstract_line1 += "現金払"
                # その他、相手勘定名で表現
                else:
                    abstract_line1 += f"（{counter_account_name}）"
            elif transaction_type == "仕入引戻し":
                if counter_account_name == "買掛金":
                    abstract_line1 += "掛戻し"
                else:
                    abstract_line1 += f"（{counter_account_name}戻）"

            # 内訳明細の作成
            # 項目は空白で初期化
            purchase_detail = PurchaseBookEntry(
                date=entry.date,
                company=company_name,
                items=[],
                counter_account=counter_account_name,
                is_return=(transaction_type == "仕入引戻し"),
                total_amount=amount,
            )

            # 商品の数だけ内訳行を追加
            for detail in entry.purchase_details.all():
                item_name = detail.item.name if detail.item else "不明商品"
                detail_amount = detail.quantity * detail.unit_price

                purchase_item = PurchaseItem(
                    name=item_name,
                    quantity=detail.quantity,
                    unit_price=detail.unit_price,
                )

                purchase_detail.items.append(purchase_item)

                total_detail_amount += detail_amount

            # 4. 金額の確認 (仕訳金額と内訳の合計が一致することを確認)
            if round(total_detail_amount) != round(amount):
                # 会計上のエラーなのでログ出力などが望ましいが、今回はデータ表示を優先
                print(
                    f"Warning: Journal ID {entry.id} - Detail total ({total_detail_amount}) does not match entry amount ({amount})."
                )
                context["error"] = (
                    f"仕訳ID {entry.id} の内訳金額合計が仕訳金額と一致しません。"
                )

            # 整形データの作成
            book_entries.append(purchase_detail)

        # 6. 純仕入高の計算
        net_purchase = total_purchase - total_returns_allowances

        purchase_book = PurchaseBook(
            date=target_year_month,
            book_entries=book_entries,
            closing_entry=ClosingEntry(
                total_purchase=total_purchase,
                total_returns=total_returns_allowances,
                net_purchase=net_purchase,
            ),
        )

        # テンプレートに渡すコンテキストに追加
        context["purchase_book"] = purchase_book

        return context


class DashboardView(TemplateView):
    """ダッシュボードビュー"""
    template_name = "ledger/dashboard/page.html"

    PARTIALS = {
        "sales_chart": "ledger/dashboard/sales_chart.html",
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current_year = datetime.now().year
        current_month = datetime.now().month
        context["monthly_sales"] = calc_monthly_sales(current_year, current_month)
        # TODO: 損失の場合，絶対値+赤文字+損失で表示する
        context["monthly_profit"] = calc_monthly_profit(current_year, current_month)

        # 売上・利益推移グラフ用データ
        # HACK: 売上・利益推移グラフ用データのJSONシリアライズ処理
        labels, sales_data, profit_data = self._get_sales_chart_data()
        context["sales_chart_labels"] = json.dumps(labels)
        context["sales_chart_sales_data"] = json.dumps(sales_data)
        context["sales_chart_profit_data"] = json.dumps(profit_data)
        return context

    def get(self, request, *args, **kwargs):
        """AJAXリクエストに対してJSONデータを返す処理を追加"""
        partial = request.GET.get("partial")
        span = request.GET.get("span", "6months")
        # 部分テンプレートのレンダリング

        if request.headers.get("HX-Request") and partial in self.PARTIALS:
            context = self.get_context_data(**kwargs)
            return render(request, self.PARTIALS[partial], context)
        return super().get(request, *args, **kwargs)

    def _get_sales_chart_data(self, span: int=6) -> tuple[list[str], list[int], list[int]]:
        labels = [
            f"{(datetime.now() - timedelta(days=30*i)).strftime('%Y-%m')}"
            for i in range(span - 1, -1, -1)
        ]
        sales_data = list_decimal_to_int(calc_recent_half_year_sales())
        profit_data = list_decimal_to_int(calc_recent_half_year_profits())
        return labels, sales_data, profit_data
