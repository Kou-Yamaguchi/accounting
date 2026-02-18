# views/pdf/journal_pdf.py

from weasyprint import HTML
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.utils.timezone import now

from ledger.models import JournalEntry


def journal_pdf(request):
    journal_entries = JournalEntry.objects.all().order_by("date")

    context = {
        "journal_entries": journal_entries,
        "company_name": "Sample Company",
        "period": "2025/4/1 - 2025/4/30",
        "generated_at": now(),
    }

    html = render_to_string("pdf/journal.html", context)

    pdf = HTML(string=html).write_pdf()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = "inline; filename=journal.pdf"
    return response
