from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('patients', '0002_patient_user_and_rbac_permission')]

    operations = [
        migrations.AddField(
            model_name='bill',
            name='invoice_pdf',
            field=models.FileField(blank=True, upload_to='invoices/'),
        ),
        migrations.AddField(
            model_name='bill',
            name='invoice_status',
            field=models.CharField(
                choices=[('pending', 'Pending'), ('processing', 'Processing'), ('ready', 'Ready'), ('failed', 'Failed')],
                default='pending',
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name='bill',
            name='invoice_email_sent',
            field=models.BooleanField(default=False),
        ),
    ]
