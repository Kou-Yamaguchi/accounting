from datetime import datetime
from decimal import Decimal
from itertools import zip_longest

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View
from openpyxl import Workbook

# TODO: 以下のimport文は分割後に修正
# from ledger.services.accounting_period import DayRange, get_fiscal_range
# from ledger.services.financial_statement import (
#     AccountWithTotal,
#     FinancialStatementEntry,
#     calc_each_account_totals,
# )
from ledger.services import get_fiscal_range, calc_each_account_totals
from ledger.structures import AccountWithTotal, FinancialStatementEntry, DayRange


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
