from rest_framework import serializers

from ai_analyze.serializers import OrderItemSerializer
from ai_analyze.models import OrderItem
from payments.models import Payment
from tracking.models import Tracking
from .models import Order, OrderWorker


class OrderWorkerSerializer(serializers.ModelSerializer):
    worker_full_name = serializers.CharField(source="worker.get_full_name", read_only=True)

    class Meta:
        model = OrderWorker
        fields = (
            "id",
            "order",
            "worker",
            "worker_full_name",
            "status",
            "role_description",
            "assigned_at",
            "started_at",
            "completed_at",
        )
        read_only_fields = ("assigned_at",)


class PaymentInlineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ("id", "amount", "currency", "status", "method", "paid_at")


class TrackingInlineSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tracking
        fields = (
            "order",
            "current_latitude",
            "current_longitude",
            "heading",
            "speed_kmh",
            "last_ping_at",
            "is_active",
        )


class OrderSerializer(serializers.ModelSerializer):
    order_workers = OrderWorkerSerializer(many=True, read_only=True)
    items = OrderItemSerializer(many=True, required=False)
    payment = PaymentInlineSerializer(read_only=True)
    tracking = TrackingInlineSerializer(read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "customer",
            "driver",
            "vehicle",
            "workers",
            "required_workers",
            "required_vehicle_type",
            "assembly",
            "disassembly",
            "service_type",
            "status",
            "scheduled_start",
            "scheduled_end",
            "pickup_address",
            "pickup_latitude",
            "pickup_longitude",
            "dropoff_address",
            "dropoff_latitude",
            "dropoff_longitude",
            "special_instructions",
            "estimated_distance_km",
            "estimated_duration_minutes",
            "estimated_price",
            "final_price",
            "is_priority",
            "order_workers",
            "items",
            "payment",
            "tracking",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "customer",
            "order_workers",
            "payment",
            "tracking",
            "created_at",
            "updated_at",
        )

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        order = super().create(validated_data)
        for item in items_data:
            OrderItem.objects.create(order=order, **item)
        return order

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        order = super().update(instance, validated_data)
        if items_data is not None:
            order.items.all().delete()
            for item in items_data:
                OrderItem.objects.create(order=order, **item)
        return order
