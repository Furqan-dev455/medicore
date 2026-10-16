import hashlib
import hmac
import json
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from io import BytesIO
from math import ceil
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.forms.models import model_to_dict
from django.http import FileResponse, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .forms import AppointmentForm, BillForm, DoctorForm, MedicationForm, PatientForm, PaymentForm, SignUpForm
from .models import (
    ZERO,
    Appointment,
    AppointmentStatus,
    Bill,
    Doctor,
    InvoiceStatus,
    Medication,
    Patient,
    Payment,
    PaymentCheckout,
    PaymentProvider,
    Prescription,
    PrescriptionItem,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class Role:
    ADMIN = 'Admin'
    DOCTOR = 'Doctor'
    PATIENT = 'Patient'
    RECEPTIONIST = 'Receptionist'
    UNASSIGNED = 'Unassigned'


API_ROLES = (Role.ADMIN, Role.DOCTOR, Role.PATIENT, Role.RECEPTIONIST)
FRONT_DESK_ROLES = (Role.ADMIN, Role.RECEPTIONIST)

CURRENCY = 'PKR'
CURRENCY_LABEL = 'Rs.'
MONEY_STEP = Decimal('0.01')

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

MAX_PRESCRIPTION_ITEMS = 30
MAX_PRESCRIPTION_NOTES = 4000
MAX_DOSAGE_LENGTH = 120
MAX_DURATION_LENGTH = 120
MAX_INSTRUCTIONS_LENGTH = 300

LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60
PASSWORD_RESET_MAX_PER_EMAIL = 3
PASSWORD_RESET_MAX_PER_IP = 10
PASSWORD_RESET_WINDOW_SECONDS = 60 * 60

SAFEPAY_SIGNATURE_HEADER = 'X-SFPY-SIGNATURE'
SAFEPAY_SECRET_HEADER = 'X-SFPY-MERCHANT-SECRET'
SAFEPAY_DEFAULT_ENDPOINTS = {
    # environment: (api base, hosted checkout host). Override with
    # settings.SAFEPAY_API_BASE / settings.SAFEPAY_CHECKOUT_HOST if Safepay changes them.
    'sandbox': ('https://sandbox.api.getsafepay.com', 'https://sandbox.api.getsafepay.com'),
    'production': ('https://api.getsafepay.com', 'https://getsafepay.com'),
}
SAFEPAY_TIMEOUT_SECONDS = 15

SLOT_TAKEN_MESSAGE = 'That doctor already has an appointment at this time. Choose another time.'
RESERVED_BALANCE_MESSAGE = (
    'A patient checkout is already reserving part of this bill balance. '
    'Try again after it completes or expires.'
)


def _checkout_expiry():
    return timedelta(minutes=getattr(settings, 'PAYMENT_CHECKOUT_EXPIRY_MINUTES', 60))


# ---------------------------------------------------------------------------
# Roles and permissions
# ---------------------------------------------------------------------------

def _api_role(user):
    """The user's single portal role, or None if they have none or more than one."""
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return Role.ADMIN
    # Iterating .all() uses prefetch_related('groups') when the caller prefetched it.
    assigned_roles = [group.name for group in user.groups.all() if group.name in API_ROLES]
    return assigned_roles[0] if len(assigned_roles) == 1 else None


def role_required(*roles):
    """HTML-view guard: logged in AND holding one of `roles`. Same role rules as the API."""
    def decorator(func):
        @wraps(func)
        @login_required(login_url='login')
        def wrapper(request, *args, **kwargs):
            if _api_role(request.user) in roles:
                return func(request, *args, **kwargs)
            # A 403 instead of redirecting to the dashboard, which would loop for
            # users who cannot see the dashboard either.
            raise PermissionDenied
        return wrapper
    return decorator


# Old name, kept so existing imports keep working.
group_required = role_required


def _api_require_roles(request, allowed_roles):
    if not request.user.is_authenticated:
        return None, JsonResponse({'error': 'Authentication required.'}, status=401)
    role = _api_role(request.user)
    if role not in allowed_roles:
        return role, JsonResponse({'error': 'You do not have permission to access this resource.'}, status=403)
    return role, None


def _patients_visible_to(user, role):
    patients = Patient.objects.active()
    if role in FRONT_DESK_ROLES:
        return patients
    if role == Role.DOCTOR:
        return patients.filter(appointment__doctor__user=user).distinct()
    if role == Role.PATIENT:
        return patients.filter(user=user)
    return patients.none()


def _appointments_visible_to(user, role):
    appointments = Appointment.objects.all()
    if role in FRONT_DESK_ROLES:
        return appointments
    if role == Role.DOCTOR:
        return appointments.filter(doctor__user=user)
    if role == Role.PATIENT:
        return appointments.filter(patient__user=user)
    return appointments.none()


def _bills_visible_to(user, role):
    bills = Bill.objects.all()
    if role == Role.ADMIN:
        return bills
    if role == Role.PATIENT:
        return bills.filter(patient__user=user)
    return bills.none()


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _read_json_body(request):
    try:
        payload = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _form_errors_response(form):
    errors = {
        field: [error['message'] for error in field_errors]
        for field, field_errors in form.errors.get_json_data().items()
    }
    return JsonResponse({'errors': errors}, status=400)


def _parse_positive_int(value):
    """Strict positive integer: rejects booleans, floats like 3.9, and junk strings."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
        return number if number > 0 else None
    return None


def _to_minor_units(amount):
    """Rupees -> paisa as an exact integer."""
    return int((amount * 100).to_integral_value())


def _paginate(request, queryset):
    """Pages a queryset when ?page= is given; returns (items, pagination_meta_or_None).

    Without ?page the full list is returned so the current frontend keeps working.
    Once the frontend sends ?page, every list endpoint is bounded.
    """
    page_param = request.GET.get('page')
    if page_param is None:
        return queryset, None
    page = _parse_positive_int(page_param) or 1
    page_size = min(_parse_positive_int(request.GET.get('page_size', '')) or DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE)
    total = queryset.count()
    start = (page - 1) * page_size
    meta = {
        'page': page,
        'page_size': page_size,
        'total': total,
        'pages': max(1, ceil(total / page_size)),
    }
    return queryset[start:start + page_size], meta


def _with_pagination(payload, meta):
    if meta is not None:
        payload['pagination'] = meta
    return payload


def _client_ip(request):
    # If the app runs behind a reverse proxy, configure it to set REMOTE_ADDR
    # (or replace this with your proxy's trusted header).
    return request.META.get('REMOTE_ADDR', '') or 'unknown'


def _cache_key(prefix, *parts):
    digest = hashlib.sha256('|'.join(str(part) for part in parts).encode('utf-8')).hexdigest()
    return f'{prefix}:{digest}'


def _count_attempt(key, window_seconds):
    """Increment a counter that expires `window_seconds` after its first hit. Returns the new count."""
    cache.add(key, 0, timeout=window_seconds)
    try:
        return cache.incr(key)
    except ValueError:
        # Expired between add() and incr().
        cache.set(key, 1, timeout=window_seconds)
        return 1


def _outstanding_balance(bills):
    """Sum of unpaid balances in two aggregate queries instead of two queries per bill."""
    total = bills.aggregate(total=Sum('total_amount'))['total'] or ZERO
    paid = Payment.objects.filter(bill__in=bills).aggregate(paid=Sum('amount'))['paid'] or ZERO
    return max(total - paid, ZERO)


# ---------------------------------------------------------------------------
# Payments (shared by the HTML view, the admin API and the Safepay webhook)
# ---------------------------------------------------------------------------

def _queue_invoice_generation(bill_id):
    from .tasks import generate_and_email_invoice

    try:
        generate_and_email_invoice.delay(bill_id)
    except Exception:
        logger.exception('Unable to queue invoice generation for bill %s', bill_id)
        bill = Bill.objects.filter(pk=bill_id).first()
        if bill:
            bill.invoice_status = InvoiceStatus.FAILED
            bill._change_reason = 'System task: invoice generation could not be queued.'
            bill.save(update_fields=['invoice_status'])


def _after_payment_recorded(bill, change_reason=None):
    """Mark the invoice for regeneration, then (after commit) notify doctors and queue the invoice.

    Must run inside the same transaction that saved the payment.
    """
    bill.invoice_status = InvoiceStatus.PROCESSING
    bill.invoice_email_sent = False
    if change_reason:
        bill._change_reason = change_reason
    bill.save(update_fields=['invoice_status', 'invoice_email_sent'])

    from .notifications import notify_doctor_dashboard

    doctor_user_ids = list(
        Appointment.objects.filter(patient_id=bill.patient_id, doctor__user__isnull=False)
        .values_list('doctor__user_id', flat=True)
        .distinct()
    )
    for doctor_user_id in doctor_user_ids:
        transaction.on_commit(
            lambda user_id=doctor_user_id: notify_doctor_dashboard(user_id, 'bill.payment_recorded')
        )
    bill_id = bill.pk
    transaction.on_commit(lambda: _queue_invoice_generation(bill_id))


def _record_manual_payment(bill, form, user):
    """Save a staff-entered payment. The caller must hold transaction.atomic() and a
    select_for_update() lock on `bill`.

    Returns (payment, None) on success or (None, (message, http_status)) on failure.
    """
    amount = form.cleaned_data['amount']
    # Never let staff collect money a patient is paying online at the same moment.
    if amount > bill.balance - bill.reserved_checkout_amount():
        return None, (RESERVED_BALANCE_MESSAGE, 409)

    payment = form.save(commit=False)
    payment.bill = bill
    payment.received_by = user
    payment.provider = PaymentProvider.MANUAL
    try:
        payment.save()
    except ValidationError as error:
        return None, (' '.join(error.messages), 400)

    bill.refresh_from_db()
    _after_payment_recorded(bill)
    return payment, None


# ---------------------------------------------------------------------------
# HTML views (server-rendered admin pages)
# ---------------------------------------------------------------------------

@role_required(*FRONT_DESK_ROLES)
def dashboard(request):
    context = {
        'total_patients': Patient.objects.active().count(),
        'total_doctors': Doctor.objects.count(),
        'total_appointments': Appointment.objects.count(),
        'unpaid_bills': Bill.objects.filter(status=Bill.BillStatus.UNPAID).count(),
        'recent_appointments': Appointment.objects.select_related('patient', 'doctor').order_by('-created_at')[:5],
    }
    return render(request, 'dashboard/admin_dashboard.html', context)


# --- Patients ---

@role_required(*FRONT_DESK_ROLES)
def patient_list(request):
    patients = Patient.objects.active()
    return render(request, 'patients/patient_list.html', {'patients': patients})


@role_required(Role.ADMIN)
def create_patient(request):
    form = PatientForm(request.POST or None)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.created_by = request.user
        obj.save()
        messages.success(request, 'Patient added successfully.')
        return redirect('patients:patient_list')
    return render(request, 'patients/patient_form.html', {'form': form, 'title': 'Add Patient'})


@role_required(Role.ADMIN)
def update_patient(request, pk):
    patient = get_object_or_404(Patient.objects.active(), pk=pk)
    form = PatientForm(request.POST or None, instance=patient)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.updated_by = request.user
        obj.save()
        messages.success(request, 'Patient updated successfully.')
        return redirect('patients:patient_list')
    return render(request, 'patients/patient_form.html', {'form': form, 'title': 'Update Patient'})


@role_required(Role.ADMIN)
def delete_patient(request, pk):
    patient = get_object_or_404(Patient.objects.active(), pk=pk)
    if request.method == 'POST':
        patient.soft_delete(request.user)
        messages.success(request, 'Patient moved to trash.')
        return redirect('patients:patient_list')
    return render(request, 'patients/confirm_delete.html', {'patient': patient})


@role_required(Role.ADMIN)
def trash_list(request):
    patients = Patient.objects.deleted()
    return render(request, 'patients/trash_list.html', {'patients': patients})


@require_POST
@role_required(Role.ADMIN)
def restore_patient(request, pk):
    # POST only: a GET link or <img> on any page could otherwise restore patients.
    patient = get_object_or_404(Patient.objects.deleted(), pk=pk)
    patient.restore(request.user)
    messages.success(request, 'Patient restored successfully.')
    return redirect('patients:trash_list')


# --- Doctors ---

@role_required(*FRONT_DESK_ROLES)
def doctor_list(request):
    doctors = Doctor.objects.all()
    return render(request, 'patients/doctor_list.html', {'doctors': doctors})


@role_required(Role.ADMIN)
def register_doctor(request):
    form = DoctorForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Doctor registered successfully.')
        return redirect('patients:doctor_list')
    return render(request, 'patients/doctor_form.html', {'form': form, 'title': 'Register Doctor'})


@role_required(Role.ADMIN)
def update_doctor(request, pk):
    doctor = get_object_or_404(Doctor, pk=pk)
    form = DoctorForm(request.POST or None, instance=doctor)
    if form.is_valid():
        form.save()
        messages.success(request, 'Doctor updated successfully.')
        return redirect('patients:doctor_list')
    return render(request, 'patients/doctor_form.html', {'form': form, 'title': 'Update Doctor'})


# --- Appointments ---

def _save_appointment_with_slot_lock(appointment):
    is_new = appointment.pk is None
    with transaction.atomic():
        # A doctor row is the stable lock target for a time slot, including
        # slots that do not have an appointment row yet.
        Doctor.objects.select_for_update().get(pk=appointment.doctor_id)
        if appointment.status != AppointmentStatus.CANCELLED:
            conflicts = Appointment.objects.filter(
                doctor_id=appointment.doctor_id,
                appointment_date=appointment.appointment_date,
                appointment_time=appointment.appointment_time,
            ).exclude(status=AppointmentStatus.CANCELLED)
            if appointment.pk:
                conflicts = conflicts.exclude(pk=appointment.pk)
            if conflicts.exists():
                return False

        try:
            # The conditional unique constraint is the final guard for writers
            # that do not take the doctor lock.
            with transaction.atomic():
                appointment.save()
        except IntegrityError:
            return False
    doctor_user_id = appointment.doctor.user_id
    if is_new and doctor_user_id:
        from .notifications import notify_doctor_dashboard

        transaction.on_commit(lambda: notify_doctor_dashboard(doctor_user_id, 'appointment.created'))
    return True


def _appointment_slot_conflict_response():
    return JsonResponse({
        'error': 'That doctor already has an appointment at this time.',
        'errors': {'appointment_time': [SLOT_TAKEN_MESSAGE]},
    }, status=409)


@role_required(*FRONT_DESK_ROLES)
def appointment_list(request):
    appointments = Appointment.objects.select_related('patient', 'doctor').order_by('-created_at')
    return render(request, 'patients/appointment_list.html', {'appointments': appointments})


@role_required(*FRONT_DESK_ROLES)
def create_appointment(request):
    form = AppointmentForm(request.POST or None)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.created_by = request.user
        if not _save_appointment_with_slot_lock(obj):
            form.add_error('appointment_time', SLOT_TAKEN_MESSAGE)
            return render(request, 'patients/appointment_form.html', {'form': form, 'title': 'Create Appointment'})
        messages.success(request, 'Appointment created successfully.')
        return redirect('patients:appointment_list')
    return render(request, 'patients/appointment_form.html', {'form': form, 'title': 'Create Appointment'})


@role_required(Role.ADMIN)
def update_appointment(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    form = AppointmentForm(request.POST or None, instance=appointment)
    if form.is_valid():
        if not _save_appointment_with_slot_lock(form.save(commit=False)):
            form.add_error('appointment_time', SLOT_TAKEN_MESSAGE)
            return render(request, 'patients/appointment_form.html', {'form': form, 'title': 'Update Appointment'})
        messages.success(request, 'Appointment updated successfully.')
        return redirect('patients:appointment_list')
    return render(request, 'patients/appointment_form.html', {'form': form, 'title': 'Update Appointment'})


# --- Bills ---

@role_required(Role.ADMIN)
def bill_list(request):
    bills = Bill.objects.with_paid_total().select_related('patient').order_by('-created_at')
    return render(request, 'patients/bill_list.html', {'bills': bills})


@role_required(Role.ADMIN)
def create_bill(request):
    form = BillForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Bill created successfully.')
        return redirect('patients:bill_list')
    return render(request, 'patients/bill_form.html', {'form': form, 'title': 'Create Bill'})


@role_required(Role.ADMIN)
def bill_detail(request, pk):
    bill = get_object_or_404(Bill.objects.select_related('patient'), pk=pk)
    payments = bill.payment_set.order_by('payment_date', 'pk')
    return render(request, 'patients/bill_detail.html', {'bill': bill, 'payments': payments})


@role_required(Role.ADMIN)
def update_bill(request, pk):
    bill = get_object_or_404(Bill, pk=pk)
    form = BillForm(request.POST or None, instance=bill)
    if form.is_valid():
        form.save()
        messages.success(request, 'Bill updated successfully.')
        return redirect('patients:bill_list')
    return render(request, 'patients/bill_form.html', {'form': form, 'title': 'Update Bill'})


@role_required(Role.ADMIN)
def add_payment(request, pk):
    if request.method != 'POST':
        bill = get_object_or_404(Bill, pk=pk)
        return render(request, 'patients/payment_form.html', {'form': PaymentForm(bill=bill), 'bill': bill})

    with transaction.atomic():
        # Lock the bill so two cashiers cannot both take the last balance.
        bill = get_object_or_404(Bill.objects.select_for_update(), pk=pk)
        form = PaymentForm(request.POST, bill=bill)
        if form.is_valid():
            payment, error = _record_manual_payment(bill, form, request.user)
            if payment is not None:
                # The bill status is updated by the model; no manual status code here.
                messages.success(request, 'Payment recorded successfully.')
                return redirect('patients:bill_detail', pk=bill.pk)
            form.add_error('amount', error[0])
    return render(request, 'patients/payment_form.html', {'form': form, 'bill': bill})


# ---------------------------------------------------------------------------
# Invoice PDF
# ---------------------------------------------------------------------------

BRAND_NAME = 'MediCore'
BRAND_TAGLINE = 'HOSPITAL MANAGEMENT'
INVOICE_PREFIX = 'MC'

PRIMARY = colors.HexColor('#0f3b66')
MUTED = colors.HexColor('#64748b')


def invoice_filename(bill):
    return f'{BRAND_NAME}-invoice-{bill.pk}.pdf'


def invoice_number(bill):
    return f'{INVOICE_PREFIX}-{bill.pk:06d}'


def _money(amount):
    return f'{CURRENCY_LABEL} {amount:,.2f}'


def _markup_safe(value):
    """Escape text for ReportLab's mini-markup. Unescaped '<' or '&' in a
    patient name or description would break PDF generation."""
    return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br/>')


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Brand', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=24, leading=28, textColor=PRIMARY, alignment=0, spaceAfter=2))
    styles.add(ParagraphStyle(name='Subtitle', parent=styles['Normal'], fontSize=9, textColor=MUTED))
    styles.add(ParagraphStyle(name='SectionHeading', parent=styles['Heading2'], fontSize=11, leading=14, textColor=PRIMARY, spaceBefore=12, spaceAfter=7))
    styles.add(ParagraphStyle(name='RightBody', parent=styles['Normal'], alignment=TA_RIGHT))
    return styles


def _invoice_pdf_bytes(bill):
    """Return the invoice for `bill` as PDF bytes."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f'{BRAND_NAME} Invoice {bill.pk}',
        author=BRAND_NAME,
    )
    styles = _styles()
    issued = timezone.localtime(bill.created_at)

    story = [
        Table(
            [[
                [Paragraph(BRAND_NAME, styles['Brand']), Paragraph(BRAND_TAGLINE, styles['Subtitle'])],
                [
                    Paragraph('<b>INVOICE</b>', styles['RightBody']),
                    Paragraph(f'Invoice # {invoice_number(bill)}', styles['RightBody']),
                    Paragraph(f'Issued {issued:%d %b %Y}', styles['RightBody']),
                ],
            ]],
            colWidths=[95 * mm, 75 * mm],
            style=TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('LINEBELOW', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
            ]),
        ),
        Spacer(1, 12),
        Paragraph('BILL TO', styles['SectionHeading']),
        Paragraph(f'<b>{_markup_safe(bill.patient.name)}</b>', styles['Normal']),
        Paragraph(f'Status: <b>{_markup_safe(bill.get_status_display())}</b>', styles['Normal']),
        Paragraph('Services', styles['SectionHeading']),
    ]

    description = _markup_safe(bill.description or 'Medical services')
    details = Table(
        [
            [Paragraph('<b>Description</b>', styles['Normal']), Paragraph('<b>Amount</b>', styles['RightBody'])],
            [Paragraph(description, styles['Normal']), Paragraph(_money(bill.total_amount), styles['RightBody'])],
        ],
        colWidths=[125 * mm, 45 * mm],
        repeatRows=1,
        style=TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eff6ff')),
            ('TEXTCOLOR', (0, 0), (-1, 0), PRIMARY),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dbe3ec')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 9),
            ('RIGHTPADDING', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]),
    )
    story.extend([details, Paragraph('Payment history', styles['SectionHeading'])])

    # One query for the payments; the totals below reuse this list.
    payments = list(bill.payment_set.order_by('payment_date', 'pk'))
    payment_rows = [[
        Paragraph('<b>Date</b>', styles['Normal']),
        Paragraph('<b>Method</b>', styles['Normal']),
        Paragraph('<b>Amount</b>', styles['RightBody']),
    ]]
    payment_rows.extend([
        [
            f'{timezone.localtime(payment.payment_date):%d %b %Y, %H:%M}',
            payment.get_payment_method_display(),
            Paragraph(_money(payment.amount), styles['RightBody']),
        ]
        for payment in payments
    ])
    if not payments:
        payment_rows.append([Paragraph('No payments recorded', styles['Subtitle']), '', ''])

    amount_paid = sum((payment.amount for payment in payments), start=0)
    balance_due = max(bill.total_amount - amount_paid, 0)

    payment_table = Table(
        payment_rows,
        colWidths=[55 * mm, 65 * mm, 50 * mm],
        repeatRows=1,
        style=TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8fafc')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ]),
    )
    totals = Table(
        [
            ['Total charges', Paragraph(_money(bill.total_amount), styles['RightBody'])],
            ['Amount paid', Paragraph(_money(amount_paid), styles['RightBody'])],
            [Paragraph('<b>Balance due</b>', styles['Normal']), Paragraph(f'<b>{_money(balance_due)}</b>', styles['RightBody'])],
        ],
        colWidths=[120 * mm, 50 * mm],
        hAlign='RIGHT',
        style=TableStyle([
            ('LINEABOVE', (0, 0), (-1, 0), 1, colors.HexColor('#94a3b8')),
            ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#eff6ff')),
            ('LEFTPADDING', (0, 0), (-1, -1), 9),
            ('RIGHTPADDING', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ]),
    )
    story.extend([
        payment_table,
        Spacer(1, 10),
        KeepTogether([totals]),
        Spacer(1, 22),
        Paragraph(f'Thank you for choosing {BRAND_NAME}.', styles['Subtitle']),
    ])
    document.build(story)
    return buffer.getvalue()


def _invoice_file_response(bill):
    """Serve the stored invoice when it is up to date, otherwise build one now.
    Both paths use the same PDF builder, so the HTML and API invoices match."""
    if bill.invoice_status == InvoiceStatus.READY and bill.invoice_pdf:
        return FileResponse(
            bill.invoice_pdf.open('rb'),
            as_attachment=True,
            filename=invoice_filename(bill),
            content_type='application/pdf',
        )
    response = HttpResponse(_invoice_pdf_bytes(bill), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{invoice_filename(bill)}"'
    return response


@role_required(Role.ADMIN)
def download_invoice(request, pk):
    bill = get_object_or_404(Bill.objects.select_related('patient'), pk=pk)
    return _invoice_file_response(bill)


# ---------------------------------------------------------------------------
# API endpoints for the Next.js frontend
# ---------------------------------------------------------------------------

def _appointment_summary(appointment):
    return {
        'id': appointment.id,
        'patient': appointment.patient.name,
        'doctor': appointment.doctor.name,
        'date': appointment.appointment_date.isoformat(),
        'time': appointment.appointment_time.strftime('%H:%M'),
        'status': appointment.status,
    }


def _bill_summary(bill):
    paid = bill.amount_paid
    return {
        'id': bill.id,
        'patient': bill.patient.name,
        'total': float(bill.total_amount),
        'paid': float(paid),
        'balance': float(max(bill.total_amount - paid, ZERO)),
        'status': bill.status,
    }


def dashboard_api(request):
    role, auth_error = _api_require_roles(request, API_ROLES)
    if auth_error:
        return auth_error

    today = timezone.localdate()
    recent_appointments = (
        _appointments_visible_to(request.user, role).select_related('patient', 'doctor').order_by('-created_at')[:5]
    )
    # The full queryset feeds the stats; only the list shown on the page is sliced.
    all_bills = _bills_visible_to(request.user, role)
    recent_bills = all_bills.with_paid_total().select_related('patient').order_by('-created_at')[:3]

    if role == Role.ADMIN:
        stats = [
            {'label': 'Patients', 'value': Patient.objects.active().count(), 'change': 'All records', 'tone': 'emerald'},
            {'label': 'Doctors', 'value': Doctor.objects.count(), 'change': 'All staff', 'tone': 'blue'},
            {'label': 'Appointments', 'value': Appointment.objects.count(), 'change': 'All schedules', 'tone': 'violet'},
            {'label': 'Outstanding', 'value': float(_outstanding_balance(Bill.objects.all())), 'change': 'Current balance', 'tone': 'amber'},
        ]
    elif role == Role.RECEPTIONIST:
        stats = [
            {'label': 'Patients', 'value': Patient.objects.active().count(), 'change': 'Directory', 'tone': 'emerald'},
            {'label': 'Doctors', 'value': Doctor.objects.count(), 'change': 'Available staff', 'tone': 'blue'},
            {'label': 'Appointments', 'value': Appointment.objects.count(), 'change': 'All schedules', 'tone': 'violet'},
            {'label': "Today's appointments", 'value': Appointment.objects.filter(appointment_date=today).count(), 'change': 'Today', 'tone': 'amber'},
        ]
    elif role == Role.DOCTOR:
        visible_appointments = _appointments_visible_to(request.user, role)
        stats = [
            {'label': 'Assigned patients', 'value': _patients_visible_to(request.user, role).count(), 'change': 'Care team', 'tone': 'emerald'},
            {'label': 'My appointments', 'value': visible_appointments.count(), 'change': 'My schedule', 'tone': 'blue'},
            {'label': "Today's schedule", 'value': visible_appointments.filter(appointment_date=today).count(), 'change': 'Today', 'tone': 'violet'},
            {'label': 'Upcoming', 'value': visible_appointments.filter(appointment_date__gte=today, status=AppointmentStatus.SCHEDULED).count(), 'change': 'Scheduled', 'tone': 'amber'},
        ]
    else:
        own_appointments = _appointments_visible_to(request.user, role)
        stats = [
            {'label': 'My appointments', 'value': own_appointments.count(), 'change': 'My schedule', 'tone': 'emerald'},
            {'label': 'Upcoming', 'value': own_appointments.filter(appointment_date__gte=today, status=AppointmentStatus.SCHEDULED).count(), 'change': 'Scheduled', 'tone': 'blue'},
            {'label': 'My bills', 'value': all_bills.count(), 'change': 'Billing records', 'tone': 'violet'},
            {'label': 'Balance due', 'value': float(_outstanding_balance(all_bills)), 'change': 'My account', 'tone': 'amber'},
        ]

    return JsonResponse({
        'role': role,
        'stats': stats,
        'recent_appointments': [_appointment_summary(appointment) for appointment in recent_appointments],
        'bills': [_bill_summary(bill) for bill in recent_bills],
    })


def patient_list_api(request):
    role, error = _api_require_roles(request, API_ROLES)
    if error:
        return error
    can_see_all_history = role == Role.ADMIN or (
        role == Role.DOCTOR and request.user.has_perm('patients.view_patient_medical_history')
    )
    patients, meta = _paginate(request, _patients_visible_to(request.user, role).order_by('-created_at'))
    payload = []
    for patient in patients:
        item = {
            'id': patient.id,
            'name': patient.name,
            'age': patient.age,
            'gender': patient.gender,
            'phone': patient.phone,
            'address': patient.address,
            # Deleted patients are filtered out above, so every listed patient is active.
            'status': 'Active',
        }
        if can_see_all_history or (role == Role.PATIENT and patient.user_id == request.user.id):
            item['medical_history'] = patient.medical_history
        payload.append(item)
    return JsonResponse(_with_pagination({'patients': payload}, meta))


def doctor_list_api(request):
    role, error = _api_require_roles(request, API_ROLES)
    if error:
        return error
    doctors = Doctor.objects.all()
    if role == Role.DOCTOR:
        doctors = doctors.filter(user=request.user)
    doctors, meta = _paginate(request, doctors.order_by('name'))
    payload = [{
        'id': doctor.id,
        'name': doctor.name,
        'specialization': doctor.specialization,
        'phone': doctor.phone,
        'email': doctor.email,
    } for doctor in doctors]
    return JsonResponse(_with_pagination({'doctors': payload}, meta))


def appointment_list_api(request):
    role, error = _api_require_roles(request, API_ROLES)
    if error:
        return error
    appointments, meta = _paginate(
        request,
        _appointments_visible_to(request.user, role).select_related('patient', 'doctor').order_by('-created_at'),
    )
    payload = []
    for appointment in appointments:
        item = {
            **_appointment_summary(appointment),
            'patient_id': appointment.patient_id,
            'doctor_id': appointment.doctor_id,
        }
        if role != Role.RECEPTIONIST:
            item['notes'] = appointment.notes
        payload.append(item)
    return JsonResponse(_with_pagination({'appointments': payload}, meta))


def bill_list_api(request):
    role, error = _api_require_roles(request, (Role.ADMIN, Role.PATIENT))
    if error:
        return error
    bills, meta = _paginate(
        request,
        _bills_visible_to(request.user, role).with_paid_total().select_related('patient').order_by('-created_at'),
    )
    payload = [{
        **_bill_summary(bill),
        'patient_id': bill.patient_id,
        'total_amount': str(bill.total_amount),
        'description': bill.description,
        'invoice_status': bill.invoice_status,
    } for bill in bills]
    return JsonResponse(_with_pagination({'bills': payload}, meta))


@require_POST
@transaction.atomic
def bill_payment_api(request, pk):
    _, auth_error = _api_require_roles(request, (Role.ADMIN,))
    if auth_error:
        return auth_error

    bill = get_object_or_404(Bill.objects.select_for_update(), pk=pk)
    payload = _read_json_body(request)
    if payload is None:
        return JsonResponse({'error': 'Request body must be a JSON object.'}, status=400)

    form = PaymentForm(payload, bill=bill)
    if not form.is_valid():
        return _form_errors_response(form)

    payment, error = _record_manual_payment(bill, form, request.user)
    if payment is None:
        message, status = error
        return JsonResponse({'error': message}, status=status)

    paid = bill.amount_paid
    return JsonResponse({
        'payment_id': payment.pk,
        'bill': {
            'id': bill.pk,
            'total': float(bill.total_amount),
            'paid': float(paid),
            'balance': float(max(bill.total_amount - paid, ZERO)),
            'status': bill.status,
            'invoice_status': bill.invoice_status,
        },
    }, status=201)


@require_GET
def bill_invoice_api(request, pk):
    role, auth_error = _api_require_roles(request, (Role.ADMIN, Role.PATIENT))
    if auth_error:
        return auth_error
    bill = get_object_or_404(Bill.objects.select_related('patient'), pk=pk)
    if role == Role.PATIENT and bill.patient.user_id != request.user.id:
        return JsonResponse({'error': 'You do not have permission to access this invoice.'}, status=403)
    if bill.invoice_status != InvoiceStatus.READY or not bill.invoice_pdf:
        return JsonResponse({'status': bill.invoice_status, 'message': 'Invoice is being prepared.'}, status=202)
    # Streams the file instead of reading the whole PDF into memory.
    return FileResponse(
        bill.invoice_pdf.open('rb'),
        as_attachment=True,
        filename=invoice_filename(bill),
        content_type='application/pdf',
    )


# --- Prescriptions ---

def _prescription_payload(prescription):
    return {
        'id': prescription.pk,
        'patient_id': prescription.patient_id,
        'appointment_id': prescription.appointment_id,
        'patient': prescription.patient.name,
        'doctor': prescription.doctor.name,
        'date': prescription.created_at.isoformat(),
        'notes': prescription.notes,
        'items': [{
            'medication_id': item.medication_id,
            'medication': str(item.medication),
            'quantity': item.quantity,
            'unit': item.medication.unit,
            'dosage': item.dosage,
            'duration': item.duration,
            'instructions': item.instructions,
        } for item in prescription.items.all()],
    }


def _parse_prescription_items(raw_items):
    """Validate the items list. Returns (lines, None) or (None, error_response)."""
    if not isinstance(raw_items, list) or not raw_items or len(raw_items) > MAX_PRESCRIPTION_ITEMS:
        return None, JsonResponse({'error': f'Add between 1 and {MAX_PRESCRIPTION_ITEMS} medicines to the prescription.'}, status=400)

    lines = []
    seen_ids = set()
    for item in raw_items:
        if not isinstance(item, dict):
            return None, JsonResponse({'error': 'Each medicine entry must be an object.'}, status=400)
        medication_id = _parse_positive_int(item.get('medication_id'))
        quantity = _parse_positive_int(item.get('quantity'))
        if medication_id is None or quantity is None:
            return None, JsonResponse({'error': 'Each medicine needs a valid item and a whole-number quantity.'}, status=400)
        dosage = item.get('dosage', '')
        duration = item.get('duration', '')
        instructions = item.get('instructions', '')
        if (
            not isinstance(dosage, str) or not dosage.strip() or len(dosage) > MAX_DOSAGE_LENGTH
            or not isinstance(duration, str) or len(duration) > MAX_DURATION_LENGTH
            or not isinstance(instructions, str) or len(instructions) > MAX_INSTRUCTIONS_LENGTH
        ):
            return None, JsonResponse({'error': 'Check medicine dosage, duration, and instructions.'}, status=400)
        if medication_id in seen_ids:
            return None, JsonResponse({'error': 'A medication may only appear once on a prescription.'}, status=400)
        seen_ids.add(medication_id)
        lines.append({
            'medication_id': medication_id,
            'quantity': quantity,
            'dosage': dosage.strip(),
            'duration': duration.strip(),
            'instructions': instructions.strip(),
        })
    return lines, None


@require_http_methods(['GET', 'POST'])
def prescriptions_api(request):
    role, auth_error = _api_require_roles(request, (Role.ADMIN, Role.DOCTOR, Role.PATIENT))
    if auth_error:
        return auth_error

    if request.method == 'GET':
        prescriptions = Prescription.objects.select_related('patient', 'doctor').prefetch_related('items__medication')
        if role == Role.DOCTOR:
            prescriptions = prescriptions.filter(doctor__user=request.user)
        elif role == Role.PATIENT:
            prescriptions = prescriptions.filter(patient__user=request.user)
        prescriptions, meta = _paginate(request, prescriptions)
        return JsonResponse(_with_pagination({'prescriptions': [_prescription_payload(p) for p in prescriptions]}, meta))

    if role != Role.DOCTOR:
        return JsonResponse({'error': 'Only doctors can write prescriptions.'}, status=403)
    try:
        doctor = request.user.doctor_profile
    except Doctor.DoesNotExist:
        return JsonResponse({'error': 'This account is not linked to a doctor profile.'}, status=403)

    payload = _read_json_body(request)
    if payload is None:
        return JsonResponse({'error': 'Request body must be a JSON object.'}, status=400)
    patient_id = _parse_positive_int(payload.get('patient_id'))
    if patient_id is None:
        return JsonResponse({'error': 'Choose a valid patient.'}, status=400)

    notes = payload.get('notes', '')
    if not isinstance(notes, str) or len(notes) > MAX_PRESCRIPTION_NOTES:
        return JsonResponse({'error': f'Prescription notes must be {MAX_PRESCRIPTION_NOTES:,} characters or fewer.'}, status=400)
    lines, error_response = _parse_prescription_items(payload.get('items'))
    if error_response:
        return error_response

    active_statuses = (AppointmentStatus.SCHEDULED, AppointmentStatus.COMPLETED)
    with transaction.atomic():
        patient = Patient.objects.active().filter(pk=patient_id).first()
        appointment = None
        if patient is not None:
            appointment = (
                Appointment.objects.filter(patient=patient, doctor=doctor, status__in=active_statuses)
                .order_by('-appointment_date', '-appointment_time')
                .first()
            )
        if appointment is None:
            return JsonResponse({'error': 'You can only prescribe for a patient assigned to you.'}, status=403)

        medication_ids = [line['medication_id'] for line in lines]
        medications = {
            medication.pk: medication
            for medication in Medication.objects.select_for_update()
            .filter(pk__in=medication_ids, is_active=True)
            .order_by('pk')
        }
        if len(medications) != len(medication_ids):
            return JsonResponse({'error': 'One or more selected medicines are unavailable.'}, status=400)
        insufficient = [
            f"{medications[line['medication_id']].name}: {medications[line['medication_id']].stock_quantity} available"
            for line in lines
            if medications[line['medication_id']].stock_quantity < line['quantity']
        ]
        if insufficient:
            return JsonResponse({'error': 'Insufficient pharmacy stock. ' + '; '.join(insufficient)}, status=409)

        prescription = Prescription.objects.create(
            patient=patient,
            doctor=doctor,
            appointment=appointment,
            notes=notes.strip(),
        )
        for line in lines:
            medication = medications[line['medication_id']]
            # NOTE: stock is deducted when the prescription is written, not when it
            # is dispensed. If you add a dispensing step, move this there and use
            # medication.dispense(quantity).
            medication.dispense(line['quantity'])
            PrescriptionItem.objects.create(
                prescription=prescription,
                medication=medication,
                quantity=line['quantity'],
                dosage=line['dosage'],
                duration=line['duration'],
                instructions=line['instructions'],
            )

    prescription = (
        Prescription.objects.select_related('patient', 'doctor').prefetch_related('items__medication').get(pk=prescription.pk)
    )
    return JsonResponse({'prescription': _prescription_payload(prescription)}, status=201)


# --- Inventory ---

@require_http_methods(['GET', 'POST', 'PUT'])
@transaction.atomic
def inventory_api(request, pk=None):
    role, auth_error = _api_require_roles(request, (Role.ADMIN, Role.DOCTOR))
    if auth_error:
        return auth_error
    if (pk is not None and request.method != 'PUT') or (pk is None and request.method == 'PUT'):
        return JsonResponse({'error': 'Unsupported inventory operation.'}, status=405)
    if request.method != 'GET':
        if role != Role.ADMIN:
            return JsonResponse({'error': 'Only administrators can manage pharmacy inventory.'}, status=403)
        payload = _read_json_body(request)
        if payload is None:
            return JsonResponse({'error': 'Request body must be a JSON object.'}, status=400)
        instance = None
        if request.method == 'PUT':
            try:
                instance = Medication.objects.select_for_update().get(pk=pk)
            except (Medication.DoesNotExist, ValueError, TypeError):
                return JsonResponse({'error': 'Medicine not found.'}, status=404)
        form = MedicationForm(payload, instance=instance)
        if not form.is_valid():
            return _form_errors_response(form)
        medicine = form.save()
        return JsonResponse({'id': medicine.pk}, status=201 if instance is None else 200)
    medications = Medication.objects.all() if role == Role.ADMIN else Medication.objects.filter(is_active=True)
    return JsonResponse({'medications': [{
        'id': medicine.pk,
        'name': medicine.name,
        'strength': medicine.strength,
        'dosage_form': medicine.dosage_form,
        'unit': medicine.unit,
        'stock_quantity': medicine.stock_quantity,
        'low_stock': medicine.is_low_stock,
    } for medicine in medications]})


# --- Online payments (Safepay) ---

def _safepay_endpoints(environment):
    default_api, default_checkout = SAFEPAY_DEFAULT_ENDPOINTS[environment]
    api_base = getattr(settings, 'SAFEPAY_API_BASE', '') or default_api
    checkout_host = getattr(settings, 'SAFEPAY_CHECKOUT_HOST', '') or default_checkout
    return api_base.rstrip('/'), checkout_host.rstrip('/')


def _parse_checkout_amount(raw_amount, available):
    """Returns the amount to charge, or None if invalid. Missing amount = full available balance."""
    if raw_amount in (None, ''):
        return available
    if isinstance(raw_amount, bool) or not isinstance(raw_amount, (int, float, str)):
        return None
    try:
        amount = Decimal(str(raw_amount))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount != amount.quantize(MONEY_STEP):
        return None
    return amount


@require_POST
def patient_payment_checkout_api(request, pk):
    _, auth_error = _api_require_roles(request, (Role.PATIENT,))
    if auth_error:
        return auth_error
    if not (settings.SAFEPAY_API_KEY and settings.SAFEPAY_SECRET_KEY):
        return JsonResponse({'error': 'Patient checkout is not configured yet. Add Safepay sandbox keys to the backend .env.'}, status=503)
    environment = settings.SAFEPAY_ENVIRONMENT
    # Checked before a checkout row is created, so a misconfiguration leaves nothing behind.
    if environment not in SAFEPAY_DEFAULT_ENDPOINTS:
        return JsonResponse({'error': 'Safepay environment must be sandbox or production.'}, status=503)
    payload = _read_json_body(request)
    if payload is None:
        return JsonResponse({'error': 'Request body must be a JSON object.'}, status=400)

    with transaction.atomic():
        bill = get_object_or_404(Bill.objects.select_for_update(), pk=pk)
        if bill.patient.user_id != request.user.id:
            return JsonResponse({'error': 'Bill not found.'}, status=404)
        now = timezone.now()
        PaymentCheckout.objects.filter(
            bill=bill, status=PaymentCheckout.Status.PENDING, expires_at__lte=now
        ).update(status=PaymentCheckout.Status.FAILED)
        available = bill.balance - bill.reserved_checkout_amount()
        amount = _parse_checkout_amount(payload.get('amount'), available)
        if amount is None:
            return JsonResponse({'error': 'Enter a valid payment amount.'}, status=400)
        if amount <= 0 or amount > available:
            return JsonResponse({'error': f'Payment amount must be between {CURRENCY_LABEL} 0.01 and {CURRENCY_LABEL} {available}.'}, status=400)
        checkout = PaymentCheckout.objects.create(
            bill=bill,
            patient=bill.patient,
            amount=amount.quantize(MONEY_STEP),
            expires_at=now + _checkout_expiry(),
        )

    api_base, checkout_host = _safepay_endpoints(environment)
    headers = {SAFEPAY_SECRET_HEADER: settings.SAFEPAY_SECRET_KEY}
    try:
        session_response = requests.post(
            f'{api_base}/order/payments/v3/',
            headers=headers,
            json={
                'merchant_api_key': settings.SAFEPAY_API_KEY,
                'intent': 'CYBERSOURCE',
                'mode': 'payment',
                'entry_mode': 'raw',
                'currency': CURRENCY,
                'amount': _to_minor_units(checkout.amount),
                'metadata': {'order_id': str(checkout.pk)},
                'include_fees': False,
            },
            timeout=SAFEPAY_TIMEOUT_SECONDS,
        )
        session_response.raise_for_status()
        tracker = session_response.json()['data']['tracker']['token']
        token_response = requests.post(f'{api_base}/client/passport/v1/token', headers=headers, timeout=SAFEPAY_TIMEOUT_SECONDS)
        token_response.raise_for_status()
        time_token = token_response.json()['data']
        if not isinstance(tracker, str) or not isinstance(time_token, str):
            raise ValueError('Safepay returned an invalid checkout session.')
    except (requests.RequestException, ValueError, KeyError, TypeError):
        logger.exception('Unable to create Safepay checkout for bill %s', pk)
        PaymentCheckout.objects.filter(pk=checkout.pk, status=PaymentCheckout.Status.PENDING).update(
            status=PaymentCheckout.Status.FAILED
        )
        return JsonResponse({'error': 'The payment provider could not start checkout. Please try again.'}, status=502)

    checkout.tracker_token = tracker
    checkout.save(update_fields=['tracker_token'])
    frontend_url = settings.FRONTEND_URL.rstrip('/')
    params = urlencode({
        'env': environment,
        'beacon': tracker,
        'tbt': time_token,
        'source': 'hosted',
        'order_id': checkout.pk,
        'redirect_url': f'{frontend_url}/bills?payment=return&tracker={tracker}',
        'cancel_url': f'{frontend_url}/bills?payment=cancelled',
        'webhooks': 'true',
    })
    return JsonResponse({'checkout_url': f'{checkout_host}/checkout/pay?{params}'})


@require_GET
def patient_payment_checkout_status_api(request, tracker):
    _, auth_error = _api_require_roles(request, (Role.PATIENT,))
    if auth_error:
        return auth_error
    checkout = get_object_or_404(PaymentCheckout, tracker_token=tracker, patient__user=request.user)
    return JsonResponse({
        'status': checkout.status,
        'amount': str(checkout.amount),
        'bill_id': checkout.bill_id,
    })


def _flag_checkout_for_reconciliation(checkout, tracker, reason):
    """The gateway took the patient's money but it cannot be applied to the bill.
    Record it in the database (not just a log line) so an admin can refund or apply it."""
    checkout.status = PaymentCheckout.Status.NEEDS_RECONCILIATION
    checkout.completed_at = timezone.now()
    checkout.save(update_fields=['status', 'completed_at'])
    logger.error('Safepay payment %s for Bill #%s needs reconciliation: %s', tracker, checkout.bill_id, reason)


@csrf_exempt
@require_POST
def safepay_webhook_api(request):
    secret = settings.SAFEPAY_WEBHOOK_SECRET
    if not secret:
        return JsonResponse({'error': 'Webhook signing key is not configured.'}, status=503)
    signature = request.headers.get(SAFEPAY_SIGNATURE_HEADER, '').removeprefix('sha512=').strip()
    expected = hmac.new(secret.encode('utf-8'), request.body, hashlib.sha512).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected):
        return JsonResponse({'error': 'Invalid webhook signature.'}, status=400)
    try:
        event = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid webhook payload.'}, status=400)
    if not isinstance(event, dict):
        return JsonResponse({'error': 'Invalid webhook payload.'}, status=400)
    if event.get('type') != 'payment.succeeded':
        return JsonResponse({'received': True})

    data = event.get('data') or {}
    if not isinstance(data, dict):
        return JsonResponse({'error': 'Invalid webhook payload.'}, status=400)
    tracker = data.get('tracker')
    if isinstance(tracker, dict):
        tracker = tracker.get('token')
    # Safepay's payment.succeeded event itself is the success signal; its
    # documented payload does not include a separate `success` boolean.
    if not isinstance(tracker, str) or not tracker.startswith('track_'):
        return JsonResponse({'error': 'Invalid payment confirmation.'}, status=400)
    received_minor = _parse_positive_int(data.get('amount'))
    if received_minor is None:
        return JsonResponse({'error': 'Invalid payment amount.'}, status=400)
    if str(data.get('currency', '')).upper() != CURRENCY:
        return JsonResponse({'error': 'Unexpected payment currency.'}, status=400)

    with transaction.atomic():
        checkout = PaymentCheckout.objects.select_for_update().filter(tracker_token=tracker).first()
        if checkout is None:
            return JsonResponse({'error': 'Checkout not found.'}, status=404)
        if checkout.status in (PaymentCheckout.Status.COMPLETED, PaymentCheckout.Status.NEEDS_RECONCILIATION):
            return JsonResponse({'received': True, 'duplicate': True})
        bill = Bill.objects.select_for_update().get(pk=checkout.bill_id)
        if received_minor != _to_minor_units(checkout.amount) or bill.patient_id != checkout.patient_id:
            return JsonResponse({'error': 'Payment confirmation does not match checkout.'}, status=400)
        if Payment.objects.filter(provider=PaymentProvider.SAFEPAY, provider_reference=tracker).exists():
            checkout.status = PaymentCheckout.Status.COMPLETED
            checkout.completed_at = timezone.now()
            checkout.save(update_fields=['status', 'completed_at'])
            return JsonResponse({'received': True, 'duplicate': True})

        # Note: a checkout marked FAILED because it expired is still accepted here,
        # because the patient really did pay.
        if bill.balance < checkout.amount:
            # e.g. staff took cash after the checkout expired. Acknowledge with 200 so
            # Safepay stops retrying; the money is tracked on the checkout row.
            _flag_checkout_for_reconciliation(checkout, tracker, 'payment exceeds the remaining bill balance')
            return JsonResponse({'received': True, 'reconciliation_required': True})

        payment = Payment(
            bill=bill,
            amount=checkout.amount,
            payment_method=Payment.PaymentMethod.CARD,
            provider=PaymentProvider.SAFEPAY,
            provider_reference=tracker,
        )
        payment._change_reason = 'Safepay webhook: payment.succeeded.'
        try:
            payment.save()
        except ValidationError as error:
            _flag_checkout_for_reconciliation(checkout, tracker, ' '.join(error.messages))
            return JsonResponse({'received': True, 'reconciliation_required': True})

        checkout.status = PaymentCheckout.Status.COMPLETED
        checkout.completed_at = timezone.now()
        checkout.save(update_fields=['status', 'completed_at'])
        bill.refresh_from_db()
        _after_payment_recorded(bill, change_reason='Safepay webhook: payment.succeeded.')

    return JsonResponse({'received': True})


# --- Generic record create/update ---

@require_http_methods(['GET', 'POST'])
def record_collection_api(request, resource):
    role, auth_error = _api_require_roles(request, API_ROLES)
    if auth_error:
        return auth_error

    if request.method == 'POST':
        if role != Role.ADMIN and not (resource == 'appointments' and role in (Role.RECEPTIONIST, Role.PATIENT)):
            return JsonResponse({'error': 'You do not have permission to create this record.'}, status=403)
        return record_write_api(request, resource)

    list_views = {
        'patients': patient_list_api,
        'doctors': doctor_list_api,
        'appointments': appointment_list_api,
        'bills': bill_list_api,
    }
    list_view = list_views.get(resource)
    if list_view is None:
        return JsonResponse({'error': 'Unknown resource.'}, status=404)
    return list_view(request)


# resource: (form, queryset for lookups, creator field, updater field)
WRITABLE_RESOURCES = {
    'patients': (PatientForm, lambda: Patient.objects.active(), 'created_by', 'updated_by'),
    'doctors': (DoctorForm, lambda: Doctor.objects.all(), None, None),
    'appointments': (AppointmentForm, lambda: Appointment.objects.all(), 'created_by', None),
    'bills': (BillForm, lambda: Bill.objects.all(), None, None),
}


@require_http_methods(['POST', 'PUT', 'PATCH'])
@transaction.atomic
def record_write_api(request, resource, pk=None):
    role, auth_error = _api_require_roles(request, API_ROLES)
    if auth_error:
        return auth_error

    if role != Role.ADMIN and not (
        resource == 'appointments' and request.method == 'POST' and role in (Role.RECEPTIONIST, Role.PATIENT)
    ):
        return JsonResponse({'error': 'You do not have permission to modify this record.'}, status=403)
    if role == Role.PATIENT and (resource != 'appointments' or request.method != 'POST' or pk is not None):
        return JsonResponse({'error': 'Patients can only book new appointments.'}, status=403)

    config = WRITABLE_RESOURCES.get(resource)
    if config is None:
        return JsonResponse({'error': 'Unknown resource.'}, status=404)
    form_class, get_queryset, creator_field, updater_field = config

    payload = _read_json_body(request)
    if payload is None:
        return JsonResponse({'error': 'Request body must be a JSON object.'}, status=400)

    if role == Role.PATIENT:
        try:
            patient = request.user.patient_profile
        except Patient.DoesNotExist:
            return JsonResponse({'error': 'This account is not linked to a patient profile.'}, status=403)
        if patient.is_deleted:
            return JsonResponse({'error': 'This patient profile is inactive.'}, status=403)
        payload = {
            **payload,
            'patient': patient.pk,
            'status': AppointmentStatus.SCHEDULED,
        }

    # Soft-deleted patients are not editable through the API.
    instance = get_object_or_404(get_queryset(), pk=pk) if pk is not None else None
    if instance is not None and request.method == 'PATCH':
        # PATCH = partial update: start from the record's current values so
        # fields the client did not send are kept instead of failing validation.
        current = model_to_dict(instance, fields=form_class._meta.fields)
        payload = {**current, **payload}

    form = form_class(payload, instance=instance)
    if not form.is_valid():
        return _form_errors_response(form)

    record = form.save(commit=False)
    if instance is None and creator_field:
        setattr(record, creator_field, request.user)
    if instance is not None and updater_field:
        setattr(record, updater_field, request.user)

    if resource == 'appointments':
        if not _save_appointment_with_slot_lock(record):
            return _appointment_slot_conflict_response()
    else:
        record.save()
    return JsonResponse({'id': record.pk}, status=201 if instance is None else 200)


# ---------------------------------------------------------------------------
# Auth, session and user management
# ---------------------------------------------------------------------------

@require_GET
def csrf_api(request):
    return JsonResponse({'csrfToken': get_token(request)})


def csrf_failure(request, reason=''):
    logger.warning('CSRF request rejected for %s: %s', request.path, reason)
    return JsonResponse(
        {'error': 'CSRF verification failed. Refresh the page and try again.', 'reason': reason},
        status=403,
    )


@require_GET
def auth_session_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({'authenticated': False})
    return JsonResponse({
        'authenticated': True,
        'username': request.user.get_username(),
        'role': _api_role(request.user) or Role.UNASSIGNED,
    })


@require_GET
def user_roles_api(request):
    _, auth_error = _api_require_roles(request, (Role.ADMIN,))
    if auth_error:
        return auth_error

    doctors = list(Doctor.objects.order_by('name'))
    patients = list(Patient.objects.active().order_by('name'))
    doctors_by_user = {doctor.user_id: doctor for doctor in doctors if doctor.user_id}
    patients_by_user = {patient.user_id: patient for patient in patients if patient.user_id}
    # prefetch_related('groups') turns one groups query per user into a single query.
    users = User.objects.order_by('username').prefetch_related('groups')

    return JsonResponse({
        'current_user_id': request.user.pk,
        'doctor_profiles': [
            {'id': doctor.pk, 'name': doctor.name, 'user_id': doctor.user_id}
            for doctor in doctors
        ],
        'patient_profiles': [
            {'id': patient.pk, 'name': patient.name, 'user_id': patient.user_id}
            for patient in patients
        ],
        'users': [
            {
                'id': user.pk,
                'username': user.get_username(),
                'email': user.email,
                'role': _api_role(user) or Role.UNASSIGNED,
                'is_active': user.is_active,
                'is_superuser': user.is_superuser,
                'doctor_profile_id': doctors_by_user[user.pk].pk if user.pk in doctors_by_user else None,
                'patient_profile_id': patients_by_user[user.pk].pk if user.pk in patients_by_user else None,
            }
            for user in users
        ],
    })


def _active_admin_count():
    return (
        User.objects.filter(is_active=True)
        .filter(Q(is_superuser=True) | Q(groups__name=Role.ADMIN))
        .distinct()
        .count()
    )


def _unlink_profile(profile):
    if profile is not None:
        profile.user = None
        profile.save(update_fields=['user'])


@require_POST
@transaction.atomic
def user_role_api(request, pk):
    _, auth_error = _api_require_roles(request, (Role.ADMIN,))
    if auth_error:
        return auth_error

    payload = _read_json_body(request)
    if payload is None:
        return JsonResponse({'error': 'Request body must be a JSON object.'}, status=400)

    role = payload.get('role')
    if role not in (*API_ROLES, Role.UNASSIGNED):
        return JsonResponse({'error': 'Choose a valid portal role.'}, status=400)

    user = get_object_or_404(User.objects.select_for_update(), pk=pk)
    if user.is_superuser and role != Role.ADMIN:
        return JsonResponse({'error': 'Superuser accounts must keep the Admin role.'}, status=400)
    if role != Role.ADMIN:
        # Prevent locking everyone out of user management.
        if user.pk == request.user.pk:
            return JsonResponse({'error': 'You cannot remove your own Admin role. Ask another administrator.'}, status=400)
        if _api_role(user) == Role.ADMIN and _active_admin_count() <= 1:
            return JsonResponse({'error': 'This is the last administrator account and must keep the Admin role.'}, status=400)

    profile_id = payload.get('profile_id')
    if profile_id == '':
        profile_id = None
    if profile_id is not None and (isinstance(profile_id, bool) or not isinstance(profile_id, int) or profile_id < 1):
        return JsonResponse({'error': 'Choose a valid linked profile.'}, status=400)

    doctor_profile = None
    patient_profile = None
    if role == Role.DOCTOR and profile_id is not None:
        doctor_profile = get_object_or_404(Doctor.objects.select_for_update(), pk=profile_id)
        if doctor_profile.user_id not in (None, user.pk):
            return JsonResponse({'error': 'That doctor profile is already linked to another account.'}, status=400)
    elif role == Role.PATIENT and profile_id is not None:
        patient_profile = get_object_or_404(Patient.objects.active().select_for_update(), pk=profile_id)
        if patient_profile.user_id not in (None, user.pk):
            return JsonResponse({'error': 'That patient profile is already linked to another account.'}, status=400)

    user.groups.remove(*Group.objects.filter(name__in=API_ROLES))
    if role != Role.UNASSIGNED:
        role_group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(role_group)

    current_doctor = Doctor.objects.select_for_update().filter(user=user).first()
    current_patient = Patient.objects.select_for_update().filter(user=user).first()
    if role == Role.DOCTOR:
        _unlink_profile(current_patient)
        if current_doctor and (doctor_profile is None or current_doctor.pk != doctor_profile.pk):
            _unlink_profile(current_doctor)
        if doctor_profile and doctor_profile.user_id != user.pk:
            doctor_profile.user = user
            doctor_profile.save(update_fields=['user'])
    elif role == Role.PATIENT:
        _unlink_profile(current_doctor)
        if current_patient and (patient_profile is None or current_patient.pk != patient_profile.pk):
            _unlink_profile(current_patient)
        if patient_profile and patient_profile.user_id != user.pk:
            patient_profile.user = user
            patient_profile.save(update_fields=['user'])
    else:
        _unlink_profile(current_doctor)
        _unlink_profile(current_patient)

    return JsonResponse({
        'ok': True,
        'id': user.pk,
        'role': role,
        'doctor_profile_id': doctor_profile.pk if doctor_profile else None,
        'patient_profile_id': patient_profile.pk if patient_profile else None,
    })


@require_POST
def signup_api(request):
    if not settings.ALLOW_PUBLIC_SIGNUP:
        return JsonResponse({'error': 'Public account creation is disabled.'}, status=403)

    payload = _read_json_body(request)
    if payload is None:
        return JsonResponse({'error': 'Request body must be a JSON object.'}, status=400)

    form = SignUpForm(payload)
    if not form.is_valid():
        return _form_errors_response(form)

    # New accounts have no role, so they can't see any records until an admin assigns one.
    user = form.save()
    return JsonResponse({'username': user.get_username()}, status=201)


@require_POST
def login_api(request):
    payload = _read_json_body(request)
    if payload is None:
        return JsonResponse({'error': 'Request body must be a JSON object.'}, status=400)

    username = payload.get('username')
    password = payload.get('password')
    if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
        return JsonResponse({'error': 'Enter your username and password.'}, status=400)

    # Brute-force protection: lock this username from this IP after repeated failures.
    failure_key = _cache_key('login-fail', _client_ip(request), username.lower())
    if (cache.get(failure_key) or 0) >= LOGIN_MAX_FAILURES:
        return JsonResponse({'error': 'Too many failed login attempts. Try again in a few minutes.'}, status=429)

    user = authenticate(request, username=username, password=password)
    if user is None:
        _count_attempt(failure_key, LOGIN_LOCKOUT_SECONDS)
        return JsonResponse({'error': 'Invalid username or password.'}, status=401)

    cache.delete(failure_key)
    login(request, user)
    return JsonResponse({'username': user.get_username()})


@require_POST
def password_reset_request_api(request):
    payload = _read_json_body(request)
    if payload is None:
        return JsonResponse({'error': 'Request body must be a JSON object.'}, status=400)

    email = payload.get('email')
    if not isinstance(email, str):
        return JsonResponse({'error': 'Enter a valid email address.'}, status=400)
    email = email.strip()
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({'error': 'Enter a valid email address.'}, status=400)

    generic_response = JsonResponse({
        'ok': True,
        'message': 'If an account exists for that email, password reset instructions have been sent.',
    })

    ip_key = _cache_key('pwreset-ip', _client_ip(request))
    if _count_attempt(ip_key, PASSWORD_RESET_WINDOW_SECONDS) > PASSWORD_RESET_MAX_PER_IP:
        return JsonResponse({'error': 'Too many password reset requests. Try again later.'}, status=429)
    email_key = _cache_key('pwreset-email', email.lower())
    if _count_attempt(email_key, PASSWORD_RESET_WINDOW_SECONDS) > PASSWORD_RESET_MAX_PER_EMAIL:
        # Same response as success, so this can't be used to probe for accounts.
        return generic_response

    from .tasks import send_password_reset_email

    # Sent in the background: the response time no longer depends on whether the
    # account exists, and an SMTP failure can't turn into a 500 that reveals it.
    for user_id in User.objects.filter(email__iexact=email, is_active=True).values_list('pk', flat=True):
        try:
            send_password_reset_email.delay(user_id)
        except Exception:
            logger.exception('Unable to queue password reset email for user %s', user_id)

    return generic_response


@require_POST
def password_reset_confirm_api(request):
    payload = _read_json_body(request)
    if payload is None:
        return JsonResponse({'error': 'Request body must be a JSON object.'}, status=400)

    if payload.get('password') != payload.get('password_confirm'):
        return JsonResponse({'errors': {'password_confirm': ['Passwords do not match.']}}, status=400)
    password = payload.get('password')
    if not isinstance(password, str) or not password:
        return JsonResponse({'errors': {'password': ['Enter a new password.']}}, status=400)

    uid = payload.get('uid')
    token = payload.get('token')
    user = None
    if isinstance(uid, str) and uid:
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

    if user is None or not isinstance(token, str) or not default_token_generator.check_token(user, token):
        return JsonResponse({'error': 'This password reset link is invalid or has expired.'}, status=400)

    try:
        validate_password(password, user)
    except ValidationError as error:
        return JsonResponse({'errors': {'password': error.messages}}, status=400)

    user.set_password(password)
    user.save(update_fields=['password'])
    return JsonResponse({'ok': True})


@require_POST
def logout_api(request):
    logout(request)
    return JsonResponse({'ok': True})