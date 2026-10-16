from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group, User
from .models import Patient, Doctor, Appointment, Bill, Payment


class MediCoreAdminSite(AdminSite):
    site_header = 'MediCore administration'
    site_title = 'MediCore admin'
    index_title = 'Manage hospital records and access'

    def has_permission(self, request):
        user = request.user
        return user.is_active and user.is_staff and (
            user.is_superuser or user.groups.filter(name='Admin').exists()
        )


medicore_admin_site = MediCoreAdminSite(name='medicore_admin')
medicore_admin_site.register(User, UserAdmin)
medicore_admin_site.register(Group, GroupAdmin)
medicore_admin_site.register(Patient)
medicore_admin_site.register(Doctor)
medicore_admin_site.register(Appointment)
medicore_admin_site.register(Bill)
medicore_admin_site.register(Payment)
