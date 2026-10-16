import json
import logging

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.contrib import messages
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from .models import Patient, Doctor, Appointment, Bill, Payment
from .forms import PatientForm, DoctorForm, AppointmentForm, BillForm, PaymentForm, SignUpForm
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from functools import wraps


def group_required(*group_names):
    def decorator(func):
        @wraps(func)
        @login_required(login_url='login')
        def wrapper(request, *args, **kwargs):
            if request.user.groups.filter(name__in=group_names).exists() or request.user.is_superuser:
                return func(request, *args, **kwargs)
            messages.error(request, "You don't have permission to access this page.")
            return redirect('patients:dashboard')
        return wrapper
    return decorator


@login_required(login_url='login')
def dashboard(request):
    total_patients = Patient.objects.filter(is_deleted=False).count()
    total_doctors = Doctor.objects.count()
    total_appointments = Appointment.objects.count()
    unpaid_bills = Bill.objects.filter(status='Unpaid').count()
    recent_appointments = Appointment.objects.select_related('patient', 'doctor').order_by('-created_at')[:5]

    context = {
        'total_patients': total_patients,
        'total_doctors': total_doctors,
        'total_appointments': total_appointments,
        'unpaid_bills': unpaid_bills,
        'recent_appointments': recent_appointments,
    }
    return render(request, 'dashboard/admin_dashboard.html', context)


# --- Patients ---

@login_required(login_url='login')
def patient_list(request):
    patients = Patient.objects.filter(is_deleted=False)
    return render(request, 'patients/patient_list.html', {'patients': patients})


@login_required(login_url='login')
def create_patient(request):
    form = PatientForm(request.POST or None)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.created_by = request.user
        obj.save()
        messages.success(request, 'Patient added successfully.')
        return redirect('patients:patient_list')
    return render(request, 'patients/patient_form.html', {'form': form, 'title': 'Add Patient'})


@login_required(login_url='login')
def update_patient(request, pk):
    patient = get_object_or_404(Patient, pk=pk, is_deleted=False)
    form = PatientForm(request.POST or None, instance=patient)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.updated_by = request.user
        obj.save()
        messages.success(request, 'Patient updated successfully.')
        return redirect('patients:patient_list')
    return render(request, 'patients/patient_form.html', {'form': form, 'title': 'Update Patient'})


@login_required(login_url='login')
def delete_patient(request, pk):
    patient = get_object_or_404(Patient, pk=pk, is_deleted=False)
    if request.method == 'POST':
        patient.is_deleted = True
        patient.deleted_at = timezone.now()
        patient.save()
        messages.success(request, 'Patient moved to trash.')
        return redirect('patients:patient_list')
    return render(request, 'patients/confirm_delete.html', {'patient': patient})


@login_required(login_url='login')
def trash_list(request):
    patients = Patient.objects.filter(is_deleted=True)
    return render(request, 'patients/trash_list.html', {'patients': patients})


@login_required(login_url='login')
def restore_patient(request, pk):
    patient = get_object_or_404(Patient, pk=pk, is_deleted=True)
    patient.is_deleted = False
    patient.deleted_at = None
    patient.save()
    messages.success(request, 'Patient restored successfully.')
    return redirect('patients:trash_list')


# --- Doctors ---

@login_required(login_url='login')
def doctor_list(request):
    doctors = Doctor.objects.all()
    return render(request, 'patients/doctor_list.html', {'doctors': doctors})


@group_required('Admin')
def register_doctor(request):
    form = DoctorForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Doctor registered successfully.')
        return redirect('patients:doctor_list')
    return render(request, 'patients/doctor_form.html', {'form': form, 'title': 'Register Doctor'})

@login_required(login_url='login')
def update_doctor(request, pk):
    doctor = get_object_or_404(Doctor, pk=pk)
    form = DoctorForm(request.POST or None, instance=doctor)
    if form.is_valid():
        form.save()
        messages.success(request, 'Doctor updated successfully.')
        return redirect('patients:doctor_list')
    return render(request, 'patients/doctor_form.html', {'form': form, 'title': 'Update Doctor'})


# --- Appointments ---

@login_required(login_url='login')
def appointment_list(request):
    appointments = Appointment.objects.select_related('patient', 'doctor').order_by('-created_at')
    return render(request, 'patients/appointment_list.html', {'appointments': appointments})


@login_required(login_url='login')
def create_appointment(request):
    form = AppointmentForm(request.POST or None)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.created_by = request.user
        obj.save()
        messages.success(request, 'Appointment created successfully.')
        return redirect('patients:appointment_list')
    return render(request, 'patients/appointment_form.html', {'form': form, 'title': 'Create Appointment'})


@login_required(login_url='login')
def update_appointment(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    form = AppointmentForm(request.POST or None, instance=appointment)
    if form.is_valid():
        form.save()
        messages.success(request, 'Appointment updated successfully.')
        return redirect('patients:appointment_list')
    return render(request, 'patients/appointment_form.html', {'form': form, 'title': 'Update Appointment'})


# --- Bills ---

@login_required(login_url='login')
def bill_list(request):
    bills = Bill.objects.select_related('patient').order_by('-created_at')
    return render(request, 'patients/bill_list.html', {'bills': bills})


@login_required(login_url='login')
def create_bill(request):
    form = BillForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Bill created successfully.')
        return redirect('patients:bill_list')
    return render(request, 'patients/bill_form.html', {'form': form, 'title': 'Create Bill'})


@login_required(login_url='login')
def bill_detail(request, pk):
    bill = get_object_or_404(Bill, pk=pk)
    payments = bill.payment_set.all()
    return render(request, 'patients/bill_detail.html', {'bill': bill, 'payments': payments})


@login_required(login_url='login')
def update_bill(request, pk):
    bill = get_object_or_404(Bill, pk=pk)
    form = BillForm(request.POST or None, instance=bill)
    if form.is_valid():
        form.save()
        messages.success(request, 'Bill updated successfully.')
        return redirect('patients:bill_list')
    return render(request, 'patients/bill_form.html', {'form': form, 'title': 'Update Bill'})


@login_required(login_url='login')
def add_payment(request, pk):
    bill = get_object_or_404(Bill, pk=pk)
    form = PaymentForm(request.POST or None, bill=bill)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.bill = bill
        obj.received_by = request.user
        obj.save()
        # Auto update bill status
        if bill.balance <= 0:
            bill.status = 'Paid'
        else:
            bill.status = 'Partial'
        bill.save()
        messages.success(request, 'Payment recorded successfully.')
        return redirect('patients:bill_detail', pk=bill.pk)
    return render(request, 'patients/payment_form.html', {'form': form, 'bill': bill})


@login_required(login_url='login')
def download_invoice(request, pk):
    bill = get_object_or_404(Bill.objects.select_related('patient'), pk=pk)
    return _invoice_pdf_response(bill)


def _invoice_pdf_response(bill):
    response = HttpResponse(_invoice_pdf_bytes(bill), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="MediCore-invoice-{bill.pk}.pdf"'
    return response


def _invoice_pdf_bytes(bill):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f'MediCore Invoice {bill.pk}',
        author='MediCore',
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Brand', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=24, leading=28, textColor=colors.HexColor('#0f3b66'), alignment=0, spaceAfter=2))
    styles.add(ParagraphStyle(name='Subtitle', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#64748b')))
    styles.add(ParagraphStyle(name='SectionHeading', parent=styles['Heading2'], fontSize=11, leading=14, textColor=colors.HexColor('#0f3b66'), spaceBefore=12, spaceAfter=7))
    styles.add(ParagraphStyle(name='RightBody', parent=styles['Normal'], alignment=TA_RIGHT))

    money = lambda amount: f'Rs. {amount:,.2f}'
    story = [
        Table(
            [[
                [Paragraph('MediCore', styles['Brand']), Paragraph('HOSPITAL MANAGEMENT', styles['Subtitle'])],
                [Paragraph('<b>INVOICE</b>', styles['RightBody']), Paragraph(f'Invoice # MC-{bill.pk:06d}', styles['RightBody']), Paragraph(f'Issued {bill.created_at.strftime("%d %b %Y")}', styles['RightBody'])],
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
        Paragraph(f'<b>{bill.patient.name}</b>', styles['Normal']),
        Paragraph(f'Status: <b>{bill.status}</b>', styles['Normal']),
        Paragraph('Services', styles['SectionHeading']),
    ]

    description = (bill.description or 'Medical services').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br/>')
    details = Table(
        [
            [Paragraph('<b>Description</b>', styles['Normal']), Paragraph('<b>Amount</b>', styles['RightBody'])],
            [Paragraph(description, styles['Normal']), Paragraph(money(bill.total_amount), styles['RightBody'])],
        ],
        colWidths=[125 * mm, 45 * mm],
        repeatRows=1,
        style=TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eff6ff')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0f3b66')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dbe3ec')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 9),
            ('RIGHTPADDING', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]),
    )
    story.extend([details, Paragraph('Payment history', styles['SectionHeading'])])

    payments = bill.payment_set.order_by('payment_date', 'pk')
    payment_rows = [[
        Paragraph('<b>Date</b>', styles['Normal']),
        Paragraph('<b>Method</b>', styles['Normal']),
        Paragraph('<b>Amount</b>', styles['RightBody']),
    ]]
    payment_rows.extend([
        [payment.payment_date.strftime('%d %b %Y, %H:%M'), payment.payment_method, Paragraph(money(payment.amount), styles['RightBody'])]
        for payment in payments
    ])
    if not payments.exists():
        payment_rows.append([Paragraph('No payments recorded', styles['Subtitle']), '', ''])

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
            ['Total charges', Paragraph(money(bill.total_amount), styles['RightBody'])],
            ['Amount paid', Paragraph(money(bill.amount_paid), styles['RightBody'])],
            [Paragraph('<b>Balance due</b>', styles['Normal']), Paragraph(f'<b>{money(max(bill.balance, 0))}</b>', styles['RightBody'])],
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
    story.extend([payment_table, Spacer(1, 10), KeepTogether([totals]), Spacer(1, 22), Paragraph('Thank you for choosing MediCore.', styles['Subtitle'])])
    document.build(story)
    return buffer.getvalue()


# --- API endpoints for Next.js frontend ---

API_ROLES = ('Admin', 'Doctor', 'Patient', 'Receptionist')
logger = logging.getLogger(__name__)


def _api_role(user):
    if user.is_superuser:
        return 'Admin'
    assigned_roles = list(user.groups.filter(name__in=API_ROLES).values_list('name', flat=True))
    return assigned_roles[0] if len(assigned_roles) == 1 else None


def _api_require_roles(request, allowed_roles):
    if not request.user.is_authenticated:
        return None, JsonResponse({'error': 'Authentication required.'}, status=401)
    role = _api_role(request.user)
    if role not in allowed_roles:
        return role, JsonResponse({'error': 'You do not have permission to access this resource.'}, status=403)
    return role, None


def _patients_visible_to(user, role):
    patients = Patient.objects.filter(is_deleted=False)
    if role == 'Admin' or role == 'Receptionist':
        return patients
    if role == 'Doctor':
        return patients.filter(appointment__doctor__user=user).distinct()
    if role == 'Patient':
        return patients.filter(user=user)
    return patients.none()


def _appointments_visible_to(user, role):
    appointments = Appointment.objects.all()
    if role == 'Admin' or role == 'Receptionist':
        return appointments
    if role == 'Doctor':
        return appointments.filter(doctor__user=user)
    if role == 'Patient':
        return appointments.filter(patient__user=user)
    return appointments.none()


def _bills_visible_to(user, role):
    bills = Bill.objects.all()
    if role == 'Admin':
        return bills
    if role == 'Patient':
        return bills.filter(patient__user=user)
    return bills.none()


def dashboard_api(request):
    role, auth_error = _api_require_roles(request, API_ROLES)
    if auth_error:
        return auth_error

    recent_appointments = _appointments_visible_to(request.user, role).select_related('patient', 'doctor').order_by('-created_at')[:5]
    visible_bills = _bills_visible_to(request.user, role).select_related('patient').order_by('-created_at')[:3]
    if role == 'Admin':
        stats = [
            {'label': 'Patients', 'value': Patient.objects.filter(is_deleted=False).count(), 'change': 'All records', 'tone': 'emerald'},
            {'label': 'Doctors', 'value': Doctor.objects.count(), 'change': 'All staff', 'tone': 'blue'},
            {'label': 'Appointments', 'value': Appointment.objects.count(), 'change': 'All schedules', 'tone': 'violet'},
            {'label': 'Outstanding', 'value': float(sum((bill.balance for bill in Bill.objects.all()), start=0)), 'change': 'Current balance', 'tone': 'amber'},
        ]
    elif role == 'Receptionist':
        stats = [
            {'label': 'Patients', 'value': Patient.objects.filter(is_deleted=False).count(), 'change': 'Directory', 'tone': 'emerald'},
            {'label': 'Doctors', 'value': Doctor.objects.count(), 'change': 'Available staff', 'tone': 'blue'},
            {'label': 'Appointments', 'value': Appointment.objects.count(), 'change': 'All schedules', 'tone': 'violet'},
            {'label': "Today's appointments", 'value': Appointment.objects.filter(appointment_date=timezone.localdate()).count(), 'change': 'Today', 'tone': 'amber'},
        ]
    elif role == 'Doctor':
        visible_appointments = _appointments_visible_to(request.user, role)
        stats = [
            {'label': 'Assigned patients', 'value': _patients_visible_to(request.user, role).count(), 'change': 'Care team', 'tone': 'emerald'},
            {'label': 'My appointments', 'value': visible_appointments.count(), 'change': 'My schedule', 'tone': 'blue'},
            {'label': "Today's schedule", 'value': visible_appointments.filter(appointment_date=timezone.localdate()).count(), 'change': 'Today', 'tone': 'violet'},
            {'label': 'Upcoming', 'value': visible_appointments.filter(appointment_date__gte=timezone.localdate(), status='Scheduled').count(), 'change': 'Scheduled', 'tone': 'amber'},
        ]
    else:
        own_appointments = _appointments_visible_to(request.user, role)
        stats = [
            {'label': 'My appointments', 'value': own_appointments.count(), 'change': 'My schedule', 'tone': 'emerald'},
            {'label': 'Upcoming', 'value': own_appointments.filter(appointment_date__gte=timezone.localdate(), status='Scheduled').count(), 'change': 'Scheduled', 'tone': 'blue'},
            {'label': 'My bills', 'value': visible_bills.count(), 'change': 'Billing records', 'tone': 'violet'},
            {'label': 'Balance due', 'value': float(sum((bill.balance for bill in visible_bills), start=0)), 'change': 'My account', 'tone': 'amber'},
        ]

    payload = {
        'role': role,
        'stats': stats,
        'recent_appointments': [
            {
                'id': appointment.id,
                'patient': appointment.patient.name,
                'doctor': appointment.doctor.name,
                'date': appointment.appointment_date.isoformat(),
                'time': appointment.appointment_time.strftime('%H:%M'),
                'status': appointment.status,
            }
            for appointment in recent_appointments
        ],
        'bills': [
            {
                'id': bill.id,
                'patient': bill.patient.name,
                'total': float(bill.total_amount),
                'paid': float(bill.amount_paid),
                'balance': float(bill.balance),
                'status': bill.status,
            }
            for bill in visible_bills
        ],
    }
    return JsonResponse(payload)


def patient_list_api(request):
    role, error = _api_require_roles(request, ('Admin', 'Doctor', 'Patient', 'Receptionist'))
    if error:
        return error
    patients = _patients_visible_to(request.user, role).order_by('-created_at')
    payload = []
    for patient in patients:
        item = {
        'id': patient.id,
        'name': patient.name,
        'age': patient.age,
        'gender': patient.gender,
        'phone': patient.phone,
        'address': patient.address,
        'status': 'Active' if not patient.is_deleted else 'Discharged',
        }
        if role != 'Receptionist' and (
            role == 'Admin'
            or (role == 'Doctor' and request.user.has_perm('patients.view_patient_medical_history'))
            or (role == 'Patient' and patient.user_id == request.user.id)
        ):
            item['medical_history'] = patient.medical_history
        payload.append(item)
    return JsonResponse({'patients': payload})


def doctor_list_api(request):
    role, error = _api_require_roles(request, ('Admin', 'Doctor', 'Patient', 'Receptionist'))
    if error:
        return error
    doctors = Doctor.objects.all()
    if role == 'Doctor':
        doctors = doctors.filter(user=request.user)
    elif role == 'Patient':
        doctors = doctors.filter(appointment__patient__user=request.user).distinct()
    doctors = doctors.order_by('name')
    payload = [{
        'id': doctor.id,
        'name': doctor.name,
        'specialization': doctor.specialization,
        'phone': doctor.phone,
        'email': doctor.email,
    } for doctor in doctors]
    return JsonResponse({'doctors': payload})


def appointment_list_api(request):
    role, error = _api_require_roles(request, ('Admin', 'Doctor', 'Patient', 'Receptionist'))
    if error:
        return error
    appointments = _appointments_visible_to(request.user, role).select_related('patient', 'doctor').order_by('-created_at')
    payload = []
    for appointment in appointments:
        item = {
        'id': appointment.id,
        'patient_id': appointment.patient_id,
        'doctor_id': appointment.doctor_id,
        'patient': appointment.patient.name,
        'doctor': appointment.doctor.name,
        'date': appointment.appointment_date.isoformat(),
        'time': appointment.appointment_time.strftime('%H:%M'),
        'status': appointment.status,
        }
        if role != 'Receptionist':
            item['notes'] = appointment.notes
        payload.append(item)
    return JsonResponse({'appointments': payload})


def bill_list_api(request):
    role, error = _api_require_roles(request, ('Admin', 'Patient'))
    if error:
        return error
    bills = _bills_visible_to(request.user, role).select_related('patient').order_by('-created_at')
    payload = [{
        'id': bill.id,
        'patient_id': bill.patient_id,
        'patient': bill.patient.name,
        'total': float(bill.total_amount),
        'total_amount': str(bill.total_amount),
        'description': bill.description,
        'paid': float(bill.amount_paid),
        'balance': float(bill.balance),
        'status': bill.status,
        'invoice_status': bill.invoice_status,
    } for bill in bills]
    return JsonResponse({'bills': payload})


def _read_json_body(request):
    try:
        payload = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


@require_POST
@transaction.atomic
def bill_payment_api(request, pk):
    _, auth_error = _api_require_roles(request, ('Admin',))
    if auth_error:
        return auth_error

    bill = get_object_or_404(Bill.objects.select_for_update(), pk=pk)
    payload = _read_json_body(request)
    if payload is None:
        return JsonResponse({'error': 'Request body must be a JSON object.'}, status=400)

    form = PaymentForm(payload, bill=bill)
    if not form.is_valid():
        errors = {
            field: [error['message'] for error in field_errors]
            for field, field_errors in form.errors.get_json_data().items()
        }
        return JsonResponse({'errors': errors}, status=400)

    payment = form.save(commit=False)
    payment.bill = bill
    payment.received_by = request.user
    payment.save()
    bill.refresh_from_db()
    bill.invoice_status = 'processing'
    bill.invoice_email_sent = False
    bill.save(update_fields=['invoice_status', 'invoice_email_sent'])
    from .tasks import generate_and_email_invoice

    def queue_invoice():
        try:
            generate_and_email_invoice.delay(bill.pk)
        except Exception:
            logger.exception('Unable to queue invoice generation for bill %s', bill.pk)
            Bill.objects.filter(pk=bill.pk).update(invoice_status='failed')

    transaction.on_commit(queue_invoice)
    return JsonResponse({
        'payment_id': payment.pk,
        'bill': {
            'id': bill.pk,
            'total': float(bill.total_amount),
            'paid': float(bill.amount_paid),
            'balance': float(max(bill.balance, 0)),
            'status': bill.status,
            'invoice_status': bill.invoice_status,
        },
    }, status=201)


@require_GET
def bill_invoice_api(request, pk):
    role, auth_error = _api_require_roles(request, ('Admin', 'Patient'))
    if auth_error:
        return auth_error
    bill = get_object_or_404(Bill.objects.select_related('patient'), pk=pk)
    if role == 'Patient' and bill.patient.user_id != request.user.id:
        return JsonResponse({'error': 'You do not have permission to access this invoice.'}, status=403)
    if bill.invoice_status != 'ready' or not bill.invoice_pdf:
        return JsonResponse({'status': bill.invoice_status, 'message': 'Invoice is being prepared.'}, status=202)
    with bill.invoice_pdf.open('rb') as invoice_file:
        response = HttpResponse(invoice_file.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="MediCore-invoice-{bill.pk}.pdf"'
    return response


@require_http_methods(['GET', 'POST'])
def record_collection_api(request, resource):
    role, auth_error = _api_require_roles(request, API_ROLES)
    if auth_error:
        return auth_error

    if request.method == 'POST':
        if role != 'Admin' and not (resource == 'appointments' and role == 'Receptionist'):
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


@require_http_methods(['POST', 'PUT', 'PATCH'])
def record_write_api(request, resource, pk=None):
    role, auth_error = _api_require_roles(request, API_ROLES)
    if auth_error:
        return auth_error

    if role != 'Admin' and not (role == 'Receptionist' and resource == 'appointments' and request.method == 'POST'):
        return JsonResponse({'error': 'You do not have permission to modify this record.'}, status=403)

    resource_config = {
        'patients': (PatientForm, Patient, 'created_by', 'updated_by'),
        'doctors': (DoctorForm, Doctor, None, None),
        'appointments': (AppointmentForm, Appointment, 'created_by', None),
        'bills': (BillForm, Bill, None, None),
    }
    config = resource_config.get(resource)
    if config is None:
        return JsonResponse({'error': 'Unknown resource.'}, status=404)

    form_class, model, creator_field, updater_field = config
    payload = _read_json_body(request)
    if payload is None:
        return JsonResponse({'error': 'Request body must be a JSON object.'}, status=400)

    instance = get_object_or_404(model, pk=pk) if pk is not None else None
    form = form_class(payload, instance=instance)
    if not form.is_valid():
        errors = {
            field: [error['message'] for error in field_errors]
            for field, field_errors in form.errors.get_json_data().items()
        }
        return JsonResponse({'errors': errors}, status=400)

    record = form.save(commit=False)
    if instance is None and creator_field:
        setattr(record, creator_field, request.user)
    if instance is not None and updater_field:
        setattr(record, updater_field, request.user)
    record.save()
    return JsonResponse({'id': record.pk}, status=201 if instance is None else 200)


@require_GET
def csrf_api(request):
    return JsonResponse({'csrfToken': get_token(request)})


@require_GET
def auth_session_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({'authenticated': False})
    return JsonResponse({
        'authenticated': True,
        'username': request.user.get_username(),
        'role': _api_role(request.user) or 'Unassigned',
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
        errors = {
            field: [error['message'] for error in field_errors]
            for field, field_errors in form.errors.get_json_data().items()
        }
        return JsonResponse({'errors': errors}, status=400)

    user = form.save()
    return JsonResponse({'username': user.get_username()}, status=201)


@require_POST
def login_api(request):
    payload = _read_json_body(request)
    if payload is None:
        return JsonResponse({'error': 'Request body must be a JSON object.'}, status=400)

    user = authenticate(
        request,
        username=payload.get('username', ''),
        password=payload.get('password', ''),
    )
    if user is None:
        return JsonResponse({'error': 'Invalid username or password.'}, status=401)

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
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({'error': 'Enter a valid email address.'}, status=400)

    users = User.objects.filter(email__iexact=email, is_active=True)
    for user in users:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_url = f'{settings.FRONTEND_URL}/reset-password/{uid}/{token}'
        send_mail(
            'Reset your MediCore password',
            f'Use this link to choose a new password. The link expires in 3 days:\n\n{reset_url}',
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )

    return JsonResponse({
        'ok': True,
        'message': 'If an account exists for that email, password reset instructions have been sent.',
    })


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

    try:
        uid = force_str(urlsafe_base64_decode(payload.get('uid', '')))
        user = User.objects.get(pk=uid, is_active=True)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    token = payload.get('token')
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

