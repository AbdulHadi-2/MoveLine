from rest_framework import serializers

from .models import Rating


class RatingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rating
        fields = (
            "id",
            "order",
            "customer",
            "driver",
            "score",
            "feedback",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")
