from django.contrib import admin

from .models import Tracking, TrackingAlert


@admin.register(Tracking)
class TrackingAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "driver",
        "current_latitude",
        "current_longitude",
        "speed_kmh",
        "stopped_since",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("order__id", "driver__username")


@admin.register(TrackingAlert)
class TrackingAlertAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "driver",
        "alert_type",
        "status",
        "driver_reason",
        "driver_notified_at",
        "admin_notified_at",
        "customer_notified_at",
        "created_at",
    )
    list_filter = ("alert_type", "status", "driver_reason", "created_at")
    search_fields = ("order__id", "driver__username", "driver__email")
