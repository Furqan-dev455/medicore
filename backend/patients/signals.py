import logging

from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .models import AppointmentStatus

logger = logging.getLogger(__name__)

# Roles that may read medical history (checked via has_perm in the API).
MEDICAL_HISTORY_ROLES = ('Admin', 'Doctor')


@receiver(post_migrate)
def ensure_role_groups(sender, using='default', **kwargs):
    if sender.label != 'patients':
        return
    from .views import API_ROLES  # lazy: keeps app startup from importing the web layer

    groups = {
        name: Group.objects.using(using).get_or_create(name=name)[0]
        for name in API_ROLES
    }

    # The permission row is created by django.contrib.auth's own post_migrate
    # handler. If it isn't there yet (unusual app order, partial migrate), skip
    # instead of crashing `migrate`; the next migrate run adds it.
    history_permission = Permission.objects.using(using).filter(
        content_type__app_label='patients',
        codename='view_patient_medical_history',
    ).first()
    if history_permission is None:
        logger.warning('Permission view_patient_medical_history not found yet; skipped assigning it to role groups.')
        return
    for name in MEDICAL_HISTORY_ROLES:
        groups[name].permissions.add(history_permission)


def _enqueue_confirmation(appointment_id):
    try:
        from .appointment_notifications import create_appointment_confirmation
        create_appointment_confirmation(appointment_id)
    except Exception:
        # Never fail a confirmed booking because the broker is unavailable.
        logger.exception('Could not queue confirmation for appointment %s.', appointment_id)


@receiver(post_save, sender='patients.Appointment')
def queue_appointment_confirmation(sender, instance, created, raw=False, **kwargs):
    # raw=True means loaddata/fixtures: never email patients while importing data.
    if raw or not created or instance.status != AppointmentStatus.SCHEDULED:
        return
    appointment_id = instance.pk
    transaction.on_commit(lambda: _enqueue_confirmation(appointment_id))