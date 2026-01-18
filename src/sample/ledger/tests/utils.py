from dataclasses import dataclass
from decimal import Decimal
from datetime import date

from ledger.models import Account, JournalEntry, Debit, Credit, Company

@dataclass
class AccountData:
    name: str
    type: str


def create_accounts(list_account: list[AccountData]) -> dict[str, Account]:
    """
    テスト用の勘定科目を作成するヘルパー関数
    Args:
        list_account (list[AccountData]): 作成する勘定科目データのリスト

    Returns:
        dict {勘定科目名: Accountオブジェクト, ...}
    """
    accounts = {}
    for acc_data in list_account:
        account = Account.objects.create(name=acc_data.name, type=acc_data.type)
        accounts[acc_data.name] = account
    return accounts


def create_journal_entry(
    entry_date: date,
    summary: str,
    debits_data: list[tuple[Account, Decimal]],
    credits_data: list[tuple[Account, Decimal]],
    company: Company = None,
    created_by=None,
) -> JournalEntry:
    """
    取引 (JournalEntry) とその明細 (Debit/Credit) を作成するヘルパー関数
    debits_data/credits_data は [(Accountオブジェクト, Decimal金額), ...] のリスト
    Args:
        entry_date (date): 取引日
        summary (str): 摘要
        debits_data (list[tuple[Account, Decimal]]): 借方明細データ
        credits_data (list[tuple[Account, Decimal]]): 貸方明細データ
        company (Company, optional): 会社情報。指定しない場合はNone。
        created_by (User, optional): 作成者情報。指定しない場合はNone。

    Returns:
        JournalEntry: 作成された取引オブジェクト
    """
    entry = JournalEntry.objects.create(
        date=entry_date, summary=summary, company=company, created_by=created_by
    )

    for account, amount in debits_data:
        Debit.objects.create(
            journal_entry=entry, account=account, amount=amount, created_by=created_by
        )

    for account, amount in credits_data:
        Credit.objects.create(
            journal_entry=entry, account=account, amount=amount, created_by=created_by
        )

    return entry
