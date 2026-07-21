from django.contrib import admin

from .models import Payment, PendingOrderCheckout


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "amount", "currency", "method", "status", "paid_at")
    list_filter = ("method", "status")
    search_fields = ("order__id", "transaction_reference")


@admin.register(PendingOrderCheckout)
class PendingOrderCheckoutAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer",
        "order",
        "reserved_driver",
        "reserved_vehicle",
        "amount",
        "currency",
        "status",
        "expires_at",
        "created_at",
    )
    list_filter = ("status", "currency")
    search_fields = ("id", "customer__email", "stripe_session_id", "order__id")
    readonly_fields = (
        "customer",
        "order",
        "order_payload",
        "amount",
        "currency",
        "reserved_driver",
        "reserved_vehicle",
        "reserved_workers",
        "stripe_session_id",
        "status",
        "expires_at",
        "paid_at",
        "metadata",
        "created_at",
        "updated_at",
    )
