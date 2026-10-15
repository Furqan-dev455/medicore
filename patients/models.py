from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class Doctor(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=200)
    specialization = models.CharField(max_length=200)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Dr. {self.name} - {self.specialization}"


class Patient(models.Model):
    class GenderChoices(models.TextChoices):
        MALE = "Male", "Male"
        FEMALE = "Female", "Female"
        OTHER = "Other", "Other"

    name = models.CharField(max_length=200)
    age = models.PositiveIntegerField()
    gender = models.CharField(
        max_length=10,
        choices=GenderChoices.choices,
        default=GenderChoices.MALE,
    )
    phone = models.CharField(max_length=20)
    address = models.TextField()
    medical_history = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="created_patients")
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="updated_patients")
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Appointment(models.Model):
    class AppointmentStatus(models.TextChoices):
        SCHEDULED = "Scheduled", "Scheduled"
        COMPLETED = "Completed", "Completed"
        CANCELLED = "Cancelled", "Cancelled"

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE)
    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    status = models.CharField(
        max_length=20,
        choices=AppointmentStatus.choices,
        default=AppointmentStatus.SCHEDULED,
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="created_appointments")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.patient.name} - {self.doctor.name} on {self.appointment_date}"


class Bill(models.Model):
    class BillStatus(models.TextChoices):
        UNPAID = "Unpaid", "Unpaid"
        PARTIAL = "Partial", "Partial"
        PAID = "Paid", "Paid"

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    status = models.CharField(
        max_length=20,
        choices=BillStatus.choices,
        default=BillStatus.UNPAID,
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(total_amount__gte=0), name="bill_total_amount_non_negative"),
        ]

    @property
    def amount_paid(self):
        total = self.payment_set.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        return total

    @property
    def balance(self):
        return self.total_amount - self.amount_paid

    def update_status(self):
        paid = self.amount_paid

        if paid <= 0:
            new_status = self.BillStatus.UNPAID
        elif paid >= self.total_amount:
            new_status = self.BillStatus.PAID
        else:
            new_status = self.BillStatus.PARTIAL

        if self.status != new_status:
            Bill.objects.filter(pk=self.pk).update(status=new_status)
            self.status = new_status

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.update_status()

    def __str__(self):
        return f"Bill #{self.id} - {self.patient.name}"


class Payment(models.Model):
    class PaymentMethod(models.TextChoices):
        CASH = "Cash", "Cash"
        CARD = "Card", "Card"
        BANK_TRANSFER = "Bank Transfer", "Bank Transfer"

    bill = models.ForeignKey(Bill, on_delete=models.CASCADE)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    received_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="received_payments")
    payment_date = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gte=0), name="payment_amount_non_negative"),
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.bill.update_status()

    def __str__(self):
        return f"Payment of {self.amount} for Bill #{self.bill.id}"