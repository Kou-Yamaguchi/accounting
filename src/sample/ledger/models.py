from django.conf import settings
from django.db import models
from datetime import date, datetime

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
    type = models.CharField(max_length=64, choices=ACCOUNT_TYPE_CHOICES)
    is_default = models.BooleanField(default=False)
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


class JournalEntry(models.Model):
    """
    journal_entries (取引) — 仕訳ヘッダ
    """

    date = models.DateField()
    summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    company = models.ForeignKey(
        Company,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="companies",
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

    def __str__(self):
        return f"{self.date} — {self.summary[:50]}"


class Debit(models.Model):
    """
    debits (借方明細)
    """

    journal_entry = models.ForeignKey(
        JournalEntry, on_delete=models.CASCADE, related_name="debits"
    )
    account = models.ForeignKey(
        Account, on_delete=models.RESTRICT, related_name="debits"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
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


class Credit(models.Model):
    """
    credits (貸方明細)
    """

    journal_entry = models.ForeignKey(
        JournalEntry, on_delete=models.CASCADE, related_name="credits"
    )
    account = models.ForeignKey(
        Account, on_delete=models.RESTRICT, related_name="credits"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
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
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="単価")
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
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="単価")
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
