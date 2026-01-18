from decimal import Decimal
from datetime import datetime
from itertools import zip_longest

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
from openpyxl import Workbook

from ledger.models import JournalEntry, Account, Company, Entry, Debit, Credit, PurchaseDetail
from ledger.forms import JournalEntryForm, DebitFormSet, CreditFormSet
from ledger.structures import (
    AccountWithTotal,
    DayRange,
    FinancialStatementEntry,
)
from ledger.services import (
    get_fiscal_range,
    get_all_journal_entries_for_account,
    calc_each_account_totals,
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

    template_name = "ledger/balance_sheet/table.html"
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

    template_name = "ledger/profit_and_loss/table.html"
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
