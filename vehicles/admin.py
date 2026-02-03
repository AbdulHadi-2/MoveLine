from django.contrib import admin

from .models import Vehicle


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "vehicle_type",
        "plate_number",
        "office",
        "is_available",
    )
    list_filter = ("vehicle_type", "is_available", "office")
    search_fields = ("name", "plate_number", "office__name")
