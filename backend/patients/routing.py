from django.urls import path

from .consumers import DoctorDashboardConsumer


websocket_urlpatterns = [
    path('ws/notifications/', DoctorDashboardConsumer.as_asgi()),
]
