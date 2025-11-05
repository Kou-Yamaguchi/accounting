from enum import Enum

class ErrorMessages(Enum):
    REQUIRED = "このフィールドは必須です。"
    INVALID = "無効な値です。"
    MAX_LENGTH = "最大長を超えています。"
    MESSAGE_0001 = "借方合計と貸方合計は一致する必要があります。"
    MESSAGE_0002 = "TARGET_ACCOUNT_NAME をサブクラスで設定してください。"
    MESSAGE_0003 = "金額は正の値でなければなりません。"
    MESSAGE_0004 = "勘定科目と金額の両方を入力してください。"
