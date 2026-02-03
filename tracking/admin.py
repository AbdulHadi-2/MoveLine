from django.contrib import admin

from .models import Tracking


@admin.register(Tracking)
class TrackingAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "driver",
        "current_latitude",
        "current_longitude",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("order__id", "driver__username")
