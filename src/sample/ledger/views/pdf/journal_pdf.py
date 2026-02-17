# views/pdf/journal_pdf.py

from django.template.loader import render_to_string
from weasyprint import HTML
from django.http import HttpResponse
from ledger.models import JournalEntry


def journal_pdf(request):
    journal_entries = JournalEntry.objects.all().order_by("date")

    html = render_to_string("pdf/journal.html", {"journal_entries": journal_entries})

    pdf = HTML(string=html).write_pdf()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = "inline; filename=journal.pdf"
    return response
