from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Tracking, TrackingAlert
from .serializers import (
    TrackingAlertDriverResponseSerializer,
    TrackingAlertManualNotificationSerializer,
    TrackingAlertSerializer,
    TrackingSerializer,
)
from users.notifications import send_push_to_user


User = get_user_model()


class TrackingViewSet(viewsets.ModelViewSet):
    queryset = Tracking.objects.select_related("order", "driver").all()
    serializer_class = TrackingSerializer


class TrackingAlertViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        TrackingAlert.objects.select_related("order", "tracking", "driver")
        .prefetch_related("order__workers")
        .all()
    )
    serializer_class = TrackingAlertSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = self.queryset
        if user.is_staff or user.is_superuser:
            base_qs = qs
        else:
            base_qs = (
                qs.filter(
                    models.Q(order__customer=user)
                    | models.Q(order__driver=user)
                    | models.Q(order__workers=user)
                )
                .distinct()
            )

        status_param = self.request.query_params.get("status")
        if status_param:
            base_qs = base_qs.filter(status=status_param)

        alert_type = self.request.query_params.get("alert_type")
        if alert_type:
            base_qs = base_qs.filter(alert_type=alert_type)

        order_id = self.request.query_params.get("order")
        if order_id:
            base_qs = base_qs.filter(order_id=order_id)

        admin_attention = self.request.query_params.get("admin_attention")
        if admin_attention in {"1", "true", "True"}:
            base_qs = base_qs.filter(
                admin_notified_at__isnull=False,
                status__in=[TrackingAlert.Status.OPEN, TrackingAlert.Status.ACKNOWLEDGED],
            )

        return base_qs

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        qs = self.get_queryset()
        data = {
            "open": qs.filter(status=TrackingAlert.Status.OPEN).count(),
            "acknowledged": qs.filter(status=TrackingAlert.Status.ACKNOWLEDGED).count(),
            "resolved": qs.filter(status=TrackingAlert.Status.RESOLVED).count(),
            "admin_attention": qs.filter(
                admin_notified_at__isnull=False,
                status__in=[TrackingAlert.Status.OPEN, TrackingAlert.Status.ACKNOWLEDGED],
            ).count(),
        }
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="driver-response")
    def driver_response(self, request, pk=None):
        alert = self.get_object()
        if alert.driver_id != request.user.id and not request.user.is_staff:
            return Response(
                {"detail": "Only the assigned driver can respond to this alert."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = TrackingAlertDriverResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        alert.driver_reason = serializer.validated_data["reason"]
        alert.driver_note = serializer.validated_data.get("note", "")
        alert.driver_responded_at = timezone.now()
        alert.status = TrackingAlert.Status.ACKNOWLEDGED
        alert.save(
            update_fields=(
                "driver_reason",
                "driver_note",
                "driver_responded_at",
                "status",
            )
        )
        return Response(TrackingAlertSerializer(alert).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="resolve")
    def resolve(self, request, pk=None):
        alert = self.get_object()
        if not (request.user.is_staff or request.user.is_superuser):
            return Response(
                {"detail": "Only admins can resolve tracking alerts."},
                status=status.HTTP_403_FORBIDDEN,
            )
        alert.status = TrackingAlert.Status.RESOLVED
        alert.resolved_at = timezone.now()
        alert.save(update_fields=("status", "resolved_at"))
        if alert.driver_id:
            send_push_to_user(
                alert.driver,
                title="Tracking Alert Resolved",
                body=f"Alert for Order #{alert.order_id} has been resolved.",
                data={
                    "type": "tracking_alert_resolved",
                    "alert_id": alert.id,
                    "order_id": alert.order_id,
                },
            )
        return Response(TrackingAlertSerializer(alert).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="send-notification")
    def send_notification(self, request, pk=None):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response(
                {"detail": "Only admins can send manual tracking alert notifications."},
                status=status.HTTP_403_FORBIDDEN,
            )

        alert = self.get_object()
        serializer = TrackingAlertManualNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        state = serializer.validated_data["state"]

        recipients = self._tracking_alert_recipients(alert, state)
        title, body = self._tracking_alert_message(alert, state)
        sent_count = 0
        for recipient in recipients:
            sent_count += send_push_to_user(
                recipient,
                title=title,
                body=body,
                data={
                    "type": self._tracking_alert_notification_type(state),
                    "state": state,
                    "alert_id": alert.id,
                    "order_id": alert.order_id,
                },
            )

        return Response(
            {
                "detail": "Tracking alert notification requested.",
                "state": state,
                "recipient_count": len(recipients),
                "sent_count": sent_count,
            },
            status=status.HTTP_200_OK,
        )

    def _tracking_alert_recipients(self, alert, state):
        if state == "open":
            return [alert.driver] if alert.driver_id else []
        if state in {"acknowledged", "admin_attention"}:
            return list(User.objects.filter(models.Q(is_staff=True) | models.Q(is_superuser=True)).distinct())
        if state == "customer_delay":
            return [alert.order.customer] if alert.order and alert.order.customer_id else []
        if state == "resolved":
            recipients = []
            if alert.driver_id:
                recipients.append(alert.driver)
            if alert.order and alert.order.customer_id:
                recipients.append(alert.order.customer)
            return recipients
        return []

    def _tracking_alert_message(self, alert, state):
        messages = {
            "open": (
                "Unexpected Stop Detected",
                f"Order #{alert.order_id}: an unexpected stop was detected. Please respond with the reason.",
            ),
            "acknowledged": (
                "Driver Responded To Tracking Alert",
                f"Order #{alert.order_id}: the driver responded to the tracking alert.",
            ),
            "admin_attention": (
                "Tracking Alert Needs Attention",
                f"Order #{alert.order_id}: tracking alert requires admin review.",
            ),
            "customer_delay": (
                "Order Delay Update",
                f"Order #{alert.order_id}: there may be a delay. The MoveLine team is following up.",
            ),
            "resolved": (
                "Tracking Alert Resolved",
                f"Order #{alert.order_id}: the tracking alert has been resolved.",
            ),
        }
        return messages[state]

    def _tracking_alert_notification_type(self, state):
        types = {
            "open": "unexpected_stop_driver_check",
            "customer_delay": "order_delay_customer_notice",
            "resolved": "tracking_alert_resolved",
            "acknowledged": "tracking_alert",
            "admin_attention": "tracking_alert",
        }
        return types[state]
