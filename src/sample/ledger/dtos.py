from dataclasses import dataclass

@dataclass
class JournalRow:
    date: str = ""
    description: str = ""
    debit_account: str = ""
    debit_amount: str = ""
    credit_account: str = ""
    credit_amount: str = ""