from rest_framework import serializers

from .models import Tracking


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
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")
