from typing import Iterable
import logging

from django.conf import settings

from .models import DeviceToken, UserNotification


logger = logging.getLogger(__name__)
_firebase_app = None


def _get_firebase_app():
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    try:
        import firebase_admin
        from firebase_admin import credentials
    except Exception:
        logger.exception("Failed to import firebase_admin.")
        return None

    credentials_path = getattr(settings, "FIREBASE_CREDENTIALS_PATH", None)
    if not credentials_path:
        return None

    try:
        cred = credentials.Certificate(str(credentials_path))
        _firebase_app = firebase_admin.initialize_app(cred)
    except Exception:
        logger.exception("Failed to initialize Firebase app.")
        return None

    return _firebase_app


def send_push_to_tokens(tokens: Iterable[str], title: str, body: str, data: dict | None = None) -> int:
    app = _get_firebase_app()
    if app is None:
        return 0

    try:
        from firebase_admin import messaging
    except Exception:
        logger.exception("Failed to import Firebase messaging.")
        return 0

    token_list = [t for t in tokens if t]
    if not token_list:
        return 0

    message_data = {}
    if data:
        message_data = {k: str(v) for k, v in data.items()}

    notification = messaging.Notification(title=title, body=body)
    message = messaging.MulticastMessage(
        notification=notification,
        data=message_data,
        tokens=token_list,
    )
    try:
        if hasattr(messaging, "send_each_for_multicast"):
            result = messaging.send_each_for_multicast(message, app=app)
        else:
            result = messaging.send_multicast(message, app=app)
    except Exception:
        logger.exception("Failed to send Firebase push notification.")
        return 0
    for response in getattr(result, "responses", []):
        if not response.success:
            logger.warning("Firebase token send failed: %s", response.exception)
    return result.success_count


def send_push_to_user(user, title: str, body: str, data: dict | None = None) -> int:
    UserNotification.objects.create(
        user=user,
        title=title,
        body=body,
        data=data or {},
    )
    tokens = DeviceToken.objects.filter(user=user).values_list("token", flat=True)
    return send_push_to_tokens(tokens, title, body, data)
