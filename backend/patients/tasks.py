import logging

from celery import shared_task
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage, send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import Bill, InvoiceStatus

# Keep notification tasks discoverable by Celery's standard tasks.py autodiscovery.
from .appointment_notifications import process_appointment_reminders, send_appointment_notification  # noqa: F401,E402

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def generate_and_email_invoice(self, bill_id):
    # Imported here (as before) so the worker doesn't load views at module import time.
    from .views import BRAND_NAME, _invoice_pdf_bytes, invoice_filename, invoice_number

    try:
        bill = Bill.objects.select_related('patient__user').filter(pk=bill_id).first()
        if bill is None:
            logger.warning('Invoice requested for missing bill %s', bill_id)
            return {'bill_id': bill_id, 'emailed': False}

        # Only a retry may reuse the stored PDF (e.g. the PDF was built but the
        # email failed). A fresh run always rebuilds, because a newer payment may
        # have arrived since the stored file was made.
        regenerated = False
        if self.request.retries > 0 and bill.invoice_status == InvoiceStatus.READY and bill.invoice_pdf:
            with bill.invoice_pdf.open('rb') as stored_invoice:
                pdf_content = stored_invoice.read()
        else:
            pdf_content = _invoice_pdf_bytes(bill)
            previous_file = bill.invoice_pdf.name
            bill.invoice_pdf.save(invoice_filename(bill), ContentFile(pdf_content), save=False)
            bill.invoice_status = InvoiceStatus.READY
            bill._change_reason = 'System task: invoice generated.'
            bill.save(update_fields=['invoice_pdf', 'invoice_status'])
            if previous_file and previous_file != bill.invoice_pdf.name:
                bill.invoice_pdf.storage.delete(previous_file)
            regenerated = True

        emailed = False
        patient_email = bill.patient.user.email if bill.patient.user_id else ''
        # A freshly built invoice is always sent (it reflects a new payment);
        # on a retry, only send if the earlier attempt didn't get through.
        if patient_email and (regenerated or not bill.invoice_email_sent):
            message = EmailMessage(
                subject=f'{BRAND_NAME} invoice {invoice_number(bill)}',
                body=(
                    f'Hello {bill.patient.name},\n\n'
                    f'Your invoice for bill #{bill.pk} is attached. '
                    'The invoice includes your latest payment history and balance.\n\n'
                    f'Regards,\n{BRAND_NAME}'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[patient_email],
            )
            message.attach(invoice_filename(bill), pdf_content, 'application/pdf')
            message.send(fail_silently=False)
            bill.invoice_email_sent = True
            bill._change_reason = 'System task: invoice emailed.'
            bill.save(update_fields=['invoice_email_sent'])
            emailed = True
        return {'bill_id': bill.pk, 'emailed': emailed}
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            bill = Bill.objects.filter(pk=bill_id).first()
            # If the PDF itself was built, only the email failed: keep it downloadable.
            # Otherwise mark it failed so the frontend stops showing "processing" forever.
            if bill and bill.invoice_status != InvoiceStatus.READY:
                bill.invoice_status = InvoiceStatus.FAILED
                bill._change_reason = 'System task: invoice generation failed.'
                bill.save(update_fields=['invoice_status'])
            raise
        raise self.retry(exc=exc)


def _reset_link_lifetime():
    """Human-readable PASSWORD_RESET_TIMEOUT, so the email never disagrees with the real expiry."""
    seconds = settings.PASSWORD_RESET_TIMEOUT
    if seconds >= 86400 and seconds % 86400 == 0:
        days = seconds // 86400
        return f'{days} day{"s" if days != 1 else ""}'
    hours = max(1, round(seconds / 3600))
    return f'{hours} hour{"s" if hours != 1 else ""}'


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_password_reset_email(self, user_id):
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None or not user.email:
        return
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    reset_url = f'{settings.FRONTEND_URL.rstrip("/")}/reset-password/{uid}/{token}'
    try:
        send_mail(
            'Reset your MediCore password',
            f'Use this link to choose a new password. The link expires in {_reset_link_lifetime()}:\n\n{reset_url}',
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
    except Exception as exc:
        raise self.retry(exc=exc)