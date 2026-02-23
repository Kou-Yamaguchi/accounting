from datetime import date, datetime

from weasyprint import HTML
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.utils.timezone import now
from django.db.models import Prefetch

from ledger.models import JournalEntry, Debit, Credit
from ledger.dtos import LedgerRow
from ledger.services import get_month_range, get_year_month_from_string, get_general_ledger_data


def ledger_pdf(request):
    """
    総勘定元帳のPDFを生成して返すビュー関数

    URLパラメータ:
        year_month (str): 対象年月 (YYYY-MM形式)

    Args:
        request (HttpRequest): HTTPリクエストオブジェクト

    Returns:
        HttpResponse: PDFファイルを含むHTTPレスポンス
    """
    # クエリパラメータからyear_monthを取得
    year_month_str: str = request.GET.get("year_month")
    if year_month_str == "":
        # TODO: 指定がない場合は当月のデータを表示するようにする
        raise ValueError("year_monthパラメータが空です。")
    day_range = get_month_range(get_year_month_from_string(year_month_str))

    general_ledger_data = get_general_ledger_data(day_range=day_range)

    # テンプレートに渡すコンテキストを作成
    # TODO: 会社名の情報も追加する必要があるかもしれない
    context = {
        "general_ledger_data": general_ledger_data,
        "company_name": "サンプル株式会社",
        "period": f"{day_range.start} - {day_range.end}",
        "generated_at": now(),
    }

    html = render_to_string("pdf/ledger.html", context)
    pdf_file = HTML(string=html).write_pdf()

    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="general_ledger_{year_month_str}.pdf"'
    return response