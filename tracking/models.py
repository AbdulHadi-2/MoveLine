from django.db import models


class Tracking(models.Model):
    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="tracking",
        primary_key=True,
    )
    driver = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tracking_sessions",
    )
    current_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    current_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    heading = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    speed_kmh = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    route_geometry = models.JSONField(default=dict, blank=True)
    last_ping_at = models.DateTimeField(null=True, blank=True)
    stopped_since = models.DateTimeField(null=True, blank=True)
    last_movement_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable string
        return f"Tracking(order={self.order_id})"


class TrackingAlert(models.Model):
    class AlertType(models.TextChoices):
        UNEXPECTED_STOP = "unexpected_stop", "Unexpected Stop"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        RESOLVED = "resolved", "Resolved"

    class DriverReason(models.TextChoices):
        TRAFFIC = "traffic", "Traffic"
        VEHICLE_ISSUE = "vehicle_issue", "Vehicle Issue"
        REST = "rest", "Rest"
        EXTRA_LOADING = "extra_loading", "Extra Loading"
        OTHER = "other", "Other"

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="tracking_alerts",
    )
    tracking = models.ForeignKey(
        "tracking.Tracking",
        on_delete=models.CASCADE,
        related_name="alerts",
    )
    driver = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tracking_alerts",
    )
    alert_type = models.CharField(
        max_length=30,
        choices=AlertType.choices,
        default=AlertType.UNEXPECTED_STOP,
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    driver_reason = models.CharField(max_length=30, choices=DriverReason.choices, blank=True)
    driver_note = models.TextField(blank=True)
    driver_notified_at = models.DateTimeField(null=True, blank=True)
    driver_responded_at = models.DateTimeField(null=True, blank=True)
    admin_notified_at = models.DateTimeField(null=True, blank=True)
    customer_notified_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable string
        return f"TrackingAlert(order={self.order_id}, type={self.alert_type}, status={self.status})"
