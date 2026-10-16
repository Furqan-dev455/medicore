from django.urls import path
from . import views

app_name = 'patients'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Patients
    path('patients/', views.patient_list, name='patient_list'),
    path('patients/create/', views.create_patient, name='create_patient'),
    path('patients/<int:pk>/update/', views.update_patient, name='update_patient'),
    path('patients/<int:pk>/delete/', views.delete_patient, name='delete_patient'),
    path('patients/<int:pk>/restore/', views.restore_patient, name='restore_patient'),
    path('patients/trash/', views.trash_list, name='trash_list'),

    # Doctors
    path('doctors/', views.doctor_list, name='doctor_list'),
    path('doctors/create/', views.register_doctor, name='register_doctor'),
    path('doctors/<int:pk>/update/', views.update_doctor, name='update_doctor'),

    # Appointments
    path('appointments/', views.appointment_list, name='appointment_list'),
    path('appointments/create/', views.create_appointment, name='create_appointment'),
    path('appointments/<int:pk>/update/', views.update_appointment, name='update_appointment'),

    # Bills
    path('bills/', views.bill_list, name='bill_list'),
    path('bills/create/', views.create_bill, name='create_bill'),
    path('bills/<int:pk>/', views.bill_detail, name='bill_detail'),
    path('bills/<int:pk>/update/', views.update_bill, name='update_bill'),
    path('bills/<int:pk>/payment/', views.add_payment, name='add_payment'),
    path('bills/<int:pk>/invoice/', views.download_invoice, name='download_invoice'),
]