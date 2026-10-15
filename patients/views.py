from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.db.models import Sum
from .models import Patient, Doctor, Appointment, Bill, Payment
from .forms import PatientForm, DoctorForm, AppointmentForm, BillForm, PaymentForm
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
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
    bill = get_object_or_404(Bill, pk=pk)
    payments = bill.payment_set.all()

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_{bill.id}.pdf"'

    p = canvas.Canvas(response, pagesize=A4)
    width, height = A4

    # Header
    p.setFont('Helvetica-Bold', 24)
    p.drawString(50, height - 60, 'MediCore')
    p.setFont('Helvetica', 12)
    p.drawString(50, height - 80, 'Hospital Management System')

    # Line
    p.line(50, height - 90, width - 50, height - 90)

    # Invoice details
    p.setFont('Helvetica-Bold', 14)
    p.drawString(50, height - 120, f'Invoice #{bill.id}')
    p.setFont('Helvetica', 12)
    p.drawString(50, height - 145, f'Patient: {bill.patient.name}')
    p.drawString(50, height - 165, f'Date: {bill.created_at.strftime("%d %b %Y")}')
    p.drawString(50, height - 185, f'Status: {bill.status}')

    # Line
    p.line(50, height - 200, width - 50, height - 200)

    # Bill details
    p.setFont('Helvetica-Bold', 12)
    p.drawString(50, height - 225, 'Description')
    p.drawString(400, height - 225, 'Amount')
    p.line(50, height - 235, width - 50, height - 235)

    p.setFont('Helvetica', 12)
    p.drawString(50, height - 255, bill.description or 'Medical Services')
    p.drawString(400, height - 255, f'Rs. {bill.total_amount}')

    # Payments
    y = height - 300
    p.setFont('Helvetica-Bold', 12)
    p.drawString(50, y, 'Payments Received:')
    y -= 20
    p.setFont('Helvetica', 11)
    for payment in payments:
        p.drawString(50, y, f'- {payment.payment_date.strftime("%d %b %Y")} | {payment.payment_method}')
        p.drawString(400, y, f'Rs. {payment.amount}')
        y -= 20

    # Totals
    p.line(50, y - 10, width - 50, y - 10)
    p.setFont('Helvetica-Bold', 12)
    p.drawString(50, y - 30, 'Total Amount:')
    p.drawString(400, y - 30, f'Rs. {bill.total_amount}')
    p.drawString(50, y - 50, 'Amount Paid:')
    p.drawString(400, y - 50, f'Rs. {bill.amount_paid}')
    p.drawString(50, y - 70, 'Balance:')
    p.drawString(400, y - 70, f'Rs. {bill.balance}')

    p.showPage()
    p.save()
    return response


# --- API endpoints for Next.js frontend ---

def dashboard_api(request):
    recent_appointments = Appointment.objects.select_related('patient', 'doctor').order_by('-created_at')[:5]
    payload = {
        'stats': [
            {'label': 'Patients', 'value': Patient.objects.filter(is_deleted=False).count(), 'change': '+12.5%', 'tone': 'emerald'},
            {'label': 'Doctors', 'value': Doctor.objects.count(), 'change': '+4.2%', 'tone': 'blue'},
            {'label': 'Appointments', 'value': Appointment.objects.count(), 'change': '+8.1%', 'tone': 'violet'},
            {'label': 'Outstanding', 'value': float(Bill.objects.aggregate(total=Sum('total_amount'))['total'] or 0), 'change': '-3.4%', 'tone': 'amber'},
        ],
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
            for bill in Bill.objects.select_related('patient').order_by('-created_at')[:3]
        ],
    }
    return JsonResponse(payload)


def patient_list_api(request):
    patients = Patient.objects.filter(is_deleted=False).order_by('-created_at')
    payload = [{
        'id': patient.id,
        'name': patient.name,
        'age': patient.age,
        'gender': patient.gender,
        'phone': patient.phone,
        'address': patient.address,
        'status': 'Active' if not patient.is_deleted else 'Discharged',
    } for patient in patients]
    return JsonResponse({'patients': payload})


def doctor_list_api(request):
    doctors = Doctor.objects.all().order_by('name')
    payload = [{
        'id': doctor.id,
        'name': doctor.name,
        'specialization': doctor.specialization,
        'phone': doctor.phone,
        'email': doctor.email,
    } for doctor in doctors]
    return JsonResponse({'doctors': payload})


def appointment_list_api(request):
    appointments = Appointment.objects.select_related('patient', 'doctor').order_by('-created_at')
    payload = [{
        'id': appointment.id,
        'patient': appointment.patient.name,
        'doctor': appointment.doctor.name,
        'date': appointment.appointment_date.isoformat(),
        'time': appointment.appointment_time.strftime('%H:%M'),
        'status': appointment.status,
    } for appointment in appointments]
    return JsonResponse({'appointments': payload})


def bill_list_api(request):
    bills = Bill.objects.select_related('patient').order_by('-created_at')
    payload = [{
        'id': bill.id,
        'patient': bill.patient.name,
        'total': float(bill.total_amount),
        'paid': float(bill.amount_paid),
        'balance': float(bill.balance),
        'status': bill.status,
    } for bill in bills]
    return JsonResponse({'bills': payload})

