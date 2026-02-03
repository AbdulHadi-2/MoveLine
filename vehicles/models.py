from django.conf import settings
from django.db import models


class Vehicle(models.Model):
    class VehicleType(models.TextChoices):
        SMALL = "small", "Small"
        MEDIUM = "medium", "Medium"
        LARGE = "large", "Large"

    office = models.ForeignKey(
        "users.Office",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehicles",
    )
    name = models.CharField(max_length=100)
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices)
    max_payload_kg = models.PositiveIntegerField()
    plate_number = models.CharField(max_length=20, unique=True)
    is_available = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:  # pragma: no cover - human readable string
        return f"{self.name} ({self.plate_number})"
