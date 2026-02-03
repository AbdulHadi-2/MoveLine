from django.contrib import admin

from .models import OrderItem


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "label", "quantity", "is_fragile", "created_at")
    search_fields = ("order__id", "label")
    list_filter = ("is_fragile",)
