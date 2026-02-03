from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "amount", "currency", "method", "status", "paid_at")
    list_filter = ("method", "status")
    search_fields = ("order__id", "transaction_reference")
