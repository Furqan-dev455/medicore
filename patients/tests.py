from django.test import TestCase
from django.contrib.auth.models import User
from django.core import mail
from django.test import Client, override_settings
from urllib.parse import urlparse
from .forms import AppointmentForm, BillForm, PaymentForm
from .models import Appointment, Bill, Doctor, Patient


@override_settings(
	EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
	FRONTEND_URL='http://localhost:3000',
)
class AccountRecoveryApiTests(TestCase):
	@override_settings(ALLOW_PUBLIC_SIGNUP=False)
	def test_signup_can_be_disabled(self):
		response = self.client.post(
			'/api/auth/signup',
			data={},
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 403)

	def test_signup_saves_regular_user_then_signin_opens_session(self):
		response = self.client.post(
			'/api/auth/signup',
			data={
				'username': 'new-clinic-user',
				'email': 'new-user@example.com',
				'password1': 'Cedar-River-724!Strong',
				'password2': 'Cedar-River-724!Strong',
			},
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 201, response.content)
		user = User.objects.get(username='new-clinic-user')
		self.assertFalse(user.is_superuser)
		session_response = self.client.get('/api/auth/session')
		self.assertEqual(session_response.status_code, 200)
		self.assertFalse(session_response.json()['authenticated'])

		login_response = self.client.post(
			'/api/auth/login',
			data={'username': 'new-clinic-user', 'password': 'Cedar-River-724!Strong'},
			content_type='application/json',
		)
		self.assertEqual(login_response.status_code, 200)
		self.assertTrue(self.client.get('/api/auth/session').json()['authenticated'])

	def test_signup_accepts_the_frontend_origin_and_returns_json_errors(self):
		for index, origin in enumerate(('http://localhost:3000', 'http://127.0.0.1:3000')):
			host = origin.split('//', 1)[1].split(':', 1)[0]
			username = f'csrf-probe-user-{index}'
			client = Client(enforce_csrf_checks=True)
			csrf_token = client.get('/api/csrf', HTTP_HOST=host).json()['csrfToken']
			response = client.post(
				'/api/auth/signup',
				data={
					'username': username,
					'email': f'{username}@example.com',
					'password1': 'a',
					'password2': 'a',
				},
				content_type='application/json',
				HTTP_HOST=host,
				HTTP_ORIGIN=origin,
				HTTP_X_CSRFTOKEN=csrf_token,
			)

			self.assertEqual(response.status_code, 400, origin)
			self.assertEqual(response['Content-Type'], 'application/json')
			self.assertIn('password2', response.json()['errors'])
			self.assertFalse(User.objects.filter(username=username).exists())

	def test_password_reset_request_sends_link_and_changes_password(self):
		old_password = 'Cedar-River-724!Strong'
		new_password = 'Lunar-Field-831!Secure'
		user = User.objects.create_user(
			username='forgot-user',
			email='forgot-user@example.com',
			password=old_password,
		)
		request_response = self.client.post(
			'/api/auth/password-reset',
			data={'email': user.email},
			content_type='application/json',
		)

		self.assertEqual(request_response.status_code, 200)
		self.assertEqual(len(mail.outbox), 1)
		reset_link = next(
			line for line in mail.outbox[0].body.splitlines()
			if '/reset-password/' in line
		)
		uid, token = urlparse(reset_link).path.rstrip('/').split('/')[-2:]
		confirm_response = self.client.post(
			'/api/auth/password-reset/confirm',
			data={
				'uid': uid,
				'token': token,
				'password': new_password,
				'password_confirm': new_password,
			},
			content_type='application/json',
		)

		self.assertEqual(confirm_response.status_code, 200, confirm_response.content)
		user.refresh_from_db()
		self.assertTrue(user.check_password(new_password))
		self.assertFalse(user.check_password(old_password))

	def test_unknown_reset_email_has_generic_response(self):
		response = self.client.post(
			'/api/auth/password-reset',
			data={'email': 'missing@example.com'},
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 200)
		self.assertIn('If an account exists', response.json()['message'])
		self.assertEqual(mail.outbox, [])


class PatientSelectionFormTests(TestCase):
	def setUp(self):
		self.patient = Patient.objects.create(
			name='Archived Patient',
			age=45,
			gender='Other',
			phone='555-0103',
			address='2 Old Street',
			is_deleted=True,
		)
		self.doctor = Doctor.objects.create(
			name='Taylor Doctor',
			specialization='General Practice',
			phone='555-0104',
			email='taylor@example.com',
		)

	def test_new_appointment_and_bill_reject_deleted_patients(self):
		appointment_form = AppointmentForm(data={
			'patient': self.patient.pk,
			'doctor': self.doctor.pk,
			'appointment_date': '2026-10-20',
			'appointment_time': '10:30',
			'status': 'Scheduled',
			'notes': '',
		})
		bill_form = BillForm(data={
			'patient': self.patient.pk,
			'total_amount': '12.50',
			'description': 'Consultation',
		})

		self.assertFalse(appointment_form.is_valid())
		self.assertIn('patient', appointment_form.errors)
		self.assertFalse(bill_form.is_valid())
		self.assertIn('patient', bill_form.errors)

	def test_existing_records_keep_their_deleted_patient_editable(self):
		appointment = Appointment.objects.create(
			patient=self.patient,
			doctor=self.doctor,
			appointment_date='2026-10-20',
			appointment_time='10:30',
		)
		bill = Bill.objects.create(patient=self.patient, total_amount='12.50')
		appointment_form = AppointmentForm(instance=appointment, data={
			'patient': self.patient.pk,
			'doctor': self.doctor.pk,
			'appointment_date': '2026-10-21',
			'appointment_time': '11:00',
			'status': 'Scheduled',
			'notes': '',
		})
		bill_form = BillForm(instance=bill, data={
			'patient': self.patient.pk,
			'total_amount': '12.50',
			'description': '',
		})

		self.assertTrue(appointment_form.is_valid(), appointment_form.errors)
		self.assertTrue(bill_form.is_valid(), bill_form.errors)

	def test_currency_widgets_accept_cents(self):
		self.assertEqual(BillForm().fields['total_amount'].widget.attrs['step'], '0.01')
		self.assertEqual(PaymentForm().fields['amount'].widget.attrs['step'], '0.01')


class RecordWriteApiTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username='clinic-admin', password='secure-test-password')

	def test_anonymous_users_cannot_create_records(self):
		response = self.client.post(
			'/api/patients',
			data={'name': 'A Patient'},
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 401)
		self.assertEqual(self.client.get('/api/patients').status_code, 401)
		session_response = self.client.get('/api/auth/session')
		self.assertEqual(session_response.status_code, 200)
		self.assertFalse(session_response.json()['authenticated'])

	def test_authenticated_user_can_create_and_update_patient(self):
		client = Client(enforce_csrf_checks=True)
		csrf_response = client.get('/api/csrf')
		csrf_token = csrf_response.json()['csrfToken']
		login_response = client.post(
			'/api/auth/login',
			data={'username': 'clinic-admin', 'password': 'secure-test-password'},
			content_type='application/json',
			HTTP_X_CSRFTOKEN=csrf_token,
		)

		self.assertEqual(login_response.status_code, 200)
		csrf_token = client.get('/api/csrf').json()['csrfToken']

		patient_data = {
			'name': 'Ada Patient',
			'age': 34,
			'gender': 'Female',
			'phone': '555-0100',
			'address': '12 Clinic Street',
			'medical_history': '',
		}
		create_response = client.post(
			'/api/patients',
			data=patient_data,
			content_type='application/json',
			HTTP_X_CSRFTOKEN=csrf_token,
		)

		self.assertEqual(create_response.status_code, 201)
		patient_id = create_response.json()['id']
		patient_data['name'] = 'Ada Updated'
		update_response = client.put(
			f'/api/patients/{patient_id}',
			data=patient_data,
			content_type='application/json',
			HTTP_X_CSRFTOKEN=csrf_token,
		)

		self.assertEqual(update_response.status_code, 200)
		self.assertEqual(update_response.json()['id'], patient_id)

	def test_invalid_form_data_returns_field_errors(self):
		self.client.force_login(self.user)
		response = self.client.post(
			'/api/patients',
			data={'name': '', 'age': 'not-a-number'},
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 400)
		self.assertIn('errors', response.json())

	def test_authenticated_user_can_create_all_record_types(self):
		self.client.force_login(self.user)
		patient_response = self.client.post(
			'/api/patients',
			data={
				'name': 'Grace Patient',
				'age': 29,
				'gender': 'Female',
				'phone': '555-0101',
				'address': '1 Health Way',
			},
			content_type='application/json',
		)
		doctor_response = self.client.post(
			'/api/doctors',
			data={
				'name': 'Morgan Doctor',
				'specialization': 'Cardiology',
				'phone': '555-0102',
				'email': 'morgan@example.com',
			},
			content_type='application/json',
		)

		self.assertEqual(patient_response.status_code, 201)
		self.assertEqual(doctor_response.status_code, 201)
		patient_id = patient_response.json()['id']
		doctor_id = doctor_response.json()['id']

		appointment_response = self.client.post(
			'/api/appointments',
			data={
				'patient': patient_id,
				'doctor': doctor_id,
				'appointment_date': '2026-10-20',
				'appointment_time': '10:30',
				'status': 'Scheduled',
				'notes': '',
			},
			content_type='application/json',
		)
		bill_response = self.client.post(
			'/api/bills',
			data={'patient': patient_id, 'total_amount': '120.00', 'description': 'Consultation'},
			content_type='application/json',
		)

		self.assertEqual(appointment_response.status_code, 201, appointment_response.content)
		self.assertEqual(bill_response.status_code, 201, bill_response.content)
