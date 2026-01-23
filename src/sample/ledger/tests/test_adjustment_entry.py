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

    def test_form_includes_fiscal_period_field(self):
        """fiscal_periodフィールドが含まれていることを確認"""
        form = AdjustmentJournalEntryForm()
        self.assertIn("fiscal_period", form.fields)

    def test_fiscal_period_queryset_excludes_closed_periods(self):
        """クローズ済み期間が選択肢から除外されることを確認"""
        form = AdjustmentJournalEntryForm()
        fiscal_periods = list(form.fields["fiscal_period"].queryset)

        self.assertIn(self.fiscal_period_open, fiscal_periods)
        self.assertNotIn(self.fiscal_period_closed, fiscal_periods)

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

        self.base_post = {
            "fiscal_period": str(self.fiscal_period.id),
            "summary": "決算整理仕訳",
            "company": str(self.company.id),
            "debits-TOTAL_FORMS": "0",
            "debits-INITIAL_FORMS": "0",
            "credits-TOTAL_FORMS": "0",
            "credits-INITIAL_FORMS": "0",
        }

    def build_post(self, date=None, summary=None, debit_items=None, credit_items=None):
        """
        debit_items / credit_items はリスト。各要素は
        {'account': account_id, 'amount': '123.45', 'id': existing_id (optional)}
        を想定する。id がある要素は INITIAL_FORMS のカウントに含める。
        """
        data = self.base_post.copy()
        if date is not None:
            data["date"] = date
        if summary is not None:
            data["summary"] = summary

        # デビット
        if debit_items is not None:
            data["debits-TOTAL_FORMS"] = str(len(debit_items))
            initial_count = sum(1 for it in debit_items if it.get("id") is not None)
            data["debits-INITIAL_FORMS"] = str(initial_count)
            for i, item in enumerate(debit_items):
                if "id" in item:
                    data[f"debits-{i}-id"] = str(item["id"])
                data[f"debits-{i}-account"] = str(item["account"])
                data[f"debits-{i}-amount"] = str(item["amount"])

        # クレジット
        if credit_items is not None:
            data["credits-TOTAL_FORMS"] = str(len(credit_items))
            initial_count = sum(1 for it in credit_items if it.get("id") is not None)
            data["credits-INITIAL_FORMS"] = str(initial_count)
            for i, item in enumerate(credit_items):
                if "id" in item:
                    data[f"credits-{i}-id"] = str(item["id"])
                data[f"credits-{i}-account"] = str(item["account"])
                data[f"credits-{i}-amount"] = str(item["amount"])

        return data

    def test_get_context_includes_reference_info(self):
        """コンテキストに参考情報が含まれることを確認"""
        view = AdjustmentEntryCreateView()
        view.request = self.factory.get(
            reverse("adjustment_entry_new"),
            {"fiscal_period_id": self.fiscal_period.id},
        )

        context = view.get_context_data()

        # 参考情報が含まれていることを確認
        self.assertIn("reference_info", context)
        reference_info = context["reference_info"]

        # 減価償却と貸倒引当金の情報が含まれることを確認
        self.assertIn("depreciation", reference_info)
        self.assertIn("allowance", reference_info)

    def test_get_context_with_fiscal_period(self):
        """会計期間が選択されている場合のコンテキストを確認"""
        view = AdjustmentEntryCreateView()
        view.request = self.factory.get(
            reverse("adjustment_entry_new"),
            {"fiscal_period_id": self.fiscal_period.id},
        )

        context = view.get_context_data()

        self.assertIn("selected_fiscal_period", context)
        self.assertEqual(context["selected_fiscal_period"], self.fiscal_period)

    def test_form_valid_sets_date_to_period_end(self):
        """form_validで日付が期末日に設定されることを確認"""
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

        FixedAsset.objects.create(
            name="本社ビル",
            account=building_account,
            acquisition_date=date(2024, 4, 1),
            acquisition_cost=Decimal("10000000"),
            useful_life=20,
            residual_value=Decimal("0"),
            acquisition_journal_entry=je,
        )

        # POSTデータを準備
        # post_data = {
        #     "fiscal_period": self.fiscal_period.id,
        #     "summary": "決算整理仕訳",
        #     "company": self.company.id,
        #     "debit-TOTAL_FORMS": "1",
        #     "debit-INITIAL_FORMS": "0",
        #     "debit-0-account": Account.objects.get(name="減価償却費").id,
        #     "debit-0-amount": "500000",
        #     "credit-TOTAL_FORMS": "1",
        #     "credit-INITIAL_FORMS": "0",
        #     "credit-0-account": Account.objects.get(name="減価償却累計額").id,
        #     "credit-0-amount": "500000",
        # }
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
        # POSTデータを準備
        # NOTE: 以下のコメントアウト部分は参考用に残しています
        # post_data = {
        #     "fiscal_period": self.fiscal_period.id,
        #     "summary": "決算整理仕訳",
        #     "company": self.company.id,
        #     "debit-TOTAL_FORMS": "1",
        #     "debit-INITIAL_FORMS": "1",
        #     "debit-0-account": Account.objects.get(name="減価償却費").id,
        #     "debit-0-amount": "500000",
        #     "credit-TOTAL_FORMS": "1",
        #     "credit-INITIAL_FORMS": "1",
        #     "credit-0-account": Account.objects.get(name="減価償却累計額").id,
        #     "credit-0-amount": "500000",
        # }

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
        journal_entry: JournalEntry = JournalEntry.objects.filter(summary="決算整理仕訳").first()

        self.assertIsNotNone(journal_entry)
        # entry_typeがadjustmentに設定されていることを確認
        self.assertEqual(journal_entry.entry_type, "adjustment")

    def test_form_valid_sets_fiscal_period(self):
        """form_validでfiscal_periodが設定されることを確認"""
        # POSTデータを準備
        # NOTE: 以下のコメントアウト部分は参考用に残しています
        # このデータだと動作しないため、下の build_post を使っています
        # post_data = {
        #     "fiscal_period": self.fiscal_period.id,
        #     "summary": "決算整理仕訳",
        #     "company": self.company.id,
        #     "debit-TOTAL_FORMS": "1",
        #     "debit-INITIAL_FORMS": "0",
        #     "debit-0-account": Account.objects.get(name="減価償却費").id,
        #     "debit-0-amount": "500000",
        #     "credit-TOTAL_FORMS": "1",
        #     "credit-INITIAL_FORMS": "0",
        #     "credit-0-account": Account.objects.get(name="減価償却累計額").id,
        #     "credit-0-amount": "500000",
        # }

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

        # ビューからコンテキストを取得
        view = AdjustmentEntryCreateView()
        view.request = self.factory.get(
            reverse("adjustment_entry_new"),
            {"fiscal_period_id": self.fiscal_period.id},
        )

        context = view.get_context_data()
        reference_info = context["reference_info"]

        # 減価償却情報が含まれることを確認
        self.assertIn("depreciation", reference_info)
        depreciation = reference_info["depreciation"]

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

        # ビューからコンテキストを取得
        view = AdjustmentEntryCreateView()
        view.request = self.factory.get(
            reverse("adjustment_entry_new"),
            {"fiscal_period_id": self.fiscal_period.id},
        )

        context = view.get_context_data()
        reference_info = context["reference_info"]

        # 貸倒引当金情報が含まれることを確認
        self.assertIn("allowance", reference_info)
        allowance = reference_info["allowance"]

        # 売掛金残高が含まれることを確認
        self.assertIn("receivables_balance", allowance)
        self.assertEqual(allowance["receivables_balance"], Decimal("1000000"))

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
