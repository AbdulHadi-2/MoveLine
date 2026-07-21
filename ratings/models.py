from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Rating(models.Model):
    class TargetRole(models.TextChoices):
        DRIVER = "driver", "Driver"
        WORKER = "worker", "Worker"

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="ratings",
    )
    customer = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="given_ratings",
    )
    rated_user = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_ratings",
    )
    target_role = models.CharField(max_length=20, choices=TargetRole.choices)
    score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("order", "rated_user"),
                name="unique_rating_per_order_target",
            )
        ]

    def __str__(self) -> str:  # pragma: no cover - human readable string
        return f"Rating(order={self.order_id}, target={self.rated_user_id}, score={self.score})"


class OrderRatingFeedback(models.Model):
    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="rating_feedback",
    )
    customer = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_rating_feedbacks",
    )
    feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable string
        return f"OrderRatingFeedback(order={self.order_id})"


class PerformanceAlert(models.Model):
    class Level(models.TextChoices):
        NOTICE = "notice", "Notice"
        WARNING = "warning", "Warning"
        SUSPENSION = "suspension", "Suspension"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="performance_alerts",
    )
    target_role = models.CharField(max_length=20, choices=Rating.TargetRole.choices)
    level = models.CharField(max_length=20, choices=Level.choices)
    reason = models.CharField(max_length=255)
    average_rating = models.FloatField(default=0.0)
    low_rating_count = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    suspended_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable string
        return f"PerformanceAlert(user={self.user_id}, level={self.level})"
