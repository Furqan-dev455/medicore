import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch
from urllib.parse import urlparse

from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import appointment_notifications
from .forms import AppointmentForm, BillForm, PaymentForm
from .models import (
	Appointment, AppointmentNotification, Bill, Doctor, Medication, Patient, Payment,
	PaymentCheckout, Prescription, PrescriptionItem,
)
from .tasks import send_password_reset_email
from .views import _invoice_pdf_bytes


def future_date(days=3):
	"""Appointment dates relative to today, so tests don't start failing once a
	hardcoded date is in the past (new bookings in the past are rejected)."""
	return (timezone.localdate() + timedelta(days=days)).isoformat()


def make_user(username, role=None, password='Cedar-River-724!Strong', **extra):
	user = User.objects.create_user(username=username, email=f'{username}@example.com', password=password, **extra)
	if role:
		Group.objects.get_or_create(name=role)[0].user_set.add(user)
	return user


def run_celery_task_inline(task):
	"""Tests have no Celery worker: make task.delay() run the task immediately."""
	return patch.object(task, 'delay', side_effect=lambda *args, **kwargs: task(*args, **kwargs))


class CacheClearingTestCase(TestCase):
	"""Login lockout and reset limits live in the cache; start every test clean."""

	def setUp(self):
		cache.clear()
		super().setUp()


@override_settings(
	EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
	FRONTEND_URL='http://localhost:3000',
)
class AccountRecoveryApiTests(CacheClearingTestCase):
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
		# The reset email is now sent by a Celery task.
		with run_celery_task_inline(send_password_reset_email):
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

	def test_reset_email_states_the_configured_expiry(self):
		make_user('expiry-user')
		with self.settings(PASSWORD_RESET_TIMEOUT=2 * 60 * 60), run_celery_task_inline(send_password_reset_email):
			self.client.post('/api/auth/password-reset', data={'email': 'expiry-user@example.com'}, content_type='application/json')
		self.assertIn('expires in 2 hours', mail.outbox[0].body)

	def test_unknown_reset_email_has_generic_response(self):
		with run_celery_task_inline(send_password_reset_email):
			response = self.client.post(
				'/api/auth/password-reset',
				data={'email': 'missing@example.com'},
				content_type='application/json',
			)

		self.assertEqual(response.status_code, 200)
		self.assertIn('If an account exists', response.json()['message'])
		self.assertEqual(mail.outbox, [])

	def test_reset_requests_are_rate_limited_per_email_without_revealing_it(self):
		make_user('flooded')
		with run_celery_task_inline(send_password_reset_email):
			for _ in range(6):
				response = self.client.post('/api/auth/password-reset', data={'email': 'flooded@example.com'}, content_type='application/json')
				self.assertEqual(response.status_code, 200)
		self.assertEqual(len(mail.outbox), 3)

	def test_reset_confirm_with_non_string_uid_is_400_not_500(self):
		response = self.client.post(
			'/api/auth/password-reset/confirm',
			data={'uid': 123, 'token': 'x', 'password': 'a', 'password_confirm': 'a'},
			content_type='application/json',
		)
		self.assertEqual(response.status_code, 400)

	def test_login_locks_out_after_repeated_failures(self):
		make_user('target')
		for _ in range(5):
			response = self.client.post('/api/auth/login', data={'username': 'target', 'password': 'wrong'}, content_type='application/json')
			self.assertEqual(response.status_code, 401)
		response = self.client.post('/api/auth/login', data={'username': 'target', 'password': 'Cedar-River-724!Strong'}, content_type='application/json')
		self.assertEqual(response.status_code, 429)

	def test_login_rejects_non_string_credentials(self):
		response = self.client.post('/api/auth/login', data={'username': {'a': 1}, 'password': 'x'}, content_type='application/json')
		self.assertEqual(response.status_code, 400)


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
			'appointment_date': future_date(),
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
			appointment_date=future_date(),
			appointment_time='10:30',
		)
		bill = Bill.objects.create(patient=self.patient, total_amount='12.50')
		appointment_form = AppointmentForm(instance=appointment, data={
			'patient': self.patient.pk,
			'doctor': self.doctor.pk,
			'appointment_date': future_date(4),
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

	def test_new_appointment_in_the_past_is_rejected(self):
		self.patient.restore()
		form = AppointmentForm(data={
			'patient': self.patient.pk,
			'doctor': self.doctor.pk,
			'appointment_date': (timezone.localdate() - timedelta(days=1)).isoformat(),
			'appointment_time': '10:30',
			'status': 'Scheduled',
			'notes': '',
		})
		self.assertFalse(form.is_valid())

	def test_currency_widgets_accept_cents(self):
		self.assertEqual(BillForm().fields['total_amount'].widget.attrs['step'], '0.01')
		self.assertEqual(PaymentForm().fields['amount'].widget.attrs['step'], '0.01')

	def test_staff_cannot_enter_card_payments_manually(self):
		methods = [value for value, _ in PaymentForm().fields['payment_method'].choices]
		self.assertNotIn(Payment.PaymentMethod.CARD, methods)


class HtmlPageAccessTests(TestCase):
	def setUp(self):
		self.patient = Patient.objects.create(name='P', age=30, phone='555-0130', address='a')

	def test_user_without_a_role_cannot_open_patient_pages(self):
		self.client.force_login(make_user('no-role'))
		self.assertEqual(self.client.get(reverse('patients:patient_list')).status_code, 403)
		self.assertEqual(self.client.get(reverse('patients:bill_list')).status_code, 403)

	def test_patient_role_cannot_open_staff_pages(self):
		self.client.force_login(make_user('portal-patient', 'Patient'))
		self.assertEqual(self.client.get(reverse('patients:dashboard')).status_code, 403)
		self.assertEqual(self.client.get(reverse('patients:doctor_list')).status_code, 403)

	def test_receptionist_sees_patients_but_not_bills(self):
		self.client.force_login(make_user('front-desk', 'Receptionist'))
		self.assertEqual(self.client.get(reverse('patients:patient_list')).status_code, 200)
		self.assertEqual(self.client.get(reverse('patients:bill_list')).status_code, 403)

	def test_soft_delete_records_who_and_when(self):
		admin = make_user('html-admin', 'Admin')
		self.client.force_login(admin)
		self.client.post(reverse('patients:delete_patient', args=[self.patient.pk]))
		self.patient.refresh_from_db()
		self.assertTrue(self.patient.is_deleted)
		self.assertIsNotNone(self.patient.deleted_at)
		self.assertEqual(self.patient.updated_by, admin)


class RecordWriteApiTests(CacheClearingTestCase):
	def setUp(self):
		super().setUp()
		self.user = User.objects.create_user(username='clinic-admin', password='secure-test-password')
		Group.objects.get_or_create(name='Admin')[0].user_set.add(self.user)

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

	def test_patch_updates_only_the_fields_sent(self):
		self.client.force_login(self.user)
		patient = Patient.objects.create(name='Partial', age=40, phone='555-0140', address='Keep This Address')
		response = self.client.patch(f'/api/patients/{patient.pk}', data={'phone': '555-0141'}, content_type='application/json')

		self.assertEqual(response.status_code, 200, response.content)
		patient.refresh_from_db()
		self.assertEqual(patient.phone, '555-0141')
		self.assertEqual(patient.address, 'Keep This Address')

	def test_deleted_patient_cannot_be_edited_through_the_api(self):
		self.client.force_login(self.user)
		patient = Patient.objects.create(name='Gone', age=40, phone='555-0142', address='x')
		patient.soft_delete()
		response = self.client.put(f'/api/patients/{patient.pk}', data={'name': 'Back'}, content_type='application/json')
		self.assertEqual(response.status_code, 404)

	def test_list_pagination_is_opt_in(self):
		self.client.force_login(self.user)
		for index in range(3):
			Patient.objects.create(name=f'P{index}', age=20, phone='555-0150', address='x')

		self.assertNotIn('pagination', self.client.get('/api/patients').json())
		paged = self.client.get('/api/patients?page=2&page_size=2').json()
		self.assertEqual(len(paged['patients']), 1)
		self.assertEqual(paged['pagination'], {'page': 2, 'page_size': 2, 'total': 3, 'pages': 2})

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
				'appointment_date': future_date(),
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


class PrescriptionInventoryApiTests(TestCase):
	def setUp(self):
		self.doctor_user = User.objects.create_user(username='rx-doctor', password='test-password')
		Group.objects.get_or_create(name='Doctor')[0].user_set.add(self.doctor_user)
		self.doctor = Doctor.objects.create(
			user=self.doctor_user,
			name='Dr. Rx',
			specialization='General Practice',
			phone='555-0110',
			email='rx-doctor@example.com',
		)
		self.patient = Patient.objects.create(
			name='Prescription Patient', age=32, gender='Other', phone='555-0111', address='Clinic Road'
		)
		Appointment.objects.create(
			patient=self.patient,
			doctor=self.doctor,
			appointment_date=future_date(),
			appointment_time='09:00',
		)
		self.medicine = Medication.objects.create(
			name='Amoxicillin', strength='500 mg', dosage_form='Capsule', unit='capsules', stock_quantity=8
		)
		self.client.force_login(self.doctor_user)

	def _payload(self, lines):
		return {
			'patient_id': self.patient.pk,
			'notes': 'Take with water',
			'items': lines,
		}

	def _line(self, medication, quantity):
		return {
			'medication_id': medication.pk,
			'quantity': quantity,
			'dosage': '1 capsule twice daily',
			'duration': '5 days',
			'instructions': 'Take after food',
		}

	def test_saving_prescription_deducts_stock_and_creates_item(self):
		response = self.client.post(
			'/api/prescriptions/',
			data=self._payload([self._line(self.medicine, 3)]),
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 201, response.content)
		self.medicine.refresh_from_db()
		self.assertEqual(self.medicine.stock_quantity, 5)
		self.assertEqual(Prescription.objects.count(), 1)
		self.assertEqual(PrescriptionItem.objects.get().quantity, 3)

	def test_insufficient_stock_keeps_entire_prescription_unchanged(self):
		other = Medication.objects.create(name='Second medicine', stock_quantity=1)
		response = self.client.post(
			'/api/prescriptions/',
			data=self._payload([self._line(self.medicine, 2), self._line(other, 2)]),
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 409)
		self.medicine.refresh_from_db()
		other.refresh_from_db()
		self.assertEqual(self.medicine.stock_quantity, 8)
		self.assertEqual(other.stock_quantity, 1)
		self.assertEqual(Prescription.objects.count(), 0)

	def test_doctor_cannot_prescribe_for_an_unassigned_patient(self):
		other_patient = Patient.objects.create(
			name='Other Patient', age=40, gender='Other', phone='555-0112', address='Elsewhere'
		)
		payload = self._payload([self._line(self.medicine, 1)])
		payload['patient_id'] = other_patient.pk
		response = self.client.post('/api/prescriptions/', data=payload, content_type='application/json')

		self.assertEqual(response.status_code, 403)
		self.assertEqual(self.medicine.__class__.objects.get(pk=self.medicine.pk).stock_quantity, 8)

	def test_fractional_or_boolean_values_are_rejected_not_truncated(self):
		for bad_line in (
			{**self._line(self.medicine, 1), 'quantity': 3.9},
			{**self._line(self.medicine, 1), 'medication_id': True},
		):
			response = self.client.post('/api/prescriptions/', data=self._payload([bad_line]), content_type='application/json')
			self.assertEqual(response.status_code, 400, bad_line)
		self.medicine.refresh_from_db()
		self.assertEqual(self.medicine.stock_quantity, 8)


class BillingModelTests(TestCase):
	def setUp(self):
		self.patient = Patient.objects.create(name='Ali <&> Khan', age=30, phone='555-0160', address='Lahore')
		self.bill = Bill.objects.create(patient=self.patient, total_amount=Decimal('1000.00'))

	def test_overpayment_is_blocked_by_the_model(self):
		with self.assertRaises(ValidationError):
			Payment.objects.create(bill=self.bill, amount=Decimal('1000.01'))

	def test_status_follows_payments_including_deletes(self):
		payment = Payment.objects.create(bill=self.bill, amount=Decimal('400'))
		self.bill.refresh_from_db()
		self.assertEqual(self.bill.status, Bill.BillStatus.PARTIAL)
		Payment.objects.create(bill=self.bill, amount=Decimal('600'))
		self.bill.refresh_from_db()
		self.assertEqual(self.bill.status, Bill.BillStatus.PAID)
		Payment.objects.filter(pk=payment.pk).delete()
		self.bill.refresh_from_db()
		self.assertEqual(self.bill.status, Bill.BillStatus.PARTIAL)

	def test_bill_with_payments_cannot_be_deleted(self):
		from django.db.models import ProtectedError

		Payment.objects.create(bill=self.bill, amount=Decimal('10'))
		with self.assertRaises(ProtectedError):
			self.bill.delete()

	def test_invoice_pdf_handles_markup_characters_in_names(self):
		self.assertTrue(_invoice_pdf_bytes(self.bill).startswith(b'%PDF'))


class SafepayPaymentApiTests(TestCase):
	def setUp(self):
		self.patient_user = User.objects.create_user(username='pay-patient', password='test-password')
		Group.objects.get_or_create(name='Patient')[0].user_set.add(self.patient_user)
		self.patient = Patient.objects.create(
			user=self.patient_user,
			name='Pay Patient', age=28, gender='Other', phone='555-0120', address='Payment Road'
		)
		self.bill = Bill.objects.create(patient=self.patient, total_amount=Decimal('1250.00'))
		self.client.force_login(self.patient_user)

	def _signed_success(self, tracker, amount_minor):
		body = json.dumps({
			'type': 'payment.succeeded',
			'data': {'tracker': tracker, 'amount': amount_minor, 'currency': 'PKR'},
		}, separators=(',', ':')).encode()
		signature = hmac.new(b'webhook-test-secret', body, hashlib.sha512).hexdigest()
		return self.client.post(
			'/api/webhooks/safepay',
			data=body,
			content_type='application/json',
			HTTP_X_SFPY_SIGNATURE=signature,
		)

	@override_settings(
		SAFEPAY_ENVIRONMENT='sandbox',
		SAFEPAY_API_KEY='public-test-key',
		SAFEPAY_SECRET_KEY='secret-test-key',
		FRONTEND_URL='http://localhost:3000',
	)
	@patch('patients.views.requests.post')
	def test_patient_checkout_uses_bill_amount_and_returns_provider_url(self, mock_post):
		tracker_response = Mock()
		tracker_response.json.return_value = {'data': {'tracker': {'token': 'track_checkout_test'}}}
		token_response = Mock()
		token_response.json.return_value = {'data': 'temporary-auth-token'}
		mock_post.side_effect = [tracker_response, token_response]

		# Use the real pk: on PostgreSQL, ids are not reset between tests, so "1" is not guaranteed.
		response = self.client.post(f'/api/bills/{self.bill.pk}/checkout', data={}, content_type='application/json')

		self.assertEqual(response.status_code, 200, response.content)
		self.assertIn('checkout/pay', response.json()['checkout_url'])
		self.assertEqual(PaymentCheckout.objects.get().amount, Decimal('1250.00'))
		self.assertEqual(mock_post.call_args_list[0].kwargs['json']['amount'], 125000)

	@override_settings(SAFEPAY_ENVIRONMENT='staging', SAFEPAY_API_KEY='k', SAFEPAY_SECRET_KEY='s')
	def test_bad_environment_creates_no_checkout(self):
		response = self.client.post(f'/api/bills/{self.bill.pk}/checkout', data={}, content_type='application/json')
		self.assertEqual(response.status_code, 503)
		self.assertFalse(PaymentCheckout.objects.exists())

	@override_settings(SAFEPAY_WEBHOOK_SECRET='webhook-test-secret')
	def test_signed_success_webhook_records_payment_once(self):
		checkout = PaymentCheckout.objects.create(
			bill=self.bill,
			patient=self.patient,
			amount=Decimal('1250.00'),
			tracker_token='track_paid_test',
			expires_at=timezone.now() + timedelta(hours=1),
		)

		for _ in range(2):
			response = self._signed_success('track_paid_test', 125000)
			self.assertEqual(response.status_code, 200, response.content)

		checkout.refresh_from_db()
		self.bill.refresh_from_db()
		self.assertEqual(checkout.status, PaymentCheckout.Status.COMPLETED)
		self.assertEqual(self.bill.status, Bill.BillStatus.PAID)
		self.assertEqual(Payment.objects.filter(provider_reference='track_paid_test').count(), 1)

	@override_settings(SAFEPAY_WEBHOOK_SECRET='webhook-test-secret')
	def test_late_payment_that_no_longer_fits_is_flagged_for_reconciliation(self):
		# Checkout expired, staff took cash for the whole bill, then Safepay confirms.
		checkout = PaymentCheckout.objects.create(
			bill=self.bill,
			patient=self.patient,
			amount=Decimal('1250.00'),
			tracker_token='track_late_test',
			status=PaymentCheckout.Status.FAILED,
			expires_at=timezone.now() - timedelta(minutes=5),
		)
		Payment.objects.create(bill=self.bill, amount=Decimal('1250.00'))

		response = self._signed_success('track_late_test', 125000)

		self.assertEqual(response.status_code, 200)  # acknowledged, so Safepay stops retrying
		self.assertTrue(response.json()['reconciliation_required'])
		checkout.refresh_from_db()
		self.assertEqual(checkout.status, PaymentCheckout.Status.NEEDS_RECONCILIATION)
		self.assertEqual(Payment.objects.count(), 1)

	@override_settings(SAFEPAY_WEBHOOK_SECRET='webhook-test-secret')
	def test_webhook_rejects_invalid_signature(self):
		response = self.client.post(
			'/api/webhooks/safepay',
			data=b'{"type":"payment.succeeded"}',
			content_type='application/json',
			HTTP_X_SFPY_SIGNATURE='invalid',
		)
		self.assertEqual(response.status_code, 400)
		self.assertEqual(Payment.objects.count(), 0)


class RoleSetupTests(TestCase):
	def test_migrate_creates_role_groups_with_history_permission(self):
		self.assertEqual(
			set(Group.objects.values_list('name', flat=True)),
			{'Admin', 'Doctor', 'Patient', 'Receptionist'},
		)
		for role, expected in (('Admin', True), ('Doctor', True), ('Receptionist', False), ('Patient', False)):
			has_permission = Group.objects.get(name=role).permissions.filter(codename='view_patient_medical_history').exists()
			self.assertEqual(has_permission, expected, role)


class AppointmentNotificationTests(TestCase):
	def setUp(self):
		patient_user = make_user('notify-patient')
		patient = Patient.objects.create(name='N', age=30, phone='555-0170', address='x', user=patient_user)
		doctor = Doctor.objects.create(name='D', specialization='GP', phone='555-0171', email='d@example.com')
		self.appointment = Appointment.objects.create(
			patient=patient, doctor=doctor, appointment_date=future_date(), appointment_time='10:00'
		)

	def test_failing_notification_stops_after_max_attempts(self):
		notification = AppointmentNotification.objects.create(
			appointment=self.appointment, kind='confirmation', channel='email'
		)
		with patch.object(appointment_notifications, '_send_email', side_effect=RuntimeError('x' * 900)):
			for _ in range(AppointmentNotification.MAX_ATTEMPTS + 2):
				AppointmentNotification.objects.filter(pk=notification.pk).update(next_attempt_at=timezone.now())
				appointment_notifications.send_appointment_notification(notification.pk)

		notification.refresh_from_db()
		self.assertEqual(notification.status, AppointmentNotification.Status.FAILED)
		self.assertEqual(notification.attempts, AppointmentNotification.MAX_ATTEMPTS)
		self.assertEqual(len(notification.last_error), AppointmentNotification.LAST_ERROR_MAX_LENGTH)

	def test_notification_stuck_in_sending_is_retried(self):
		notification = AppointmentNotification.objects.create(
			appointment=self.appointment,
			kind='confirmation',
			channel='email',
			status=AppointmentNotification.Status.SENDING,
			claimed_at=timezone.now() - timedelta(hours=1),
		)
		with patch.object(appointment_notifications.send_appointment_notification, 'delay') as delay:
			appointment_notifications.process_appointment_reminders()
		delay.assert_any_call(notification.pk)