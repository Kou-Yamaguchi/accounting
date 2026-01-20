from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ledger.models import Account, JournalEntry, Debit, Credit, FixedAsset, Company
from ledger.tests.utils import create_accounts, create_journal_entry, AccountData
from enums.error_messages import ErrorMessages


class JournalEntryViewTest(TestCase):
    """
    journal_entryテーブルに対するCRUD操作のテスト
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="testuser", password="testpass"
        )
        self.client.force_login(self.user)
        self.accounts: dict[str, Account] = create_accounts(
            [
                AccountData(name="現金", type="asset"),
                AccountData(name="売上", type="revenue"),
            ]
        )
        self.entry = create_journal_entry(
            entry_date=date(2024, 1, 1),
            summary="初期取引",
            debits_data=[(self.accounts["現金"], Decimal("1000.00"))],
            credits_data=[(self.accounts["売上"], Decimal("1000.00"))],
            created_by=self.user,
        )

        self.base_post = {
            "date": "2024-01-01",
            "summary": "",
            "debits-TOTAL_FORMS": "0",
            "debits-INITIAL_FORMS": "0",
            "debits-MIN_NUM_FORMS": "0",
            "debits-MAX_NUM_FORMS": "1000",
            "credits-TOTAL_FORMS": "0",
            "credits-INITIAL_FORMS": "0",
            "credits-MIN_NUM_FORMS": "0",
            "credits-MAX_NUM_FORMS": "1000",
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

    def test_journal_entry_list_view(self):
        response = self.client.get(reverse("journal_entry_list"))
        self.assertTemplateUsed(response, "ledger/journal_entry/list.html")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "初期取引")

    def test_create_journal_entry(self):
        data = self.build_post(
            date="2024-01-01",
            summary="テスト取引",
            debit_items=[{"account": self.accounts["現金"].id, "amount": "100.00"}],
            credit_items=[{"account": self.accounts["売上"].id, "amount": "100.00"}],
        )
        response = self.client.post("/ledger/new/", data)
        self.assertEqual(response.status_code, 302)
        journal_entries = JournalEntry.objects.all()
        self.assertEqual(journal_entries.count(), 2)
        self.assertEqual(
            float(
                journal_entries.filter(summary="テスト取引")
                .first()
                .debits.first()
                .amount
            ),
            100.00,
        )
        self.assertEqual(
            float(
                journal_entries.filter(summary="テスト取引")
                .first()
                .credits.first()
                .amount
            ),
            100.00,
        )

    def test_update_journal_entry(self):
        data = self.build_post(
            date="2024-01-02",
            summary="更新取引",
            debit_items=[
                {
                    "id": self.entry.debits.first().id,
                    "account": self.accounts["現金"].id,
                    "amount": "200.00",
                }
            ],
            credit_items=[
                {
                    "id": self.entry.credits.first().id,
                    "account": self.accounts["売上"].id,
                    "amount": "200.00",
                }
            ],
        )
        response = self.client.post(f"/ledger/{self.entry.id}/edit/", data)
        self.assertEqual(response.status_code, 302)
        updated_entry = JournalEntry.objects.get(id=self.entry.id)
        self.assertEqual(updated_entry.summary, "更新取引")
        self.assertEqual(float(updated_entry.debits.first().amount), 200.00)
        self.assertEqual(float(updated_entry.credits.first().amount), 200.00)

    def test_delete_journal_entry(self):
        response = self.client.post(f"/ledger/{self.entry.id}/delete/")
        self.assertEqual(response.status_code, 302)
        journal_entries = JournalEntry.objects.all()
        self.assertEqual(journal_entries.count(), 0)
        self.assertEqual(Debit.objects.count(), 0)
        self.assertEqual(Credit.objects.count(), 0)


class JournalEntryValidationTest(TestCase):
    """
    journal_entryのバリデーションテスト
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="testuser", password="testpass"
        )
        self.client.force_login(self.user)
        self.accounts: dict[str, Account] = create_accounts(
            [
                AccountData(name="現金", type="asset"),
                AccountData(name="売上", type="revenue"),
            ]
        )
        # self.accounts["現金"] = Account.objects.create(name="現金", type="asset")
        # self.accounts["売上"] = Account.objects.create(name="売上", type="revenue")

        self.base_post = {
            "date": "2024-01-01",
            "summary": "",
            "debits-TOTAL_FORMS": "0",
            "debits-INITIAL_FORMS": "0",
            "debits-MIN_NUM_FORMS": "0",
            "debits-MAX_NUM_FORMS": "1000",
            "credits-TOTAL_FORMS": "0",
            "credits-INITIAL_FORMS": "0",
            "credits-MIN_NUM_FORMS": "0",
            "credits-MAX_NUM_FORMS": "1000",
        }

    def build_post(self, date=None, summary=None, debit_items=None, credit_items=None):
        # 同上のヘルパー
        data = self.base_post.copy()
        if date is not None:
            data["date"] = date
        if summary is not None:
            data["summary"] = summary

        if debit_items is not None:
            data["debits-TOTAL_FORMS"] = str(len(debit_items))
            initial_count = sum(1 for it in debit_items if it.get("id") is not None)
            data["debits-INITIAL_FORMS"] = str(initial_count)
            for i, item in enumerate(debit_items):
                if "id" in item:
                    data[f"debits-{i}-id"] = str(item["id"])
                data[f"debits-{i}-account"] = str(item["account"])
                data[f"debits-{i}-amount"] = str(item["amount"])

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

    def test_empty_journal_entry(self):
        data = self.build_post(date="", summary="", debit_items=[], credit_items=[])
        response = self.client.post("/ledger/new/", data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ErrorMessages.REQUIRED.value)

    def test_negative_amount_debit(self):
        data = self.build_post(
            date="2024-01-01",
            summary="負の金額取引",
            debit_items=[{"account": self.accounts["現金"].id, "amount": "-100.00"}],
            credit_items=[{"account": self.accounts["売上"].id, "amount": "100.00"}],
        )
        response = self.client.post("/ledger/new/", data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ErrorMessages.MESSAGE_0003.value)

    def test_unbalanced_journal_entry(self):
        data = self.build_post(
            date="2024-01-01",
            summary="不均衡取引",
            debit_items=[{"account": self.accounts["現金"].id, "amount": "100.00"}],
            credit_items=[{"account": self.accounts["売上"].id, "amount": "50.00"}],
        )
        response = self.client.post("/ledger/new/", data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ErrorMessages.MESSAGE_0001.value)


class JournalEntryWithFixedAssetTest(TestCase):
    """
    仕訳入力時の固定資産登録機能のテスト
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="testuser", password="testpass"
        )
        self.client.force_login(self.user)

        # 会社
        self.company = Company.objects.create(name="テスト株式会社")

        # 勘定科目
        self.accounts = create_accounts(
            [
                AccountData(name="建物", type="asset"),
                AccountData(name="備品", type="asset"),
                AccountData(name="現金", type="asset"),
            ]
        )

        self.base_post = {
            "date": "2024-04-01",
            "summary": "",
            "company": self.company.id,
            "debits-TOTAL_FORMS": "0",
            "debits-INITIAL_FORMS": "0",
            "debits-MIN_NUM_FORMS": "0",
            "debits-MAX_NUM_FORMS": "1000",
            "credits-TOTAL_FORMS": "0",
            "credits-INITIAL_FORMS": "0",
            "credits-MIN_NUM_FORMS": "0",
            "credits-MAX_NUM_FORMS": "1000",
        }

    def build_post(
        self,
        date=None,
        summary=None,
        debit_items=None,
        credit_items=None,
        fixed_asset_data=None,
    ):
        """POSTデータを構築するヘルパーメソッド"""
        data = self.base_post.copy()
        if date is not None:
            data["date"] = date
        if summary is not None:
            data["summary"] = summary

        # デビット
        if debit_items is not None:
            data["debits-TOTAL_FORMS"] = str(len(debit_items))
            for i, item in enumerate(debit_items):
                data[f"debits-{i}-account"] = str(item["account"])
                data[f"debits-{i}-amount"] = str(item["amount"])

        # クレジット
        if credit_items is not None:
            data["credits-TOTAL_FORMS"] = str(len(credit_items))
            for i, item in enumerate(credit_items):
                data[f"credits-{i}-account"] = str(item["account"])
                data[f"credits-{i}-amount"] = str(item["amount"])

        # 固定資産データ
        if fixed_asset_data:
            data.update(fixed_asset_data)

        return data

    def test_create_journal_entry_with_fixed_asset(self):
        """仕訳入力時に固定資産を同時登録するテスト"""
        data = self.build_post(
            date="2024-04-01",
            summary="建物取得",
            debit_items=[
                {"account": self.accounts["建物"].id, "amount": "10000000.00"}
            ],
            credit_items=[
                {"account": self.accounts["現金"].id, "amount": "10000000.00"}
            ],
            fixed_asset_data={
                "register_as_fixed_asset": "on",
                "name": "本社ビル",
                "asset_number": "FA-001",
                "account": self.accounts["建物"].id,
                "useful_life": "20",
                "depreciation_method": "straight_line",
                "residual_value": "0",
            },
        )

        response = self.client.post("/ledger/new/", data)
        self.assertEqual(response.status_code, 302)

        # 仕訳が作成されていることを確認
        journal_entries = JournalEntry.objects.filter(summary="建物取得")
        self.assertEqual(journal_entries.count(), 1)
        je = journal_entries.first()

        # 固定資産が作成されていることを確認
        fixed_assets = FixedAsset.objects.filter(asset_number="FA-001")
        self.assertEqual(fixed_assets.count(), 1)

        fixed_asset = fixed_assets.first()
        self.assertEqual(fixed_asset.name, "本社ビル")
        self.assertEqual(fixed_asset.asset_number, "FA-001")
        self.assertEqual(fixed_asset.account, self.accounts["建物"])
        self.assertEqual(fixed_asset.acquisition_cost, Decimal("10000000.00"))
        self.assertEqual(fixed_asset.acquisition_date, date(2024, 4, 1))
        self.assertEqual(fixed_asset.acquisition_journal_entry, je)
        self.assertEqual(fixed_asset.useful_life, 20)
        self.assertEqual(fixed_asset.depreciation_method, "straight_line")
        self.assertEqual(fixed_asset.residual_value, Decimal("0"))

    def test_create_journal_entry_without_fixed_asset(self):
        """固定資産登録フラグがOFFの場合、固定資産は登録されないテスト"""
        data = self.build_post(
            date="2024-04-01",
            summary="消耗品購入",
            debit_items=[{"account": self.accounts["備品"].id, "amount": "50000.00"}],
            credit_items=[{"account": self.accounts["現金"].id, "amount": "50000.00"}],
            fixed_asset_data={
                "register_as_fixed_asset": "",  # OFF
            },
        )

        response = self.client.post("/ledger/new/", data)
        self.assertEqual(response.status_code, 302)

        # 仕訳のみ作成され、固定資産は作成されていない
        self.assertEqual(JournalEntry.objects.filter(summary="消耗品購入").count(), 1)
        self.assertEqual(FixedAsset.objects.count(), 0)

    def test_fixed_asset_validation_when_flag_on(self):
        """固定資産登録フラグがONの場合、必須フィールドのバリデーションテスト"""
        data = self.build_post(
            date="2024-04-01",
            summary="建物取得",
            debit_items=[{"account": self.accounts["建物"].id, "amount": "5000000.00"}],
            credit_items=[
                {"account": self.accounts["現金"].id, "amount": "5000000.00"}
            ],
            fixed_asset_data={
                "register_as_fixed_asset": "on",
                "name": "",  # 必須フィールドが空
                "asset_number": "",  # 必須フィールドが空
                # account, useful_lifeも未指定
            },
        )

        response = self.client.post("/ledger/new/", data)
        self.assertEqual(response.status_code, 200)  # バリデーションエラーで再表示

        # 固定資産は作成されていない
        self.assertEqual(FixedAsset.objects.count(), 0)

    def test_multiple_debit_accounts_fixed_asset(self):
        """複数の借方科目がある場合、指定した勘定科目の金額のみが取得価額になるテスト"""
        data = self.build_post(
            date="2024-04-01",
            summary="建物と備品を同時取得",
            debit_items=[
                {"account": self.accounts["建物"].id, "amount": "8000000.00"},
                {"account": self.accounts["備品"].id, "amount": "2000000.00"},
            ],
            credit_items=[
                {"account": self.accounts["現金"].id, "amount": "10000000.00"}
            ],
            fixed_asset_data={
                "register_as_fixed_asset": "on",
                "name": "本社ビル",
                "asset_number": "FA-001",
                "account": self.accounts["建物"].id,  # 建物のみ
                "useful_life": "20",
                "depreciation_method": "straight_line",
                "residual_value": "0",
            },
        )

        response = self.client.post("/ledger/new/", data)
        self.assertEqual(response.status_code, 302)

        # 固定資産の取得価額は建物の金額（8,000,000）のみ
        fixed_asset = FixedAsset.objects.get(asset_number="FA-001")
        self.assertEqual(fixed_asset.acquisition_cost, Decimal("8000000.00"))
