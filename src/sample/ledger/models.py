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


class JournalEntry(models.Model):
    """
    journal_entries (取引) — 仕訳ヘッダ
    """

    date = models.DateField()
    summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
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
        verbose_name = "期首残高"
        verbose_name_plural = "期首残高"
