from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from users.models import ApplicantStatus


class ActiveUserTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = "email"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[self.username_field] = serializers.EmailField()
        self.fields["password"] = serializers.CharField(write_only=True)
        self.fields.pop("username", None)

    def _pending_message(self, user):
        User = get_user_model()
        if user.role == User.Role.DRIVER:
            app = getattr(user, "driver_application", None)
        elif user.role == User.Role.WORKER:
            app = getattr(user, "worker_application", None)
        else:
            app = None
        if app and app.status in {ApplicantStatus.PENDING, ApplicantStatus.REVIEW}:
            return "Your account is pending approval. Please wait for the interview and activation."
        return None

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")
        if not email or not password:
            raise serializers.ValidationError("Email and password are required.")

        User = get_user_model()
        try:
            self.user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid email or password.")

        if not self.user.check_password(password):
            raise serializers.ValidationError("Invalid email or password.")

        if not self.user.is_active:
            pending_message = self._pending_message(self.user)
            if pending_message:
                raise PermissionDenied(pending_message)
            raise PermissionDenied("Account is inactive. Please wait for approval.")

        refresh = self.get_token(self.user)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }


class ActiveUserTokenObtainPairView(TokenObtainPairView):
    serializer_class = ActiveUserTokenObtainPairSerializer
