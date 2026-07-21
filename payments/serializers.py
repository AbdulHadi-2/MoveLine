from rest_framework import serializers

from .models import Payment, PendingOrderCheckout
from orders.models import Order


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            "id",
            "order",
            "amount",
            "currency",
            "method",
            "status",
            "transaction_reference",
            "paid_amount",
            "paid_at",
            "metadata",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")


class PendingOrderCheckoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = PendingOrderCheckout
        fields = (
            "id",
            "customer",
            "order",
            "amount",
            "currency",
            "reserved_driver",
            "reserved_vehicle",
            "reserved_workers",
            "stripe_session_id",
            "status",
            "expires_at",
            "paid_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class PaymeraInitiateSerializer(serializers.Serializer):
    order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())
    success_url = serializers.URLField()
    cancel_url = serializers.URLField()

    def validate_order(self, order):
        request = self.context.get("request")
        if request and not request.user.is_staff and order.customer_id != request.user.id:
            raise serializers.ValidationError("You can only pay for your own orders.")
        if not order.estimated_price and not order.final_price:
            raise serializers.ValidationError("Order price is not calculated yet.")
        return order


class PaymeraVerifySerializer(serializers.Serializer):
    payment = serializers.PrimaryKeyRelatedField(queryset=Payment.objects.all(), required=False)
    transaction_reference = serializers.CharField(required=False)

    def validate(self, attrs):
        if not attrs.get("payment") and not attrs.get("transaction_reference"):
            raise serializers.ValidationError("payment or transaction_reference is required.")
        return attrs


class StripeCheckoutSessionSerializer(serializers.Serializer):
    order = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())
    success_url = serializers.URLField()
    cancel_url = serializers.URLField()

    def validate_order(self, order):
        request = self.context.get("request")
        if request and not request.user.is_staff and order.customer_id != request.user.id:
            raise serializers.ValidationError("You can only pay for your own orders.")
        amount = order.final_price or order.estimated_price
        if not amount:
            raise serializers.ValidationError("Order price is not calculated yet.")
        if amount <= 0:
            raise serializers.ValidationError("Order price must be greater than zero.")
        return order


class StripeVerifySessionSerializer(serializers.Serializer):
    session_id = serializers.CharField()


class StripeOrderCheckoutUrlSerializer(serializers.Serializer):
    success_url = serializers.URLField()
    cancel_url = serializers.URLField()


class StripeConfirmOrderCheckoutSerializer(serializers.Serializer):
    session_id = serializers.CharField()
