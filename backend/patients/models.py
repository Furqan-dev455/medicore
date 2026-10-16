from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models, transaction
from django.db.models import DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

ZERO = Decimal("0.00")

phone_validator = RegexValidator(
    regex=r"^\+?[0-9\- ]{7,20}$",
    message="Enter a valid phone number (digits, spaces, dashes, optional leading +).",
)


# ---------------------------------------------------------------------------
# Shared choices
# Defined at module level so Meta classes (which cannot see a model's inner
# classes) can reference them instead of hardcoded strings.
# ---------------------------------------------------------------------------

class AppointmentStatus(models.TextChoices):
    SCHEDULED = "Scheduled", "Scheduled"
    COMPLETED = "Completed", "Completed"
    CANCELLED = "Cancelled", "Cancelled"


class InvoiceStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"


class PaymentProvider:
    """Known provider identifiers. Add online providers here instead of typing raw strings."""
    MANUAL = "manual"
    SAFEPAY = "safepay"


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------

class Doctor(models.Model):
    # SET_NULL: deleting a login account must not delete the doctor and their history.
    user = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="doctor_profile"
    )
    name = models.CharField(max_length=200)
    specialization = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, validators=[phone_validator])
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Dr. {self.name} - {self.specialization}"


# ---------------------------------------------------------------------------
# Patient
# ---------------------------------------------------------------------------

class PatientQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_deleted=False)

    def deleted(self):
        return self.filter(is_deleted=True)


class Patient(models.Model):
    class GenderChoices(models.TextChoices):
        MALE = "Male", "Male"
        FEMALE = "Female", "Female"
        OTHER = "Other", "Other"

    name = models.CharField(max_length=200)
    user = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="patient_profile"
    )
    age = models.PositiveIntegerField(validators=[MaxValueValidator(150)])
    # No default: silently assuming a gender produces wrong medical data.
    gender = models.CharField(max_length=10, choices=GenderChoices.choices, blank=True)
    phone = models.CharField(max_length=20, validators=[phone_validator])
    address = models.TextField()
    medical_history = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_patients"
    )
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="updated_patients"
    )
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Use Patient.objects.active() in views instead of Patient.objects.all().
    objects = PatientQuerySet.as_manager()

    class Meta:
        permissions = [
            ("view_patient_medical_history", "Can view patient medical history"),
        ]

    def soft_delete(self, user=None):
        """Always use this instead of delete(), so is_deleted and deleted_at never disagree."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.updated_by = user or self.updated_by
        self.save(update_fields=["is_deleted", "deleted_at", "updated_by", "updated_at"])

    def restore(self, user=None):
        self.is_deleted = False
        self.deleted_at = None
        self.updated_by = user or self.updated_by
        self.save(update_fields=["is_deleted", "deleted_at", "updated_by", "updated_at"])

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------

class Appointment(models.Model):
    # Kept as an attribute so existing code using Appointment.AppointmentStatus still works.
    AppointmentStatus = AppointmentStatus

    # PROTECT: appointment history must survive; patients are soft-deleted instead.
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    doctor = models.ForeignKey(Doctor, on_delete=models.PROTECT)
    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    status = models.CharField(
        max_length=20,
        choices=AppointmentStatus.choices,
        default=AppointmentStatus.SCHEDULED,
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_appointments"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["doctor", "appointment_date", "appointment_time"],
                condition=~models.Q(status=AppointmentStatus.CANCELLED),
                name="unique_active_doctor_appointment_slot",
            ),
        ]
        indexes = [
            models.Index(fields=["doctor", "appointment_date"], name="appt_doctor_date_idx"),
            models.Index(fields=["patient", "appointment_date"], name="appt_patient_date_idx"),
        ]

    def clean(self):
        super().clean()
        # Only block past slots when booking, so old appointments can still be edited.
        if self._state.adding and self.appointment_date and self.appointment_time:
            now = timezone.localtime()
            if self.appointment_date < now.date() or (
                self.appointment_date == now.date() and self.appointment_time < now.time()
            ):
                raise ValidationError("Appointments cannot be booked in the past.")
        # New bookings only: existing appointments of a since-deleted patient stay editable.
        if self._state.adding and self.patient_id and self.patient.is_deleted:
            raise ValidationError({"patient": "This patient has been deleted."})

    def __str__(self):
        return f"Appointment #{self.pk} (patient {self.patient_id}, doctor {self.doctor_id}) on {self.appointment_date}"


class AppointmentNotification(models.Model):
    MAX_ATTEMPTS = 5
    LAST_ERROR_MAX_LENGTH = 500

    class Kind(models.TextChoices):
        CONFIRMATION = "confirmation", "Confirmation"
        REMINDER = "reminder", "Reminder"

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"  # gives up after MAX_ATTEMPTS instead of retrying forever

    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    channel = models.CharField(max_length=10, choices=Channel.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    recipient = models.CharField(max_length=254, blank=True)
    last_error = models.CharField(max_length=LAST_ERROR_MAX_LENGTH, blank=True)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    claimed_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["appointment", "kind", "channel"], name="unique_appointment_notification"),
        ]
        indexes = [models.Index(fields=["status", "next_attempt_at"], name="appt_notif_due_idx")]

    def __str__(self):
        return f"{self.kind} {self.channel} for appointment {self.appointment_id}"


# ---------------------------------------------------------------------------
# Billing
# ---------------------------------------------------------------------------

class BillQuerySet(models.QuerySet):
    def with_paid_total(self):
        """Annotate paid totals in one query. Use for list views to avoid N+1 queries."""
        return self.annotate(
            paid_total=Coalesce(
                Sum("payment__amount"),
                Value(ZERO, output_field=DecimalField(max_digits=12, decimal_places=2)),
            )
        )


class Bill(models.Model):
    class BillStatus(models.TextChoices):
        UNPAID = "Unpaid", "Unpaid"
        PARTIAL = "Partial", "Partial"
        PAID = "Paid", "Paid"

    InvoiceStatus = InvoiceStatus

    # PROTECT: financial records must never disappear with a patient.
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
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
    invoice_pdf = models.FileField(upload_to="invoices/", blank=True)
    invoice_status = models.CharField(
        max_length=12,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.PENDING,
    )
    invoice_email_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = BillQuerySet.as_manager()

    class Meta:
        constraints = [
            # Matches the validator: a bill must be greater than zero.
            models.CheckConstraint(condition=models.Q(total_amount__gt=0), name="bill_total_amount_positive"),
        ]

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._loaded_total_amount = instance.__dict__.get("total_amount")
        return instance

    def _compute_paid(self):
        if not self.pk:
            return ZERO
        return self.payment_set.aggregate(total=Sum("amount"))["total"] or ZERO

    @property
    def amount_paid(self):
        # Uses the with_paid_total() annotation when present, otherwise one query.
        annotated = getattr(self, "paid_total", None)
        return annotated if annotated is not None else self._compute_paid()

    @property
    def balance(self):
        return self.total_amount - self.amount_paid

    def reserved_checkout_amount(self):
        """Amount held by unexpired online checkouts, which staff must not also collect."""
        if not self.pk:
            return ZERO
        return self.payment_checkouts.filter(
            status=PaymentCheckout.Status.PENDING,
            expires_at__gt=timezone.now(),
        ).aggregate(total=Sum("amount"))["total"] or ZERO

    def clean(self):
        super().clean()
        if self.pk and self.total_amount is not None and self.total_amount < self._compute_paid():
            raise ValidationError({"total_amount": "Total cannot be lower than the amount already paid."})

    def update_status(self):
        paid = self._compute_paid()

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
        # Only recalculate status when it can actually change, not on every description edit.
        total_changed = self._state.adding or self.total_amount != getattr(self, "_loaded_total_amount", None)
        super().save(*args, **kwargs)
        if total_changed:
            self.update_status()
            self._loaded_total_amount = self.total_amount

    def __str__(self):
        return f"Bill #{self.pk} (patient {self.patient_id})"


class Payment(models.Model):
    class PaymentMethod(models.TextChoices):
        CASH = "Cash", "Cash"
        CARD = "Card", "Card"
        BANK_TRANSFER = "Bank Transfer", "Bank Transfer"

    # PROTECT: a bill with payments cannot be deleted.
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT)
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
    received_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="received_payments"
    )
    provider = models.CharField(max_length=30, default=PaymentProvider.MANUAL)
    provider_reference = models.CharField(max_length=120, blank=True, null=True, unique=True)
    payment_date = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            # Matches the validator: a payment must be greater than zero.
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="payment_amount_positive"),
        ]
        indexes = [models.Index(fields=["bill", "payment_date"], name="payment_bill_date_idx")]

    def _check_not_overpaying(self, bill):
        already_paid = bill.payment_set.exclude(pk=self.pk).aggregate(total=Sum("amount"))["total"] or ZERO
        if self.amount is not None and already_paid + self.amount > bill.total_amount:
            remaining = bill.total_amount - already_paid
            raise ValidationError({"amount": f"Payment exceeds the remaining balance of {remaining}."})

    def clean(self):
        super().clean()
        if self.bill_id:
            self._check_not_overpaying(self.bill)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            # Lock the bill row so concurrent payments cannot both pass the balance check.
            bill = Bill.objects.select_for_update().get(pk=self.bill_id)

            previous_bill_id = None
            if self.pk:
                previous_bill_id = (
                    Payment.objects.filter(pk=self.pk).values_list("bill_id", flat=True).first()
                )

            self._check_not_overpaying(bill)
            super().save(*args, **kwargs)

            bill.update_status()
            self.bill = bill

            # If the payment was moved to another bill, fix the old bill too.
            if previous_bill_id and previous_bill_id != bill.pk:
                old_bill = Bill.objects.select_for_update().filter(pk=previous_bill_id).first()
                if old_bill:
                    old_bill.update_status()

    def __str__(self):
        return f"Payment of {self.amount} for Bill #{self.bill_id}"


@receiver(post_delete, sender=Payment)
def refresh_bill_status_after_payment_delete(sender, instance, **kwargs):
    # Runs for instance.delete() and queryset .delete(), so the bill never keeps a stale status.
    bill = Bill.objects.filter(pk=instance.bill_id).first()
    if bill:
        bill.update_status()


# ---------------------------------------------------------------------------
# Pharmacy
# ---------------------------------------------------------------------------

class Medication(models.Model):
    name = models.CharField(max_length=160)
    strength = models.CharField(max_length=80, blank=True)
    dosage_form = models.CharField(max_length=50, blank=True)
    unit = models.CharField(max_length=30, default="unit")
    stock_quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "strength"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "strength", "dosage_form"],
                name="unique_medication_catalog_item",
            ),
        ]

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.low_stock_threshold

    def dispense(self, quantity):
        """Atomically reduce stock. Safe under concurrent requests."""
        if quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.")
        updated = Medication.objects.filter(pk=self.pk, stock_quantity__gte=quantity).update(
            stock_quantity=F("stock_quantity") - quantity,
            updated_at=timezone.now(),
        )
        if not updated:
            raise ValidationError(f"Insufficient stock for {self}.")
        self.refresh_from_db(fields=["stock_quantity", "updated_at"])

    def __str__(self):
        return " ".join(part for part in (self.name, self.strength, self.dosage_form) if part)


class Prescription(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="prescriptions")
    doctor = models.ForeignKey(Doctor, on_delete=models.PROTECT, related_name="prescriptions")
    appointment = models.ForeignKey(
        Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name="prescriptions"
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        super().clean()
        # The prescription must belong to the same patient and doctor as its appointment.
        if self.appointment_id:
            errors = {}
            if self.patient_id and self.appointment.patient_id != self.patient_id:
                errors["patient"] = "Patient does not match the appointment."
            if self.doctor_id and self.appointment.doctor_id != self.doctor_id:
                errors["doctor"] = "Doctor does not match the appointment."
            if errors:
                raise ValidationError(errors)

    def __str__(self):
        return f"Prescription #{self.pk} (patient {self.patient_id})"


class PrescriptionItem(models.Model):
    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name="items")
    medication = models.ForeignKey(Medication, on_delete=models.PROTECT, related_name="prescription_items")
    dosage = models.CharField(max_length=120)
    duration = models.CharField(max_length=120, blank=True)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    instructions = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="prescription_item_quantity_positive"),
        ]

    def __str__(self):
        return f"{self.medication_id} x {self.quantity}"


# ---------------------------------------------------------------------------
# Online checkout
# ---------------------------------------------------------------------------

class PaymentCheckout(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        # The gateway took the money but it could not be applied to the bill
        # (e.g. staff collected the balance meanwhile). An admin must refund or apply it.
        NEEDS_RECONCILIATION = "reconcile", "Needs reconciliation"

    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name="payment_checkouts")
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="payment_checkouts")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    tracker_token = models.CharField(max_length=120, unique=True, null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["bill", "status", "expires_at"], name="paychk_bill_status_exp_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="payment_checkout_amount_positive"),
        ]

    @property
    def is_expired(self):
        return self.status == self.Status.PENDING and self.expires_at <= timezone.now()

    def clean(self):
        super().clean()
        if self.bill_id and self.amount is not None and self.amount > self.bill.balance:
            raise ValidationError({"amount": "Checkout amount exceeds the bill balance."})

    def save(self, *args, **kwargs):
        # The patient always comes from the bill, so the two can never disagree.
        # Skipped for partial saves (e.g. status updates), which never change the bill.
        if self.bill_id and kwargs.get("update_fields") is None:
            self.patient_id = Bill.objects.values_list("patient_id", flat=True).get(pk=self.bill_id)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.status} checkout for Bill #{self.bill_id}"