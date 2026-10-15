from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import include, path

def redirect_to_frontend(request, path=""):
    return HttpResponseRedirect(f"http://localhost:3000/{path}")

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('patients.api_urls')),
    path('', lambda request: redirect_to_frontend(request), name='frontend_root'),
    path('login/', lambda request: redirect_to_frontend(request, 'login'), name='login'),
    path('logout/', lambda request: redirect_to_frontend(request, 'login'), name='logout'),
]