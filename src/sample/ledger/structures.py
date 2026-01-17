from dataclasses import dataclass
from decimal import Decimal
from datetime import date

from ledger.models import Account


@dataclass
class AccountWithTotal:
    account_object: Account
    total_amount: Decimal


@dataclass
class ClosingEntry:
    total_purchase: int
    total_returns: int
    net_purchase: int


@dataclass
class PurchaseItem:
    name: str
    quantity: int
    unit_price: int


@dataclass
class PurchaseBookEntry:
    date: date
    company: str
    items: list[PurchaseItem]
    counter_account: str
    is_return: bool
    total_amount: int


@dataclass
class YearMonth:
    year: int
    month: int


@dataclass
class PurchaseBook:
    date: YearMonth
    book_entries: list[PurchaseBookEntry]  # List of PurchaseBookEntry instances
    closing_entry: ClosingEntry = None
    error: str = None


@dataclass
class DayRange:
    start: date
    end: date


@dataclass
class FinancialStatementEntry:
    """財務諸表エントリの共通データクラス"""
    name: str
    type: str
    total: Decimal
