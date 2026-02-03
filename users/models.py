from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Office(models.Model):
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:  # pragma: no cover - human readable string
        return f"{self.name}"


class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        DRIVER = "driver", "Driver"
        WORKER = "worker", "Worker"
        ADMIN = "admin", "Admin"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER)
    phone = models.CharField(max_length=20, blank=True)
    is_verified = models.BooleanField(default=False)

    def __str__(self) -> str:  # pragma: no cover - human readable string
        return f"{self.username} ({self.get_role_display()})"

    @property
    def is_customer(self) -> bool:
        return self.role == self.Role.CUSTOMER

    @property
    def is_driver(self) -> bool:
        return self.role == self.Role.DRIVER

    @property
    def is_worker(self) -> bool:
        return self.role == self.Role.WORKER


class CustomerProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_profile",
    )
    payment_preferences = models.CharField(max_length=100, blank=True)

    def __str__(self) -> str:  # pragma: no cover - human readable string
        return f"CustomerProfile<{self.user_id}>"


class DriverProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="driver_profile",
    )
    office = models.ForeignKey(
        "users.Office",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drivers",
    )
    license_number = models.CharField(max_length=100, blank=True)
    rating = models.FloatField(default=0.0)
    availability = models.BooleanField(default=True)
    current_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    current_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_updated_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:  # pragma: no cover - human readable string
        return f"DriverProfile<{self.user_id}>"


class WorkerProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="worker_profile",
    )
    office = models.ForeignKey(
        "users.Office",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workers",
    )
    skills = models.TextField(blank=True)
    availability = models.BooleanField(default=True)
    current_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    current_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_updated_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:  # pragma: no cover - human readable string
        return f"WorkerProfile<{self.user_id}>"


class PasswordResetCode(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="password_reset_codes")
    code = models.CharField(max_length=4)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable string
        return f"PasswordResetCode<{self.user_id}>"


class ApplicantStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    REVIEW = "review", "Review"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"


class InterviewStatus(models.TextChoices):
    PENDING_SCHEDULING = "pending_scheduling", "Pending Scheduling"
    SCHEDULED = "scheduled", "Scheduled"
    COMPLETED = "completed", "Completed"


class AvailabilityType(models.TextChoices):
    FULL_TIME = "full_time", "Full Time"
    PART_TIME = "part_time", "Part Time"


class DriverApplication(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="driver_application",
    )
    city_area = models.CharField(max_length=120)
    availability = models.CharField(max_length=20, choices=AvailabilityType.choices)
    driver_license_number = models.CharField(max_length=100)
    driver_license_photo = models.ImageField(upload_to="applications/driver/licenses/")
    personal_photo = models.ImageField(upload_to="applications/driver/personal/")
    status = models.CharField(max_length=20, choices=ApplicantStatus.choices, default=ApplicantStatus.PENDING)
    interview_status = models.CharField(
        max_length=30,
        choices=InterviewStatus.choices,
        default=InterviewStatus.PENDING_SCHEDULING,
    )
    interview_datetime = models.DateTimeField(null=True, blank=True)
    interview_location = models.CharField(max_length=255, default="MoveLine Office")
    suggested_interview_window = models.CharField(max_length=255, blank=True)
    admin_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable string
        return f"DriverApplication(user={self.user_id}, status={self.status})"


class WorkerApplication(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="worker_application",
    )
    city_area = models.CharField(max_length=120)
    availability = models.CharField(max_length=20, choices=AvailabilityType.choices)
    skills = models.TextField(blank=True)
    can_lift_heavy = models.BooleanField(default=False)
    personal_photo = models.ImageField(upload_to="applications/worker/personal/")
    id_card_photo_front = models.ImageField(upload_to="applications/worker/id_cards/")
    id_card_photo_back = models.ImageField(upload_to="applications/worker/id_cards/")
    status = models.CharField(max_length=20, choices=ApplicantStatus.choices, default=ApplicantStatus.PENDING)
    interview_status = models.CharField(
        max_length=30,
        choices=InterviewStatus.choices,
        default=InterviewStatus.PENDING_SCHEDULING,
    )
    interview_datetime = models.DateTimeField(null=True, blank=True)
    interview_location = models.CharField(max_length=255, default="MoveLine Office")
    suggested_interview_window = models.CharField(max_length=255, blank=True)
    admin_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - human readable string
        return f"WorkerApplication(user={self.user_id}, status={self.status})"
