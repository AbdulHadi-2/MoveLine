from django.conf import settings
from django.db import models


class Order(models.Model):
    class ServiceType(models.TextChoices):
        MOVING = "moving", "Moving"
        CLEANING = "cleaning", "Cleaning"
        SCRAP_REMOVAL = "scrap", "Scrap Removal"

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In Progress"
        DELIVERED = "delivered", "Delivered"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class VehicleSize(models.TextChoices):
        SMALL = "small", "Small"
        MEDIUM = "medium", "Medium"
        LARGE = "large", "Large"

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_orders",
    )
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="driver_orders",
    )
    vehicle = models.ForeignKey(
        "vehicles.Vehicle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    workers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="OrderWorker",
        related_name="worker_orders",
        blank=True,
    )
    required_workers = models.PositiveIntegerField(default=0)
    required_vehicle_type = models.CharField(
        max_length=20,
        choices=VehicleSize.choices,
        null=True,
        blank=True,
    )
    assembly = models.BooleanField(default=False)
    disassembly = models.BooleanField(default=False)
    service_type = models.CharField(max_length=20, choices=ServiceType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)
    scheduled_start = models.DateTimeField(null=True, blank=True)
    scheduled_end = models.DateTimeField(null=True, blank=True)
    pickup_address = models.CharField(max_length=255)
    pickup_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    pickup_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_address = models.CharField(max_length=255, blank=True)
    dropoff_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    special_instructions = models.TextField(blank=True)
    estimated_distance_km = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    estimated_duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    estimated_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    final_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_priority = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable string
        return f"Order #{self.id} - {self.get_service_type_display()}"

    @property
    def is_active(self) -> bool:
        return self.status not in {self.Status.COMPLETED, self.Status.CANCELLED}


class OrderWorker(models.Model):
    class WorkerStatus(models.TextChoices):
        ASSIGNED = "assigned", "Assigned"
        ACCEPTED = "accepted", "Accepted"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        DECLINED = "declined", "Declined"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="order_workers")
    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    status = models.CharField(max_length=20, choices=WorkerStatus.choices, default=WorkerStatus.ASSIGNED)
    role_description = models.CharField(max_length=100, blank=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("order", "worker")

    def __str__(self) -> str:  # pragma: no cover - human readable string
        return f"OrderWorker(order={self.order_id}, worker={self.worker_id})"
##

class OrderPhoto(models.Model):
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="order_photos/")
    analysis_json = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
