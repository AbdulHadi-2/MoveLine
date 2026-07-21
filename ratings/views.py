from django.db import models, transaction
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import OrderRatingFeedback, PerformanceAlert, Rating
from .serializers import (
    BulkOrderRatingSerializer,
    OrderRatingFeedbackSerializer,
    PerformanceAlertManualNotificationSerializer,
    PerformanceAlertSerializer,
    RatingSerializer,
)
from users.models import DriverProfile, WorkerProfile
from users.notifications import send_push_to_user


MIN_RATINGS_FOR_MONITORING = 5
NOTICE_AVG_THRESHOLD = 3.5
WARNING_LOW_SCORE_THRESHOLD = 2
WARNING_LOW_COUNT_LAST_10 = 3
SUSPEND_LOW_COUNT_LAST_5 = 2
SUSPENSION_DAYS = 3


class RatingViewSet(viewsets.ModelViewSet):
    queryset = Rating.objects.select_related("order", "customer", "rated_user")
    serializer_class = RatingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = self.queryset
        if user.is_staff or user.is_superuser:
            return qs
        return qs.filter(models.Q(customer=user) | models.Q(rated_user=user))

    def perform_create(self, serializer):
        rating = serializer.save()
        self._update_user_rating(rating.rated_user_id, rating.target_role)
        self._check_performance(rating.rated_user, rating.target_role)

    def perform_update(self, serializer):
        old_rated_user_id = serializer.instance.rated_user_id
        old_target_role = serializer.instance.target_role
        rating = serializer.save()
        self._update_user_rating(old_rated_user_id, old_target_role)
        self._update_user_rating(rating.rated_user_id, rating.target_role)
        self._check_performance(rating.rated_user, rating.target_role)

    def perform_destroy(self, instance):
        rated_user_id = instance.rated_user_id
        target_role = instance.target_role
        instance.delete()
        self._update_user_rating(rated_user_id, target_role)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if not self._can_modify_rating(request.user, instance):
            return Response(
                {"detail": "Only the rating owner or admin can update this rating."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        if not self._can_modify_rating(request.user, instance):
            return Response(
                {"detail": "Only the rating owner or admin can update this rating."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if not self._can_modify_rating(request.user, instance):
            return Response(
                {"detail": "Only the rating owner or admin can delete this rating."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().destroy(request, *args, **kwargs)

    def _can_modify_rating(self, user, rating):
        return user.is_staff or user.is_superuser or rating.customer_id == user.id

    def _get_order_for_rating_access(self, request, order_id):
        from orders.models import Order

        order = (
            Order.objects.select_related("customer", "driver")
            .prefetch_related("workers", "ratings")
            .filter(id=order_id)
            .first()
        )
        if order is None:
            return None, Response(
                {"detail": "Order not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not (request.user.is_staff or request.user.is_superuser) and order.customer_id != request.user.id:
            return None, Response(
                {"detail": "You can only access rating data for your own orders."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return order, None

    def _build_rating_targets(self, order):
        existing_by_user = {
            rating.rated_user_id: rating
            for rating in order.ratings.all()
        }
        targets = []
        if order.driver_id:
            driver_rating = existing_by_user.get(order.driver_id)
            driver_name = order.driver.get_full_name().strip() or order.driver.username
            targets.append(
                {
                    "id": order.driver_id,
                    "full_name": driver_name,
                    "role": Rating.TargetRole.DRIVER,
                    "already_rated": driver_rating is not None,
                    "rating_id": driver_rating.id if driver_rating else None,
                }
            )
        for worker in order.workers.all():
            worker_rating = existing_by_user.get(worker.id)
            worker_name = worker.get_full_name().strip() or worker.username
            targets.append(
                {
                    "id": worker.id,
                    "full_name": worker_name,
                    "role": Rating.TargetRole.WORKER,
                    "already_rated": worker_rating is not None,
                    "rating_id": worker_rating.id if worker_rating else None,
                }
            )
        return targets

    @action(detail=False, methods=["get"], url_path=r"order-targets/(?P<order_id>\d+)")
    def order_targets(self, request, order_id=None):
        order, error_response = self._get_order_for_rating_access(request, order_id)
        if error_response is not None:
            return error_response
        feedback = OrderRatingFeedback.objects.filter(order=order).first()
        return Response(
            {
                "order": order.id,
                "status": order.status,
                "can_rate": order.status == order.Status.COMPLETED,
                "feedback": OrderRatingFeedbackSerializer(feedback).data if feedback else None,
                "targets": self._build_rating_targets(order),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="rate-order")
    def rate_order(self, request):
        serializer = BulkOrderRatingSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            result = serializer.save()
            for rating in result["ratings"]:
                self._update_user_rating(rating.rated_user_id, rating.target_role)
                self._check_performance(rating.rated_user, rating.target_role)

        feedback = OrderRatingFeedback.objects.filter(order=result["order"]).first()
        return Response(
            {
                "detail": "Order ratings submitted.",
                "order": result["order"].id,
                "feedback": OrderRatingFeedbackSerializer(feedback).data if feedback else None,
                "ratings": RatingSerializer(result["ratings"], many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"], url_path="admin-order-ratings")
    def admin_order_ratings(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response(
                {"detail": "Only admins can view all order ratings."},
                status=status.HTTP_403_FORBIDDEN,
            )

        queryset = (
            OrderRatingFeedback.objects.select_related("order", "customer")
            .prefetch_related("order__ratings__rated_user")
            .all()
        )

        order_id = request.query_params.get("order")
        if order_id:
            queryset = queryset.filter(order_id=order_id)

        customer_id = request.query_params.get("customer")
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)

        page = self.paginate_queryset(queryset)
        if page is not None:
            data = [self._serialize_order_rating_dashboard_item(feedback) for feedback in page]
            return self.get_paginated_response(data)

        data = [self._serialize_order_rating_dashboard_item(feedback) for feedback in queryset]
        return Response(data, status=status.HTTP_200_OK)

    def _serialize_order_rating_dashboard_item(self, feedback):
        order = feedback.order
        return {
            "order": order.id,
            "order_status": order.status,
            "customer": self._user_summary(feedback.customer),
            "feedback": feedback.feedback,
            "feedback_created_at": feedback.created_at.isoformat() if feedback.created_at else None,
            "feedback_updated_at": feedback.updated_at.isoformat() if feedback.updated_at else None,
            "ratings": [
                {
                    "id": rating.id,
                    "rated_user": self._user_summary(rating.rated_user),
                    "target_role": rating.target_role,
                    "score": rating.score,
                    "created_at": rating.created_at.isoformat() if rating.created_at else None,
                    "updated_at": rating.updated_at.isoformat() if rating.updated_at else None,
                }
                for rating in order.ratings.all()
            ],
        }

    def _user_summary(self, user):
        if user is None:
            return None
        return {
            "id": user.id,
            "full_name": user.get_full_name().strip() or user.username,
            "email": user.email,
            "role": user.role,
        }

    def _update_user_rating(self, user_id, target_role):
        if not user_id:
            return
        avg_score = (
            Rating.objects.filter(rated_user_id=user_id)
            .aggregate(avg=models.Avg("score"))
            .get("avg")
            or 0.0
        )
        avg_score = round(float(avg_score), 2)
        if target_role == Rating.TargetRole.DRIVER:
            DriverProfile.objects.filter(user_id=user_id).update(rating=avg_score)
        elif target_role == Rating.TargetRole.WORKER:
            WorkerProfile.objects.filter(user_id=user_id).update(rating=avg_score)

    def _check_performance(self, user, target_role):
        if not user:
            return
        ratings = list(
            Rating.objects.filter(rated_user=user)
            .order_by("-created_at")
            .values_list("score", flat=True)[:10]
        )
        if len(ratings) < MIN_RATINGS_FOR_MONITORING:
            return

        recent_5 = ratings[:5]
        average_5 = sum(recent_5) / len(recent_5)
        low_10 = sum(1 for score in ratings if score <= WARNING_LOW_SCORE_THRESHOLD)
        low_5 = sum(1 for score in recent_5 if score <= WARNING_LOW_SCORE_THRESHOLD)

        has_active_suspension = PerformanceAlert.objects.filter(
            user=user,
            level=PerformanceAlert.Level.SUSPENSION,
            status=PerformanceAlert.Status.OPEN,
            suspended_until__gt=timezone.now(),
        ).exists()
        if has_active_suspension:
            return

        has_warning = PerformanceAlert.objects.filter(
            user=user,
            level=PerformanceAlert.Level.WARNING,
            status=PerformanceAlert.Status.OPEN,
        ).exists()

        if has_warning and low_5 >= SUSPEND_LOW_COUNT_LAST_5:
            self._create_performance_alert(
                user=user,
                target_role=target_role,
                level=PerformanceAlert.Level.SUSPENSION,
                reason="Repeated low ratings after warning.",
                average_rating=average_5,
                low_rating_count=low_5,
                suspend=True,
            )
            return

        if low_10 >= WARNING_LOW_COUNT_LAST_10:
            self._create_performance_alert(
                user=user,
                target_role=target_role,
                level=PerformanceAlert.Level.WARNING,
                reason="Multiple low ratings in recent orders.",
                average_rating=average_5,
                low_rating_count=low_10,
            )
            return

        if average_5 < NOTICE_AVG_THRESHOLD:
            self._create_performance_alert(
                user=user,
                target_role=target_role,
                level=PerformanceAlert.Level.NOTICE,
                reason="Recent average rating is below the expected level.",
                average_rating=average_5,
                low_rating_count=low_5,
            )

    def _create_performance_alert(
        self,
        user,
        target_role,
        level,
        reason,
        average_rating,
        low_rating_count,
        suspend=False,
    ):
        if PerformanceAlert.objects.filter(
            user=user,
            level=level,
            status=PerformanceAlert.Status.OPEN,
        ).exists():
            return

        suspended_until = None
        if suspend:
            suspended_until = timezone.now() + timezone.timedelta(days=SUSPENSION_DAYS)
            if target_role == Rating.TargetRole.DRIVER:
                DriverProfile.objects.filter(user=user).update(
                    availability=False,
                    suspended_until=suspended_until,
                )
            elif target_role == Rating.TargetRole.WORKER:
                WorkerProfile.objects.filter(user=user).update(
                    availability=False,
                    suspended_until=suspended_until,
                )

        alert = PerformanceAlert.objects.create(
            user=user,
            target_role=target_role,
            level=level,
            reason=reason,
            average_rating=round(float(average_rating), 2),
            low_rating_count=low_rating_count,
            suspended_until=suspended_until,
        )
        self._notify_performance_alert(alert)

    def _notify_performance_alert(self, alert):
        titles = {
            PerformanceAlert.Level.NOTICE: "Performance Notice",
            PerformanceAlert.Level.WARNING: "Performance Warning",
            PerformanceAlert.Level.SUSPENSION: "Temporary Suspension",
        }
        bodies = {
            PerformanceAlert.Level.NOTICE: "Your recent ratings are below the expected level. Please improve service quality.",
            PerformanceAlert.Level.WARNING: "You received multiple low ratings. Repeated issues may cause temporary suspension.",
            PerformanceAlert.Level.SUSPENSION: "Your account has been temporarily suspended from new assignments.",
        }
        send_push_to_user(
            alert.user,
            title=titles[alert.level],
            body=bodies[alert.level],
            data={
                "type": "performance_alert",
                "alert_id": alert.id,
                "level": alert.level,
                "target_role": alert.target_role,
            },
        )


class PerformanceAlertViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PerformanceAlert.objects.select_related("user").all()
    serializer_class = PerformanceAlertSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = self.queryset
        if user.is_staff or user.is_superuser:
            base_qs = qs
        else:
            base_qs = qs.filter(user=user)

        status_param = self.request.query_params.get("status")
        if status_param:
            base_qs = base_qs.filter(status=status_param)

        level = self.request.query_params.get("level")
        if level:
            base_qs = base_qs.filter(level=level)

        return base_qs

    @action(detail=True, methods=["post"], url_path="resolve")
    def resolve(self, request, pk=None):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response(
                {"detail": "Only admins can resolve performance alerts."},
                status=status.HTTP_403_FORBIDDEN,
            )
        alert = self.get_object()
        alert.status = PerformanceAlert.Status.RESOLVED
        alert.resolved_at = timezone.now()
        alert.save(update_fields=("status", "resolved_at"))
        return Response(PerformanceAlertSerializer(alert).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="send-notification")
    def send_notification(self, request, pk=None):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response(
                {"detail": "Only admins can send manual performance alert notifications."},
                status=status.HTTP_403_FORBIDDEN,
            )

        alert = self.get_object()
        serializer = PerformanceAlertManualNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        state = serializer.validated_data["state"]

        title, body = self._performance_alert_message(alert, state)
        sent_count = send_push_to_user(
            alert.user,
            title=title,
            body=body,
            data={
                "type": "performance_alert",
                "state": state,
                "alert_id": alert.id,
                "target_role": alert.target_role,
            },
        )
        return Response(
            {
                "detail": "Performance alert notification requested.",
                "state": state,
                "recipient_count": 1,
                "sent_count": sent_count,
            },
            status=status.HTTP_200_OK,
        )

    def _performance_alert_message(self, alert, state):
        messages = {
            "notice": (
                "Performance Notice",
                "Your recent ratings are below the expected level. Please improve service quality.",
            ),
            "warning": (
                "Performance Warning",
                "You received multiple low ratings. Repeated issues may cause temporary suspension.",
            ),
            "suspension": (
                "Temporary Suspension",
                "Your account has been temporarily suspended from new assignments.",
            ),
            "resolved": (
                "Performance Alert Resolved",
                "Your performance alert has been reviewed and resolved.",
            ),
        }
        return messages[state]
