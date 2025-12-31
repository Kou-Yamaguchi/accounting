from decimal import Decimal
from datetime import date, datetime, timedelta
from calendar import monthrange
from dataclasses import dataclass
from itertools import zip_longest
from operator import attrgetter
import json

from django.shortcuts import render, get_object_or_404
from django.db.models import F, Q, Value, CharField, Prefetch, Sum
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
from django.core.exceptions import ImproperlyConfigured
from openpyxl import Workbook

from ledger.models import JournalEntry, Account, Company, Entry, Debit, Credit, PurchaseDetail
from ledger.forms import JournalEntryForm, DebitFormSet, CreditFormSet
from ledger.services import (
    YearMonth,
    get_last_year_month,
    decimal_to_int,
    list_decimal_to_int,
    calculate_monthly_balance,
    get_fiscal_range,
    get_month_range,
    DayRange,
    get_all_journal_entries_for_account,
    collect_account_set_from_je,
    calculate_account_total,
    calc_monthly_sales,
    calc_recent_half_year_sales,
    calc_monthly_profit,
    calc_recent_half_year_profits,
    get_company_sales_last_month,
    prepare_pareto_chart_data,
)
from enums.error_messages import ErrorMessages


def get_all_account_objects() -> list[Account]:
    """全ての勘定科目オブジェクトを取得するユーティリティ関数。"""
    return list(Account.objects.all().order_by("type", "name"))


def get_account_object_by_type(account_type: str) -> list[Account]:
    """指定されたタイプの勘定科目オブジェクトを取得するユーティリティ関数。

    Args:
        account_type (str): 勘定科目タイプ（例："asset", "liability", "equity", "revenue", "expense"）

    Returns:
        list[Account]: 指定されたタイプのAccountオブジェクトのリスト
    """
    return list(Account.objects.filter(type=account_type).order_by("name"))


@dataclass
class AccountWithTotal:
    account_object: Account
    total_amount: Decimal


def calc_each_account_totals(
    day_range: DayRange, pop_list: list[str] = None
) -> list[AccountWithTotal]:
    """全ての勘定科目の合計金額を計算するユーティリティ関数。

    Args:
        day_range (DayRange): 期間開始日と終了日を含むDayRangeオブジェクト
        pop_list (list[str]|None): 対象とする勘定科目タイプのリスト。デフォルトはNone（全ての勘定科目を対象）

    Returns:
        list[AccountWithTotal]: List of AccountWithTotal instances
    """
    if pop_list is None:
        accounts = get_all_account_objects()
    else:
        accounts = [acc for acc in get_all_account_objects() if acc.type in pop_list]

    account_totals: list[AccountWithTotal] = [
        AccountWithTotal(account, calculate_account_total(account, day_range))
        for account in accounts
    ]
    return account_totals


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
        account_name: str = self.kwargs["account_name"]

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


@dataclass
class FinancialStatementEntry:
    """財務諸表エントリの共通データクラス"""

    name: str
    type: str
    total: Decimal


class FinancialStatementView(View):
    """財務諸表の共通処理を提供する抽象ビュー

    サブクラスは以下の属性を設定する必要があります：
    - template_name: テンプレートファイル名
    - ACCOUNT_TYPES: 対象とする勘定科目タイプのリスト
    - DEBIT_TYPES: 借方側の勘定タイプのリスト
    - CREDIT_TYPES: 貸方側の勘定タイプのリスト
    """

    template_name = None
    ACCOUNT_TYPES = []  # サブクラスで設定必須
    DEBIT_TYPES = []  # サブクラスで設定必須
    CREDIT_TYPES = []  # サブクラスで設定必須

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """GETリクエストハンドラ。
        Args:
            request (HttpRequest): HTTPリクエストオブジェクト

        Returns:
            HttpResponse: HTTPレスポンスオブジェクト
        """
        year = int(request.GET.get("year", datetime.now().year))
        output_format = request.GET.get("format", "html")
        data_dict = self.get_data(year)

        if output_format == "xlsx":
            return self._export_as_xlsx(data_dict, year)

        context = self.build_context(year, data_dict)
        return self._export_as_html(request, self.template_name, context)

    def get_data(self, year: int) -> dict:
        """指定された年度の財務諸表データを取得するユーティリティメソッド。

        Args:
            year (int): 対象年度

        Returns:
            dict: データ辞書（entries, debit_accounts, credit_accounts, total_debits, total_creditsを含む）
        """
        fiscal_range: DayRange = get_fiscal_range(year)
        account_totals: list[AccountWithTotal] = calc_each_account_totals(
            fiscal_range, self.ACCOUNT_TYPES
        )
        entries: list[FinancialStatementEntry] = self._create_entries(account_totals)

        debit_accounts, credit_accounts = self._split_by_type(entries)
        total_debits, total_credits = self._get_total_debits_credits(
            debit_accounts, credit_accounts
        )

        return {
            "entries": entries,
            "debit_accounts": debit_accounts,
            "credit_accounts": credit_accounts,
            "total_debits": total_debits,
            "total_credits": total_credits,
        }

    def build_context(self, year: int, data_dict: dict) -> dict:
        """基本的なコンテキスト構築。サブクラスでオーバーライド可能。

        Args:
            year (int): 対象年度
            data_dict (dict): get_dataから返されたデータ辞書

        Returns:
            dict: テンプレートに渡すコンテキストデータ
        """
        context = {
            "year": year,
            "total_debits": data_dict["total_debits"],
            "total_credits": data_dict["total_credits"],
            "paired_columns": self.get_transpose_columns(
                data_dict["debit_accounts"], data_dict["credit_accounts"]
            ),
        }
        # サブクラス固有の処理を追加
        self.add_specific_context(context, data_dict)
        return context

    def add_specific_context(self, context: dict, data_dict: dict) -> None:
        """サブクラス固有のコンテキスト追加。サブクラスで実装。

        Args:
            context (dict): コンテキストデータ（この関数内で直接変更される）
            data_dict (dict): get_dataから返されたデータ辞書
        """
        pass

    def _split_by_type(
        self, entries: list[FinancialStatementEntry]
    ) -> tuple[list[FinancialStatementEntry], list[FinancialStatementEntry]]:
        """勘定タイプで借方・貸方に分割するユーティリティメソッド。

        Args:
            entries (list[FinancialStatementEntry]): 財務諸表エントリのリスト

        Returns:
            tuple: (借方勘定リスト, 貸方勘定リスト)
        """
        debit_accounts = [e for e in entries if e.type in self.DEBIT_TYPES]
        credit_accounts = [e for e in entries if e.type in self.CREDIT_TYPES]
        return debit_accounts, credit_accounts

    def get_transpose_columns(
        self,
        debit_accounts: list[FinancialStatementEntry],
        credit_accounts: list[FinancialStatementEntry],
    ) -> list[tuple]:
        """財務諸表の表示用に列を転置するユーティリティメソッド。

        Args:
            debit_accounts (list[FinancialStatementEntry]): 借方勘定リスト
            credit_accounts (list[FinancialStatementEntry]): 貸方勘定リスト

        Returns:
            list[tuple]: 転置された列のリスト
        """
        transposed = [
            (debit, credit)
            for debit, credit in zip_longest(
                debit_accounts,
                credit_accounts,
                fillvalue=None,
            )
        ]
        return transposed

    def _get_total_debits_credits(
        self,
        debit_accounts: list[FinancialStatementEntry],
        credit_accounts: list[FinancialStatementEntry],
    ) -> tuple[Decimal, Decimal]:
        """借方・貸方合計を計算するユーティリティメソッド。

        Args:
            debit_accounts (list[FinancialStatementEntry]): 借方勘定リスト
            credit_accounts (list[FinancialStatementEntry]): 貸方勘定リスト

        Returns:
            tuple[Decimal, Decimal]: (借方合計, 貸方合計)
        """
        total_debits = sum(item.total for item in debit_accounts)
        total_credits = sum(item.total for item in credit_accounts)
        return total_debits, total_credits

    def _create_entries(
        self, account_totals: list[AccountWithTotal]
    ) -> list[FinancialStatementEntry]:
        """勘定科目合計リストから財務諸表エントリを生成するユーティリティメソッド。

        Args:
            account_totals (list[AccountWithTotal]): 勘定科目合計のリスト

        Returns:
            list[FinancialStatementEntry]: 財務諸表エントリのリスト
        """
        return [
            FinancialStatementEntry(
                account_total.account_object.name,
                account_total.account_object.type,
                account_total.total_amount,
            )
            for account_total in account_totals
        ]

    def _export_as_html(
        self, request: HttpRequest, template_name: str, context: dict
    ) -> HttpResponse:
        """HTML形式でエクスポートするユーティリティメソッド。

        Args:
            request (HttpRequest): HTTPリクエストオブジェクト
            template_name (str): テンプレート名
            context (dict): コンテキストデータ

        Returns:
            HttpResponse: HTMLレスポンス
        """
        return render(request, template_name, context)

    def _export_as_xlsx(self, data_dict: dict, year: int) -> HttpResponse:
        """Excel形式でエクスポートするユーティリティメソッド。

        Args:
            data_dict (dict): get_dataから返されたデータ辞書
            year (int): 対象年度

        Returns:
            HttpResponse: ExcelファイルのHTTPレスポンス
        """
        insert_data = self._form_to_xlsx_rows(data_dict)

        wb = Workbook()
        ws = wb.active
        self._write_xlsx_header(ws)
        self._write_xlsx_data(ws, insert_data)

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        filename = self._get_xlsx_filename(year)
        response["Content-Disposition"] = f"attachment; filename={filename}"
        wb.save(response)
        return response

    def _write_xlsx_header(self, ws) -> None:
        """Excelのヘッダー行を書き込むユーティリティメソッド。サブクラスでオーバーライド可能。

        Args:
            ws: ワークシートオブジェクト
        """
        ws.append(["借方", "勘定科目", "貸方"])

    def _write_xlsx_data(self, ws, insert_data: list[list]) -> None:
        """Excelにデータを書き込むユーティリティメソッド。

        Args:
            ws: ワークシートオブジェクト
            insert_data (list[list]): 書き込むデータのリスト
        """
        for row in insert_data:
            ws.append(row)

    def _form_to_xlsx_rows(self, data_dict: dict) -> list[list]:
        """データ辞書をExcel書き込み用の行データに変換するユーティリティメソッド。
        サブクラスでオーバーライド可能。

        Args:
            data_dict (dict): get_dataから返されたデータ辞書

        Returns:
            list[list]: Excelに書き込む行データのリスト
        """
        insert_data = []
        for entry in data_dict["entries"]:
            if entry.type in self.DEBIT_TYPES:
                insert_data.append([entry.total, entry.name, ""])
            else:
                insert_data.append(["", entry.name, entry.total])

        # 合計行を追加
        insert_data.append(
            [data_dict["total_debits"], "合計", data_dict["total_credits"]]
        )
        return insert_data

    def _get_xlsx_filename(self, year: int) -> str:
        """Excelファイル名を生成するユーティリティメソッド。サブクラスでオーバーライド可能。

        Args:
            year (int): 対象年度

        Returns:
            str: ファイル名
        """
        # サブクラス名からファイル名を生成（例: BalanceSheetView -> balance_sheet）
        class_name = self.__class__.__name__.replace("View", "")
        # キャメルケースをスネークケースに変換
        import re

        filename_base = re.sub(r"(?<!^)(?=[A-Z])", "_", class_name).lower()
        return f"{filename_base}_{year}.xlsx"


class TrialBalanceView(FinancialStatementView):
    """
    試算表ビュー
    該当年度の試算表を表示する。
    URL: /ledger/trial_balance_by_year/
    """

    template_name = "ledger/trial_balance_partial.html"
    ACCOUNT_TYPES = None  # 全ての勘定科目を対象
    DEBIT_TYPES = ["asset", "expense"]
    CREDIT_TYPES = ["liability", "equity", "revenue"]

    def build_context(self, year: int, data_dict: dict) -> dict:
        """試算表用のコンテキスト構築。

        Args:
            year (int): 対象年度
            data_dict (dict): get_dataから返されたデータ辞書

        Returns:
            dict: テンプレートに渡すコンテキストデータ
        """
        context = {
            "total_debits": data_dict["total_debits"],
            "total_credits": data_dict["total_credits"],
            "year": year,
            "trial_balance_data": data_dict["entries"],
        }
        return context

    def _get_xlsx_filename(self, year: int) -> str:
        """Excelファイル名を生成するユーティリティメソッド。

        Args:
            year (int): 対象年度

        Returns:
            str: ファイル名
        """
        return f"trial_balance_{year}.xlsx"


class BalanceSheetView(FinancialStatementView):
    """貸借対照表ビュー"""

    template_name = "ledger/balance_sheet_table.html"
    ACCOUNT_TYPES = ["asset", "liability", "equity"]
    DEBIT_TYPES = ["asset"]
    CREDIT_TYPES = ["liability", "equity"]

    def add_specific_context(self, context: dict, data_dict: dict) -> None:
        """貸借対照表固有のコンテキスト追加。

        Args:
            context (dict): コンテキストデータ
            data_dict (dict): get_dataから返されたデータ辞書
        """
        # 貸借対照表データを追加
        context["balance_sheet_data"] = data_dict["entries"]

        # HACK: 貸借差額を繰越利益剰余金or繰越欠損金を直接計算している
        # 本来は損益振替・資本振替をした決算整理仕訳を経由して反映させるべき
        total_debits = data_dict["total_debits"]
        total_credits = data_dict["total_credits"]

        if total_debits > total_credits:
            context["rebf"] = total_debits - total_credits
        else:
            context["debfb"] = total_credits - total_debits


class ProfitAndLossView(FinancialStatementView):
    """損益計算書ビュー"""

    template_name = "ledger/profit_and_loss_table.html"
    ACCOUNT_TYPES = ["revenue", "expense"]
    DEBIT_TYPES = ["expense"]
    CREDIT_TYPES = ["revenue"]

    def add_specific_context(self, context: dict, data_dict: dict) -> None:
        """損益計算書固有のコンテキスト追加。

        Args:
            context (dict): コンテキストデータ
            data_dict (dict): get_dataから返されたデータ辞書
        """
        # 損益計算書では借方=費用、貸方=収益なので入れ替える
        context["loss_data"] = data_dict["debit_accounts"]  # 費用
        context["profit_data"] = data_dict["credit_accounts"]  # 収益
        context["total_expense"] = data_dict["total_debits"]  # 費用合計
        context["total_revenue"] = data_dict["total_credits"]  # 収益合計

        # HACK: 当期純利益・純損失を直接計算している
        # 本来は損益振替仕訳を経由して反映させるべき
        self.add_net_income_or_loss_to_context(
            context,
            data_dict["total_credits"],  # 収益
            data_dict["total_debits"],  # 費用
        )

    def calc_net_income_or_loss(
        self, total_revenue: Decimal, total_expense: Decimal
    ) -> tuple[Decimal, Decimal]:
        """当期純利益または純損失を計算するユーティリティメソッド。

        Args:
            total_revenue (Decimal): 総収益
            total_expense (Decimal): 総費用

        Returns:
            tuple[Decimal, Decimal]: (当期純利益, 当期純損失)
        """
        if total_revenue >= total_expense:
            net_income = total_revenue - total_expense
            net_loss = Decimal("0.00")
        else:
            net_income = Decimal("0.00")
            net_loss = total_expense - total_revenue
        return net_income, net_loss

    def add_net_income_or_loss_to_context(
        self,
        context: dict,
        total_revenue: Decimal,
        total_expense: Decimal,
    ) -> None:
        """コンテキストに当期純利益または純損失を追加するユーティリティメソッド。

        Args:
            context (dict): コンテキストデータ
            total_revenue (Decimal): 総収益
            total_expense (Decimal): 総費用
        """
        net_income, net_loss = self.calc_net_income_or_loss(
            total_revenue, total_expense
        )
        if net_income > Decimal("0.00"):
            context["net_income"] = net_income
        elif net_loss > Decimal("0.00"):
            context["net_loss"] = net_loss


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
            raise ImproperlyConfigured(ErrorMessages.MESSAGE_0002.value)

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

    PARTIAL_CONFIG: dict = {
        "sales_chart": {
            "template": "ledger/dashboard/sales_chart.html",
            "context": "get_sales_chart_context",
        },
        "cost_chart": {
            "template": "ledger/dashboard/expense_breakdown_chart.html",
            "context": "get_expense_breakdown_context",
        },
        "pareto_sales_chart": {
            "template": "ledger/dashboard/pareto_sales_chart.html",
            "context": "get_pareto_sales_context",
        },
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current_year_month: YearMonth = YearMonth(
            year=datetime.now().year, month=datetime.now().month
        )
        context["monthly_sales"] = calc_monthly_sales(current_year_month)
        context["monthly_profit"] = calc_monthly_profit(current_year_month)

        context.update(self.get_sales_chart_context())
        context.update(self.get_expense_breakdown_context())
        context.update(self.get_pareto_sales_context())
        return context

    def get(self, request, *args, **kwargs):
        """AJAXリクエストに対してJSONデータを返す処理を追加"""
        partial = request.GET.get("partial")
        span = request.GET.get("span", "6months")
        # 部分テンプレートのレンダリング

        if request.headers.get("HX-Request") and partial in self.PARTIAL_CONFIG:
            cfg = self.PARTIAL_CONFIG[partial]
            context = getattr(self, cfg["context"])()
            return render(request, cfg["template"], context)
        return super().get(request, *args, **kwargs)

    def _get_sales_chart_data(
        self, span: int = 6
    ) -> tuple[list[str], list[int], list[int]]:
        labels = [
            f"{(datetime.now() - timedelta(days=30*i)).strftime('%Y-%m')}"
            for i in range(span - 1, -1, -1)
        ]
        sales_data = list_decimal_to_int(calc_recent_half_year_sales())
        profit_data = list_decimal_to_int(calc_recent_half_year_profits())
        return labels, sales_data, profit_data

    def get_sales_chart_context(self, span: int = 6) -> dict:
        labels, sales_data, profit_data = self._get_sales_chart_data(span)
        return {
            "sales_chart_labels": json.dumps(labels),
            "sales_chart_sales_data": json.dumps(sales_data),
            "sales_chart_profit_data": json.dumps(profit_data),
        }
    
    
    def _get_expense_breakdown_data(self) -> tuple[list[str], list[int]]:
        last_month_range: DayRange = get_month_range(get_last_year_month())
        list_total_expense_by_account: list[AccountWithTotal] = calc_each_account_totals(last_month_range, ["expense"])
        sorted_list_total_expense_by_account= sorted(
            list_total_expense_by_account,
            key=attrgetter("total_amount"),
            reverse=True
        )
        labels = [
            account_total.account_object.name
            for account_total in sorted_list_total_expense_by_account
        ]
        expense_data = [
            account_total.total_amount
            for account_total in sorted_list_total_expense_by_account
        ]
        expense_data_int = list_decimal_to_int(expense_data)
        return labels, expense_data_int

    def get_expense_breakdown_context(self) -> dict:
        labels, expense_data = self._get_expense_breakdown_data()
        return {
            "expense_breakdown_labels": json.dumps(labels),
            "expense_breakdown_data": json.dumps(expense_data),
        }
    
    def get_pareto_sales_context(self) -> dict:
        company_sales: dict[str, Decimal] = get_company_sales_last_month()
        labels, sales_data, list_cumulative_sales = prepare_pareto_chart_data(company_sales)
        return {
            "pareto_sales_labels": json.dumps(labels),
            "pareto_sales_data": json.dumps(sales_data),
            "pareto_sales_cumulative_data": json.dumps(list_cumulative_sales),
        }
