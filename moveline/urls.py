from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from ai_analyze.views import AnalyzeImageView, OrderItemViewSet
from orders.views import OrderViewSet, OrderWorkerViewSet
from payments.views import PaymentViewSet
from ratings.views import RatingViewSet
from tracking.views import TrackingViewSet
from users.auth import ActiveUserTokenObtainPairView
from users.views import (
    AdminApproveApplicantView,
    AdminRejectApplicantView,
    AdminScheduleInterviewView,
    AdminDriverApplicantListView,
    AdminWorkerApplicantListView,
    CustomerProfileViewSet,
    DriverApplicantRegisterView,
    DriverProfileViewSet,
    OfficeViewSet,
    PasswordChangeView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PasswordResetVerifyView,
    UserViewSet,
    WorkerApplicantRegisterView,
    WorkerProfileViewSet,
)
from vehicles.views import VehicleViewSet


router = DefaultRouter()
router.register(r"users", UserViewSet)
router.register(r"customers", CustomerProfileViewSet)
router.register(r"drivers", DriverProfileViewSet)
router.register(r"offices", OfficeViewSet)
router.register(r"workers", WorkerProfileViewSet)
router.register(r"vehicles", VehicleViewSet)
router.register(r"orders", OrderViewSet)
router.register(r"order-workers", OrderWorkerViewSet)
router.register(r"payments", PaymentViewSet)
router.register(r"tracking", TrackingViewSet)
router.register(r"order-items", OrderItemViewSet)
router.register(r"ratings", RatingViewSet)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/token/", ActiveUserTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/password-reset/", PasswordResetRequestView.as_view(), name="password_reset_request"),
    path("api/auth/password-reset/verify/", PasswordResetVerifyView.as_view(), name="password_reset_verify"),
    path("api/auth/password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("api/auth/password-reset/complete/", PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("api/auth/password-change/", PasswordChangeView.as_view(), name="password_change"),
    path("api/applicants/drivers/register/", DriverApplicantRegisterView.as_view(), name="driver_applicant_register"),
    path("api/applicants/workers/register/", WorkerApplicantRegisterView.as_view(), name="worker_applicant_register"),
    path("api/admin/applicants/drivers/", AdminDriverApplicantListView.as_view(), name="admin_driver_applicants"),
    path("api/admin/applicants/workers/", AdminWorkerApplicantListView.as_view(), name="admin_worker_applicants"),
    path(
        "api/admin/applicants/<str:app_type>/<int:pk>/schedule-interview/",
        AdminScheduleInterviewView.as_view(),
        name="applicant_schedule_interview",
    ),
    path(
        "api/admin/applicants/<str:app_type>/<int:pk>/approve/",
        AdminApproveApplicantView.as_view(),
        name="applicant_approve",
    ),
    path(
        "api/admin/applicants/<str:app_type>/<int:pk>/reject/",
        AdminRejectApplicantView.as_view(),
        name="applicant_reject",
    ),
    path("api/ai/analyze/", AnalyzeImageView.as_view(), name="ai_analyze"),
    path("api/", include(router.urls)),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
