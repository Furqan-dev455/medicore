from django.urls import path

from . import views

urlpatterns = [
    path('dashboard', views.dashboard_api, name='dashboard_api'),
    path('dashboard/', views.dashboard_api, name='dashboard_api_slash'),
    path('patients', views.patient_list_api, name='patient_list_api'),
    path('patients/', views.patient_list_api, name='patient_list_api_slash'),
    path('doctors', views.doctor_list_api, name='doctor_list_api'),
    path('doctors/', views.doctor_list_api, name='doctor_list_api_slash'),
    path('appointments', views.appointment_list_api, name='appointment_list_api'),
    path('appointments/', views.appointment_list_api, name='appointment_list_api_slash'),
    path('bills', views.bill_list_api, name='bill_list_api'),
    path('bills/', views.bill_list_api, name='bill_list_api_slash'),
]
