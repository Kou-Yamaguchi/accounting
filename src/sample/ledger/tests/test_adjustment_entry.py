"""
決算整理仕訳入力画面のテスト
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.urls import reverse

from ledger.models import (
    Account,
    Company,
    FiscalPeriod,
    JournalEntry,
    Debit,
    Credit,
    FixedAsset,
    DepreciationHistory,
)
from ledger.views.adjustment_entry import AdjustmentEntryCreateView
from ledger.forms import AdjustmentJournalEntryForm
from ledger.tests.utils import create_accounts, AccountData


class AdjustmentJournalEntryFormTest(TestCase):
    """AdjustmentJournalEntryFormのテスト"""

    def setUp(self):
        # 会計期間を作成
        self.fiscal_period_open = FiscalPeriod.objects.create(
            name="2024年度",
            start_date=date(2024, 4, 1),
            end_date=date(2025, 3, 31),
            is_closed=False,
        )
        self.fiscal_period_closed = FiscalPeriod.objects.create(
            name="2023年度",
            start_date=date(2023, 4, 1),
            end_date=date(2024, 3, 31),
            is_closed=True,
        )

    def test_form_excludes_date_field(self):
        """dateフィールドが除外されていることを確認"""
        form = AdjustmentJournalEntryForm()
        self.assertNotIn("date", form.fields)

    def test_form_includes_summary_and_company_fields(self):
        """summaryとcompanyフィールドが含まれていることを確認"""
        form = AdjustmentJournalEntryForm()
        self.assertIn("summary", form.fields)
        self.assertIn("company", form.fields)


class AdjustmentEntryCreateViewTest(TestCase):
    """AdjustmentEntryCreateView のテスト"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="testuser",
            password="testpass",
        )
        self.client.force_login(self.user)
        self.factory = RequestFactory()

        # 勘定科目を作成
        self.accounts = create_accounts(
            [
                AccountData(name="建物", type="asset"),
                AccountData(name="減価償却累計額", type="asset_contra"),
                AccountData(name="減価償却費", type="expense"),
                AccountData(name="売掛金", type="asset"),
                AccountData(name="貸倒引当金", type="asset_contra"),
                AccountData(name="貸倒引当金繰入", type="expense"),
                AccountData(name="現金", type="asset"),
            ]
        )

        # 会社を作成
        self.company = Company.objects.create(name="テスト会社")

        # 会計期間を作成
        self.fiscal_period = FiscalPeriod.objects.create(
            name="2024年度",
            start_date=date(2024, 4, 1),
            end_date=date(2025, 3, 31),
            is_closed=False,
        )

    def _create_building_asset(self):
        """未計上の減価償却費がある固定資産を作成するヘルパー"""
        building_account = Account.objects.get(name="建物")
        je = JournalEntry.objects.create(
            date=date(2024, 4, 1),
            summary="建物購入",
            company=self.company,
            entry_type="normal",
        )
        # NOTE: 固定資産の取得仕訳は、減価償却費の計算に影響するため、必ず作成する必要があります。減価償却費の計算は、取得原価をもとに行われるため、取得仕訳がないと正しい減価償却費が計算されません。
        Debit.objects.create(
            journal_entry=je,
            account=building_account,
            amount=Decimal("10000000"),
        )
        FixedAsset.objects.create(
            name="本社ビル",
            account=building_account,
            acquisition_date=date(2024, 4, 1),
            acquisition_cost=Decimal("10000000"),
            useful_life=20,
            residual_value=Decimal("0"),
            acquisition_journal_entry=je,
        )

    def build_post(
        self,
        block_key="depreciation",
        summary=None,
        debit_items=None,
        credit_items=None,
    ):
        """
        block_key   : EntryBlock のキー（デフォルト "depreciation"）
        debit_items / credit_items はリスト。各要素は
        {'account': account_id, 'amount': '123.45', 'id': existing_id (optional)}
        を想定する。id がある要素は INITIAL_FORMS のカウントに含める。
        """
        data = {
            "fiscal_period": str(self.fiscal_period.id),
            f"{block_key}-summary": summary or "決算整理仕訳",
            f"{block_key}-company": str(self.company.id),
            f"{block_key}-debit-TOTAL_FORMS": "0",
            f"{block_key}-debit-INITIAL_FORMS": "0",
            f"{block_key}-debit-MIN_NUM_FORMS": "0",
            f"{block_key}-debit-MAX_NUM_FORMS": "1000",
            f"{block_key}-credit-TOTAL_FORMS": "0",
            f"{block_key}-credit-INITIAL_FORMS": "0",
            f"{block_key}-credit-MIN_NUM_FORMS": "0",
            f"{block_key}-credit-MAX_NUM_FORMS": "1000",
        }

        # デビット
        if debit_items is not None:
            data[f"{block_key}-debit-TOTAL_FORMS"] = str(len(debit_items))
            initial_count = sum(1 for it in debit_items if it.get("id") is not None)
            data[f"{block_key}-debit-INITIAL_FORMS"] = str(initial_count)
            for i, item in enumerate(debit_items):
                if "id" in item:
                    data[f"{block_key}-debit-{i}-id"] = str(item["id"])
                data[f"{block_key}-debit-{i}-account"] = str(item["account"])
                data[f"{block_key}-debit-{i}-amount"] = str(item["amount"])

        # クレジット
        if credit_items is not None:
            data[f"{block_key}-credit-TOTAL_FORMS"] = str(len(credit_items))
            initial_count = sum(1 for it in credit_items if it.get("id") is not None)
            data[f"{block_key}-credit-INITIAL_FORMS"] = str(initial_count)
            for i, item in enumerate(credit_items):
                if "id" in item:
                    data[f"{block_key}-credit-{i}-id"] = str(item["id"])
                data[f"{block_key}-credit-{i}-account"] = str(item["account"])
                data[f"{block_key}-credit-{i}-amount"] = str(item["amount"])

        return data

    def test_get_context_includes_reference_info(self):
        """コンテキストに参考情報が含まれることを確認"""
        response = self.client.get(
            reverse("adjustment_entry_new"),
            {"fiscal_period": self.fiscal_period.id},
        )

        context = response.context
        self.assertEqual(response.status_code, 200)

        # 参考情報が含まれていることを確認
        # NOTE: 参考情報はreference_infoキーを経由せずに直接コンテキストに展開されるようになったため、以下のコメントアウト部分は参考用に残しています
        # self.assertIn("reference_info", context)
        # reference_info = context["reference_info"]

        # 減価償却と貸倒引当金の情報が含まれることを確認
        self.assertIn("depreciation", context)
        self.assertIn("allowance", context)

    def test_get_context_with_fiscal_period(self):
        """会計期間が選択されている場合のコンテキストを確認"""
        response = self.client.get(
            reverse("adjustment_entry_new"),
            {"fiscal_period": self.fiscal_period.id},
        )

        context = response.context

        self.assertIn("fiscal_period", context)
        self.assertEqual(context["fiscal_period"], self.fiscal_period)

    def test_form_valid_sets_date_to_period_end(self):
        """form_validで日付が期末日に設定されることを確認"""
        self._create_building_asset()

        data = self.build_post(
            debit_items=[
                {
                    "account": Account.objects.get(name="減価償却費").id,
                    "amount": "500000",
                }
            ],
            credit_items=[
                {
                    "account": Account.objects.get(name="減価償却累計額").id,
                    "amount": "500000",
                }
            ],
        )

        response = self.client.post(
            reverse("adjustment_entry_new"),
            data=data,
        )

        # 仕訳が作成されたことを確認
        journal_entry = JournalEntry.objects.filter(summary="決算整理仕訳").first()

        self.assertIsNotNone(journal_entry)
        # 日付が期末日に設定されていることを確認
        self.assertEqual(journal_entry.date, self.fiscal_period.end_date)

    def test_form_valid_sets_entry_type_to_adjustment(self):
        """form_validでentry_typeがadjustmentに設定されることを確認"""
        self._create_building_asset()

        data = self.build_post(
            debit_items=[
                {
                    "account": Account.objects.get(name="減価償却費").id,
                    "amount": "500000",
                }
            ],
            credit_items=[
                {
                    "account": Account.objects.get(name="減価償却累計額").id,
                    "amount": "500000",
                }
            ],
        )

        response = self.client.post(
            reverse("adjustment_entry_new"),
            data=data,
        )

        self.assertEqual(response.status_code, 302)  # リダイレクトを確認

        # 仕訳が作成されたことを確認
        journal_entry: JournalEntry = JournalEntry.objects.filter(
            summary="決算整理仕訳"
        ).first()

        self.assertIsNotNone(journal_entry)
        # entry_typeがadjustmentに設定されていることを確認
        self.assertEqual(journal_entry.entry_type, "adjustment")

    def test_form_valid_sets_fiscal_period(self):
        """form_validでfiscal_periodが設定されることを確認"""
        self._create_building_asset()

        data = self.build_post(
            debit_items=[
                {
                    "account": Account.objects.get(name="減価償却費").id,
                    "amount": "500000",
                }
            ],
            credit_items=[
                {
                    "account": Account.objects.get(name="減価償却累計額").id,
                    "amount": "500000",
                }
            ],
        )

        response = self.client.post(
            reverse("adjustment_entry_new"),
            data=data,
        )

        # 仕訳が作成されたことを確認
        journal_entry = JournalEntry.objects.filter(summary="決算整理仕訳").first()
        self.assertIsNotNone(journal_entry)
        # fiscal_periodが設定されていることを確認
        self.assertEqual(journal_entry.fiscal_period, self.fiscal_period)


class AdjustmentReferenceInfoTest(TestCase):
    """決算整理仕訳の参考情報表示のテスト"""

    def setUp(self):
        self.factory = RequestFactory()

        # 勘定科目を作成
        self.accounts = create_accounts(
            [
                AccountData(name="建物", type="asset"),
                AccountData(name="減価償却累計額", type="asset_contra"),
                AccountData(name="減価償却費", type="expense"),
                AccountData(name="売掛金", type="asset"),
                AccountData(name="貸倒引当金", type="asset_contra"),
                AccountData(name="貸倒引当金繰入", type="expense"),
            ]
        )

        # 会社を作成
        self.company = Company.objects.create(name="テスト会社")

        # 会計期間を作成
        self.fiscal_period = FiscalPeriod.objects.create(
            name="2024年度",
            start_date=date(2024, 4, 1),
            end_date=date(2025, 3, 31),
            is_closed=False,
        )

    def test_depreciation_info_with_fixed_assets(self):
        """固定資産がある場合の減価償却情報を確認"""
        # 固定資産を作成
        building_account = Account.objects.get(name="建物")
        je = JournalEntry.objects.create(
            date=date(2024, 4, 1),
            summary="建物購入",
            company=self.company,
            entry_type="normal",
        )
        Debit.objects.create(
            journal_entry=je,
            account=building_account,
            amount=Decimal("10000000"),
        )

        fixed_asset = FixedAsset.objects.create(
            name="本社ビル",
            account=building_account,
            acquisition_date=date(2024, 4, 1),
            acquisition_cost=Decimal("10000000"),
            useful_life=20,
            residual_value=Decimal("0"),
            acquisition_journal_entry=je,
        )

        response = self.client.get(
            reverse("adjustment_entry_new"),
            {"fiscal_period": self.fiscal_period.id},
        )

        context = response.context

        # 減価償却情報が含まれることを確認
        self.assertIn("depreciation", context)
        depreciation = context["depreciation"]["assets"]

        # 固定資産情報が含まれることを確認
        self.assertTrue(len(depreciation) > 0)
        asset_info = depreciation[0]

        self.assertEqual(asset_info["asset_name"], "本社ビル")
        self.assertEqual(asset_info["acquisition_cost"], Decimal("10000000"))

    def test_allowance_info_with_receivables(self):
        """売掛金がある場合の貸倒引当金情報を確認"""
        # 売掛金を計上する仕訳を作成
        receivable_account = Account.objects.get(name="売掛金")
        je = JournalEntry.objects.create(
            date=date(2024, 5, 1),
            summary="売上",
            company=self.company,
            entry_type="normal",
        )
        Debit.objects.create(
            journal_entry=je,
            account=receivable_account,
            amount=Decimal("1000000"),
        )

        response = self.client.get(
            reverse("adjustment_entry_new"),
            {"fiscal_period": self.fiscal_period.id},
        )

        context = response.context

        # 貸倒引当金情報が含まれることを確認
        self.assertIn("allowance", context)
        allowance = context["allowance"]
        # 売掛金残高が含まれることを確認
        self.assertIn("receivables_accounts", allowance)
        self.assertEqual(
            allowance["receivables_accounts"][0]["balance"], Decimal("1000000")
        )

    def test_depreciation_history_recording(self):
        """減価償却履歴が記録されることを確認"""
        # 固定資産を作成
        building_account = Account.objects.get(name="建物")
        je = JournalEntry.objects.create(
            date=date(2024, 4, 1),
            summary="建物購入",
            company=self.company,
            entry_type="normal",
        )
        Debit.objects.create(
            journal_entry=je,
            account=building_account,
            amount=Decimal("10000000"),
        )

        fixed_asset = FixedAsset.objects.create(
            name="本社ビル",
            account=building_account,
            acquisition_date=date(2024, 4, 1),
            acquisition_cost=Decimal("10000000"),
            useful_life=20,
            residual_value=Decimal("0"),
            acquisition_journal_entry=je,
        )

        # 減価償却の決算整理仕訳を作成
        adjustment_je = JournalEntry.objects.create(
            date=self.fiscal_period.end_date,
            summary="減価償却",
            company=self.company,
            entry_type="adjustment",
            fiscal_period=self.fiscal_period,
        )
        Debit.objects.create(
            journal_entry=adjustment_je,
            account=Account.objects.get(name="減価償却費"),
            amount=Decimal("500000"),
        )
        Credit.objects.create(
            journal_entry=adjustment_je,
            account=Account.objects.get(name="減価償却累計額"),
            amount=Decimal("500000"),
        )

        # 減価償却履歴を記録
        depreciation_history = DepreciationHistory.objects.create(
            fixed_asset=fixed_asset,
            fiscal_period=self.fiscal_period,
            amount=Decimal("500000"),
            depreciation_journal_entry=adjustment_je,
        )

        # 減価償却履歴が記録されたことを確認
        self.assertEqual(
            DepreciationHistory.objects.filter(fixed_asset=fixed_asset).count(),
            1,
        )
        self.assertEqual(depreciation_history.amount, Decimal("500000"))


class AdjustmentEntryDepreciationHistoryTest(TestCase):
    """決算整理仕訳POST時のDepreciationHistory作成のテスト"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="testuser",
            password="testpass",
        )
        self.client.force_login(self.user)

        self.accounts = create_accounts(
            [
                AccountData(name="建物", type="asset"),
                AccountData(name="減価償却累計額", type="asset_contra"),
                AccountData(name="減価償却費", type="expense"),
                AccountData(name="現金", type="asset"),
            ]
        )

        self.company = Company.objects.create(name="テスト会社")
        self.fiscal_period = FiscalPeriod.objects.create(
            name="2024年度",
            start_date=date(2024, 4, 1),
            end_date=date(2025, 3, 31),
            is_closed=False,
        )

    def _create_building_asset(self, asset_number="FA-001"):
        building_account = Account.objects.get(name="建物")
        je = JournalEntry.objects.create(
            date=date(2024, 4, 1),
            summary="建物購入",
            company=self.company,
            entry_type="normal",
        )
        Debit.objects.create(
            journal_entry=je,
            account=building_account,
            amount=Decimal("10000000"),
        )
        return FixedAsset.objects.create(
            name="本社ビル",
            asset_number=asset_number,
            account=building_account,
            acquisition_date=date(2024, 4, 1),
            acquisition_cost=Decimal("10000000"),
            useful_life=20,
            residual_value=Decimal("0"),
            acquisition_journal_entry=je,
        )

    def _post_depreciation(self, amount="500000"):
        debit_account_id = Account.objects.get(name="減価償却費").id
        credit_account_id = Account.objects.get(name="減価償却累計額").id
        data = {
            "fiscal_period": str(self.fiscal_period.id),
            "depreciation-summary": "減価償却費の計上",
            "depreciation-company": str(self.company.id),
            "depreciation-debit-TOTAL_FORMS": "1",
            "depreciation-debit-INITIAL_FORMS": "0",
            "depreciation-debit-MIN_NUM_FORMS": "0",
            "depreciation-debit-MAX_NUM_FORMS": "1000",
            "depreciation-debit-0-account": str(debit_account_id),
            "depreciation-debit-0-amount": amount,
            "depreciation-credit-TOTAL_FORMS": "1",
            "depreciation-credit-INITIAL_FORMS": "0",
            "depreciation-credit-MIN_NUM_FORMS": "0",
            "depreciation-credit-MAX_NUM_FORMS": "1000",
            "depreciation-credit-0-account": str(credit_account_id),
            "depreciation-credit-0-amount": amount,
        }
        return self.client.post(reverse("adjustment_entry_new"), data=data)

    def test_post_creates_depreciation_history(self):
        """POST成功時にDepreciationHistoryが作成されること"""
        asset = self._create_building_asset()

        response = self._post_depreciation()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            DepreciationHistory.objects.filter(
                fixed_asset=asset, fiscal_period=self.fiscal_period
            ).count(),
            1,
        )

    def test_post_history_has_correct_amount(self):
        """作成されたDepreciationHistoryの金額が計算値と一致すること"""
        asset = self._create_building_asset()

        self._post_depreciation(amount="500000")

        history = DepreciationHistory.objects.get(
            fixed_asset=asset, fiscal_period=self.fiscal_period
        )
        self.assertEqual(history.amount, Decimal("500000.00"))

    def test_post_history_linked_to_journal_entry(self):
        """作成されたDepreciationHistoryが保存された仕訳と紐付けられること"""
        asset = self._create_building_asset()

        self._post_depreciation()

        journal_entry = JournalEntry.objects.get(summary="減価償却費の計上")
        history = DepreciationHistory.objects.get(
            fixed_asset=asset, fiscal_period=self.fiscal_period
        )
        self.assertEqual(history.depreciation_journal_entry, journal_entry)

    def test_post_does_not_duplicate_history_when_already_recorded(self):
        """全資産が計上済みの場合、POSTしてもDepreciationHistoryが増加しないこと"""
        asset = self._create_building_asset()
        DepreciationHistory.objects.create(
            fixed_asset=asset,
            fiscal_period=self.fiscal_period,
            amount=Decimal("500000"),
        )

        # 計上済みのため depreciation ブロックは生成されず、空のPOSTになる
        response = self.client.post(
            reverse("adjustment_entry_new"),
            data={"fiscal_period": str(self.fiscal_period.id)},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            DepreciationHistory.objects.filter(
                fixed_asset=asset, fiscal_period=self.fiscal_period
            ).count(),
            1,
        )
