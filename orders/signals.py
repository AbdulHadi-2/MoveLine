from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from users.notifications import send_push_to_user

from .models import Order


ORDER_STATUS_MESSAGES = {
    Order.Status.DELIVERED: (
        "Order Delivered",
        "Order #{order_id} has reached the dropoff location.",
        "order_delivered",
    ),
    Order.Status.COMPLETED: (
        "Order Completed",
        "Order #{order_id} has been completed.",
        "order_completed",
    ),
    Order.Status.CANCELLED: (
        "Order Cancelled",
        "Order #{order_id} has been cancelled.",
        "order_cancelled",
    ),
    Order.Status.IN_PROGRESS: (
        "Order In Progress",
        "Order #{order_id} is now in progress.",
        "order_in_progress",
    ),
}


def _order_users(order):
    users = []
    if order.customer_id:
        users.append(order.customer)
    if order.driver_id:
        users.append(order.driver)
    users.extend(list(order.workers.all()))

    unique_users = []
    seen = set()
    for user in users:
        if user and user.id not in seen:
            unique_users.append(user)
            seen.add(user.id)
    return unique_users


def notify_order_status_changed(order, status_value=None):
    status_value = status_value or order.status
    message = ORDER_STATUS_MESSAGES.get(status_value)
    if not message:
        return

    title, body_template, event_type = message
    body = body_template.format(order_id=order.id)
    data = {
        "type": event_type,
        "order_id": order.id,
        "status": status_value,
    }
    for user in _order_users(order):
        send_push_to_user(user, title=title, body=body, data=data)


@receiver(pre_save, sender=Order)
def remember_previous_order_status(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_status = None
        return
    instance._previous_status = (
        sender.objects.filter(pk=instance.pk)
        .values_list("status", flat=True)
        .first()
    )


@receiver(post_save, sender=Order)
def notify_on_order_status_change(sender, instance, created, **kwargs):
    if created:
        return
    if getattr(instance, "_skip_status_notification", False):
        return
    previous_status = getattr(instance, "_previous_status", None)
    if previous_status == instance.status:
        return
    transaction.on_commit(lambda: notify_order_status_changed(instance))
