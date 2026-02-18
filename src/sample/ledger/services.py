from decimal import Decimal
from datetime import date
from typing import Literal

from dateutil.relativedelta import relativedelta
from django.db.models import Q, Prefetch
from django.db.models import Sum

from .models import (
    JournalEntry,
    InitialBalance,
    Account,
    Entry,
    Debit,
    Credit,
    PurchaseDetail,
    Item,
    Company,
)
from .structures import YearMonth, DayRange, AccountWithTotal


def get_current_year_month() -> YearMonth:
    """
    現在の日付からYearMonthオブジェクトを生成して返します。

    Returns:
        YearMonth: 現在の年と月を持つYearMonthオブジェクト
    """
    today = date.today()
    return YearMonth(year=today.year, month=today.month)


def get_last_year_month() -> YearMonth:
    """
    現在の日付の1ヶ月前のYearMonthオブジェクトを生成して返します。

    Returns:
        YearMonth: 1ヶ月前の年と月を持つYearMonthオブジェクト
    """
    today = date.today()
    last_month_date = today - relativedelta(months=1)
    return YearMonth(year=last_month_date.year, month=last_month_date.month)


def decimal_to_int(value: Decimal) -> int:
    """
    Decimal型の金額をint型に変換します。
    小数点以下は切り捨てられます。

    Args:
        value (Decimal): 変換するDecimal値

    Returns:
        int: 変換後のint値
    """
    return int(value.quantize(Decimal("1.")))


def list_decimal_to_int(values: list[Decimal]) -> list[int]:
    """
    Decimal型の金額リストをint型のリストに変換します。
    小数点以下は切り捨てられます。

    Args:
        values (list[Decimal]): 変換するDecimal値のリスト

    Returns:
        list[int]: 変換後のint値のリスト
    """
    return [decimal_to_int(value) for value in values]


def get_fiscal_range(year: int, start_month: int = 4, months: int = 12) -> DayRange:
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
        DayRange: 会計期間の開始日と終了日
    """
    start_date = date(year, start_month, 1)
    end_date = start_date + relativedelta(months=months) - relativedelta(days=1)
    result = DayRange(start=start_date, end=end_date)
    return result


def get_month_range(year_month: YearMonth) -> DayRange:
    """
    指定された年月の開始日と終了日を取得します。

    Args:
        year_month (YearMonth): 年月を表すYearMonthオブジェクト

    Returns:
        DayRange: 月の開始日と終了日
    """
    start_date = date(year_month.year, year_month.month, 1)
    end_date = start_date + relativedelta(months=1) - relativedelta(days=1)
    result = DayRange(start=start_date, end=end_date)
    return result


def get_initial_balance(account_id: int) -> Decimal:
    """
    指定された勘定科目の初期残高を取得します。
    ここではシンプルにInitialBalanceモデルから取得しますが、実務では前月までの残高計算結果を使用します。
    """
    try:
        return InitialBalance.objects.get(account_id=account_id).balance
    except InitialBalance.DoesNotExist:
        return Decimal("0.00")


def get_all_account_objects() -> list[Account]:
    """全ての勘定科目オブジェクトを取得するユーティリティ関数。"""
    return list(Account.objects.all().order_by("type", "name"))


def get_account_object_by_type(account_type: str) -> list[Account]:
    """指定されたタイプの勘定科目オブジェクトを取得するユーティリティ関数。

    Args:
        account_type (str): 勘定科目タイプ（例："asset", "liability", "equity", "revenue", "expense"）

    Returns:
        list[Account]: 指定されたタイプのAccountオブジェクトのリスト
    """
    return list(Account.objects.filter(type=account_type).order_by("name"))


def calc_each_account_totals(
    day_range: DayRange, pop_list: list[str] = None
) -> list[AccountWithTotal]:
    """全ての勘定科目の合計金額を計算するユーティリティ関数。

    Args:
        day_range (DayRange): 期間開始日と終了日を含むDayRangeオブジェクト
        pop_list (list[str]|None): 対象とする勘定科目タイプのリスト。デフォルトはNone（全ての勘定科目を対象）

    Returns:
        list[AccountWithTotal]: List of AccountWithTotal instances
    """
    if pop_list is None:
        accounts = get_all_account_objects()
    else:
        accounts = [acc for acc in get_all_account_objects() if acc.type in pop_list]

    account_totals: list[AccountWithTotal] = [
        AccountWithTotal(account, calculate_account_total(account, day_range))
        for account in accounts
    ]
    return account_totals


def get_all_journal_entries_for_account(account: Account) -> list[JournalEntry]:
    """
    指定された勘定科目に関連する全ての仕訳を取得するユーティリティメソッド。
    N+1問題を避けるため、prefetch_relatedを使用して関連オブジェクトを事前に取得

    Args:
        account (Account): 対象の勘定科目

    Returns:
        QuerySet: 指定された勘定科目に関連する全ての仕訳のクエリセット
    """
    journal_entries = (
        JournalEntry.objects.filter(
            Q(debits__account=account) | Q(credits__account=account)
        )
        .distinct()
        .order_by("date", "pk")
        .prefetch_related(
            Prefetch(
                "debits",
                queryset=Debit.objects.select_related("account"),
                to_attr="prefetched_debits",
            ),
            Prefetch(
                "credits",
                queryset=Credit.objects.select_related("account"),
                to_attr="prefetched_credits",
            ),
        )
    )
    return journal_entries


def collect_account_set_from_je(je: JournalEntry, is_debit: bool) -> set[Account]:
    """
    取引に含まれる勘定科目をEntryごとに収集するユーティリティメソッド。

    注意: 事前にprefetch_relatedでDebit/Creditをprefetched_debits/prefetched_creditsとして設定しておく必要があります。
    Args:
        je (JournalEntry): 仕訳エントリ
        is_debit (bool): 借方勘定科目を収集するか、貸方勘定科目を収集するかのフラグ

    Returns:
        set[Account]: 収集された勘定科目のセット
    """
    if is_debit:
        return set(debit.account for debit in je.prefetched_debits)
    else:
        return set(credit.account for credit in je.prefetched_credits)


def determine_counter_party_name(accounts: set[Account]) -> str:
    """
    相手勘定科目の名前を決定するユーティリティメソッド。
    一つの場合にはその名前を返し、複数の場合は「諸口」、0の場合は「取引エラー」とする。

    Args:
        accounts (set[Account]): 対象勘定科目以外の勘定科目のセット

    Returns:
        str: 相手勘定科目の名前
    """
    counter_party_name = ""
    if len(accounts) == 1:
        # 相手勘定科目が1つの場合、その名前をセット
        counter_party_name = [acc.name for acc in accounts][0]
    elif len(accounts) > 1:
        # 相手勘定科目が複数の場合
        counter_party_name = "諸口"
    else:
        # 相手勘定科目が0の場合（例：自己取引、またはデータ不備）
        counter_party_name = "取引エラー"
    return counter_party_name


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
    prev_debit_sum = Debit.objects.filter(
        account_id=target_id,
        journal_entry__date__gte=start_of_period,
        journal_entry__date__lte=end_of_prev_month,
    ).aggregate(Sum("amount"))["amount__sum"] or Decimal("0")

    # 勘定科目が credit の場合 (支出)
    prev_credit_sum = Credit.objects.filter(
        account_id=target_id,
        journal_entry__date__gte=start_of_period,
        journal_entry__date__lte=end_of_prev_month,
    ).aggregate(Sum("amount"))["amount__sum"] or Decimal("0")

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


def calculate_each_entry_total(entry: Entry, account: Account, day_range: DayRange):
    """
    各勘定科目の借方・貸方合計を計算するユーティリティメソッド。

    Args:
        entry (Entry): DebitまたはCreditモデル
        account (Account): 対象の勘定科目
        day_range (DayRange): 期間開始日と終了日を含むDayRangeオブジェクト

    Returns:
        Decimal: 指定期間内の借方or貸方の合計金額
    """
    total_amount = entry.objects.filter(
        account=account,
        journal_entry__date__gte=day_range.start,
        journal_entry__date__lte=day_range.end,
    ).aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
    return total_amount


def calculate_account_total(account: Account, day_range: DayRange) -> Decimal:
    """
    各勘定科目の合計金額を計算するユーティリティメソッド。

    Args:
        account (Account): 対象の勘定科目
        day_range (DayRange): 期間開始日と終了日を含むDayRangeオブジェクト

    Returns:
        Decimal: 指定期間内の勘定科目の合計金額
    """
    debit_total = calculate_each_entry_total(Debit, account, day_range)
    credit_total = calculate_each_entry_total(Credit, account, day_range)

    if account.type in ["asset", "expense"]:
        total_amount = debit_total - credit_total
    else:
        total_amount = credit_total - debit_total

    return total_amount


# TODO: get_amount_totalに命名変更
def get_total_by_account_type(
    account_type: Literal["asset", "liability", "equity", "revenue", "expense"],
    day_range: DayRange,
) -> Decimal:
    """
    指定された勘定科目タイプの合計金額を計算します。

    Args:
        account_type (Literal["asset", "liability", "equity", "revenue", "expense"]): 勘定科目タイプ
        day_range (DayRange): 期間開始日と終了日を含むDayRangeオブジェクト

    Returns:
        Decimal: 指定された勘定科目タイプの合計金額
    """
    accounts = Account.objects.filter(type=account_type)

    total_amount = sum(
        calculate_account_total(account, day_range) for account in accounts
    )

    return total_amount


def calc_monthly_sales(year_month: YearMonth) -> Decimal:
    """
    指定された年月の月次収益を計算します。

    Args:
        year_month (YearMonth): 年月を表すYearMonthオブジェクト

    Returns:
        Decimal: 月次収益
    """
    month_range: DayRange = get_month_range(year_month)

    total_sales = get_total_by_account_type("revenue", month_range)

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
        monthly_sales = calc_monthly_sales(YearMonth(year, month))
        sales_list.append(monthly_sales)

    sales_list.reverse()  # 古い順に並び替え

    return sales_list


def calc_monthly_expense(year_month: YearMonth) -> Decimal:
    """
    指定された年月の月次費用を計算します。

    Args:
        year_month (YearMonth): 年月を表すYearMonthオブジェクト

    Returns:
        Decimal: 月次費用
    """
    month_range: DayRange = get_month_range(year_month)

    total_expense = get_total_by_account_type("expense", month_range)

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
        monthly_expense = calc_monthly_expense(YearMonth(year, month))
        expense_list.append(monthly_expense)

    expense_list.reverse()  # 古い順に並び替え

    return expense_list


def calc_monthly_profit(year_month: YearMonth) -> Decimal:
    """
    指定された年月の月次利益を計算します。

    Args:
        year_month (YearMonth): 年月を表すYearMonthオブジェクト

    Returns:
        Decimal: 月次利益
    """
    total_sales = calc_monthly_sales(year_month)
    total_expense = calc_monthly_expense(year_month)

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


def total_expense_recent_month() -> dict[int, Decimal]:
    """
    当月の費用を勘定科目ごとに集計します。

    Returns:
        dict[int, Decimal]: {勘定科目ID: 合計費用} の辞書
    """
    today = date.today()
    year_month = YearMonth(year=today.year, month=today.month)
    month_range: DayRange = get_month_range(year_month)

    expense_accounts = Account.objects.filter(type="expense")
    account_totals = {}

    for account in expense_accounts:
        total_amount = calculate_account_total(account, month_range)
        account_totals[account.id] = total_amount

    return account_totals


def get_company_sales_last_month() -> dict[str, Decimal]:
    """
    先月の取引先別売上を集計します。

    N+1問題を回避するため、JournalEntryベースで以下を実施：
    1. 先月の範囲内のJournalEntryを取得
    2. revenueタイプの勘定科目を含む仕訳のみをフィルタ
    3. prefetch_relatedで関連データを一括取得
    4. Pythonレベルで取引先別に集計

    Returns:
        dict[str, Decimal]: {取引先名: 売上金額} の辞書（降順ソート済み）
    """
    last_month = get_last_year_month()
    month_range = get_month_range(last_month)

    # 先月のrevenueを含む仕訳を一括取得（N+1問題回避）
    journal_entries = (
        JournalEntry.objects.filter(
            Q(debits__account__type="revenue") | Q(credits__account__type="revenue"),
            date__gte=month_range.start,
            date__lte=month_range.end,
            company__isnull=False,  # companyが紐づいている仕訳のみ
        )
        .distinct()
        .select_related("company")  # companyを一括取得
        .prefetch_related(
            Prefetch(
                "debits",
                queryset=Debit.objects.select_related("account"),
                to_attr="prefetched_debits",
            ),
            Prefetch(
                "credits",
                queryset=Credit.objects.select_related("account"),
                to_attr="prefetched_credits",
            ),
        )
    )

    # 取引先別売上を集計
    company_sales = {}

    for je in journal_entries:
        company_name = je.company.name

        # 売上（credit側のrevenue）を集計
        revenue_amount = sum(
            credit.amount
            for credit in je.prefetched_credits
            if credit.account.type == "revenue"
        )

        # 売上返品などがある場合（debit側のrevenue）を減算
        revenue_return = sum(
            debit.amount
            for debit in je.prefetched_debits
            if debit.account.type == "revenue"
        )

        net_revenue = revenue_amount - revenue_return

        # 取引先別に累積
        company_sales[company_name] = (
            company_sales.get(company_name, Decimal("0.00")) + net_revenue
        )

    # 売上金額の降順でソート
    sorted_company_sales = dict(
        sorted(company_sales.items(), key=lambda x: x[1], reverse=True)
    )

    return sorted_company_sales


def prepare_pareto_chart_data(
    company_sales: dict[str, Decimal],
) -> tuple[list[str], list[int], list[int]]:
    """
    取引先別売上データをパレート図用のデータに変換します。

    Args:
        company_sales (dict[str, Decimal]): {取引先名: 売上金額} の辞書（降順ソート済み前提）

    Returns:
        tuple[list[str], list[int], list[int]]:
            - 取引先名リスト
            - 売上の割合リスト（％）
            - 累積売上割合リスト（％）
    """
    if not company_sales:
        return [], [], []

    # データ抽出
    company_names = list(company_sales.keys())
    sales_amounts = list(company_sales.values())

    # 合計売上
    total_sales = sum(sales_amounts)

    if total_sales == 0:
        return company_names, [0] * len(company_names), [0] * len(company_names)

    # 売上割合（%）を計算
    sales_percentages = [
        int((amount / total_sales * 100).quantize(Decimal("1")))
        for amount in sales_amounts
    ]

    # 累積売上割合（%）を計算
    cumulative_percentages = []
    cumulative = 0
    for percentage in sales_percentages:
        cumulative += percentage
        cumulative_percentages.append(cumulative)

    return company_names, sales_percentages, cumulative_percentages
