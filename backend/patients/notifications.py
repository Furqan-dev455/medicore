import logging
import re
from datetime import datetime, timedelta

import requests
from celery import shared_task
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .models import Appointment, AppointmentNotification

logger = logging.getLogger(__name__)


def notify_doctor_dashboard(user_id, event_type):
    """Push a dashboard refresh event to a doctor's active WebSocket sessions.

    Notifications are best-effort: a Redis/channel-layer outage must not turn a
    successfully saved appointment or payment into an HTTP 500.
    """
    if not user_id or not isinstance(event_type, str) or not event_type:
        return
    try:
        from .consumers import doctor_group_name

        channel_layer = get_channel_layer()
        if channel_layer is None:
            logger.warning('Cannot notify doctor %s: no channel layer is configured.', user_id)
            return
        async_to_sync(channel_layer.group_send)(
            doctor_group_name(user_id),
            {'type': 'dashboard.event', 'event_type': event_type},
        )
    except Exception:
        logger.exception('Unable to send dashboard event %s to doctor %s.', event_type, user_id)

# A claim older than this is treated as a crashed worker and the notification is retried.
SENDING_CLAIM_TIMEOUT = timedelta(minutes=10)
NO_RECIPIENT_RETRY_DELAY = timedelta(hours=6)
MAX_RETRY_DELAY_MINUTES = 6 * 60
REMINDER_LEAD_TIME = timedelta(hours=24)
DUE_BATCH_SIZE = 200
SENDGRID_URL = 'https://api.sendgrid.com/v3/mail/send'
TWILIO_MESSAGES_URL = 'https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json'


def _appointment_datetime(appointment):
    value = datetime.combine(appointment.appointment_date, appointment.appointment_time)
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _notification_for(appointment, kind, channel):
    try:
        notification, _ = AppointmentNotification.objects.get_or_create(
            appointment=appointment,
            kind=kind,
            channel=channel,
        )
        return notification
    except IntegrityError:
        return AppointmentNotification.objects.get(
            appointment=appointment,
            kind=kind,
            channel=channel,
        )


def create_appointment_confirmation(appointment_id):
    appointment = Appointment.objects.select_related('patient__user', 'doctor').filter(pk=appointment_id).first()
    if not appointment or appointment.status != Appointment.AppointmentStatus.SCHEDULED:
        return
    delivery = _notification_for(appointment, AppointmentNotification.Kind.CONFIRMATION, AppointmentNotification.Channel.EMAIL)
    if delivery.status != AppointmentNotification.Status.SENT:
        send_appointment_notification.delay(delivery.pk)


def _recipient(delivery):
    appointment = delivery.appointment
    if delivery.channel == AppointmentNotification.Channel.EMAIL:
        user = appointment.patient.user
        return (user.email.strip() if user and user.email else '')
    return (appointment.patient.phone or '').strip()


def _normalize_phone(phone):
    compact = re.sub(r'[\s().-]', '', phone)
    if compact.startswith('00'):
        compact = '+' + compact[2:]
    if not compact.startswith('+'):
        country_code = getattr(settings, 'SMS_DEFAULT_COUNTRY_CODE', '').strip()
        if not country_code:
            raise ValueError('Patient phone must use E.164 format, or configure SMS_DEFAULT_COUNTRY_CODE.')
        country_code = country_code if country_code.startswith('+') else f'+{country_code}'
        compact = country_code + compact.lstrip('0')
    if not re.fullmatch(r'\+[1-9]\d{7,14}', compact):
        raise ValueError('Patient phone number is not a valid E.164 number.')
    return compact


def _send_email(delivery, recipient):
    appointment = delivery.appointment
    subject = 'Appointment confirmation - MediCore'
    local_datetime = timezone.localtime(_appointment_datetime(appointment))
    body = (
        f"Hello {appointment.patient.name},\n\n"
        f"Your appointment with Dr. {appointment.doctor.name} is confirmed for "
        f"{local_datetime:%A, %B %d, %Y at %I:%M %p %Z}.\n\n"
        "Please contact the hospital if you need to change your appointment.\n"
    )
    api_key = getattr(settings, 'SENDGRID_API_KEY', '')
    if api_key:
        response = requests.post(
            SENDGRID_URL,
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={
                'personalizations': [{'to': [{'email': recipient}]}],
                'from': {'email': settings.SENDGRID_FROM_EMAIL or settings.DEFAULT_FROM_EMAIL},
                'subject': subject,
                'content': [{'type': 'text/plain', 'value': body}],
            },
            timeout=15,
        )
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f'SendGrid returned HTTP {response.status_code}.')
        return

    from django.core.mail import send_mail
    sent = send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=False)
    if sent != 1:
        raise RuntimeError('Email backend did not accept the appointment email.')


def _send_sms(delivery, recipient):
    account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
    auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
    from_number = getattr(settings, 'TWILIO_FROM_NUMBER', '')
    service_sid = getattr(settings, 'TWILIO_MESSAGING_SERVICE_SID', '')
    if not account_sid or not auth_token or not (from_number or service_sid):
        raise RuntimeError('Twilio is not configured; set its account credentials and sender.')

    appointment = delivery.appointment
    local_datetime = timezone.localtime(_appointment_datetime(appointment))
    body = (
        f"MediCore reminder: your appointment with Dr. {appointment.doctor.name} is "
        f"{local_datetime:%b %d at %I:%M %p %Z}. Please contact the hospital to reschedule."
    )
    data = {'To': _normalize_phone(recipient), 'Body': body}
    if service_sid:
        data['MessagingServiceSid'] = service_sid
    else:
        data['From'] = from_number
    response = requests.post(
        TWILIO_MESSAGES_URL.format(account_sid=account_sid),
        data=data,
        auth=(account_sid, auth_token),
        timeout=15,
    )
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f'Twilio returned HTTP {response.status_code}.')


def _give_up_if_exhausted(delivery):
    """Stop retrying forever: after MAX_ATTEMPTS the notification is marked failed."""
    if delivery.attempts >= AppointmentNotification.MAX_ATTEMPTS:
        delivery.status = AppointmentNotification.Status.FAILED
        delivery.claimed_at = None
        delivery.save(update_fields=['status', 'claimed_at'])
        logger.warning('Appointment notification %s failed permanently after %s attempts.', delivery.pk, delivery.attempts)
        return True
    return False


@shared_task
def send_appointment_notification(notification_id):
    Status = AppointmentNotification.Status
    now = timezone.now()
    with transaction.atomic():
        delivery = AppointmentNotification.objects.select_for_update().select_related(
            'appointment__patient__user', 'appointment__doctor'
        ).filter(pk=notification_id).first()
        if not delivery or delivery.status in (Status.SENT, Status.FAILED):
            return
        if delivery.status == Status.SENDING and delivery.claimed_at and delivery.claimed_at > now - SENDING_CLAIM_TIMEOUT:
            return
        if delivery.next_attempt_at > now:
            return
        if delivery.appointment.status != Appointment.AppointmentStatus.SCHEDULED:
            return
        if (
            delivery.kind == AppointmentNotification.Kind.REMINDER
            and _appointment_datetime(delivery.appointment) <= now
        ):
            return
        if _give_up_if_exhausted(delivery):
            return
        recipient = _recipient(delivery)
        if not recipient:
            # Counts as an attempt, so a patient with no contact details is
            # eventually marked failed instead of being retried every 6 hours forever.
            delivery.attempts += 1
            delivery.last_error = 'Patient has no email address or phone number on file.'
            delivery.next_attempt_at = now + NO_RECIPIENT_RETRY_DELAY
            delivery.status = Status.PENDING
            delivery.claimed_at = None
            delivery.save(update_fields=['attempts', 'last_error', 'next_attempt_at', 'status', 'claimed_at'])
            _give_up_if_exhausted(delivery)
            return
        delivery.status = Status.SENDING
        delivery.claimed_at = now
        delivery.recipient = recipient
        delivery.attempts += 1
        delivery.save(update_fields=['status', 'claimed_at', 'recipient', 'attempts'])

    try:
        if delivery.channel == AppointmentNotification.Channel.EMAIL:
            _send_email(delivery, recipient)
        else:
            _send_sms(delivery, recipient)
    except Exception as exc:
        exhausted = delivery.attempts >= AppointmentNotification.MAX_ATTEMPTS
        delay_minutes = min(60 * 2 ** min(delivery.attempts - 1, 5), MAX_RETRY_DELAY_MINUTES)
        AppointmentNotification.objects.filter(pk=delivery.pk).update(
            status=Status.FAILED if exhausted else Status.PENDING,
            last_error=str(exc)[:AppointmentNotification.LAST_ERROR_MAX_LENGTH],
            next_attempt_at=timezone.now() + timedelta(minutes=delay_minutes),
            claimed_at=None,
        )
        logger.warning(
            'Appointment notification %s failed (attempt %s/%s): %s',
            delivery.pk, delivery.attempts, AppointmentNotification.MAX_ATTEMPTS, exc,
        )
        return

    AppointmentNotification.objects.filter(pk=delivery.pk).update(
        status=Status.SENT,
        sent_at=timezone.now(),
        last_error='',
        claimed_at=None,
    )


@shared_task
def process_appointment_reminders():
    """Create due 24-hour SMS reminders and retry queued notifications."""
    Status = AppointmentNotification.Status
    now = timezone.now()
    reminder_cutoff = now + REMINDER_LEAD_TIME
    today = timezone.localdate()
    # Only scan the reminder window, not every future appointment.
    appointments = Appointment.objects.filter(
        status=Appointment.AppointmentStatus.SCHEDULED,
        appointment_date__gte=today,
        appointment_date__lte=timezone.localtime(reminder_cutoff).date(),
    ).select_related('patient__user', 'doctor')
    for appointment in appointments.iterator():
        if now < _appointment_datetime(appointment) <= reminder_cutoff:
            _notification_for(appointment, AppointmentNotification.Kind.REMINDER, AppointmentNotification.Channel.SMS)

    due_ids = list(AppointmentNotification.objects.filter(
        # Pending and due, or stuck in "sending" because a worker crashed mid-send.
        Q(status=Status.PENDING, next_attempt_at__lte=now)
        | Q(status=Status.SENDING, claimed_at__lt=now - SENDING_CLAIM_TIMEOUT),
        appointment__status=Appointment.AppointmentStatus.SCHEDULED,
        appointment__appointment_date__gte=today,
    ).order_by('created_at').values_list('pk', flat=True)[:DUE_BATCH_SIZE])
    for notification_id in due_ids:
        send_appointment_notification.delay(notification_id)
