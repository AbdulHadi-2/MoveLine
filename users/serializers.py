from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from rest_framework import serializers

from .models import (
    ApplicantStatus,
    AvailabilityType,
    CustomerProfile,
    DeviceToken,
    DriverApplication,
    DriverProfile,
    EmailVerificationCode,
    Office,
    UserNotification,
    WorkerApplication,
    WorkerProfile,
)

User = get_user_model()


def _is_unapproved_applicant(user):
    if user.role == User.Role.DRIVER:
        try:
            application = user.driver_application
        except ObjectDoesNotExist:
            return True
    elif user.role == User.Role.WORKER:
        try:
            application = user.worker_application
        except ObjectDoesNotExist:
            return True
    else:
        application = None
    return application is not None and application.status != ApplicantStatus.ACCEPTED


class CustomerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerProfile
        fields = ("id", "payment_preferences", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class ApplicationUserFieldsMixin(serializers.Serializer):
    user_id = serializers.IntegerField(read_only=True)
    full_name = serializers.SerializerMethodField()
    phone = serializers.CharField(source="user.phone", read_only=True)

    def get_full_name(self, obj):
        return obj.user.get_full_name().strip() or obj.user.username


class DriverProfileSerializer(ApplicationUserFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = DriverProfile
        fields = (
            "id",
            "user_id",
            "full_name",
            "phone",
            "office",
            "license_number",
            "rating",
            "availability",
            "suspended_until",
            "current_latitude",
            "current_longitude",
            "location_updated_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "user_id",
            "full_name",
            "phone",
            "rating",
            "suspended_until",
            "created_at",
            "updated_at",
        )


class WorkerProfileSerializer(ApplicationUserFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = WorkerProfile
        fields = (
            "id",
            "user_id",
            "full_name",
            "phone",
            "office",
            "skills",
            "rating",
            "availability",
            "suspended_until",
            "current_latitude",
            "current_longitude",
            "location_updated_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "user_id",
            "full_name",
            "phone",
            "rating",
            "suspended_until",
            "created_at",
            "updated_at",
        )


class OfficeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Office
        fields = ("id", "name", "address", "latitude", "longitude", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class DriverOfficeAssignSerializer(serializers.Serializer):
    office = serializers.PrimaryKeyRelatedField(queryset=Office.objects.all())


class DeviceTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceToken
        fields = ("id", "token", "device_type", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class TestPushNotificationSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=120, default="MoveLine Test")
    body = serializers.CharField(max_length=255, default="Firebase notification is working.")
    data = serializers.DictField(
        child=serializers.CharField(),
        required=False,
        default=dict,
    )


class UserNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserNotification
        fields = (
            "id",
            "title",
            "body",
            "data",
            "is_read",
            "read_at",
            "created_at",
        )
        read_only_fields = fields


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    customer_profile = CustomerProfileSerializer(read_only=True)
    driver_profile = DriverProfileSerializer(read_only=True)
    worker_profile = WorkerProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "phone",
            "role",
            "is_verified",
            "is_active",
            "password",
            "date_joined",
            "customer_profile",
            "driver_profile",
            "worker_profile",
        )
        read_only_fields = ("id", "is_verified", "is_active", "date_joined")

    def validate_password(self, value: str) -> str:
        if value:
            validate_password(value, user=self.instance or User())
        return value

    def validate_email(self, value: str) -> str:
        email = value.strip().lower()
        if not email:
            raise serializers.ValidationError("Email is required.")
        qs = User.objects.filter(email__iexact=email)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email

    def validate_role(self, value: str) -> str:
        if self.instance is None and value != User.Role.CUSTOMER:
            raise serializers.ValidationError(
                "Drivers and workers must register through applicant endpoints."
            )
        return value

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        user.is_active = False
        user.is_verified = False
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class DriverApplicationSerializer(ApplicationUserFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = DriverApplication
        fields = (
            "id",
            "user_id",
            "full_name",
            "phone",
            "city_area",
            "availability",
            "driver_license_number",
            "driver_license_photo",
            "personal_photo",
            "status",
            "interview_status",
            "interview_datetime",
            "interview_location",
            "suggested_interview_window",
            "admin_notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "user_id",
            "full_name",
            "phone",
            "status",
            "interview_status",
            "interview_datetime",
            "interview_location",
            "admin_notes",
            "created_at",
            "updated_at",
        )


class WorkerApplicationSerializer(ApplicationUserFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = WorkerApplication
        fields = (
            "id",
            "user_id",
            "full_name",
            "phone",
            "city_area",
            "availability",
            "skills",
            "can_lift_heavy",
            "personal_photo",
            "id_card_photo_front",
            "id_card_photo_back",
            "status",
            "interview_status",
            "interview_datetime",
            "interview_location",
            "suggested_interview_window",
            "admin_notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "user_id",
            "full_name",
            "phone",
            "status",
            "interview_status",
            "interview_datetime",
            "interview_location",
            "admin_notes",
            "created_at",
            "updated_at",
        )


class BaseApplicantRegistrationSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20)
    email = serializers.EmailField(required=False, allow_blank=True)
    city_area = serializers.CharField(max_length=120)
    availability = serializers.ChoiceField(choices=AvailabilityType.choices)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    def validate_email(self, value: str) -> str:
        email = value.strip().lower()
        if not email:
            return ""
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email

    def _build_username(self, email: str, phone: str) -> str:
        base = email or phone
        if not base:
            raise serializers.ValidationError("Email or phone is required.")
        candidate = base
        suffix = 1
        while User.objects.filter(username__iexact=candidate).exists():
            suffix += 1
            candidate = f"{base}_{suffix}"
        return candidate

    def _create_user(self, role: str, validated_data):
        full_name = validated_data.pop("full_name")
        first_name, *rest = full_name.strip().split()
        last_name = " ".join(rest) if rest else ""
        email = validated_data.pop("email", "").strip().lower()
        phone = validated_data.pop("phone")
        password = validated_data.pop("password", "")

        user = User(
            username=self._build_username(email, phone),
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            role=role,
            is_active=False,
        )
        if password:
            validate_password(password, user=user)
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user


class DriverApplicantRegistrationSerializer(BaseApplicantRegistrationSerializer):
    driver_license_number = serializers.CharField(max_length=100)
    driver_license_photo = serializers.ImageField()
    personal_photo = serializers.ImageField()

    def create(self, validated_data):
        user = self._create_user(User.Role.DRIVER, validated_data)
        application_data = {
            "city_area": validated_data.get("city_area"),
            "availability": validated_data.get("availability"),
            "driver_license_number": validated_data.get("driver_license_number"),
            "driver_license_photo": validated_data.get("driver_license_photo"),
            "personal_photo": validated_data.get("personal_photo"),
        }
        return DriverApplication.objects.create(user=user, **application_data)


class WorkerApplicantRegistrationSerializer(BaseApplicantRegistrationSerializer):
    skills = serializers.CharField(required=False, allow_blank=True)
    can_lift_heavy = serializers.BooleanField(required=False)
    personal_photo = serializers.ImageField()
    id_card_photo_front = serializers.ImageField()
    id_card_photo_back = serializers.ImageField()

    def create(self, validated_data):
        user = self._create_user(User.Role.WORKER, validated_data)
        application_data = {
            "city_area": validated_data.get("city_area"),
            "availability": validated_data.get("availability"),
            "skills": validated_data.get("skills", ""),
            "can_lift_heavy": validated_data.get("can_lift_heavy", False),
            "personal_photo": validated_data.get("personal_photo"),
            "id_card_photo_front": validated_data.get("id_card_photo_front"),
            "id_card_photo_back": validated_data.get("id_card_photo_back"),
        }
        return WorkerApplication.objects.create(user=user, **application_data)


class InterviewScheduleSerializer(serializers.Serializer):
    interview_datetime = serializers.DateTimeField()
    interview_location = serializers.CharField(max_length=255, required=False, allow_blank=True)


class EmailVerificationVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField()

    def validate(self, attrs):
        email = attrs["email"].strip().lower()
        code = attrs["code"].strip()

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "Invalid email."})
        if _is_unapproved_applicant(user):
            raise serializers.ValidationError(
                {"email": "Applicant accounts are activated after admin approval."}
            )

        verification_code = (
            EmailVerificationCode.objects.filter(user=user, code=code, used_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if verification_code is None:
            raise serializers.ValidationError({"code": "Invalid code."})
        if verification_code.expires_at < timezone.now():
            raise serializers.ValidationError({"code": "Code expired."})

        attrs["user"] = user
        attrs["verification_code"] = verification_code
        return attrs

    def save(self):
        user = self.validated_data["user"]
        verification_code = self.validated_data["verification_code"]
        user.is_active = True
        user.is_verified = True
        user.save(update_fields=("is_active", "is_verified"))
        verification_code.used_at = timezone.now()
        verification_code.save(update_fields=("used_at",))
        return user


class EmailVerificationResendSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        email = value.strip().lower()
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid email.")
        if _is_unapproved_applicant(user):
            raise serializers.ValidationError("Applicant accounts are activated after admin approval.")
        if user.is_verified:
            raise serializers.ValidationError("Email is already verified.")
        self.user = user
        return email
