from django.db import models


class OrderItem(models.Model):
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="items",
    )
    label = models.CharField(max_length=100)
    quantity = models.PositiveIntegerField(default=1)
    is_fragile = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable string
        return f"OrderItem(order={self.order_id}, label={self.label})"
