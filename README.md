# MediCore

A Django API and Next.js frontend that can be run independently.

## Run the backend

```powershell
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

## Run the frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Django serves the API and WebSockets at `http://localhost:8000`; Next.js serves the frontend at `http://localhost:3000`. Start Redis in Ubuntu/WSL for real-time dashboard updates. Backend settings are in `backend/core/settings.py`. Put shared environment variables in a `.env` file at the repository root. SQLite data, shared templates, and media stay at the repository root.

Doctor prescriptions deduct pharmacy stock atomically. Manage the medicine catalogue and replenishment quantities from the Pharmacy inventory page. Patient online checkout uses Safepay in sandbox mode by default; set `SAFEPAY_API_KEY`, `SAFEPAY_SECRET_KEY`, and `SAFEPAY_WEBHOOK_SECRET` in the root `.env`. Configure the Safepay webhook URL as `https://<backend-host>/api/webhooks/safepay`. A public HTTPS endpoint is required for Safepay to deliver payment confirmations. Use `SAFEPAY_ENVIRONMENT=production` only after the merchant account has been approved and production keys are configured.

See [backend/README.md](backend/README.md) for optional worker and backend details.
