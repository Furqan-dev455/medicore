from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_migrate
from django.dispatch import receiver


@receiver(post_migrate)
def ensure_role_groups(sender, **kwargs):
    if sender.label != 'patients':
        return

    for name in ('Admin', 'Doctor', 'Patient', 'Receptionist'):
        Group.objects.get_or_create(name=name)

    history_permission = Permission.objects.get(
        content_type__app_label='patients',
        codename='view_patient_medical_history',
    )
    for name in ('Admin', 'Doctor'):
        Group.objects.get(name=name).permissions.add(history_permission)
