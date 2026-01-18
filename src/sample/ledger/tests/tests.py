from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ledger.models import (
    Debit,
    Credit,
    InitialBalance,
    Item,
    PurchaseDetail,
    Company,
)
from ledger.views import (
    PurchaseBookView,
    PurchaseBookEntry,
)
from ledger.services import calculate_monthly_balance
from ledger.tests.utils import create_accounts, create_journal_entry, AccountData


class CashBookCalculationTest(TestCase):

    # テスト開始前に必要なマスタデータ（勘定科目）を作成
    @classmethod
    def setUpTestData(cls):
        cls.accounts = create_accounts(
            [
                AccountData(name="現金", type="Asset"),
                AccountData(name="売上", type="Revenue"),
                AccountData(name="消耗品費", type="Expense"),
                AccountData(name="雑収入", type="Revenue"),
            ]
        )
        # 現金出納帳の対象科目
        cls.cash_account = cls.accounts["現金"]
        # 相手勘定科目
        cls.sales_account = cls.accounts["売上"]
        cls.supplies_account = cls.accounts["消耗品費"]
        cls.unknown_account = cls.accounts["雑収入"]

    # --- ユーザーが要求したケース ---

    ## 1. 初期残高がある場合とない場合
    def test_initial_balance_cases(self):
        """初期残高がある場合（前月繰越あり）とない場合（0）のテスト"""

        # 【ケースA: 初期残高設定なし = 0】
        # InitialBalanceを作成しない状態
        result_no_initial = calculate_monthly_balance("現金", 2025, 1)
        self.assertEqual(
            result_no_initial["data"][0]["summary"],
            "前月繰越",
            "前月繰越の行が存在すること",
        )
        # InitialBalanceがない場合は「期首残高が設定されていません。」という警告を出す仕様としている。(エラーは出さない)
        # 今回はテスト用に、InitialBalanceをあえて作らずにテストする。
        result_no_initial = calculate_monthly_balance("現金", 2025, 1)
        self.assertEqual(result_no_initial["data"][0]["balance"], 0)
        self.assertEqual(result_no_initial["ending_balance"], 0)

        # --- ここから、InitialBalanceが設定されていることを前提とする ---

        # 【ケースB: 初期残高あり (2025/01/01期首)】
        # 2025/01/01を会計期間開始日とし、残高50000を設定
        InitialBalance.objects.create(
            account=self.cash_account, balance=50000, start_date=date(2025, 1, 1)
        )

        # 1月の取引は作成しない
        result_with_initial = calculate_monthly_balance("現金", 2025, 1)

        # 前月繰越が50000であること
        self.assertEqual(result_with_initial["data"][0]["balance"], 50000)
        # 次月繰越（最終行）の残高が50000であること
        self.assertEqual(result_with_initial["ending_balance"], 50000)

    ## 2. 1ヶ月分の集計が正しくできるかどうか
    def test_single_month_calculation(self):
        """1ヶ月内の収入と支出が正しく計算されるか"""
        InitialBalance.objects.create(
            account=self.cash_account, balance=10000, start_date=date(2025, 4, 1)
        )

        # 4月10日: 収入 (売上) 5000
        je1 = create_journal_entry(
            date(2025, 4, 10),
            "売上入金",
            [(self.cash_account, Decimal("5000"))],
            [(self.sales_account, Decimal("5000"))],
            None,  # Company is None for this test
        )

        # 4月20日: 支出 (消耗品費) 2000
        je2 = create_journal_entry(
            date(2025, 4, 20),
            "文房具購入",
            [(self.supplies_account, Decimal("2000"))],
            [(self.cash_account, Decimal("2000"))],
            None,  # Company is None for this test
        )

        result = calculate_monthly_balance("現金", 2025, 4)
        data = result["data"]

        # 前月繰越: 10000 (0行目)
        self.assertEqual(data[0]["balance"], 10000)

        # 収入取引: 5000 (1行目)
        self.assertEqual(data[1]["income"], 5000)
        self.assertEqual(data[1]["balance"], 10000 + 5000)  # 15000
        self.assertEqual(
            data[1]["summary"], "売上"
        )  # 相手勘定科目が摘要になっていること

        # 支出取引: 2000 (2行目)
        self.assertEqual(data[2]["expense"], 2000)
        self.assertEqual(data[2]["balance"], 15000 - 2000)  # 13000
        self.assertEqual(
            data[2]["summary"], "消耗品費"
        )  # 相手勘定科目が摘要になっていること

        # 次月繰越（最終行）
        self.assertEqual(result["ending_balance"], 13000)

    ## 3. 2ヶ月分の集計が正しくできるかどうか (繰越残高の検証)
    def test_two_month_carryover(self):
        """前月の残高が次月へ正しく繰り越されるか（前月繰越残高の計算ロジック検証）"""

        # 2025/03/01期首、残高 50000
        InitialBalance.objects.create(
            account=self.cash_account, balance=50000, start_date=date(2025, 3, 1)
        )

        # 3月取引: 収入 +10000
        je3 = create_journal_entry(
            date(2025, 3, 15),
            "3月入金",
            [(self.cash_account, Decimal("10000"))],
            [(self.unknown_account, Decimal("10000"))],
            None,  # Company is None for this test
        )

        # --- 3月集計結果確認 ---
        result_march = calculate_monthly_balance("現金", 2025, 3)
        self.assertEqual(
            result_march["ending_balance"],
            60000,
            "3月残高が正しく計算されていること (50000 + 10000)",
        )

        # --- 4月集計結果確認 (3月の残高が前月繰越になっていること) ---

        # 4月取引: 支出 -5000
        je4 = create_journal_entry(
            date(2025, 4, 10),
            "4月出金",
            [(self.supplies_account, Decimal("5000"))],
            [(self.cash_account, Decimal("5000"))],
            None,  # Company is None for this test
        )

        result_april = calculate_monthly_balance("現金", 2025, 4)
        data_april = result_april["data"]

        # 4月の前月繰越（0行目）が3月の最終残高(60000)と一致すること
        self.assertEqual(
            data_april[0]["balance"],
            60000,
            "4月の前月繰越が3月の最終残高と一致すること",
        )

        # 4月の最終残高 (60000 - 5000)
        self.assertEqual(
            result_april["ending_balance"],
            55000,
            "4月の最終残高が正しく計算されていること",
        )

    ## 4. 仕訳の入力内容が変更になった場合の集計
    def test_recalculation_after_change(self):
        """過去の取引を変更した場合に集計し直せるか"""
        # (ロジックがキャッシュを使用していないため、関数を再実行するだけで実現可能)

        # 2025/05/01期首、残高 10000
        InitialBalance.objects.create(
            account=self.cash_account, balance=10000, start_date=date(2025, 5, 1)
        )

        # 5月取引: 収入 (売上) 5000
        je5 = create_journal_entry(
            date(2025, 5, 10),
            "売上入金",
            [(self.cash_account, Decimal("5000"))],
            [(self.sales_account, Decimal("5000"))],
            None,  # Company is None for this test
        )

        # 5月最終残高: 10000 + 5000 = 15000
        result_initial = calculate_monthly_balance("現金", 2025, 5)
        self.assertEqual(result_initial["ending_balance"], 15000)

        # 過去の仕訳（je5）の金額を修正
        Debit.objects.filter(journal_entry=je5, account=self.cash_account).update(
            amount=8000
        )
        Credit.objects.filter(journal_entry=je5, account=self.sales_account).update(
            amount=8000
        )

        # 再集計
        result_recalculated = calculate_monthly_balance("現金", 2025, 5)

        # 修正後の最終残高: 10000 + 8000 = 18000
        self.assertEqual(
            result_recalculated["ending_balance"],
            18000,
            "仕訳変更後、残高が正しく再計算されること",
        )

    # --- 追加テストケース ---

    ## 5. 月末日と月初日の取引処理
    def test_month_boundary_transactions(self):
        """集計期間の境界（前月末日、当月1日、当月末日、翌月1日）の取引が正しく含まれるか/除外されるか"""

        # 2025/06/01期首、残高 5000
        InitialBalance.objects.create(
            account=self.cash_account, balance=5000, start_date=date(2025, 6, 1)
        )

        # 7月集計

        # 6月30日 (前月末): 収入 1000 -> 7月の集計に含めない (前月繰越に影響)
        je_prev = create_journal_entry(
            date(2025, 6, 30),
            "6月取引",
            [(self.cash_account, Decimal("1000"))],
            [(self.sales_account, Decimal("1000"))],
            None,  # Company is None for this test
        )

        # 7月1日 (月初): 支出 500 -> 7月の集計に含める
        je_start = create_journal_entry(
            date(2025, 7, 1),
            "7月1日取引",
            [(self.supplies_account, Decimal("500"))],
            [(self.cash_account, Decimal("500"))],
            None,  # Company is None for this test
        )

        # 7月31日 (月末): 収入 2000 -> 7月の集計に含める
        je_end = create_journal_entry(
            date(2025, 7, 31),
            "7月31日取引",
            [(self.cash_account, Decimal("2000"))],
            [(self.sales_account, Decimal("2000"))],
            None,  # Company is None for this test
        )

        # 8月1日 (翌月): 支出 3000 -> 7月の集計に含めない
        je_next = create_journal_entry(
            date(2025, 8, 1),
            "8月1日取引",
            [(self.supplies_account, Decimal("3000"))],
            [(self.cash_account, Decimal("3000"))],
            None,  # Company is None for this test
        )

        result_july = calculate_monthly_balance("現金", 2025, 7)
        data_july = result_july["data"]

        # 前月繰越の確認: 初期残高5000 + 6月30日の取引1000 = 6000
        self.assertEqual(
            data_july[0]["balance"],
            6000,
            "前月繰越に残月取引が正しく反映されていること",
        )

        # 7月の取引件数（前月繰越、月初、月末、次月繰越の計4行）
        self.assertEqual(
            len(data_july), 4, "当月取引（月初、月末の2件）のみが抽出されていること"
        )

        # 最終残高の確認: 6000 (繰越) - 500 (月初) + 2000 (月末) = 7500
        self.assertEqual(result_july["ending_balance"], 7500)

    ## 6. 仕訳ヘッダーの摘要 (summary) が空欄の場合のフォールバック
    def test_summary_fallback(self):
        """仕訳に総合摘要がない場合でも相手勘定科目が摘要として使われるか"""

        # 2025/08/01期首、残高 10000
        InitialBalance.objects.create(
            account=self.cash_account, balance=10000, start_date=date(2025, 8, 1)
        )

        # 8月取引: 収入 (売上) 5000、summaryは空欄
        je6 = create_journal_entry(
            date(2025, 8, 15),
            "",
            [(self.cash_account, Decimal("5000"))],
            [(self.sales_account, Decimal("5000"))],
            None,  # Company is None for this test
        )

        result = calculate_monthly_balance("現金", 2025, 8)
        data = result["data"]

        # 収入取引の摘要が相手勘定（売上）になっていること
        self.assertEqual(
            data[1]["summary"],
            "売上",
            "summaryが空欄でも相手勘定科目が摘要になること",
        )


class PurchaseBookViewTest(TestCase):
    """
    PurchaseBookViewのテスト
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="testuser", password="testpass"
        )
        self.client.force_login(self.user)

    # 必要なマスタデータを作成
    @classmethod
    def setUpTestData(cls):
        cls.accounts = create_accounts(
            [
                AccountData(name="仕入", type="Expense"),
                AccountData(name="買掛金", type="Liability"),
                AccountData(name="現金", type="Asset"),
            ]
        )
        cls.purchase = cls.accounts["仕入"]
        cls.accounts_payable = cls.accounts["買掛金"]
        cls.cash = cls.accounts["現金"]

        cls.co_a = Company.objects.create(name="甲社")
        cls.co_b = Company.objects.create(name="乙社")

        cls.item_y = Item.objects.create(name="Y商品")
        cls.item_z = Item.objects.create(name="Z商品")

    # --- ユーザーが要求した基本的なケースのテスト ---

    def test_basic_purchase_and_total(self):
        """1ヶ月分の正常な仕入と総仕入高の集計テスト"""

        # 2025/4/10: 甲社から掛仕入 (仕入 3000 / 買掛金 3000)
        je1 = create_journal_entry(
            date(2025, 4, 10),
            "掛仕入",
            [(self.purchase, 3000)],
            [(self.accounts_payable, 3000)],
            self.co_a,
        )
        PurchaseDetail.objects.create(
            journal_entry=je1, item=self.item_y, quantity=10, unit_price=300
        )

        # 2025/4/20: 乙社から現金仕入 (仕入 5000 / 現金 5000)
        je2 = create_journal_entry(
            date(2025, 4, 20),
            "現金仕入",
            [(self.purchase, 5000)],
            [(self.cash, 5000)],
            self.co_b,
        )
        PurchaseDetail.objects.create(
            journal_entry=je2, item=self.item_z, quantity=5, unit_price=1000
        )

        response = self.client.get(reverse("purchase_book", args=[2025, 4]))

        closing_entry = response.context["purchase_book"].closing_entry

        # 総仕入高の確認 (3000 + 5000 = 8000)
        self.assertEqual(
            closing_entry.total_purchase, 8000, "総仕入高が正しく集計されていること"
        )
        # 純仕入高の確認 (戻しがないため8000)
        self.assertEqual(
            closing_entry.net_purchase, 8000, "純仕入高が正しく集計されていること"
        )
        # データ件数 (取引2件, 明細2件 + 総仕入高/戻し/純仕入高の行はサービス側で集計) -> 2つの取引ヘッダー行と2つの明細行
        # self.assertEqual(
        #     len(response.context["book_entries"]["details"]), 4, "取引2件のヘッダーと明細が正しく作成されていること"
        # )

        # 明細行の内訳金額の確認
        # self.assertEqual(
        #     response.context["book_entries"]["details"][1]["total_amount"], 3000, "Y商品の内訳金額が正しいこと"
        # )

    # --- 追加ケース A: 仕入戻し・値引き取引の処理 ---
    def test_purchase_returns(self):
        """仕入戻し（貸方 仕入）が正しくマイナスとして処理され、純仕入高に反映されること"""

        je3 = create_journal_entry(
            date(2025, 5, 5),
            "掛仕入",
            [(self.purchase, 10000)],
            [(self.accounts_payable, 10000)],
            self.co_a,
        )
        PurchaseDetail.objects.create(
            journal_entry=je3, item=self.item_y, quantity=20, unit_price=500
        )

        # 2025/5/15: 仕入戻し (買掛金 2000 / 仕入 2000) -> 貸方に仕入が来る
        je4 = create_journal_entry(
            date(2025, 5, 15),
            "品違いによる返品",
            [(self.accounts_payable, 2000)],
            [(self.purchase, 2000)],
            self.co_a,
        )
        PurchaseDetail.objects.create(
            journal_entry=je4, item=self.item_y, quantity=4, unit_price=500
        )  # 明細もマイナス分を作成

        # response = self.client.get("/ledger/purchase_book/2025/5/")
        response = self.client.get(reverse("purchase_book", args=[2025, 5]))

        closing_entry = response.context["purchase_book"].closing_entry

        # 総仕入高の確認
        self.assertEqual(
            closing_entry.total_purchase,
            10000,
            "総仕入高には通常仕入のみが計上されること",
        )
        # 仕入戻し高の確認
        self.assertEqual(
            closing_entry.total_returns, 2000, "仕入戻し高が正しく計上されること"
        )
        # 純仕入高の確認 (10000 - 2000 = 8000)
        self.assertEqual(
            closing_entry.net_purchase, 8000, "純仕入高が正しく計算されていること"
        )

        # 仕入戻し取引の表示内容確認
        return_header: PurchaseBookEntry = response.context[
            "purchase_book"
        ].book_entries[
            1
        ]  # 2件目の取引が戻し
        self.assertTrue(
            return_header.is_return, "仕入戻し取引であると識別されていること"
        )
        # self.assertEqual(
        #     return_header["main_summary"], "掛戻し", "仕入戻しの摘要が正しいこと"
        # )

    # --- 追加ケース B: 仕訳と明細の不一致 ---
    def test_mismatch_validation(self):
        """仕訳の金額と明細の合計金額が一致しない場合にエラーが記録されること"""

        # 2025/6/01: 不一致仕入 (仕入 10000 / 買掛金 10000)
        je5 = create_journal_entry(
            date(2025, 6, 1),
            "金額不一致テスト",
            [(self.purchase, 10000)],
            [(self.accounts_payable, 10000)],
            self.co_b,
        )
        # 明細の合計は 10個 * 500 = 5000 (仕訳金額10000と不一致)
        PurchaseDetail.objects.create(
            journal_entry=je5, item=self.item_z, quantity=10, unit_price=500
        )

        response = self.client.get(reverse("purchase_book", args=[2025, 6]))

        # エラーメッセージがヘッダー行に記録されていること
        # header_line = response.context["data"][0]
        # self.assertIsNotNone(
        #     header_line["error"],
        #     "金額不一致の場合、エラーメッセージが記録されていること",
        # )
        self.assertIn(
            "内訳金額合計が仕訳金額と一致しません。",
            response.context["error"],
            "エラーメッセージに'金額不一致'が含まれていること",
        )

    # --- 追加ケース C: 複数商品取引の処理 ---
    # def test_multi_item_transaction(self):
    #     """一つの仕訳で複数の商品を扱った場合、複数行として正しく表示されること"""

    #     # 2025/7/01: 複数商品仕入 (仕入 760 / 買掛金 760) -> 添付画像と同じ金額
    #     je6 = self.create_journal_entry(
    #         "2025-07-01",
    #         self.co_b,
    #         "複数商品仕入",
    #         self.purchase,
    #         760,
    #         self.accounts_payable,
    #         760,
    #     )
    #     PurchaseDetail.objects.create(
    #         journal_entry=je6, item=self.item_y, quantity=8, unit_price=50
    #     )  # 内訳 400
    #     PurchaseDetail.objects.create(
    #         journal_entry=je6, item=self.item_z, quantity=6, unit_price=60
    #     )  # 内訳 360

    #     response = self.client.get(reverse("purchase_book", args=[2025, 7]))
    #     data = response.context["data"]

    #     # データ件数 (ヘッダー1行 + 明細2行 + 総仕入/戻し/純仕入の集計行)
    #     self.assertEqual(
    #         len(data), 3 + 3, "取引1件（明細2件）で3行のデータが作成されていること"
    #     )

    #     # ヘッダー行 (0行目)
    #     self.assertEqual(data[0]["type"], "header")
    #     self.assertEqual(data[0]["company_name"], "乙社")
    #     self.assertEqual(data[0]["total_amount"], 760)

    #     # 明細1行目 (1行目)
    #     self.assertEqual(data[1]["type"], "detail")
    #     self.assertEqual(data[1]["item_name"], "Y商品")
    #     self.assertEqual(data[1]["sub_total"], 400)

    #     # 明細2行目 (2行目)
    #     self.assertEqual(data[2]["type"], "detail")
    #     self.assertEqual(data[2]["item_name"], "Z商品")
    #     self.assertEqual(data[2]["sub_total"], 360)
