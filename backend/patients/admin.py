from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group, User
from simple_history.admin import SimpleHistoryAdmin
from .models import Patient, Doctor, Appointment, Bill, Payment, Medication, Prescription, PrescriptionItem


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
medicore_admin_site.register(Patient, SimpleHistoryAdmin)
medicore_admin_site.register(Doctor)
medicore_admin_site.register(Appointment)
medicore_admin_site.register(Bill, SimpleHistoryAdmin)
medicore_admin_site.register(Payment, SimpleHistoryAdmin)


@admin.register(Medication, site=medicore_admin_site)
class MedicationAdmin(admin.ModelAdmin):
    list_display = ('name', 'strength', 'dosage_form', 'stock_quantity', 'low_stock_threshold', 'is_active')
    list_filter = ('is_active', 'dosage_form')
    search_fields = ('name', 'strength')


class PrescriptionItemInline(admin.TabularInline):
    model = PrescriptionItem
    extra = 0
    can_delete = False
    readonly_fields = ('medication', 'dosage', 'duration', 'quantity', 'instructions')


@admin.register(Prescription, site=medicore_admin_site)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'patient', 'doctor', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('patient__name', 'doctor__name')
    readonly_fields = ('patient', 'doctor', 'appointment', 'notes', 'created_at')
    inlines = (PrescriptionItemInline,)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff and (
            request.user.is_superuser or request.user.groups.filter(name='Admin').exists()
        )

    def has_delete_permission(self, request, obj=None):
        return False
