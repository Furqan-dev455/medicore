import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('patients', '0005_unique_active_doctor_appointment_slot'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='provider',
            field=models.CharField(default='manual', max_length=30),
        ),
        migrations.AddField(
            model_name='payment',
            name='provider_reference',
            field=models.CharField(blank=True, max_length=120, null=True, unique=True),
        ),
        migrations.CreateModel(
            name='Medication',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=160)),
                ('strength', models.CharField(blank=True, max_length=80)),
                ('dosage_form', models.CharField(blank=True, max_length=50)),
                ('unit', models.CharField(default='unit', max_length=30)),
                ('stock_quantity', models.PositiveIntegerField(default=0)),
                ('low_stock_threshold', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['name', 'strength']},
        ),
        migrations.CreateModel(
            name='Prescription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('appointment', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='prescriptions', to='patients.appointment')),
                ('doctor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='prescriptions', to='patients.doctor')),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='prescriptions', to='patients.patient')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='PaymentCheckout',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('tracker_token', models.CharField(blank=True, max_length=120, null=True, unique=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('completed', 'Completed'), ('failed', 'Failed')], default='pending', max_length=12)),
                ('expires_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('bill', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payment_checkouts', to='patients.bill')),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payment_checkouts', to='patients.patient')),
            ],
        ),
        migrations.CreateModel(
            name='PrescriptionItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dosage', models.CharField(max_length=120)),
                ('duration', models.CharField(blank=True, max_length=120)),
                ('quantity', models.PositiveIntegerField()),
                ('instructions', models.CharField(blank=True, max_length=300)),
                ('medication', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='prescription_items', to='patients.medication')),
                ('prescription', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='patients.prescription')),
            ],
        ),
        migrations.AddConstraint(
            model_name='medication',
            constraint=models.UniqueConstraint(fields=('name', 'strength', 'dosage_form'), name='unique_medication_catalog_item'),
        ),
        migrations.AddConstraint(
            model_name='prescriptionitem',
            constraint=models.CheckConstraint(condition=models.Q(('quantity__gt', 0)), name='prescription_item_quantity_positive'),
        ),
        migrations.AddIndex(
            model_name='paymentcheckout',
            index=models.Index(fields=['bill', 'status', 'expires_at'], name='paychk_bill_status_exp_idx'),
        ),
        migrations.AddConstraint(
            model_name='paymentcheckout',
            constraint=models.CheckConstraint(condition=models.Q(('amount__gt', 0)), name='payment_checkout_amount_positive'),
        ),
    ]
