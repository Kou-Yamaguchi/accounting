# views/pdf/journal_pdf.py
from datetime import date, datetime

from weasyprint import HTML
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.utils.timezone import now

from ledger.models import JournalEntry, Debit, Credit
from ledger.dtos import JournalRow


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
    start_date_str: str = request.GET.get("start_date")
    end_date_str: str = request.GET.get("end_date")

    # 日付フィルタリング
    if start_date_str and end_date_str:
        try:
            start_date: date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date: date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            journal_entries: list[JournalEntry] = JournalEntry.objects.filter(
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

    journal_entries: list[JournalEntry] = list(journal_entries.order_by("date"))

    journal_rows: list[JournalRow] = []

    for entry in journal_entries:
        debits: list[Debit] = list(entry.debits.all())
        credits: list[Credit] = list(entry.credits.all())

        journal_rows.append(
            JournalRow(
                date=entry.date.strftime("%Y/%m/%d"),
                description=entry.summary,
                debit_account=debits[0].account.name,
                debit_amount=str(debits[0].amount),
                credit_account=credits[0].account.name,
                credit_amount=str(credits[0].amount)
            )
        )

        max_len: int = max(len(debits), len(credits))

        for i in range(1, max_len):
            debit_account = debits[i].account.name if i < len(debits) else ""
            debit_amount = str(debits[i].amount) if i < len(debits) else ""
            credit_account = credits[i].account.name if i < len(credits) else ""
            credit_amount = str(credits[i].amount) if i < len(credits) else ""

            journal_rows.append(
                JournalRow(
                    debit_account=debit_account,
                    debit_amount=debit_amount,
                    credit_account=credit_account,
                    credit_amount=credit_amount,
                )
            )

    context = {
        "journal_rows": journal_rows,
        "company_name": "Sample Company",
        "period": period,
        "generated_at": now(),
    }

    html = render_to_string("pdf/journal.html", context)

    pdf = HTML(string=html).write_pdf()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = "inline; filename=journal.pdf"
    return response
