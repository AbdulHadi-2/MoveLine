from django.contrib.auth import get_user_model
from rest_framework import serializers

from orders.models import Order
from .models import OrderRatingFeedback, PerformanceAlert, Rating


User = get_user_model()


class RatingSerializer(serializers.ModelSerializer):
    rated_user_full_name = serializers.CharField(source="rated_user.get_full_name", read_only=True)

    class Meta:
        model = Rating
        fields = (
            "id",
            "order",
            "customer",
            "rated_user",
            "rated_user_full_name",
            "target_role",
            "score",
            "feedback",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "customer",
            "target_role",
            "rated_user_full_name",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request else None
        order = attrs.get("order") or getattr(self.instance, "order", None)
        rated_user = attrs.get("rated_user") or getattr(self.instance, "rated_user", None)

        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Authentication is required.")
        if order is None:
            raise serializers.ValidationError({"order": "Order is required."})
        if rated_user is None:
            raise serializers.ValidationError({"rated_user": "Rated user is required."})
        if order.customer_id != user.id:
            raise serializers.ValidationError({"order": "You can only rate your own orders."})
        if order.status != Order.Status.COMPLETED:
            raise serializers.ValidationError({"order": "Order must be completed before rating."})

        worker_ids = set(order.workers.values_list("id", flat=True))
        if order.driver_id == rated_user.id:
            attrs["target_role"] = Rating.TargetRole.DRIVER
        elif rated_user.id in worker_ids:
            attrs["target_role"] = Rating.TargetRole.WORKER
        else:
            raise serializers.ValidationError(
                {"rated_user": "Rated user must be the assigned driver or worker for this order."}
            )

        duplicate = Rating.objects.filter(order=order, rated_user=rated_user)
        if self.instance:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError(
                {"rated_user": "This user has already been rated for this order."}
            )

        attrs["customer"] = user
        return attrs


class OrderRatingFeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderRatingFeedback
        fields = ("id", "order", "customer", "feedback", "created_at", "updated_at")
        read_only_fields = ("id", "order", "customer", "created_at", "updated_at")


class RatingTargetSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    full_name = serializers.CharField()
    role = serializers.ChoiceField(choices=Rating.TargetRole.choices)
    already_rated = serializers.BooleanField()
    rating_id = serializers.IntegerField(allow_null=True)


class BulkRatingItemSerializer(serializers.Serializer):
    rated_user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    score = serializers.IntegerField(min_value=1, max_value=5)


class BulkOrderRatingSerializer(serializers.Serializer):
    order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())
    feedback = serializers.CharField(required=False, allow_blank=True)
    ratings = BulkRatingItemSerializer(many=True)

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request else None
        order = attrs["order"]
        ratings = attrs.get("ratings") or []

        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Authentication is required.")
        if order.customer_id != user.id:
            raise serializers.ValidationError({"order": "You can only rate your own orders."})
        if order.status != Order.Status.COMPLETED:
            raise serializers.ValidationError({"order": "Order must be completed before rating."})
        if not ratings:
            raise serializers.ValidationError({"ratings": "At least one rating is required."})

        driver_id = order.driver_id
        worker_ids = set(order.workers.values_list("id", flat=True))
        rated_user_ids = []
        normalized_ratings = []

        for item in ratings:
            rated_user = item["rated_user"]
            if rated_user.id in rated_user_ids:
                raise serializers.ValidationError(
                    {"ratings": f"User {rated_user.id} is duplicated in ratings."}
                )
            rated_user_ids.append(rated_user.id)

            if rated_user.id == driver_id:
                target_role = Rating.TargetRole.DRIVER
            elif rated_user.id in worker_ids:
                target_role = Rating.TargetRole.WORKER
            else:
                raise serializers.ValidationError(
                    {
                        "ratings": (
                            f"User {rated_user.id} must be the assigned driver "
                            "or one of the assigned workers."
                        )
                    }
                )
            normalized_ratings.append(
                {
                    "rated_user": rated_user,
                    "score": item["score"],
                    "target_role": target_role,
                }
            )

        already_rated_ids = set(
            Rating.objects.filter(order=order, rated_user_id__in=rated_user_ids)
            .values_list("rated_user_id", flat=True)
        )
        if already_rated_ids:
            raise serializers.ValidationError(
                {"ratings": f"Users already rated for this order: {sorted(already_rated_ids)}"}
            )

        attrs["customer"] = user
        attrs["normalized_ratings"] = normalized_ratings
        return attrs

    def create(self, validated_data):
        order = validated_data["order"]
        customer = validated_data["customer"]
        feedback = validated_data.get("feedback", "")
        created_ratings = []

        OrderRatingFeedback.objects.update_or_create(
            order=order,
            defaults={
                "customer": customer,
                "feedback": feedback,
            },
        )
        for item in validated_data["normalized_ratings"]:
            created_ratings.append(
                Rating.objects.create(
                    order=order,
                    customer=customer,
                    rated_user=item["rated_user"],
                    target_role=item["target_role"],
                    score=item["score"],
                    feedback="",
                )
            )
        return {
            "order": order,
            "feedback": feedback,
            "ratings": created_ratings,
        }


class PerformanceAlertSerializer(serializers.ModelSerializer):
    user_full_name = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = PerformanceAlert
        fields = (
            "id",
            "user",
            "user_full_name",
            "target_role",
            "level",
            "reason",
            "average_rating",
            "low_rating_count",
            "status",
            "suspended_until",
            "created_at",
            "resolved_at",
        )
        read_only_fields = fields


class PerformanceAlertManualNotificationSerializer(serializers.Serializer):
    state = serializers.ChoiceField(
        choices=(
            ("notice", "Notice"),
            ("warning", "Warning"),
            ("suspension", "Suspension"),
            ("resolved", "Resolved"),
        )
    )
