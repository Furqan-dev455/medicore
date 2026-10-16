from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage

from .models import Bill


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def generate_and_email_invoice(self, bill_id):
    try:
        bill = Bill.objects.select_related('patient__user').get(pk=bill_id)
        from .views import _invoice_pdf_bytes

        if bill.invoice_status == 'ready' and bill.invoice_pdf:
            with bill.invoice_pdf.open('rb') as stored_invoice:
                pdf_content = stored_invoice.read()
        else:
            pdf_content = _invoice_pdf_bytes(bill)
            previous_file = bill.invoice_pdf.name
            bill.invoice_pdf.save(
                f'MediCore-invoice-{bill.pk}.pdf',
                ContentFile(pdf_content),
                save=False,
            )
            bill.invoice_status = 'ready'
            bill.save(update_fields=['invoice_pdf', 'invoice_status'])
            if previous_file and previous_file != bill.invoice_pdf.name:
                bill.invoice_pdf.storage.delete(previous_file)

        patient_email = bill.patient.user.email if bill.patient.user_id else ''
        if patient_email and not bill.invoice_email_sent:
            message = EmailMessage(
                subject=f'MediCore invoice MC-{bill.pk:06d}',
                body=(
                    f'Hello {bill.patient.name},\n\n'
                    f'Your invoice for bill #{bill.pk} is attached. '
                    'The invoice includes your latest payment history and balance.\n\n'
                    'Regards,\nMediCore'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[patient_email],
            )
            message.attach(
                f'MediCore-invoice-{bill.pk}.pdf',
                pdf_content,
                'application/pdf',
            )
            message.send(fail_silently=False)
            bill.invoice_email_sent = True
            bill.save(update_fields=['invoice_email_sent'])
        return {'bill_id': bill.pk, 'emailed': bool(patient_email)}
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            bill = Bill.objects.filter(pk=bill_id).first()
            if bill and not bill.invoice_pdf:
                Bill.objects.filter(pk=bill_id).update(invoice_status='failed')
            raise
        raise self.retry(exc=exc)
