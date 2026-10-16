# MediCore backend

This folder contains the Django API and its Python dependencies.

## Patient and billing audit history

Patient, bill, and payment create/update/delete operations are recorded by `django-simple-history`, including changed field values, the acting authenticated user, and the timestamp. In the MediCore Django admin, open a Patient, Bill, or Payment record and use **History** to review its change log. API/admin requests get their actor from Django request middleware; automated invoice and payment-webhook changes include a system change reason. Audit history reversion is disabled.

After installing requirements, apply migrations. To seed a starting snapshot of records that already exist, run `python manage.py populate_history --auto` once. Changes made before audit history was enabled cannot be reconstructed.

## Run locally

From this folder, install dependencies, apply migrations, and start the API with Daphne (Channels' ASGI-enabled `runserver`):

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

The repository root `.env` is loaded automatically. The SQLite database, media, and shared templates remain at the repository root.

When `DEBUG=True`, the app uses an in-memory WebSocket channel layer and runs Celery tasks eagerly, so local development does not require Redis, Docker, or a separate Celery worker. Dashboard WebSockets work with the single Daphne development server process. Development email is printed to the backend terminal unless an email backend is explicitly configured. In production (`DEBUG=False`), configure Redis with `CHANNEL_REDIS_URL` and `CELERY_BROKER_URL`, then run a Celery worker and beat scheduler.

The frontend connects directly to `ws://<backend-host>:8000/ws/notifications/` in local development. For a deployed frontend/backend pair, set `NEXT_PUBLIC_WS_BASE` to the backend origin (for example, `wss://api.example.com`). Serve `core.asgi:application` with Daphne or another ASGI server in production; a WSGI-only Gunicorn command cannot serve WebSockets.

## Prescriptions and pharmacy

Run `python manage.py migrate` after updating. Admin users can create and replenish medicines from the Pharmacy inventory page. Doctors can prescribe only for their assigned patients. Saving a prescription locks each medicine row, validates all requested quantities, then deducts the stock and saves every prescription item in one database transaction.

## Patient payment checkout

Safepay checkout starts in sandbox mode. Add the sandbox merchant keys to the repository root `.env`:

```dotenv
SAFEPAY_ENVIRONMENT=sandbox
SAFEPAY_API_KEY=your_sandbox_public_key
SAFEPAY_SECRET_KEY=your_sandbox_secret_key
SAFEPAY_WEBHOOK_SECRET=your_sandbox_webhook_hmac_secret
```

Configure the Safepay sandbox webhook to call `https://<public-backend-host>/api/webhooks/safepay` and subscribe to `payment.succeeded`. The endpoint verifies the HMAC and records each successful checkout idempotently. A local browser redirect is not treated as proof of payment. Safepay requires a public HTTPS webhook endpoint; synthetic signed webhook tests run locally without merchant credentials.

Patients can pay the full balance or enter a partial amount with **Pay securely**. The bill is updated only after Safepay's signed `payment.succeeded` webhook matches the checkout tracker, currency, and amount. Staff can record cash or bank transfers as offline payments; card payments must go through the provider checkout.

Run the frontend separately in another terminal:

```bash
cd frontend
npm install
npm run dev
```

For production invoice generation and scheduled appointment reminders, start Redis and run these in separate backend terminals (use `-P solo` for the worker on Windows):

```bash
celery -A core worker -l info -P solo
celery -A core beat -l info
```

New scheduled appointments queue a confirmation email. The beat scheduler checks each minute and queues one SMS reminder when an appointment is within 24 hours; notification records prevent duplicate sends and failed deliveries are retried. Install the migration with `python manage.py migrate`.

Email uses the configured Django email backend by default, or SendGrid when `SENDGRID_API_KEY` is set. SMS uses Twilio. Add these optional values to the repository root `.env`:

```dotenv
SENDGRID_API_KEY=
SENDGRID_FROM_EMAIL=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
TWILIO_MESSAGING_SERVICE_SID=
SMS_DEFAULT_COUNTRY_CODE=
```

Configure either `TWILIO_FROM_NUMBER` or `TWILIO_MESSAGING_SERVICE_SID`. Patient phone numbers should be stored in international E.164 form (for example, `+923001234567`); alternatively set `SMS_DEFAULT_COUNTRY_CODE=+92` for local numbers. Add a patient email to the linked user account to receive the confirmation. Without provider credentials, notifications remain pending and retry after configuration; appointment booking continues to work.
