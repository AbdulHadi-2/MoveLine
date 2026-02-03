from django.db import models


class Rating(models.Model):
    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="rating",
    )
    customer = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="given_ratings",
    )
    driver = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_ratings",
    )
    score = models.PositiveSmallIntegerField()
    feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable string
        return f"Rating(order={self.order_id}, score={self.score})"
