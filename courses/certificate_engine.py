from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from django.http import HttpResponse
from .models import StudentCertificate
import uuid, os


def generate_certificate(request, cert_id):
    cert = StudentCertificate.objects.get(certificate_id=cert_id)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="certificate_{cert_id}.pdf"'

    p = canvas.Canvas(response, pagesize=A4)

    p.setFont("Helvetica-Bold", 28)
    p.drawCentredString(300, 750, "CYANOPY CERTIFICATE OF COMPLETION")

    p.setFont("Helvetica", 16)
    p.drawCentredString(300, 680, "This is to certify that")

    p.setFont("Helvetica-Bold", 22)
    p.drawCentredString(300, 640, cert.student.get_full_name())

    p.setFont("Helvetica", 16)
    p.drawCentredString(300, 600, "has successfully completed")

    p.setFont("Helvetica-Bold", 20)
    p.drawCentredString(300, 560, cert.course.title)

    p.setFont("Helvetica", 14)
    p.drawCentredString(300, 500, f"Mentor: {cert.course.trainer.get_full_name()}")
    p.drawCentredString(300, 470, f"Authorized By: CYANOPY")
    p.drawCentredString(300, 440, f"Certificate ID: {cert.certificate_id}")

    p.showPage()
    p.save()
    return response