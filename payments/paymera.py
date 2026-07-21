import hashlib
import hmac
import uuid
from decimal import Decimal

import requests
from django.conf import settings
from django.urls import reverse

from .models import Payment


class PaymeraError(Exception):
    pass


def _setting(name, default=""):
    return getattr(settings, name, default)


def _amount_to_minor_units(amount: Decimal) -> int:
    return int((amount * Decimal("100")).quantize(Decimal("1")))


def _callback_url(request) -> str:
    path = reverse("payment-paymera-callback")
    if request is None:
        return path
    return request.build_absolute_uri(path)


def _headers():
    headers = {"Content-Type": "application/json"}
    api_key = _setting("PAYMERA_API_KEY")
    merchant_id = _setting("PAYMERA_MERCHANT_ID")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if merchant_id:
        headers["X-Merchant-Id"] = merchant_id
    return headers


def _endpoint(path_setting: str) -> str:
    base_url = _setting("PAYMERA_BASE_URL").rstrip("/")
    path = _setting(path_setting).strip("/")
    if not base_url or not path:
        raise PaymeraError("Paymera is not configured.")
    return f"{base_url}/{path}"


def build_payment_payload(payment, success_url: str, cancel_url: str, request=None) -> dict:
    local_reference = payment.transaction_reference or f"ML-{payment.order_id}-{uuid.uuid4().hex[:12]}"
    payment.transaction_reference = local_reference
    payment.save(update_fields=("transaction_reference", "updated_at"))

    return {
        "merchant_id": _setting("PAYMERA_MERCHANT_ID"),
        "reference": local_reference,
        "order_id": str(payment.order_id),
        "amount": str(payment.amount),
        "amount_minor": _amount_to_minor_units(payment.amount),
        "currency": payment.currency,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "callback_url": _callback_url(request),
        "description": f"MoveLine order #{payment.order_id}",
        "customer": {
            "id": str(payment.order.customer_id),
            "email": payment.order.customer.email,
            "name": payment.order.customer.get_full_name() or payment.order.customer.username,
            "phone": payment.order.customer.phone,
        },
    }


def initiate_paymera_payment(payment, success_url: str, cancel_url: str, request=None) -> dict:
    payload = build_payment_payload(payment, success_url, cancel_url, request)
    url = _endpoint("PAYMERA_INITIATE_PATH")

    try:
        response = requests.post(url, json=payload, headers=_headers(), timeout=20)
    except requests.RequestException as exc:
        raise PaymeraError(str(exc)) from exc

    try:
        response_data = response.json()
    except ValueError:
        response_data = {"raw": response.text}

    payment.metadata = {
        **payment.metadata,
        "paymera_initiate_request": payload,
        "paymera_initiate_response": response_data,
        "paymera_status_code": response.status_code,
    }
    payment.save(update_fields=("metadata", "updated_at"))

    if response.status_code >= 400:
        raise PaymeraError(response_data)

    return response_data


def verify_paymera_signature(raw_body: bytes, signature: str | None) -> bool:
    secret = _setting("PAYMERA_WEBHOOK_SECRET")
    if not secret:
        return True
    if not signature:
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def find_payment_from_callback(payload: dict) -> Payment | None:
    reference = (
        payload.get("reference")
        or payload.get("merchant_reference")
        or payload.get("transaction_reference")
    )
    order_id = payload.get("order_id")

    query = Payment.objects.select_related("order", "order__customer")
    if reference:
        return query.filter(transaction_reference=reference).first()
    if order_id:
        return query.filter(order_id=order_id, method=Payment.Method.PAYMERA).first()
    return None


def normalize_callback_status(payload: dict) -> str:
    status_value = str(payload.get("status") or payload.get("payment_status") or "").lower()
    if status_value in {"paid", "success", "successful", "completed", "approved"}:
        return Payment.Status.PAID
    if status_value in {"failed", "failure", "cancelled", "canceled", "rejected"}:
        return Payment.Status.FAILED
    if status_value in {"authorized", "auth"}:
        return Payment.Status.AUTHORIZED
    return Payment.Status.PENDING
