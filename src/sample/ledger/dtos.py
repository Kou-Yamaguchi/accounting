from dataclasses import dataclass

@dataclass
class JournalRow:
    date: str = ""
    description: str = ""
    debit_account: str = ""
    debit_amount: str = ""
    credit_account: str = ""
    credit_amount: str = ""


@dataclass
class LedgerRow:
    date: str = ""
    description: str = ""
    counter_account_name: str = ""
    debit_amount: str = ""
    credit_amount: str = ""
    debit_or_credit: str = ""  # "借" または "貸"
    balance: str = "" 