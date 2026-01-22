"""
決算整理仕訳の参考情報を計算するサービス
"""

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional
from dateutil.relativedelta import relativedelta

from django.db.models import Sum, Q

from ledger.models import (
    FiscalPeriod,
    Company,
    Account,
    FixedAsset,
    DepreciationHistory,
    JournalEntry,
    Debit,
    Credit,
)


class AdjustmentCalculator:
    """決算整理仕訳の参考情報を計算するサービスクラス"""

    @staticmethod
    def calculate_depreciation(
        fiscal_period: FiscalPeriod, company: Optional[Company] = None
    ) -> Dict:
        """
        減価償却費を計算

        Args:
            fiscal_period (FiscalPeriod): 対象会計期間
            company (Company, optional): 対象会社

        Returns:
            Dict: 減価償却費の計算結果
                {
                    'assets': [
                        {
                            'asset_number': 資産番号,
                            'asset_name': 資産名,
                            'account_name': 勘定科目名,
                            'acquisition_date': 取得日,
                            'acquisition_cost': 取得価額,
                            'useful_life': 耐用年数,
                            'depreciation_method': 償却方法,
                            'annual_depreciation': 年間償却額,
                            'monthly_depreciation': 月額償却額,
                            'months_in_period': 当期使用月数,
                            'current_period_depreciation': 当期償却額,
                            'accumulated_depreciation': 減価償却累計額,
                            'book_value': 帳簿価額,
                            'already_recorded': 既に計上済みか,
                        },
                        ...
                    ],
                    'total_depreciation': 合計償却額,
                    'has_unrecorded': 未計上の資産があるか,
                }
        """
        # 当期に使用中の固定資産を取得
        queryset = FixedAsset.objects.filter(
            status="active", acquisition_date__lte=fiscal_period.end_date
        ).select_related("account")

        if company:
            queryset = queryset.filter(company=company)

        assets = queryset.order_by("asset_number")

        results = []
        total_depreciation = Decimal("0")
        has_unrecorded = False

        for asset in assets:
            # 既に当期の減価償却が計上済みかチェック
            existing = DepreciationHistory.objects.filter(
                fixed_asset=asset, fiscal_period=fiscal_period
            ).first()

            # 年間償却額を計算
            annual_depreciation = asset.calculate_annual_depreciation()

            # 月額償却額
            monthly_depreciation = annual_depreciation / 12

            # 当期における使用月数を計算
            months_in_period = AdjustmentCalculator._calculate_months_in_period(
                asset.acquisition_date, fiscal_period
            )

            # 当期償却額（月割計算）
            if existing:
                # 既に計上済み
                current_period_depreciation = existing.amount
            else:
                # 新規計算
                current_period_depreciation = (
                    monthly_depreciation * months_in_period
                ).quantize(Decimal("0.01"))
                has_unrecorded = True

            # 減価償却累計額と帳簿価額
            accumulated_depreciation = asset.get_accumulated_depreciation(
                fiscal_period.end_date
            )

            # 既に計上済みの場合は累計額に含まれているので、未計上の場合のみ加算して表示
            if not existing:
                accumulated_depreciation_with_current = (
                    accumulated_depreciation + current_period_depreciation
                )
            else:
                accumulated_depreciation_with_current = accumulated_depreciation

            book_value = asset.acquisition_cost - accumulated_depreciation_with_current

            results.append(
                {
                    "asset_id": asset.id,
                    "asset_number": asset.asset_number,
                    "asset_name": asset.name,
                    "account_name": asset.account.name,
                    "acquisition_date": asset.acquisition_date,
                    "acquisition_cost": asset.acquisition_cost,
                    "useful_life": asset.useful_life,
                    "depreciation_method": asset.get_depreciation_method_display(),
                    "annual_depreciation": annual_depreciation,
                    "monthly_depreciation": monthly_depreciation,
                    "months_in_period": months_in_period,
                    "current_period_depreciation": current_period_depreciation,
                    "accumulated_depreciation": accumulated_depreciation,
                    "accumulated_depreciation_with_current": accumulated_depreciation_with_current,
                    "book_value": book_value,
                    "already_recorded": existing is not None,
                }
            )

            total_depreciation += current_period_depreciation

        return {
            "assets": results,
            "total_depreciation": total_depreciation,
            "has_unrecorded": has_unrecorded,
        }

    @staticmethod
    def calculate_allowance(
        fiscal_period: FiscalPeriod, company: Optional[Company] = None
    ) -> Dict:
        """
        貸倒引当金を計算

        Args:
            fiscal_period (FiscalPeriod): 対象会計期間
            company (Company, optional): 対象会社

        Returns:
            Dict: 貸倒引当金の計算結果
                {
                    'receivables_accounts': [
                        {
                            'account_name': 勘定科目名,
                            'balance': 残高,
                        },
                        ...
                    ],
                    'total_receivables': 売掛金等合計,
                    'allowance_rate': 引当率,
                    'required_allowance': 必要引当金額,
                    'previous_allowance': 前期引当金残高,
                    'entry_amount': 当期繰入額（または戻入額）,
                    'is_reversal': 戻入かどうか,
                }
        """
        # 売掛金・受取手形などの債権勘定を取得
        receivables_account_names = ["売掛金", "受取手形", "未収入金"]
        receivables_accounts = Account.objects.filter(
            name__in=receivables_account_names, type="asset"
        )

        account_balances = []
        total_receivables = Decimal("0")

        for account in receivables_accounts:
            # 期末残高を計算
            balance = AdjustmentCalculator._get_account_balance(
                account, fiscal_period.end_date, company
            )

            if balance > 0:
                account_balances.append(
                    {
                        "account_name": account.name,
                        "balance": balance,
                    }
                )
                total_receivables += balance

        # 引当率（デフォルト2%、将来的には設定可能にする）
        allowance_rate = Decimal("0.02")

        # 必要引当金額
        required_allowance = (total_receivables * allowance_rate).quantize(
            Decimal("0.01")
        )

        # 前期引当金残高
        allowance_account = Account.objects.filter(name="貸倒引当金").first()
        if allowance_account:
            previous_allowance = AdjustmentCalculator._get_account_balance(
                allowance_account, fiscal_period.end_date, company
            )
        else:
            previous_allowance = Decimal("0")

        # 当期繰入額（または戻入額）
        entry_amount = required_allowance - previous_allowance
        is_reversal = entry_amount < 0

        return {
            "receivables_accounts": account_balances,
            "total_receivables": total_receivables,
            "allowance_rate": allowance_rate,
            "required_allowance": required_allowance,
            "previous_allowance": previous_allowance,
            "entry_amount": abs(entry_amount),
            "is_reversal": is_reversal,
        }

    @staticmethod
    def _calculate_months_in_period(
        acquisition_date: date, fiscal_period: FiscalPeriod
    ) -> int:
        """
        会計期間内における資産の使用月数を計算

        Args:
            acquisition_date (date): 取得日
            fiscal_period (FiscalPeriod): 会計期間

        Returns:
            int: 使用月数
        """
        # 期間開始日と取得日のうち遅い方を開始日とする
        start = max(acquisition_date, fiscal_period.start_date)
        end = fiscal_period.end_date

        # 月数を計算
        months = (
            (end.year - start.year) * 12 + (end.month - start.month) + 1
        )  # +1は当月を含むため

        # 会計期間の月数を超えないように制限
        max_months = (
            (fiscal_period.end_date.year - fiscal_period.start_date.year) * 12
            + (fiscal_period.end_date.month - fiscal_period.start_date.month)
            + 1
        )

        return min(months, max_months)

    @staticmethod
    def _get_account_balance(
        account: Account, as_of_date: date, company: Optional[Company] = None
    ) -> Decimal:
        """
        指定日時点での勘定科目の残高を計算

        Args:
            account (Account): 勘定科目
            as_of_date (date): 基準日
            company (Company, optional): 会社

        Returns:
            Decimal: 残高
        """
        # 借方合計
        debit_query = Debit.objects.filter(
            account=account, journal_entry__date__lte=as_of_date
        )
        if company:
            debit_query = debit_query.filter(journal_entry__company=company)
        debit_total = debit_query.aggregate(total=Sum("amount"))["total"] or Decimal(
            "0"
        )

        # 貸方合計
        credit_query = Credit.objects.filter(
            account=account, journal_entry__date__lte=as_of_date
        )
        if company:
            credit_query = credit_query.filter(journal_entry__company=company)
        credit_total = credit_query.aggregate(total=Sum("amount"))["total"] or Decimal(
            "0"
        )

        # 勘定科目の種類に応じて残高を計算
        if account.type in ["asset", "expense"]:
            # 資産・費用は借方残高
            balance = debit_total - credit_total
        else:
            # 負債・純資産・収益は貸方残高
            balance = credit_total - debit_total

        return balance

    @staticmethod
    def get_all_adjustment_info(
        fiscal_period: FiscalPeriod, company: Optional[Company] = None
    ) -> Dict:
        """
        決算整理仕訳に必要な全ての参考情報を取得

        Args:
            fiscal_period (FiscalPeriod): 対象会計期間
            company (Company, optional): 対象会社

        Returns:
            Dict: 全ての参考情報
                {
                    'depreciation': 減価償却費情報,
                    'allowance': 貸倒引当金情報,
                    'fiscal_period': 会計期間,
                }
        """
        return {
            "depreciation": AdjustmentCalculator.calculate_depreciation(
                fiscal_period, company
            ),
            "allowance": AdjustmentCalculator.calculate_allowance(
                fiscal_period, company
            ),
            "fiscal_period": fiscal_period,
        }
