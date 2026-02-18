# views/pdf/journal_pdf.py

from weasyprint import HTML
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.utils.timezone import now
from datetime import datetime

from ledger.models import JournalEntry


def journal_pdf(request):
    """
    仕訳帳のPDFを生成して返すビュー関数

    URLパラメータ:
        start_date (str): 開始日 (YYYY-MM-DD形式)
        end_date (str): 終了日 (YYYY-MM-DD形式)

    Args:
        request (HttpRequest): HTTPリクエストオブジェクト

    Returns:
        HttpResponse: PDFファイルを含むHTTPレスポンス
    """
    # クエリパラメータからstart_dateとend_dateを取得
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")

    # 日付フィルタリング
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            journal_entries = JournalEntry.objects.filter(
                date__gte=start_date, date__lte=end_date
            )
            period = (
                f"{start_date.strftime('%Y/%m/%d')} - {end_date.strftime('%Y/%m/%d')}"
            )
        except ValueError:
            # 日付のパースに失敗した場合は全件取得
            journal_entries = JournalEntry.objects.all()
            period = "全期間"
    else:
        journal_entries = JournalEntry.objects.all()
        period = "全期間"

    journal_entries = journal_entries.order_by("date")

    context = {
        "journal_entries": journal_entries,
        "company_name": "Sample Company",
        "period": period,
        "generated_at": now(),
    }

    html = render_to_string("pdf/journal.html", context)

    pdf = HTML(string=html).write_pdf()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = "inline; filename=journal.pdf"
    return response
