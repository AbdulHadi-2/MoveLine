import random

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.utils import timezone
from rest_framework import serializers

from .models import PasswordResetCode


User = get_user_model()
CODE_TTL_MINUTES = 10
RESET_TOKEN_SALT = "password-reset"


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if not User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("No user found with this email.")
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value

    def save(self):
        email = self.validated_data["email"]
        code = self.validated_data["code"]
        new_password = self.validated_data["new_password"]

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "Invalid email."})

        reset_code = (
            PasswordResetCode.objects.filter(user=user, code=code, used_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if reset_code is None:
            raise serializers.ValidationError({"code": "Invalid code."})
        if reset_code.expires_at < timezone.now():
            raise serializers.ValidationError({"code": "Code expired."})

        user.set_password(new_password)
        user.save(update_fields=("password",))
        reset_code.used_at = timezone.now()
        reset_code.save(update_fields=("used_at",))
        return user


class PasswordResetVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField()

    def validate(self, attrs):
        email = attrs["email"]
        code = attrs["code"]

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "Invalid email."})

        reset_code = (
            PasswordResetCode.objects.filter(user=user, code=code, used_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if reset_code is None:
            raise serializers.ValidationError({"code": "Invalid code."})
        if reset_code.expires_at < timezone.now():
            raise serializers.ValidationError({"code": "Code expired."})

        attrs["user"] = user
        attrs["reset_code"] = reset_code
        return attrs


class PasswordResetCompleteSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        token = attrs["token"]
        try:
            payload = signing.loads(
                token,
                salt=RESET_TOKEN_SALT,
                max_age=CODE_TTL_MINUTES * 60,
            )
        except signing.BadSignature:
            raise serializers.ValidationError({"token": "Invalid or expired token."})

        reset_code_id = payload.get("reset_code_id")
        if not reset_code_id:
            raise serializers.ValidationError({"token": "Invalid token payload."})

        reset_code = (
            PasswordResetCode.objects.filter(id=reset_code_id, used_at__isnull=True)
            .select_related("user")
            .first()
        )
        if reset_code is None:
            raise serializers.ValidationError({"token": "Invalid or expired token."})
        if reset_code.expires_at < timezone.now():
            raise serializers.ValidationError({"token": "Token expired."})

        attrs["reset_code"] = reset_code
        attrs["user"] = reset_code.user
        return attrs

    def save(self):
        user = self.validated_data["user"]
        new_password = self.validated_data["new_password"]
        reset_code = self.validated_data["reset_code"]

        user.set_password(new_password)
        user.save(update_fields=("password",))
        reset_code.used_at = timezone.now()
        reset_code.save(update_fields=("used_at",))
        return user


class PasswordChangeSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value

    def save(self):
        user = self.context["request"].user
        new_password = self.validated_data["new_password"]
        user.set_password(new_password)
        user.save(update_fields=("password",))
        return user


def build_reset_payload(user):
    code = f"{random.randint(0, 9999):04d}"
    expires_at = timezone.now() + timezone.timedelta(minutes=CODE_TTL_MINUTES)
    PasswordResetCode.objects.create(user=user, code=code, expires_at=expires_at)
    return {"code": code, "expires_at": expires_at}
