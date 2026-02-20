from datetime import date, datetime

from weasyprint import HTML
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.utils.timezone import now
from django.db.models import Prefetch

from ledger.models import JournalEntry, Debit, Credit
from ledger.dtos import LedgerRow


def ledger_pdf(request):
    """
    総勘定元帳のPDFを生成して返すビュー関数

    URLパラメータ:
        start_date (str): 開始日 (YYYY-MM-DD形式)
        end_date (str): 終了日 (YYYY-MM-DD形式)

    Args:
        request (HttpRequest): HTTPリクエストオブジェクト

    Returns:
        HttpResponse: PDFファイルを含むHTTPレスポンス
    """
    # クエリパラメータからstart_dateとend_dateを取得
    start_date_str: str = request.GET.get("start_date")
    end_date_str: str = request.GET.get("end_date")

    # 日付フィルタリング
    if start_date_str and end_date_str:
        try:
            start_date: date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date: date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            journal_entries: list[JournalEntry] = JournalEntry.objects.filter(
                date__gte=start_date, date__lte=end_date
            ).prefetch_related(
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

            period = (
                f"{start_date.strftime('%Y/%m/%d')} - {end_date.strftime('%Y/%m/%d')}"
            )
        except ValueError:
            # 日付のパースに失敗した場合は全件取得
            journal_entries = JournalEntry.objects.all().prefetch_related(
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
            period = "全期間"
    else:
        journal_entries = JournalEntry.objects.all().prefetch_related(
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
        period = "全期間"

    # テンプレートに渡すコンテキストを作成
    context = {
        "journal_entries": journal_entries,
        "period": period,
        "generated_at": now(),
    }