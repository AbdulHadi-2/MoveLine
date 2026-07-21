from django.contrib.auth import get_user_model
from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.db import models
from django.utils import timezone
from rest_framework import permissions, response, status, viewsets
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView

from .models import (
    ApplicantStatus,
    DriverApplication,
    InterviewStatus,
    WorkerApplication,
    CustomerProfile,
    DeviceToken,
    DriverProfile,
    Office,
    UserNotification,
    WorkerProfile,
)
from .serializers import (
    CustomerProfileSerializer,
    DeviceTokenSerializer,
    DriverOfficeAssignSerializer,
    DriverApplicantRegistrationSerializer,
    DriverApplicationSerializer,
    DriverProfileSerializer,
    EmailVerificationResendSerializer,
    EmailVerificationVerifySerializer,
    InterviewScheduleSerializer,
    OfficeSerializer,
    TestPushNotificationSerializer,
    UserNotificationSerializer,
    UserSerializer,
    WorkerApplicantRegistrationSerializer,
    WorkerApplicationSerializer,
    WorkerProfileSerializer,
)
from .email_verification import build_email_verification_payload
from .notifications import send_push_to_user
from .password_reset import (
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PasswordResetCompleteSerializer,
    PasswordResetVerifySerializer,
    PasswordChangeSerializer,
    build_reset_payload,
)

User = get_user_model()


def send_email_verification_email(user, code):
    subject = "Verify your MoveLine email"
    message = (
        "Hello,"
        "Welcome to MoveLine."
        "Use this 4-digit code to verify your email:"
        f"{code}"
        "This code expires in 10 minutes."
        "MoveLine Support"
    )
    html_message = f"""
<div style="font-family: Arial, sans-serif; background:#f5f7fb; padding: 24px;">
  <div style="max-width: 520px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
    <h2 style="margin: 0 0 8px; color:#111827;">Verify your MoveLine email</h2>
    <p style="margin: 0 0 16px; color:#374151;">Welcome to MoveLine. Use this code to activate your account.</p>
    <div style="background:#f3f4f6; padding: 16px; border-radius: 10px; text-align:center; margin-bottom: 16px;">
      <div style="font-size: 12px; letter-spacing: 2px; color:#6b7280; text-transform: uppercase;">Verification Code</div>
      <div style="font-size: 28px; font-weight: 700; color:#111827; letter-spacing: 6px;">{code}</div>
    </div>
    <p style="margin: 0 0 8px; color:#374151;">This code expires in <strong>10 minutes</strong>.</p>
    <p style="margin: 0; color:#6b7280;">If you did not create a MoveLine account, you can ignore this email.</p>
    <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;" />
    <p style="margin: 0; color:#9ca3af; font-size: 12px;">MoveLine Support</p>
  </div>
</div>
"""
    email = EmailMultiAlternatives(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])
    email.attach_alternative(html_message, "text/html")
    email.send()


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.select_related(
        "customer_profile", "driver_profile", "worker_profile"
    ).all()
    serializer_class = UserSerializer

    def get_permissions(self):
        if self.action == "create" or self.request.method == "POST":
            return [permissions.AllowAny()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        payload = build_email_verification_payload(user)
        send_email_verification_email(user, payload["code"])
        return response.Response(
            {
                "detail": "Account created. Verification code sent to email.",
                "verification_status": "pending",
                "user": self.get_serializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class EmailVerificationVerifyView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = EmailVerificationVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return response.Response(
            {
                "detail": "Email verified. Account activated.",
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class EmailVerificationResendView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = EmailVerificationResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.user
        payload = build_email_verification_payload(user)
        send_email_verification_email(user, payload["code"])
        return response.Response(
            {"detail": "Verification code sent."},
            status=status.HTTP_200_OK,
        )


class CustomerProfileViewSet(viewsets.ModelViewSet):
    queryset = CustomerProfile.objects.select_related("user").all()
    serializer_class = CustomerProfileSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return self.queryset
        if not user.is_active:
            return self.queryset.none()
        return self.queryset.filter(user=user)


class DriverProfileViewSet(viewsets.ModelViewSet):
    queryset = DriverProfile.objects.select_related("user").all()
    serializer_class = DriverProfileSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return self.queryset
        if not user.is_active:
            return self.queryset.none()
        return self.queryset.filter(user=user)

    @action(detail=True, methods=["post"], url_path="assign-office")
    def assign_office(self, request, pk=None):
        if not (request.user.is_staff or request.user.is_superuser):
            return response.Response(
                {"detail": "Only admins can assign drivers to offices."},
                status=status.HTTP_403_FORBIDDEN,
            )

        driver_profile = (
            DriverProfile.objects.select_related("user")
            .filter(models.Q(pk=pk) | models.Q(user_id=pk))
            .first()
        )
        if driver_profile is None:
            return response.Response(
                {"detail": "Driver profile not found for this profile id or user id."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = DriverOfficeAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        driver_profile.office = serializer.validated_data["office"]
        driver_profile.save(update_fields=("office", "updated_at"))
        return response.Response(
            {
                "detail": "Driver assigned to office.",
                "driver": DriverProfileSerializer(driver_profile).data,
            },
            status=status.HTTP_200_OK,
        )


class WorkerProfileViewSet(viewsets.ModelViewSet):
    queryset = WorkerProfile.objects.select_related("user").all()
    serializer_class = WorkerProfileSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return self.queryset
        if not user.is_active:
            return self.queryset.none()
        return self.queryset.filter(user=user)

    @action(detail=True, methods=["post"], url_path="assign-office")
    def assign_office(self, request, pk=None):
        if not (request.user.is_staff or request.user.is_superuser):
            return response.Response(
                {"detail": "Only admins can assign workers to offices."},
                status=status.HTTP_403_FORBIDDEN,
            )

        worker_profile = (
            WorkerProfile.objects.select_related("user")
            .filter(models.Q(pk=pk) | models.Q(user_id=pk))
            .first()
        )
        if worker_profile is None:
            return response.Response(
                {"detail": "Worker profile not found for this profile id or user id."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = DriverOfficeAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        worker_profile.office = serializer.validated_data["office"]
        worker_profile.save(update_fields=("office", "updated_at"))
        return response.Response(
            {
                "detail": "Worker assigned to office.",
                "worker": WorkerProfileSerializer(worker_profile).data,
            },
            status=status.HTTP_200_OK,
        )


class OfficeViewSet(viewsets.ModelViewSet):
    queryset = Office.objects.all()
    serializer_class = OfficeSerializer


class DeviceTokenRegisterView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = DeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data["token"]
        device_type = serializer.validated_data.get("device_type")
        obj, created = request.user.device_tokens.update_or_create(
            token=token,
            defaults={"device_type": device_type or "android"},
        )
        data = DeviceTokenSerializer(obj).data
        return response.Response(
            {"detail": "Device token saved.", "device": data},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class TestPushNotificationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = TestPushNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sent_count = send_push_to_user(
            request.user,
            title=serializer.validated_data["title"],
            body=serializer.validated_data["body"],
            data=serializer.validated_data.get("data", {}),
        )
        device_count = DeviceToken.objects.filter(user=request.user).count()
        return response.Response(
            {
                "detail": "Push notification requested.",
                "user_id": request.user.id,
                "registered_device_count": device_count,
                "sent_count": sent_count,
            },
            status=status.HTTP_200_OK,
        )


class UserNotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = UserNotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = UserNotification.objects.filter(user=self.request.user)
        is_read = self.request.query_params.get("is_read")
        if is_read in {"true", "True", "1"}:
            queryset = queryset.filter(is_read=True)
        elif is_read in {"false", "False", "0"}:
            queryset = queryset.filter(is_read=False)
        return queryset

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=("is_read", "read_at"))
        return response.Response(
            UserNotificationSerializer(notification).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        now = timezone.now()
        updated_count = self.get_queryset().filter(is_read=False).update(
            is_read=True,
            read_at=now,
        )
        return response.Response(
            {"detail": "Notifications marked as read.", "updated_count": updated_count},
            status=status.HTTP_200_OK,
        )


class ApplicantRegisterBaseView(APIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = None
    response_serializer_class = None

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = serializer.save()
        data = self.response_serializer_class(application).data
        return response.Response(
            {
                "detail": "Application received, account pending activation after interview.",
                "application": data,
            },
            status=status.HTTP_201_CREATED,
        )


class DriverApplicantRegisterView(ApplicantRegisterBaseView):
    serializer_class = DriverApplicantRegistrationSerializer
    response_serializer_class = DriverApplicationSerializer


class WorkerApplicantRegisterView(ApplicantRegisterBaseView):
    serializer_class = WorkerApplicantRegistrationSerializer
    response_serializer_class = WorkerApplicationSerializer


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.get(email__iexact=serializer.validated_data["email"])
        payload = build_reset_payload(user)
        subject = "MoveLine password reset"
        message = (
            "Hello,"
            "We received a request to reset your MoveLine password."
            "Your 4-digit reset code:"
            f"{payload['code']}"
            "This code expires in 10 minutes."
            "If you did not request this, you can ignore this message."
            "MoveLine Support"
        )
        html_message = f"""
<div style="font-family: Arial, sans-serif; background:#f5f7fb; padding: 24px;">
  <div style="max-width: 520px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
    <h2 style="margin: 0 0 8px; color:#111827;">Reset your MoveLine password</h2>
    <p style="margin: 0 0 16px; color:#374151;">We received a request to reset your password.</p>
    <div style="background:#f3f4f6; padding: 16px; border-radius: 10px; text-align:center; margin-bottom: 16px;">
      <div style="font-size: 12px; letter-spacing: 2px; color:#6b7280; text-transform: uppercase;">Reset Code</div>
      <div style="font-size: 28px; font-weight: 700; color:#111827; letter-spacing: 6px;">{payload['code']}</div>
    </div>
    <p style="margin: 0 0 8px; color:#374151;">This code expires in <strong>10 minutes</strong>.</p>
    <p style="margin: 0; color:#6b7280;">If you did not request this, you can safely ignore this email.</p>
    <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;" />
    <p style="margin: 0; color:#9ca3af; font-size: 12px;">MoveLine Support</p>
  </div>
</div>
"""
        email = EmailMultiAlternatives(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])
        email.attach_alternative(html_message, "text/html")
        email.send()
        return response.Response({"detail": "Password reset email sent."}, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response({"detail": "Password updated."}, status=status.HTTP_200_OK)


class PasswordResetVerifyView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reset_code = serializer.validated_data["reset_code"]
        token = signing.dumps(
            {"reset_code_id": reset_code.id},
            salt="password-reset",
        )
        return response.Response(
            {
                "detail": "Code verified.",
                "reset_token": token,
                "expires_in_seconds": 600,
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetCompleteView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = PasswordResetCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response({"detail": "Password updated."}, status=status.HTTP_200_OK)


class PasswordChangeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response({"detail": "Password updated."}, status=status.HTTP_200_OK)


class AdminScheduleInterviewView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def patch(self, request, app_type: str, pk: int):
        serializer = InterviewScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if app_type == "drivers":
            application = DriverApplication.objects.filter(pk=pk).first()
        elif app_type == "workers":
            application = WorkerApplication.objects.filter(pk=pk).first()
        else:
            return response.Response(
                {"detail": "Invalid applicant type."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if application is None:
            return response.Response(
                {"detail": "Application not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        user = application.user
        recipient_email = user.email.strip()
        if not recipient_email:
            return response.Response(
                {"detail": "Applicant email is missing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        application.interview_datetime = serializer.validated_data["interview_datetime"]
        interview_location = serializer.validated_data.get("interview_location")
        if interview_location:
            application.interview_location = interview_location
        application.interview_status = InterviewStatus.SCHEDULED
        if application.status == ApplicantStatus.PENDING:
            application.status = ApplicantStatus.REVIEW
        application.save(
            update_fields=(
                "interview_datetime",
                "interview_location",
                "interview_status",
                "status",
            )
        )

        subject = "MoveLine interview scheduled"
        full_name = user.get_full_name().strip() or user.username
        message = (
            "Hello,"
            "Your MoveLine interview has been scheduled."
            f"Date & time: {application.interview_datetime}"
            f"Location: {application.interview_location}"
            "If you need to reschedule, please contact support."
            "MoveLine Support"
        )
        html_message = f"""
<div style="font-family: Arial, sans-serif; background:#f5f7fb; padding: 24px;">
  <div style="max-width: 520px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
    <h2 style="margin: 0 0 8px; color:#111827;">Interview Scheduled</h2>
    <p style="margin: 0 0 16px; color:#374151;">Hello {full_name},</p>
    <p style="margin: 0 0 16px; color:#374151;">Your MoveLine interview has been scheduled.</p>
    <div style="background:#f3f4f6; padding: 16px; border-radius: 10px; margin-bottom: 16px;">
      <div style="font-size: 12px; letter-spacing: 1px; color:#6b7280; text-transform: uppercase;">Interview Details</div>
      <div style="font-size: 16px; font-weight: 600; color:#111827; margin-top: 6px;">{application.interview_datetime}</div>
      <div style="font-size: 14px; color:#374151; margin-top: 6px;">{application.interview_location}</div>
    </div>
    <p style="margin: 0; color:#6b7280;">If you need to reschedule, please contact support.</p>
    <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;" />
    <p style="margin: 0; color:#9ca3af; font-size: 12px;">MoveLine Support</p>
  </div>
</div>
"""
        email = EmailMultiAlternatives(subject, message, settings.DEFAULT_FROM_EMAIL, [recipient_email])
        email.attach_alternative(html_message, "text/html")
        email.send()

        return response.Response(
            {"detail": "Interview scheduled."},
            status=status.HTTP_200_OK,
        )


class AdminApproveApplicantView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, app_type: str, pk: int):
        application = None
        if app_type == "drivers":
            application = DriverApplication.objects.select_related("user").filter(pk=pk).first()
        elif app_type == "workers":
            application = WorkerApplication.objects.select_related("user").filter(pk=pk).first()
        if application is None:
            return response.Response(
                {"detail": "Application not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if application.status not in {ApplicantStatus.PENDING, ApplicantStatus.REVIEW}:
            return response.Response(
                {"detail": "Application is not in a pending state."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        application.status = ApplicantStatus.ACCEPTED
        application.interview_status = InterviewStatus.COMPLETED
        application.save(update_fields=("status", "interview_status"))
        application.user.is_active = True
        application.user.is_verified = True
        application.user.save(update_fields=("is_active", "is_verified"))
        user = application.user
        recipient_email = user.email.strip()
        if recipient_email:
            subject = "Welcome to MoveLine"
            full_name = user.get_full_name().strip() or user.username
            message = (
                "Hello,"
                "Your MoveLine application has been approved."
                "You can now log in and start working."
                "MoveLine Support"
            )
            html_message = f"""
<div style="font-family: Arial, sans-serif; background:#f5f7fb; padding: 24px;">
  <div style="max-width: 520px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
    <h2 style="margin: 0 0 8px; color:#111827;">Welcome to MoveLine</h2>
    <p style="margin: 0 0 16px; color:#374151;">Hello {full_name},</p>
    <p style="margin: 0 0 16px; color:#374151;">Your application has been approved.</p>
    <p style="margin: 0 0 16px; color:#374151;">You can now log in and start working.</p>
    <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;" />
    <p style="margin: 0; color:#9ca3af; font-size: 12px;">MoveLine Support</p>
  </div>
</div>
"""
            email = EmailMultiAlternatives(subject, message, settings.DEFAULT_FROM_EMAIL, [recipient_email])
            email.attach_alternative(html_message, "text/html")
            email.send()
        return response.Response({"detail": "Applicant approved."}, status=status.HTTP_200_OK)


class AdminRejectApplicantView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, app_type: str, pk: int):
        application = None
        if app_type == "drivers":
            application = DriverApplication.objects.select_related("user").filter(pk=pk).first()
        elif app_type == "workers":
            application = WorkerApplication.objects.select_related("user").filter(pk=pk).first()
        if application is None:
            return response.Response(
                {"detail": "Application not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if application.status not in {ApplicantStatus.PENDING, ApplicantStatus.REVIEW}:
            return response.Response(
                {"detail": "Application is not in a pending state."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        application.status = ApplicantStatus.REJECTED
        application.interview_status = InterviewStatus.COMPLETED
        application.save(update_fields=("status", "interview_status"))
        return response.Response({"detail": "Applicant rejected."}, status=status.HTTP_200_OK)


class AdminDriverApplicantListView(ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = DriverApplicationSerializer
    queryset = DriverApplication.objects.select_related("user").filter(
        status__in=[ApplicantStatus.PENDING, ApplicantStatus.REVIEW]
    )


class AdminWorkerApplicantListView(ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = WorkerApplicationSerializer
    queryset = WorkerApplication.objects.select_related("user").filter(
        status__in=[ApplicantStatus.PENDING, ApplicantStatus.REVIEW]
    )
# 
