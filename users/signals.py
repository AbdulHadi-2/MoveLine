from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import CustomerProfile, DriverProfile, User, WorkerProfile


ROLE_MODEL_MAP = {
    User.Role.CUSTOMER: CustomerProfile,
    User.Role.DRIVER: DriverProfile,
    User.Role.WORKER: WorkerProfile,
}


@receiver(post_save, sender=User)
def ensure_role_profile(sender, instance: User, created: bool, **_: object) -> None:
    if not created:
        return

    profile_model = ROLE_MODEL_MAP.get(instance.role)
    if profile_model:
        profile_model.objects.get_or_create(user=instance)
