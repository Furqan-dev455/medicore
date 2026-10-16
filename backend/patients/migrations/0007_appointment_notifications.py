import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('patients', '0006_prescriptions_inventory_payment_checkout'),
    ]

    operations = [
        migrations.CreateModel(
            name='AppointmentNotification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('confirmation', 'Confirmation'), ('reminder', 'Reminder')], max_length=20)),
                ('channel', models.CharField(choices=[('email', 'Email'), ('sms', 'SMS')], max_length=10)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('sending', 'Sending'), ('sent', 'Sent')], default='pending', max_length=10)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('recipient', models.CharField(blank=True, max_length=254)),
                ('last_error', models.CharField(blank=True, max_length=500)),
                ('next_attempt_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('claimed_at', models.DateTimeField(blank=True, null=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('appointment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='patients.appointment')),
            ],
        ),
        migrations.AddConstraint(
            model_name='appointmentnotification',
            constraint=models.UniqueConstraint(fields=('appointment', 'kind', 'channel'), name='unique_appointment_notification'),
        ),
        migrations.AddIndex(
            model_name='appointmentnotification',
            index=models.Index(fields=['status', 'next_attempt_at'], name='appt_notif_due_idx'),
        ),
    ]
