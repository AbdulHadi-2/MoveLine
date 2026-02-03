from django.contrib import admin

from .models import Order, OrderWorker


class OrderWorkerInline(admin.TabularInline):
    model = OrderWorker
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "service_type",
        "status",
        "customer",
        "driver",
        "vehicle",
        "created_at",
    )
    list_filter = ("service_type", "status", "created_at")
    search_fields = ("id", "customer__username", "driver__username")
    inlines = (OrderWorkerInline,)


@admin.register(OrderWorker)
class OrderWorkerAdmin(admin.ModelAdmin):
    list_display = ("order", "worker", "status", "assigned_at")
    list_filter = ("status",)
    search_fields = ("order__id", "worker__username")
