from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    CustomerProfile,
    DriverApplication,
    DriverProfile,
    Office,
    WorkerApplication,
    WorkerProfile,
)

User = get_user_model()


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "role", "is_verified", "is_active")
    list_filter = (*DjangoUserAdmin.list_filter, "role", "is_verified")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("MoveLine", {"fields": ("role", "phone", "is_verified")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        (None, {"fields": ("role", "phone", "is_verified")}),
    )


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "payment_preferences", "created_at")
    search_fields = ("user__username", "user__email")


@admin.register(DriverProfile)
class DriverProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "office", "license_number", "rating", "availability")
    search_fields = ("user__username", "license_number")
    list_filter = ("availability",)


@admin.register(DriverApplication)
class DriverApplicationAdmin(admin.ModelAdmin):
    list_display = ("user", "city_area", "availability", "status", "interview_status", "interview_datetime")
    list_filter = ("status", "interview_status", "availability")
    search_fields = ("user__username", "user__email", "driver_license_number")


@admin.register(WorkerProfile)
class WorkerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "office", "availability", "location_updated_at", "created_at")
    list_filter = ("availability",)


@admin.register(WorkerApplication)
class WorkerApplicationAdmin(admin.ModelAdmin):
    list_display = ("user", "city_area", "availability", "status", "interview_status", "interview_datetime")
    list_filter = ("status", "interview_status", "availability")
    search_fields = ("user__username", "user__email", "skills")


@admin.register(Office)
class OfficeAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "latitude", "longitude")
    search_fields = ("name", "address")
