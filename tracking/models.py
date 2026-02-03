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
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable string
        return f"Tracking(order={self.order_id})"
