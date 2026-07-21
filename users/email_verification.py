import random

from django.utils import timezone

from .models import EmailVerificationCode


CODE_TTL_MINUTES = 10


def build_email_verification_payload(user):
    code = f"{random.randint(0, 9999):04d}"
    expires_at = timezone.now() + timezone.timedelta(minutes=CODE_TTL_MINUTES)
    EmailVerificationCode.objects.create(user=user, code=code, expires_at=expires_at)
    return {"code": code, "expires_at": expires_at}
