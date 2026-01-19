from datetime import date, datetime
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum


class FiscalPeriod(models.Model):
    """
    会計期間を管理するモデル。
    """

    name = models.CharField(
        max_length=100, unique=True, verbose_name="会計期間名", null=False
    )
    start_date = models.DateField(null=False, verbose_name="会計期間開始日")
    end_date = models.DateField(null=False, verbose_name="会計期間終了日")
    is_closed = models.BooleanField(
        null=False, default=False, verbose_name="締め済みフラグ"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="作成日時")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新日時")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fiscalperiods_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fiscalperiods_updated",
    )

    class Meta:
        verbose_name = "Fiscal Period"
        verbose_name_plural = "Fiscal Periods"

    def __str__(self):
        return f"{self.start_date} to {self.end_date}"


ACCOUNT_TYPE_CHOICES = [
    ("asset", "資産"),
    ("liability", "負債"),
    ("equity", "純資産"),
    ("revenue", "収益"),
    ("expense", "費用"),
]


class Account(models.Model):
    """
    accounts (勘定科目)
    """

    name = models.CharField(max_length=200, unique=True)
    type = models.CharField(max_length=64, choices=ACCOUNT_TYPE_CHOICES, null=False)
    is_default = models.BooleanField(default=False)
    is_adjustment_only = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="accounts_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="accounts_updated",
    )

    class Meta:
        verbose_name = "Account"
        verbose_name_plural = "Accounts"

    def __str__(self):
        return self.name


class Company(models.Model):
    """
    会社情報を管理するモデル。
    """

    name = models.CharField(max_length=255, verbose_name="会社名")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="作成日時")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新日時")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="company_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="company_updated",
    )

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"

    def __str__(self):
        return self.name


ENTRY_TYPE_CHOICES = [
    ("normal", "通常仕訳"),
    ("adjustment", "決算整理仕訳"),
    ("closing", "決算振替仕訳"),
]


class JournalEntry(models.Model):
    """
    journal_entries (取引) — 仕訳ヘッダ
    """

    date = models.DateField(null=False, verbose_name="取引日")
    summary = models.TextField(blank=True, verbose_name="摘要")
    entry_type = models.CharField(
        max_length=32,
        choices=ENTRY_TYPE_CHOICES,
        default="normal",
        verbose_name="仕訳タイプ",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    company = models.ForeignKey(
        Company,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="companies",
    )
    fiscal_period = models.ForeignKey(
        FiscalPeriod,
        # TODO: null許容を外す
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="journal_entries",
        verbose_name="会計期間",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="journalentries_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="journalentries_updated",
    )

    class Meta:
        verbose_name = "Journal Entry"
        verbose_name_plural = "Journal Entries"
        ordering = ["-date", "-created_at"]
        # constraints = [
        #     models.CheckConstraint(
        #         check=~(
        #             models.Q(entry_type__in=['adjustment', 'closing']) &
        #             ~models.Q(date=models.F('fiscal_period__end_date'))
        #         ),
        #         name='adjustment_closing_must_be_end_date'
        #     )
        # ]

    def __str__(self):
        return f"{self.date} — {self.summary[:50]}"


class Entry(models.Model):
    """
    抽象基底クラス: 仕訳の明細行 (借方・貸方) の共通部分を定義
    """

    amount = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Debit(Entry):
    """
    debits (借方明細)
    """

    journal_entry = models.ForeignKey(
        JournalEntry, on_delete=models.CASCADE, related_name="debits"
    )
    account = models.ForeignKey(
        Account, on_delete=models.RESTRICT, related_name="debits"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="debits_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="debits_updated",
    )

    class Meta:
        verbose_name = "Debit"
        verbose_name_plural = "Debits"

    def __str__(self):
        return f"Debit {self.amount} — {self.account}"


class Credit(Entry):
    """
    credits (貸方明細)
    """

    journal_entry = models.ForeignKey(
        JournalEntry, on_delete=models.CASCADE, related_name="credits"
    )
    account = models.ForeignKey(
        Account, on_delete=models.RESTRICT, related_name="credits"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="credits_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="credits_updated",
    )

    class Meta:
        verbose_name = "Credit"
        verbose_name_plural = "Credits"

    def __str__(self):
        return f"Credit {self.amount} — {self.account}"


class InitialBalance(models.Model):
    """
    期首残高、またはシステム導入時の開始残高を管理するモデル。
    """

    account = models.OneToOneField(
        Account, on_delete=models.CASCADE, primary_key=True, verbose_name="勘定科目"
    )
    balance = models.IntegerField(default=0, verbose_name="残高")
    start_date = models.DateField(
        default=date(datetime.now().year, 4, 1), verbose_name="会計期間開始日"
    )

    class Meta:
        verbose_name = "Initial Balance"
        verbose_name_plural = "Initial Balances"


class Item(models.Model):
    """
    商品・サービスを管理するモデル。
    """

    name = models.CharField(max_length=255, verbose_name="商品名")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="作成日時")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新日時")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="items_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="items_updated",
    )

    class Meta:
        verbose_name = "Item"
        verbose_name_plural = "Items"

    def __str__(self):
        return self.name


class SalesDetail(models.Model):
    """
    売上明細を管理するモデル。
    """

    quantity = models.IntegerField(verbose_name="数量")
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="単価"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="作成日時")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新日時")
    item = models.ForeignKey(
        Item,
        null=False,
        blank=False,
        on_delete=models.CASCADE,
        related_name="sales_details",
    )
    journal_entry = models.ForeignKey(
        JournalEntry,
        null=False,
        blank=False,
        on_delete=models.CASCADE,
        related_name="sales_details",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sales_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sales_updated",
    )

    class Meta:
        verbose_name = "Sales Detail"
        verbose_name_plural = "Sales Details"

    def __str__(self):
        return f"{self.item} - {self.quantity} - {self.unit_price}"


class PurchaseDetail(models.Model):
    """
    仕入明細を管理するモデル。
    """

    quantity = models.IntegerField(verbose_name="数量")
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="単価"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="作成日時")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新日時")
    item = models.ForeignKey(
        Item,
        null=False,
        blank=False,
        on_delete=models.CASCADE,
        related_name="purchase_details",
    )
    journal_entry = models.ForeignKey(
        JournalEntry,
        null=False,
        blank=False,
        on_delete=models.CASCADE,
        related_name="purchase_details",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_updated",
    )

    class Meta:
        verbose_name = "Purchase Detail"
        verbose_name_plural = "purchase_details"

    def __str__(self):
        return f"{self.item} - {self.quantity} - {self.unit_price}"


class FixedAsset(models.Model):
    """固定資産台帳"""

    # 基本情報
    name = models.CharField(max_length=255, verbose_name="資産名")
    asset_number = models.CharField(max_length=50, unique=True, verbose_name="資産番号")
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        limit_choices_to={"type": "asset"},
        verbose_name="勘定科目",
    )

    # 取得情報
    acquisition_date = models.DateField(verbose_name="取得日")
    acquisition_cost = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="取得価額"
    )
    acquisition_journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.PROTECT,
        related_name="acquired_assets",
        null=True,
        blank=True,
        verbose_name="取得仕訳",
    )

    # 償却情報
    depreciation_method = models.CharField(
        max_length=20,
        choices=[
            ("straight_line", "定額法"),
            ("declining_balance", "定率法"),
        ],
        default="straight_line",
        verbose_name="償却方法",
    )
    useful_life = models.IntegerField(verbose_name="耐用年数")
    residual_value = models.DecimalField(
        max_digits=14, decimal_places=2, default=0, verbose_name="残存価額"
    )

    # ステータス
    status = models.CharField(
        max_length=20,
        choices=[
            ("active", "使用中"),
            ("disposed", "除却済"),
            ("sold", "売却済"),
        ],
        default="active",
        verbose_name="ステータス",
    )
    disposal_date = models.DateField(null=True, blank=True, verbose_name="除却/売却日")
    disposal_journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.PROTECT,
        related_name="disposed_assets",
        null=True,
        blank=True,
        verbose_name="除却/売却仕訳",
    )

    # メタ情報
    company = models.ForeignKey(Company, on_delete=models.CASCADE, verbose_name="会社")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="作成日時")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新日時")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fixedassets_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fixedassets_updated",
    )

    class Meta:
        verbose_name = "固定資産"
        verbose_name_plural = "固定資産台帳"
        ordering = ["asset_number"]

    def __str__(self):
        return f"{self.asset_number} - {self.name}"

    def calculate_annual_depreciation(self) -> Decimal:
        """年間減価償却費を計算"""
        if self.depreciation_method == "straight_line":
            return (self.acquisition_cost - self.residual_value) / self.useful_life
        # TODO: 定率法の計算も追加可能
        return Decimal("0")

    def get_accumulated_depreciation(self, as_of_date: date) -> Decimal:
        """指定日時点での減価償却累計額を取得"""
        total = self.depreciation_history.filter(
            fiscal_period__end_date__lte=as_of_date
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        return total

    def get_book_value(self, as_of_date: date) -> Decimal:
        """帳簿価額を計算"""
        accumulated = self.get_accumulated_depreciation(as_of_date)
        return self.acquisition_cost - accumulated


class DepreciationHistory(models.Model):
    """減価償却の履歴を記録"""

    fixed_asset = models.ForeignKey(
        FixedAsset,
        on_delete=models.CASCADE,
        related_name="depreciation_history",
        verbose_name="固定資産",
    )
    fiscal_period = models.ForeignKey(
        FiscalPeriod, on_delete=models.PROTECT, verbose_name="会計期間"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="償却額")
    depreciation_journal_entry = models.OneToOneField(
        JournalEntry,
        on_delete=models.PROTECT,
        related_name="depreciation_record",
        null=True,
        blank=True,
        verbose_name="減価償却仕訳",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="作成日時")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新日時")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="depreciationhistories_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="depreciationhistories_updated",
    )

    class Meta:
        verbose_name = "減価償却履歴"
        verbose_name_plural = "減価償却履歴"
        unique_together = [["fixed_asset", "fiscal_period"]]
        ordering = ["-fiscal_period__end_date"]

    def __str__(self):
        return f"{self.fixed_asset.name} - {self.fiscal_period.name}: {self.amount}"
