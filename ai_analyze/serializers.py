from rest_framework import serializers

from .models import OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = (
            "id",
            "order",
            "label",
            "quantity",
            "is_fragile",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("order", "created_at", "updated_at")
