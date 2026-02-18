# views/pdf/journal_pdf.py
from datetime import date, datetime

from weasyprint import HTML
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.utils.timezone import now
from django.db.models import Prefetch

from ledger.models import JournalEntry, Debit, Credit
from ledger.dtos import JournalRow
from ledger.services import calc_total_debit_amount_from_journal_entry_list, calc_total_credit_amount_from_journal_entry_list


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

    journal_entries: list[JournalEntry] = list(journal_entries.order_by("date"))

    journal_rows: list[JournalRow] = []

    for entry in journal_entries:
        debits: list[Debit] = list(entry.prefetched_debits)
        credits: list[Credit] = list(entry.prefetched_credits)

        first_debit: Debit = debits[0] if debits else None
        first_credit: Credit = credits[0] if credits else None

        journal_rows.append(
            JournalRow(
                date=entry.date.strftime("%Y/%m/%d"),
                description=entry.summary,
                debit_account=first_debit.account.name if first_debit else "",
                debit_amount=str(first_debit.amount) if first_debit else "0",
                credit_account=first_credit.account.name if first_credit else "",
                credit_amount=str(first_credit.amount) if first_credit else "0"
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

    total_debit = calc_total_debit_amount_from_journal_entry_list(journal_entries)
    total_credit = calc_total_credit_amount_from_journal_entry_list(journal_entries)

    journal_rows.append(
        JournalRow(
            description="合計",
            debit_amount=str(total_debit),
            credit_amount=str(total_credit),
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
