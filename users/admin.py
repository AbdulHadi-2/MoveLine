from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    CustomerProfile,
    DeviceToken,
    DriverApplication,
    DriverProfile,
    EmailVerificationCode,
    Office,
    UserNotification,
    WorkerApplication,
    WorkerProfile,
)

User = get_user_model()


class DeviceTokenInline(admin.TabularInline):
    model = DeviceToken
    extra = 0
    fields = ("token", "device_type", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "role", "is_verified", "is_active")
    list_filter = (*DjangoUserAdmin.list_filter, "role", "is_verified")
    inlines = (*DjangoUserAdmin.inlines, DeviceTokenInline)
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


@admin.register(EmailVerificationCode)
class EmailVerificationCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "code", "expires_at", "used_at", "created_at")
    list_filter = ("used_at", "created_at")
    search_fields = ("user__username", "user__email", "code")


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "device_type", "short_token", "created_at", "updated_at")
    list_filter = ("device_type", "created_at", "updated_at")
    search_fields = ("user__username", "user__email", "token")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")

    def short_token(self, obj):
        if not obj.token:
            return ""
        return f"{obj.token[:18]}..."


@admin.register(UserNotification)
class UserNotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "is_read", "created_at", "read_at")
    list_filter = ("is_read", "created_at")
    search_fields = ("user__username", "user__email", "title", "body")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at",)


@admin.register(Office)
class OfficeAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "latitude", "longitude")
    search_fields = ("name", "address")
