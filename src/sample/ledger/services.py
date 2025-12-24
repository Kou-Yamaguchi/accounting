from decimal import Decimal
from datetime import date
from typing import Literal

from dateutil.relativedelta import relativedelta
from django.db.models import Q
from django.db.models import Sum

from .models import JournalEntry, InitialBalance, Account, Entry, Debit, Credit, PurchaseDetail, Item, Company


def get_fiscal_range(year: int, start_month: int = 4, months: int = 12) -> tuple[date, date]:
    """
    指定された年の会計期間の開始日と終了日を取得します。
    queryパラメータで会計年度を指定する場合に使用します。
    例: 2024年 -> (2024-04-01, 2025-03-31)
    期首が4月1日、期末が翌年3月31日と仮定しています。

    Args:
        year (int): 会計年度の開始年
        start_month (int): 会計年度の開始月 (デフォルトは4月)
        months (int): 会計年度の月数 (デフォルトは12ヶ月)

    Returns:
        tuple[date, date]: 会計期間の開始日と終了日
    """
    start_date = date(year, start_month, 1)
    end_date = start_date + relativedelta(months=months) - relativedelta(days=1)
    return start_date, end_date


def get_month_range(year: int, month: int) -> tuple[date, date]:
    """
    指定された年月の開始日と終了日を取得します。

    Args:
        year (int): 年
        month (int): 月

    Returns:
        tuple[date, date]: 月の開始日と終了日
    """
    start_date = date(year, month, 1)
    end_date = start_date + relativedelta(months=1) - relativedelta(days=1)
    return start_date, end_date


def get_initial_balance(account_id: int) -> Decimal:
    """
    指定された勘定科目の初期残高を取得します。
    ここではシンプルにInitialBalanceモデルから取得しますが、実務では前月までの残高計算結果を使用します。
    """
    try:
        return InitialBalance.objects.get(account_id=account_id).balance
    except InitialBalance.DoesNotExist:
        return Decimal("0.00")


def calculate_monthly_balance(account_name: str, year: int, month: int) -> dict:
    """
    指定された勘定科目の月間出納帳データを計算し、データと次月繰越残高を返します。
    Returns:
        {
            "data": List[dict],  # 各取引のデータリスト
            "ending_balance": int,  # 次月繰越残高
        }
    data: 各取引のデータリストは以下の形式の辞書を含みます。
        {
            "date": date,  # 取引日
            "summary": str,  # 摘要（相手勘定科目名）
            "income": int,  # 収入金額 (借方)
            "expense": int,  # 支出金額 (貸方)
            "balance": int,  # 取引後の残高
        }
    もし勘定科目が存在しない場合、"error"キーを含む辞書を返します。
    例:
        {
            "data": [],
            "ending_balance": 0,
            "error": "勘定科目 'XXX' が見つかりません。",
        }
    """
    try:
        target_account = Account.objects.get(name=account_name)
    except Account.DoesNotExist:
        return {
            "data": [],
            "ending_balance": 0,
            "error": f'勘定科目 "{account_name}" が見つかりません。',
        }

    target_id = target_account.id

    # 1. & 2. 前月繰越金額の取得と反映 (ここではInitialBalanceから簡易的に取得)
    # 実務では、前月までの総残高を計算するか、または専用の残高テーブルから取得します。
    # 懸念事項2 (残高計算の時間) の解決策として、前月までの計算結果をDBに持たせるのが最善です。

    # 便宜上、ここでは当会計期間開始日をInitialBalanceから取得し、
    # その日以前の全ての取引とInitialBalanceを合算して前月繰越とします。

    initial_balance_obj = InitialBalance.objects.filter(account=target_account).first()

    # 期首残高の取得
    if initial_balance_obj:
        start_of_period = initial_balance_obj.start_date
        current_balance = initial_balance_obj.balance
    else:
        # 期首残高がない場合、0とするが警告を返す
        current_balance = Decimal("0")
        start_of_period = date(year, 1, 1)  # 仮に当年初日を期首とする
    # 期首残高が0の場合、警告をログに記録する
    if current_balance == 0:
        print(f"Warning: 期首残高が設定されていません。勘定科目: {account_name}")

    # 前月までの取引を集計し、前月繰越（期首残高 + 期首～前月末の取引）を計算

    # 対象期間
    start_of_month = date(year, month, 1)

    # 前月末日
    end_of_prev_month = start_of_month - relativedelta(days=1)

    # 期首から前月末までの取引を集計 (前月繰越残高の算出)
    # 勘定科目が debit の場合 (収入)
    prev_debit_sum = (
        Debit.objects.filter(
            account_id=target_id,
            journal_entry__date__gte=start_of_period,
            journal_entry__date__lte=end_of_prev_month,
        ).aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0")
    )

    # 勘定科目が credit の場合 (支出)
    prev_credit_sum = (
        Credit.objects.filter(
            account_id=target_id,
            journal_entry__date__gte=start_of_period,
            journal_entry__date__lte=end_of_prev_month,
        ).aggregate(Sum("amount"))["amount__sum"]
        or Decimal("0")
    )

    # 前月繰越残高 = 期首残高 + 前月までの収入 - 前月までの支出
    current_balance += prev_debit_sum - prev_credit_sum

    # 3. 前月繰越レコードの作成
    book_data = []
    book_data.append(
        {
            "date": start_of_month,
            "summary": "前月繰越",
            "income": 0,
            "expense": 0,
            "balance": current_balance,
        }
    )

    # 当月の取引を取得 (JournalEntry)
    end_of_month = start_of_month + relativedelta(months=1) - relativedelta(days=1)

    # Qオブジェクトで当月分かつ対象科目が含まれる取引を取得
    # JournalEntryをキーに取引明細を取得するため、DebitとCreditのFKを辿る
    journal_entries = (
        JournalEntry.objects.filter(
            Q(debits__account_id=target_id) | Q(credits__account_id=target_id),
            date__gte=start_of_month,
            date__lte=end_of_month,
        )
        .distinct()
        .order_by("date", "pk")
    )

    # 4. & 5. 当月の取引を処理し、残高を計算
    for entry in journal_entries:
        record = {
            "date": entry.date,
            "income": Decimal("0.00"),
            "expense": Decimal("0.00"),
            "summary": entry.summary,  # まずは総合摘要を入れておく
            "balance": Decimal("0.00"),
        }

        # 当該取引で対象科目に関する明細を抽出
        debit_items = list(entry.debits.filter(account_id=target_id))
        credit_items = list(entry.credits.filter(account_id=target_id))

        if debit_items:
            # 対象科目が借方にある場合 -> 収入 (入金)
            amount = sum(item.amount for item in debit_items)
            record["income"] = amount
            current_balance += amount

            # 相手勘定科目を摘要とする（貸方明細の科目名）
            # 対象科目の明細が1つ、相手科目の明細が1つと仮定
            opponent_accounts = entry.credits.exclude(account_id=target_id).all()
            if opponent_accounts:
                record["summary"] = opponent_accounts[0].account.name

        elif credit_items:
            # 対象科目が貸方にある場合 -> 支出 (出金)
            amount = sum(item.amount for item in credit_items)
            record["expense"] = amount
            current_balance -= amount

            # 相手勘定科目を摘要とする（借方明細の科目名）
            opponent_accounts = entry.debits.exclude(account_id=target_id).all()
            if opponent_accounts:
                record["summary"] = opponent_accounts[0].account.name

        record["balance"] = current_balance
        book_data.append(record)

    # 最終レコードの残高を次月繰越として記録
    ending_balance = current_balance

    # 次月繰越の行を追加 (表示上のバランスを整えるため)
    book_data.append(
        {
            "date": end_of_month,
            "summary": "次月繰越",
            "income": Decimal("0.00"),
            "expense": ending_balance,  # 帳簿上、最終的な残高は支出側に入れる
            "balance": Decimal("0.00"),
        }
    )

    return {"data": book_data, "ending_balance": ending_balance}


def generate_purchase_book(year: int, month: int) -> list:
    pass

def calculate_each_entry_total(
    entry: Entry, account: Account, start_date: date, end_date: date
):
    """
    各勘定科目の借方・貸方合計を計算するユーティリティメソッド。

    Args:
        entry (Entry): DebitまたはCreditモデル
        account (Account): 対象の勘定科目
        start_date (date): 期間開始日
        end_date (date): 期間終了日

    Returns:
        Decimal: 指定期間内の借方or貸方の合計金額
    """
    total_amount = entry.objects.filter(
        account=account,
        journal_entry__date__gte=start_date,
        journal_entry__date__lte=end_date,
    ).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
    return total_amount


def calculate_account_total(
    account: Account, start_date: date, end_date: date
):
    """
    各勘定科目の合計金額を計算するユーティリティメソッド。

    Args:
        account (Account): 対象の勘定科目
        start_date (date): 期間開始日
        end_date (date): 期間終了日

    Returns:
        Decimal: 指定期間内の勘定科目の合計金額
    """
    debit_total = calculate_each_entry_total(
        Debit, account, start_date, end_date
    )
    credit_total = calculate_each_entry_total(
        Credit, account, start_date, end_date
    )

    if account.type in ["asset", "expense"]:
        total_amount = debit_total - credit_total
    else:
        total_amount = credit_total - debit_total

    return total_amount


def get_total_by_account_type(
    account_type: Literal["asset", "liability", "equity", "revenue", "expense"], start_date: date, end_date: date
) -> Decimal:
    """
    指定された勘定科目タイプの合計金額を計算します。

    Args:
        account_type (Literal["asset", "liability", "equity", "revenue", "expense"]): 勘定科目タイプ
        start_date (date): 期間開始日
        end_date (date): 期間終了日

    Returns:
        Decimal: 指定された勘定科目タイプの合計金額
    """
    accounts = Account.objects.filter(type=account_type)

    total_amount = sum(
        calculate_account_total(account, start_date, end_date)
        for account in accounts
    )

    return total_amount


def calc_monthly_sales(year: int, month: int) -> Decimal:
    """
    指定された年月の月次収益を計算します。

    Args:
        year (int): 年
        month (int): 月

    Returns:
        Decimal: 月次収益
    """
    start_date, end_date = get_month_range(year, month)

    total_sales = get_total_by_account_type("revenue", start_date, end_date)

    return total_sales


def calc_recent_half_year_sales() -> list[Decimal]:
    """
    直近6ヶ月の月次収益をリストで取得します。

    Returns:
        list[Decimal]: 直近6ヶ月の月次収益リスト
    """
    today = date.today()
    sales_list = []

    for i in range(6):
        target_date = today - relativedelta(months=i)
        year = target_date.year
        month = target_date.month
        monthly_sales = calc_monthly_sales(year, month)
        sales_list.append(monthly_sales)

    sales_list.reverse()  # 古い順に並び替え

    return sales_list


def calc_monthly_expense(year: int, month: int) -> Decimal:
    """
    指定された年月の月次費用を計算します。

    Args:
        year (int): 年
        month (int): 月

    Returns:
        Decimal: 月次費用
    """
    start_date, end_date = get_month_range(year, month)

    total_expense = get_total_by_account_type("expense", start_date, end_date)

    return total_expense


def calc_recent_half_year_expenses() -> list[Decimal]:
    """
    直近6ヶ月の月次費用をリストで取得します。

    Returns:
        list[Decimal]: 直近6ヶ月の月次費用リスト
    """
    today = date.today()
    expense_list = []

    for i in range(6):
        target_date = today - relativedelta(months=i)
        year = target_date.year
        month = target_date.month
        monthly_expense = calc_monthly_expense(year, month)
        expense_list.append(monthly_expense)

    expense_list.reverse()  # 古い順に並び替え

    return expense_list


def calc_monthly_profit(year: int, month: int) -> Decimal:
    """
    指定された年月の月次利益を計算します。

    Args:
        year (int): 年
        month (int): 月

    Returns:
        Decimal: 月次利益
    """
    total_sales = calc_monthly_sales(year, month)
    total_expense = calc_monthly_expense(year, month)

    monthly_profit = total_sales - total_expense

    return monthly_profit


def calc_recent_half_year_profits() -> list[Decimal]:
    """
    直近6ヶ月の月次利益をリストで取得します。

    Returns:
        list[Decimal]: 直近6ヶ月の月次利益リスト
    """
    sales_list = calc_recent_half_year_sales()
    expense_list = calc_recent_half_year_expenses()
    profit_list = []

    for sales, expense in zip(sales_list, expense_list):
        profit = sales - expense
        profit_list.append(profit)

    return profit_list