from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db.models import Q

from .models import Appointment, Bill, Doctor, Medication, Patient, Payment


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')

    def clean_email(self):
        email = self.cleaned_data['email']
        existing_users = User.objects.filter(email__iexact=email)
        if self.instance.pk:
            existing_users = existing_users.exclude(pk=self.instance.pk)
        if existing_users.exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email


def patient_queryset_for(instance):
    """Active patients, plus the record's current patient if it was soft-deleted later,
    so editing an old appointment or bill still validates."""
    if instance.pk and instance.patient_id and instance.patient.is_deleted:
        return Patient.objects.filter(Q(is_deleted=False) | Q(pk=instance.patient_id))
    return Patient.objects.active()


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = ['name', 'age', 'gender', 'phone', 'address', 'medical_history']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full name'}),
            'age': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Age', 'min': '0', 'max': '150'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone number'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Address'}),
            'medical_history': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Medical history (optional)'}),
        }

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if not name:
            raise forms.ValidationError('Patient name is required.')
        return name


class DoctorForm(forms.ModelForm):
    class Meta:
        model = Doctor
        fields = ['name', 'specialization', 'phone', 'email']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full name'}),
            'specialization': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Cardiologist'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone number'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email address'}),
        }

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if not name:
            raise forms.ValidationError('Doctor name is required.')
        return name


class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ['patient', 'doctor', 'appointment_date', 'appointment_time', 'status', 'notes']
        widgets = {
            'patient': forms.Select(attrs={'class': 'form-select'}),
            'doctor': forms.Select(attrs={'class': 'form-select'}),
            'appointment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'appointment_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Additional notes'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['patient'].queryset = patient_queryset_for(self.instance)


class BillForm(forms.ModelForm):
    class Meta:
        model = Bill
        fields = ['patient', 'total_amount', 'description']
        widgets = {
            'patient': forms.Select(attrs={'class': 'form-select'}),
            'total_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Amount in Rs.',
                'min': '0.01',
                'step': '0.01',
            }),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Bill description'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['patient'].queryset = patient_queryset_for(self.instance)


class PaymentForm(forms.ModelForm):
    # Card payments must be settled through the gateway webhook, never
    # entered manually by a staff user.
    MANUAL_METHODS = (Payment.PaymentMethod.CASH, Payment.PaymentMethod.BANK_TRANSFER)

    class Meta:
        model = Payment
        fields = ['amount', 'payment_method']
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Amount',
                'min': '0.01',
                'step': '0.01',
            }),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        self.bill = kwargs.pop('bill', None)
        super().__init__(*args, **kwargs)
        self.fields['payment_method'].choices = [
            (value, label) for value, label in Payment.PaymentMethod.choices if value in self.MANUAL_METHODS
        ]

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if self.bill:
            balance = self.bill.balance
            if amount > balance:
                raise forms.ValidationError(f'Amount cannot exceed the remaining balance of {balance}.')
        return amount


class MedicationForm(forms.ModelForm):
    class Meta:
        model = Medication
        fields = ['name', 'strength', 'dosage_form', 'unit', 'stock_quantity', 'low_stock_threshold', 'is_active']

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        if not name:
            raise forms.ValidationError('Medicine name is required.')
        return name

    def clean_strength(self):
        return self.cleaned_data['strength'].strip()

    def clean_dosage_form(self):
        return self.cleaned_data['dosage_form'].strip()