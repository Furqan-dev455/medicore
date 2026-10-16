from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('patients', '0004_alter_bill_total_amount_alter_patient_gender_and_more'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='appointment',
            constraint=models.UniqueConstraint(
                fields=('doctor', 'appointment_date', 'appointment_time'),
                condition=~models.Q(status='Cancelled'),
                name='unique_active_doctor_appointment_slot',
            ),
        ),
    ]
