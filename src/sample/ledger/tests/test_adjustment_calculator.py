"""
AdjustmentCalculatorのテスト
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase

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
from ledger.services_temp import AdjustmentCalculator


class AdjustmentCalculatorTest(TestCase):
    """AdjustmentCalculatorのテストケース"""

    def setUp(self):
        """テストデータの準備"""
        # 会社
        self.company = Company.objects.create(name="テスト株式会社")

        # 会計期間
        self.fiscal_period = FiscalPeriod.objects.create(
            name="2025年度",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            is_closed=False,
        )

        # 勘定科目
        self.account_building = Account.objects.create(name="建物", type="asset")
        self.account_equipment = Account.objects.create(name="備品", type="asset")
        self.account_cash = Account.objects.create(name="現金", type="asset")
        self.account_receivable = Account.objects.create(name="売掛金", type="asset")
        self.account_sales = Account.objects.create(name="売上", type="revenue")
        self.account_allowance = Account.objects.create(
            name="貸倒引当金", type="liability"
        )

    def test_calculate_depreciation_single_asset(self):
        """単一固定資産の減価償却費計算テスト"""
        # 期首に建物を取得
        je = JournalEntry.objects.create(
            date=date(2025, 4, 1),
            summary="建物取得",
            company=self.company,
            fiscal_period=self.fiscal_period,
        )
        Debit.objects.create(
            journal_entry=je, account=self.account_building, amount=Decimal("10000000")
        )
        Credit.objects.create(
            journal_entry=je, account=self.account_cash, amount=Decimal("10000000")
        )

        # 固定資産登録
        asset = FixedAsset.objects.create(
            name="本社ビル",
            asset_number="FA-001",
            account=self.account_building,
            acquisition_date=date(2025, 4, 1),
            acquisition_cost=Decimal("10000000"),
            acquisition_journal_entry=je,
            depreciation_method="straight_line",
            useful_life=20,
            residual_value=Decimal("0"),
        )

        # 減価償却費を計算
        result = AdjustmentCalculator.calculate_depreciation(self.fiscal_period)

        # 検証
        self.assertEqual(len(result["assets"]), 1)
        asset_info = result["assets"][0]
        self.assertEqual(asset_info["asset_number"], "FA-001")
        self.assertEqual(asset_info["asset_name"], "本社ビル")
        self.assertEqual(asset_info["acquisition_cost"], Decimal("10000000"))
        self.assertEqual(asset_info["useful_life"], 20)
        self.assertEqual(
            asset_info["annual_depreciation"], Decimal("500000")
        )  # 10,000,000 / 20
        self.assertEqual(asset_info["months_in_period"], 12)  # 期首取得なので12ヶ月
        self.assertEqual(
            asset_info["current_period_depreciation"], Decimal("500000.00")
        )
        self.assertFalse(asset_info["already_recorded"])
        self.assertEqual(result["total_depreciation"], Decimal("500000.00"))
        self.assertTrue(result["has_unrecorded"])

    def test_calculate_depreciation_mid_period_acquisition(self):
        """期中取得の固定資産の月割計算テスト"""
        # 期中（10月1日）に備品を取得
        je = JournalEntry.objects.create(
            date=date(2025, 10, 1),
            summary="備品取得",
            company=self.company,
            fiscal_period=self.fiscal_period,
        )
        Debit.objects.create(
            journal_entry=je, account=self.account_equipment, amount=Decimal("1200000")
        )
        Credit.objects.create(
            journal_entry=je, account=self.account_cash, amount=Decimal("1200000")
        )

        # 固定資産登録
        asset = FixedAsset.objects.create(
            name="ノートPC",
            asset_number="FA-002",
            account=self.account_equipment,
            acquisition_date=date(2025, 10, 1),
            acquisition_cost=Decimal("1200000"),
            acquisition_journal_entry=je,
            depreciation_method="straight_line",
            useful_life=4,
            residual_value=Decimal("0"),
        )

        # 減価償却費を計算
        result = AdjustmentCalculator.calculate_depreciation(self.fiscal_period)

        # 検証
        self.assertEqual(len(result["assets"]), 1)
        asset_info = result["assets"][0]
        self.assertEqual(
            asset_info["annual_depreciation"], Decimal("300000")
        )  # 1,200,000 / 4
        self.assertEqual(asset_info["months_in_period"], 6)  # 10月〜3月の6ヶ月
        # 月額 = 300,000 / 12 = 25,000
        # 当期償却額 = 25,000 * 6 = 150,000
        self.assertEqual(
            asset_info["current_period_depreciation"], Decimal("150000.00")
        )

    def test_calculate_depreciation_with_history(self):
        """既に計上済みの減価償却履歴があるケース"""
        # 固定資産登録
        je = JournalEntry.objects.create(
            date=date(2025, 4, 1),
            summary="建物取得",
            company=self.company,
            fiscal_period=self.fiscal_period,
        )

        asset = FixedAsset.objects.create(
            name="本社ビル",
            asset_number="FA-001",
            account=self.account_building,
            acquisition_date=date(2025, 4, 1),
            acquisition_cost=Decimal("10000000"),
            depreciation_method="straight_line",
            useful_life=20,
        )

        # 既に減価償却履歴を登録
        DepreciationHistory.objects.create(
            fixed_asset=asset,
            fiscal_period=self.fiscal_period,
            amount=Decimal("500000"),
        )

        # 減価償却費を計算
        result = AdjustmentCalculator.calculate_depreciation(self.fiscal_period)

        # 検証
        asset_info = result["assets"][0]
        self.assertTrue(asset_info["already_recorded"])
        self.assertEqual(
            asset_info["current_period_depreciation"], Decimal("500000")
        )  # 履歴の金額
        self.assertFalse(result["has_unrecorded"])

    def test_calculate_allowance(self):
        """貸倒引当金計算テスト"""
        # 売上仕訳（売掛金5,000,000円）
        je = JournalEntry.objects.create(
            date=date(2025, 12, 31),
            summary="売上",
            company=self.company,
            fiscal_period=self.fiscal_period,
        )
        Debit.objects.create(
            journal_entry=je,
            account=self.account_receivable,
            amount=Decimal("5000000"),
        )
        Credit.objects.create(
            journal_entry=je, account=self.account_sales, amount=Decimal("5000000")
        )

        # 貸倒引当金を計算
        result = AdjustmentCalculator.calculate_allowance(self.fiscal_period)

        # 検証
        self.assertEqual(result["total_receivables"], Decimal("5000000"))
        self.assertEqual(result["allowance_rate"], Decimal("0.02"))  # 2%
        self.assertEqual(
            result["required_allowance"], Decimal("100000.00")
        )  # 5,000,000 * 0.02
        self.assertEqual(result["previous_allowance"], Decimal("0"))  # 前期引当金なし
        self.assertEqual(result["entry_amount"], Decimal("100000.00"))  # 繰入額
        self.assertFalse(result["is_reversal"])

    def test_calculate_allowance_with_previous(self):
        """前期引当金がある場合の貸倒引当金計算テスト"""
        # 売上仕訳
        je1 = JournalEntry.objects.create(
            date=date(2025, 12, 31),
            summary="売上",
            company=self.company,
            fiscal_period=self.fiscal_period,
        )
        Debit.objects.create(
            journal_entry=je1,
            account=self.account_receivable,
            amount=Decimal("5000000"),
        )
        Credit.objects.create(
            journal_entry=je1, account=self.account_sales, amount=Decimal("5000000")
        )

        # 前期引当金仕訳（既に80,000円計上済み）
        je2 = JournalEntry.objects.create(
            date=date(2025, 3, 31),
            summary="前期引当金",
            company=self.company,
            fiscal_period=self.fiscal_period,
        )
        Credit.objects.create(
            journal_entry=je2,
            account=self.account_allowance,
            amount=Decimal("80000"),
        )
        Debit.objects.create(
            journal_entry=je2, account=self.account_cash, amount=Decimal("80000")
        )  # 仮

        # 貸倒引当金を計算
        result = AdjustmentCalculator.calculate_allowance(self.fiscal_period)

        # 検証
        self.assertEqual(result["required_allowance"], Decimal("100000.00"))
        self.assertEqual(result["previous_allowance"], Decimal("80000"))
        self.assertEqual(
            result["entry_amount"], Decimal("20000.00")
        )  # 追加繰入 100,000 - 80,000
        self.assertFalse(result["is_reversal"])

    def test_record_depreciation_creates_history_for_unrecorded_asset(self):
        """未計上の資産に対してDepreciationHistoryが作成されること"""
        asset = FixedAsset.objects.create(
            name="本社ビル",
            asset_number="FA-001",
            account=self.account_building,
            acquisition_date=date(2025, 4, 1),
            acquisition_cost=Decimal("10000000"),
            depreciation_method="straight_line",
            useful_life=20,
            residual_value=Decimal("0"),
        )
        je = JournalEntry.objects.create(
            date=date(2026, 3, 31),
            summary="減価償却費の計上",
            company=self.company,
            fiscal_period=self.fiscal_period,
        )

        depreciation_info = AdjustmentCalculator.calculate_depreciation(
            self.fiscal_period
        )
        AdjustmentCalculator.record_depreciation(
            depreciation_info, self.fiscal_period, je
        )

        history = DepreciationHistory.objects.filter(
            fixed_asset=asset, fiscal_period=self.fiscal_period
        )
        self.assertEqual(history.count(), 1)
        self.assertEqual(history.first().amount, Decimal("500000.00"))

    def test_record_depreciation_links_journal_entry(self):
        """作成されたDepreciationHistoryが仕訳と紐付けられること"""
        FixedAsset.objects.create(
            name="本社ビル",
            asset_number="FA-001",
            account=self.account_building,
            acquisition_date=date(2025, 4, 1),
            acquisition_cost=Decimal("10000000"),
            depreciation_method="straight_line",
            useful_life=20,
            residual_value=Decimal("0"),
        )
        je = JournalEntry.objects.create(
            date=date(2026, 3, 31),
            summary="減価償却費の計上",
            company=self.company,
            fiscal_period=self.fiscal_period,
        )

        depreciation_info = AdjustmentCalculator.calculate_depreciation(
            self.fiscal_period
        )
        AdjustmentCalculator.record_depreciation(
            depreciation_info, self.fiscal_period, je
        )

        history = DepreciationHistory.objects.get(fiscal_period=self.fiscal_period)
        self.assertEqual(history.depreciation_journal_entry, je)

    def test_record_depreciation_skips_already_recorded_asset(self):
        """計上済みの資産に対してDepreciationHistoryが重複作成されないこと"""
        asset = FixedAsset.objects.create(
            name="本社ビル",
            asset_number="FA-001",
            account=self.account_building,
            acquisition_date=date(2025, 4, 1),
            acquisition_cost=Decimal("10000000"),
            depreciation_method="straight_line",
            useful_life=20,
            residual_value=Decimal("0"),
        )
        DepreciationHistory.objects.create(
            fixed_asset=asset,
            fiscal_period=self.fiscal_period,
            amount=Decimal("500000"),
        )
        je = JournalEntry.objects.create(
            date=date(2026, 3, 31),
            summary="減価償却費の計上",
            company=self.company,
            fiscal_period=self.fiscal_period,
        )

        depreciation_info = AdjustmentCalculator.calculate_depreciation(
            self.fiscal_period
        )
        AdjustmentCalculator.record_depreciation(
            depreciation_info, self.fiscal_period, je
        )

        self.assertEqual(
            DepreciationHistory.objects.filter(
                fixed_asset=asset, fiscal_period=self.fiscal_period
            ).count(),
            1,
        )

    def test_record_depreciation_creates_history_for_multiple_assets(self):
        """複数の未計上資産に対して全てDepreciationHistoryが作成されること"""
        asset1 = FixedAsset.objects.create(
            name="本社ビル",
            asset_number="FA-001",
            account=self.account_building,
            acquisition_date=date(2025, 4, 1),
            acquisition_cost=Decimal("10000000"),
            depreciation_method="straight_line",
            useful_life=20,
            residual_value=Decimal("0"),
        )
        asset2 = FixedAsset.objects.create(
            name="ノートPC",
            asset_number="FA-002",
            account=self.account_equipment,
            acquisition_date=date(2025, 4, 1),
            acquisition_cost=Decimal("1200000"),
            depreciation_method="straight_line",
            useful_life=4,
            residual_value=Decimal("0"),
        )
        je = JournalEntry.objects.create(
            date=date(2026, 3, 31),
            summary="減価償却費の計上",
            company=self.company,
            fiscal_period=self.fiscal_period,
        )

        depreciation_info = AdjustmentCalculator.calculate_depreciation(
            self.fiscal_period
        )
        AdjustmentCalculator.record_depreciation(
            depreciation_info, self.fiscal_period, je
        )

        self.assertEqual(
            DepreciationHistory.objects.filter(
                fiscal_period=self.fiscal_period
            ).count(),
            2,
        )
        self.assertTrue(
            DepreciationHistory.objects.filter(
                fixed_asset=asset1, fiscal_period=self.fiscal_period
            ).exists()
        )
        self.assertTrue(
            DepreciationHistory.objects.filter(
                fixed_asset=asset2, fiscal_period=self.fiscal_period
            ).exists()
        )

    def test_record_depreciation_only_unrecorded_when_mixed(self):
        """計上済みと未計上が混在する場合、未計上の資産のみHistoryが作成されること"""
        asset1 = FixedAsset.objects.create(
            name="本社ビル",
            asset_number="FA-001",
            account=self.account_building,
            acquisition_date=date(2025, 4, 1),
            acquisition_cost=Decimal("10000000"),
            depreciation_method="straight_line",
            useful_life=20,
            residual_value=Decimal("0"),
        )
        asset2 = FixedAsset.objects.create(
            name="ノートPC",
            asset_number="FA-002",
            account=self.account_equipment,
            acquisition_date=date(2025, 4, 1),
            acquisition_cost=Decimal("1200000"),
            depreciation_method="straight_line",
            useful_life=4,
            residual_value=Decimal("0"),
        )
        # asset1 だけ計上済みにする
        DepreciationHistory.objects.create(
            fixed_asset=asset1,
            fiscal_period=self.fiscal_period,
            amount=Decimal("500000"),
        )
        je = JournalEntry.objects.create(
            date=date(2026, 3, 31),
            summary="減価償却費の計上",
            company=self.company,
            fiscal_period=self.fiscal_period,
        )

        depreciation_info = AdjustmentCalculator.calculate_depreciation(
            self.fiscal_period
        )
        AdjustmentCalculator.record_depreciation(
            depreciation_info, self.fiscal_period, je
        )

        # asset1 は増えていない
        self.assertEqual(
            DepreciationHistory.objects.filter(
                fixed_asset=asset1, fiscal_period=self.fiscal_period
            ).count(),
            1,
        )
        # asset2 は新規作成されている
        self.assertEqual(
            DepreciationHistory.objects.filter(
                fixed_asset=asset2, fiscal_period=self.fiscal_period
            ).count(),
            1,
        )

    def test_get_all_adjustment_info(self):
        """全ての参考情報を取得するテスト"""
        # 固定資産
        FixedAsset.objects.create(
            name="建物",
            asset_number="FA-001",
            account=self.account_building,
            acquisition_date=date(2025, 4, 1),
            acquisition_cost=Decimal("10000000"),
            depreciation_method="straight_line",
            useful_life=20,
        )

        # 売掛金
        je = JournalEntry.objects.create(
            date=date(2025, 12, 31),
            summary="売上",
            company=self.company,
            fiscal_period=self.fiscal_period,
        )
        Debit.objects.create(
            journal_entry=je,
            account=self.account_receivable,
            amount=Decimal("1000000"),
        )
        Credit.objects.create(
            journal_entry=je, account=self.account_sales, amount=Decimal("1000000")
        )

        # 全情報取得
        result = AdjustmentCalculator.get_all_adjustment_info(self.fiscal_period)

        # 検証
        self.assertIn("depreciation", result)
        self.assertIn("allowance", result)
        self.assertIn("fiscal_period", result)
        self.assertEqual(len(result["depreciation"]["assets"]), 1)
        self.assertEqual(result["allowance"]["total_receivables"], Decimal("1000000"))
