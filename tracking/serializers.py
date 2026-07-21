from rest_framework import serializers

from .models import Tracking, TrackingAlert


class TrackingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tracking
        fields = (
            "order",
            "driver",
            "current_latitude",
            "current_longitude",
            "heading",
            "speed_kmh",
            "route_geometry",
            "last_ping_at",
            "stopped_since",
            "last_movement_at",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("stopped_since", "last_movement_at", "created_at", "updated_at")


class TrackingAlertSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(source="order.id", read_only=True)
    driver_id = serializers.IntegerField(source="driver.id", read_only=True)
    driver_name = serializers.CharField(source="driver.get_full_name", read_only=True)

    class Meta:
        model = TrackingAlert
        fields = (
            "id",
            "order",
            "order_id",
            "tracking",
            "driver",
            "driver_id",
            "driver_name",
            "alert_type",
            "status",
            "driver_reason",
            "driver_note",
            "driver_notified_at",
            "driver_responded_at",
            "admin_notified_at",
            "customer_notified_at",
            "resolved_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "order",
            "order_id",
            "tracking",
            "driver",
            "driver_id",
            "driver_name",
            "alert_type",
            "driver_notified_at",
            "driver_responded_at",
            "admin_notified_at",
            "customer_notified_at",
            "resolved_at",
            "created_at",
            "updated_at",
        )


class TrackingAlertDriverResponseSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=TrackingAlert.DriverReason.choices)
    note = serializers.CharField(required=False, allow_blank=True)


class TrackingAlertManualNotificationSerializer(serializers.Serializer):
    state = serializers.ChoiceField(
        choices=(
            ("open", "Open"),
            ("acknowledged", "Acknowledged"),
            ("admin_attention", "Admin Attention"),
            ("customer_delay", "Customer Delay"),
            ("resolved", "Resolved"),
        )
    )
