import math
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from orders.models import Order
from users.notifications import send_push_to_user

from .models import Tracking, TrackingAlert


STOP_MINUTES_FOR_DRIVER_ALERT = 10
DRIVER_RESPONSE_GRACE_MINUTES = 5
ADMIN_ALERT_MINUTES = 15
CUSTOMER_DELAY_MINUTES = 30
GEOFENCE_RADIUS_KM = 0.2


def _distance_km(lat1, lon1, lat2, lon2):
    try:
        lat1 = float(lat1)
        lon1 = float(lon1)
        lat2 = float(lat2)
        lon2 = float(lon2)
    except (TypeError, ValueError):
        return None

    radius_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _is_inside_loading_or_dropoff_zone(order, tracking):
    current_lat = tracking.current_latitude
    current_lon = tracking.current_longitude
    if current_lat is None or current_lon is None:
        return False

    pickup_distance = _distance_km(
        current_lat,
        current_lon,
        order.pickup_latitude,
        order.pickup_longitude,
    )
    if pickup_distance is not None and pickup_distance <= GEOFENCE_RADIUS_KM:
        return True

    dropoff_distance = _distance_km(
        current_lat,
        current_lon,
        order.dropoff_latitude,
        order.dropoff_longitude,
    )
    return dropoff_distance is not None and dropoff_distance <= GEOFENCE_RADIUS_KM


def _has_significant_customer_delay(order, now):
    if order.scheduled_end:
        return now >= order.scheduled_end + timedelta(minutes=CUSTOMER_DELAY_MINUTES)
    if order.scheduled_start and order.estimated_duration_minutes:
        expected_end = order.scheduled_start + timedelta(minutes=order.estimated_duration_minutes)
        return now >= expected_end + timedelta(minutes=CUSTOMER_DELAY_MINUTES)
    return False


def _get_or_create_stop_alert(tracking):
    alert = (
        TrackingAlert.objects.filter(
            tracking=tracking,
            alert_type=TrackingAlert.AlertType.UNEXPECTED_STOP,
            status__in=[TrackingAlert.Status.OPEN, TrackingAlert.Status.ACKNOWLEDGED],
        )
        .order_by("-created_at")
        .first()
    )
    if alert:
        return alert
    return TrackingAlert.objects.create(
        order=tracking.order,
        tracking=tracking,
        driver=tracking.driver,
        alert_type=TrackingAlert.AlertType.UNEXPECTED_STOP,
    )


def _notify_driver(alert):
    if not alert.driver_id or alert.driver_notified_at:
        return
    send_push_to_user(
        alert.driver,
        title="Unexpected Stop Detected",
        body="Your truck appears to be stopped. Are you facing an issue?",
        data={
            "type": "unexpected_stop_driver_check",
            "alert_id": alert.id,
            "order_id": alert.order_id,
        },
    )
    alert.driver_notified_at = timezone.now()
    alert.save(update_fields=("driver_notified_at",))


def _notify_admins(alert):
    if alert.admin_notified_at:
        return
    alert.admin_notified_at = timezone.now()
    alert.save(update_fields=("admin_notified_at",))


def _notify_customer(alert):
    if alert.customer_notified_at or not alert.order.customer_id:
        return
    send_push_to_user(
        alert.order.customer,
        title="MoveLine Order Update",
        body="There is a slight delay in your move. Our team is following up.",
        data={
            "type": "order_delay_customer_notice",
            "alert_id": alert.id,
            "order_id": alert.order_id,
        },
    )
    alert.customer_notified_at = timezone.now()
    alert.save(update_fields=("customer_notified_at",))


@shared_task
def check_stopped_trucks():
    now = timezone.now()
    active_statuses = [Order.Status.IN_PROGRESS, Order.Status.ASSIGNED]
    trackings = (
        Tracking.objects.select_related("order", "driver", "order__customer")
        .filter(
            is_active=True,
            stopped_since__isnull=False,
            order__status__in=active_statuses,
        )
        .prefetch_related("order__workers")
    )

    checked = 0
    alerts_created_or_updated = 0
    for tracking in trackings:
        checked += 1
        order = tracking.order
        if _is_inside_loading_or_dropoff_zone(order, tracking):
            continue

        stopped_for = now - tracking.stopped_since
        if stopped_for < timedelta(minutes=STOP_MINUTES_FOR_DRIVER_ALERT):
            continue

        alert = _get_or_create_stop_alert(tracking)
        alerts_created_or_updated += 1
        _notify_driver(alert)

        driver_grace_expired = (
            alert.driver_notified_at
            and now >= alert.driver_notified_at + timedelta(minutes=DRIVER_RESPONSE_GRACE_MINUTES)
            and not alert.driver_responded_at
        )
        stopped_long_enough_for_admin = stopped_for >= timedelta(minutes=ADMIN_ALERT_MINUTES)
        if driver_grace_expired or stopped_long_enough_for_admin:
            _notify_admins(alert)

        if _has_significant_customer_delay(order, now):
            _notify_customer(alert)

    return {
        "checked": checked,
        "alerts_created_or_updated": alerts_created_or_updated,
    }
