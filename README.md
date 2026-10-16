# 🏥 MediCore – Hospital Management System

A modern Hospital Management System built with **Django** and **PostgreSQL** for managing patients, doctors, appointments, billing, and payments. The application is deployed on Railway and uses Neon PostgreSQL as the production database.

## 🌐 Live Demo

https://medicore-production-8796.up.railway.app

> **Admin Panel**
>
> https://medicore-production-8796.up.railway.app/admin/

---

# ✨ Features

### 👨‍⚕️ Doctor Management
- Register doctors
- Edit doctor information
- View doctor directory

### 🧑‍🤝‍🧑 Patient Management
- Add patients
- Update patient records
- Soft delete & restore patients
- Patient listing

### 📅 Appointment Management
- Schedule appointments
- Update appointment status
- View appointments

### 💳 Billing System
- Generate bills
- Track paid amount
- Calculate remaining balance
- Bill status (Paid / Partial / Unpaid)

### 💰 Payment Management
- Record payments
- Payment history
- Multiple payment methods

### 📄 PDF Generation
- Download printable invoices
- Professional PDF bills using ReportLab

### 🔐 Authentication
- Django Admin authentication
- Secure login
- Session management

### ☁️ Deployment
- Railway hosting
- Neon PostgreSQL database
- WhiteNoise static file serving
- Gunicorn production server

---

# 🛠 Tech Stack

- Python 3
- Django 6
- PostgreSQL (Neon)
- Railway
- HTML5
- CSS3
- Bootstrap 5
- WhiteNoise
- Gunicorn
- ReportLab

---

# 📷 Screenshots

## Dashboard

![Dashboard](screenshots/dashboard.png)

---

## Patients

![Patients](screenshots/patients.png)

---

## Doctors

![Doctors](screenshots/doctors.png)

---

## Appointments

![Appointments](screenshots/appointments.png)

---

## Bills

![Bills](screenshots/bills.png)

---

## Payments

![Payments](screenshots/payments.png)

---

# 🚀 Local Installation

Clone the repository

```bash
git clone https://github.com/FurqanAthar28/medicore.git
cd medicore
```

Create virtual environment

```bash
python -m venv env
```

Activate environment

### Windows

```bash
env\Scripts\activate
```

### Linux / macOS

```bash
source env/bin/activate
```

Install dependencies

```bash
pip install -r requirements.txt
```

Run migrations

```bash
python manage.py migrate
```

Create superuser

```bash
python manage.py createsuperuser
```

Run server

```bash
python manage.py runserver
```

---

# ⚙️ Environment Variables

Create a `.env` file in the project root.

```env
SECRET_KEY=your_secret_key
DEBUG=True
DATABASE_URL=your_database_url
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost:8000
FRONTEND_URL=http://localhost:3000
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-full-gmail-address
EMAIL_HOST_PASSWORD=your-google-app-password
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=MediCore <your-full-gmail-address>
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
# Optional Azure Blob Storage (otherwise invoices use local media storage)
AZURE_STORAGE_ACCOUNT_NAME=your-storage-account
AZURE_STORAGE_ACCOUNT_KEY=your-storage-account-key
AZURE_STORAGE_CONTAINER=medicore-media
```

For Gmail, use your full Gmail address as `EMAIL_HOST_USER` and as the email address in `DEFAULT_FROM_EMAIL`. You can use a display name such as `MediCore <you@gmail.com>`. Create an App Password in your Google Account and put that in `EMAIL_HOST_PASSWORD`; Gmail app passwords require 2-Step Verification. Google documents [Gmail SMTP settings](https://support.google.com/mail/answer/7104828) and [App Passwords](https://support.google.com/accounts/answer/2461835). Keep real credentials in your local `.env`, never in source control, then restart Django. If `EMAIL_HOST` is not set during development, Django prints reset emails in the server console instead.

Invoice PDFs are generated asynchronously after a payment is recorded. Install the Python packages from `requirements.txt`, start Redis, apply migrations with `python manage.py migrate`, and run a Celery worker in a second terminal with `celery -A core worker -l info` (on Windows, add `-P solo`). The patient must have a linked user account with an email address to receive the generated invoice. Without Azure settings, invoice files are stored under local media storage; to persist invoices across deployments, configure Azure Blob Storage above. Keep Azure credentials in the environment and never commit them.

## Role-based access

Run `python manage.py migrate` after updating the application. It creates the `Admin`, `Doctor`, `Patient`, and `Receptionist` groups and adds the patient-account link. New accounts have no access role until an administrator assigns one.

Use Django Admin (`/admin/`) to assign a user to exactly one role group. For a patient account, also set that user's account on the matching Patient record. For a doctor account, set the account on the matching Doctor record. The API then scopes patient, appointment, and bill data to those links. Doctor and Admin groups receive the custom medical-history permission; receptionists can view patient demographics and schedule appointments but not medical histories or billing. Patients can view only their linked profile, appointments, bills, and invoice PDFs. Admin users can manage all records and billing.

---

# 📦 Deployment

This project is deployed using:

- Railway
- Neon PostgreSQL
- WhiteNoise
- Gunicorn

---

# 📁 Project Structure

```
core/
patients/
templates/
static/
screenshots/
manage.py
requirements.txt
build.sh
README.md
```

---

# 👨‍💻 Author

**Furqan Athar**

GitHub:
https://github.com/FurqanAthar28

LinkedIn:
https://www.linkedin.com/in/furqan-athar/

---

# 📄 License

This project is intended for educational and portfolio purposes.
