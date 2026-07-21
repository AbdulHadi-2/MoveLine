from datetime import timedelta

from django.utils import timezone
from django.conf import settings
from django.db import transaction
from django.http import QueryDict
from django.http import HttpResponse
from django.utils.html import escape
from rest_framework import exceptions, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from orders.models import Order, OrderWorker
from orders.serializers import OrderSerializer
from orders.views import OrderViewSet
from tracking.models import Tracking
from users.models import DriverProfile, WorkerProfile
from vehicles.models import Vehicle

from .models import Payment, PendingOrderCheckout
from .paymera import (
    PaymeraError,
    find_payment_from_callback,
    initiate_paymera_payment,
    normalize_callback_status,
    verify_paymera_signature,
)
from .serializers import (
    PaymentSerializer,
    PendingOrderCheckoutSerializer,
    PaymeraInitiateSerializer,
    PaymeraVerifySerializer,
    StripeConfirmOrderCheckoutSerializer,
    StripeCheckoutSessionSerializer,
    StripeOrderCheckoutUrlSerializer,
    StripeVerifySessionSerializer,
)


def _payment_app_redirect_html(title, deep_link):
    safe_title = escape(title)
    safe_deep_link = escape(deep_link)
    return f"""
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{safe_title}</title>
</head>
<body style="font-family: Arial, sans-serif; padding: 24px;">
    <h3>{safe_title}</h3>
    <p>If the app does not open automatically, tap the button below.</p>
    <p>
        <a href="{safe_deep_link}" style="display:inline-block;padding:12px 16px;background:#111827;color:#fff;text-decoration:none;border-radius:8px;">
            Open MoveLine App
        </a>
    </p>
    <script>
        setTimeout(function () {{
            window.location.href = "{safe_deep_link}";
        }}, 300);
    </script>
</body>
</html>
"""


def stripe_payment_success_redirect(request):
    session_id = request.GET.get("session_id", "")
    deep_link = f"myapp://payment/success?session_id={session_id}"
    return HttpResponse(_payment_app_redirect_html("Payment completed", deep_link))


def stripe_payment_cancel_redirect(request):
    deep_link = "myapp://payment/cancel"
    return HttpResponse(_payment_app_redirect_html("Payment cancelled", deep_link))


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.select_related("order").all()
    serializer_class = PaymentSerializer

    def get_permissions(self):
        if self.action in {"paymera_callback", "stripe_webhook"}:
            return [permissions.AllowAny()]
        return super().get_permissions()

    def _get_stripe(self):
        if not settings.STRIPE_SECRET_KEY:
            raise RuntimeError("STRIPE_SECRET_KEY is not configured.")
        try:
            import stripe
        except ImportError as exc:
            raise RuntimeError("stripe package is not installed.") from exc
        stripe.api_key = settings.STRIPE_SECRET_KEY
        return stripe

    def _mark_stripe_payment_paid(self, session):
        payment_id = (session.get("metadata") or {}).get("payment_id")
        if not payment_id:
            return None
        payment = Payment.objects.select_related("order").filter(id=payment_id).first()
        if payment is None:
            return None

        payment.status = Payment.Status.PAID
        payment.paid_amount = payment.amount
        payment.paid_at = timezone.now()
        payment.transaction_reference = session.get("id", payment.transaction_reference)
        payment.metadata = {
            **payment.metadata,
            "stripe_session": {
                "id": session.get("id"),
                "payment_status": session.get("payment_status"),
                "status": session.get("status"),
                "amount_total": session.get("amount_total"),
                "currency": session.get("currency"),
            },
        }
        payment.save(
            update_fields=(
                "status",
                "paid_amount",
                "paid_at",
                "transaction_reference",
                "metadata",
                "updated_at",
            )
        )
        return payment

    def _first_payload_value(self, value):
        if isinstance(value, list):
            return value[0] if value else None
        return value

    def _split_order_checkout_payload(self, request_data):
        if isinstance(request_data, QueryDict):
            payload = request_data.copy()
        else:
            payload = dict(request_data)

        success_url = self._first_payload_value(payload.pop("success_url", None))
        cancel_url = self._first_payload_value(payload.pop("cancel_url", None))
        url_serializer = StripeOrderCheckoutUrlSerializer(
            data={
                "success_url": success_url,
                "cancel_url": cancel_url,
            }
        )
        url_serializer.is_valid(raise_exception=True)
        return payload, url_serializer.validated_data

    def _validate_order_payload_and_price(self, request, order_payload):
        order_serializer = OrderSerializer(
            data=order_payload,
            context={"request": request},
        )
        order_serializer.is_valid(raise_exception=True)

        order_view = OrderViewSet()
        order_view.request = request
        validated_data = order_serializer.validated_data
        order_view._validate_worker_count(validated_data)

        vehicle_type = validated_data.get("required_vehicle_type")
        if not vehicle_type:
            from rest_framework import exceptions

            raise exceptions.ValidationError(
                {"required_vehicle_type": "This field is required to calculate price."}
            )

        trip_distance_km = order_view._calculate_trip_distance(validated_data)
        price = order_view._calculate_order_price(
            validated_data,
            trip_distance_km,
            vehicle_type,
        )
        return order_serializer, price

    def _release_pending_checkout_resources(self, pending_checkout):
        if pending_checkout.reserved_driver_id:
            DriverProfile.objects.filter(user_id=pending_checkout.reserved_driver_id).update(
                availability=True
            )
        if pending_checkout.reserved_vehicle_id:
            Vehicle.objects.filter(id=pending_checkout.reserved_vehicle_id).update(
                is_available=True
            )
        worker_ids = list(pending_checkout.reserved_workers.values_list("id", flat=True))
        if worker_ids:
            WorkerProfile.objects.filter(user_id__in=worker_ids).update(availability=True)

    def _release_expired_pending_checkouts(self):
        expired_checkouts = (
            PendingOrderCheckout.objects.filter(
                status=PendingOrderCheckout.Status.PENDING,
                order__isnull=True,
                expires_at__lt=timezone.now(),
            )
            .prefetch_related("reserved_workers")
        )
        for pending_checkout in expired_checkouts:
            self._release_pending_checkout_resources(pending_checkout)
            pending_checkout.status = PendingOrderCheckout.Status.CANCELLED
            pending_checkout.save(update_fields=("status", "updated_at"))

    def _cancel_user_pending_checkouts(self, user):
        pending_checkouts = (
            PendingOrderCheckout.objects.filter(
                customer=user,
                status=PendingOrderCheckout.Status.PENDING,
                order__isnull=True,
            )
            .prefetch_related("reserved_workers")
        )
        for pending_checkout in pending_checkouts:
            self._release_pending_checkout_resources(pending_checkout)
            pending_checkout.status = PendingOrderCheckout.Status.CANCELLED
            pending_checkout.metadata = {
                **pending_checkout.metadata,
                "cancel_reason": "replaced_by_new_checkout",
            }
            pending_checkout.save(update_fields=("status", "metadata", "updated_at"))

    def _reserve_resources_for_checkout(self, request, validated_data):
        order_view = OrderViewSet()
        order_view.request = request
        pickup_lat = validated_data.get("pickup_latitude")
        pickup_lon = validated_data.get("pickup_longitude")
        required_workers = validated_data.get("required_workers", 0)
        required_vehicle_type = validated_data.get("required_vehicle_type")

        if required_vehicle_type:
            vehicle, distance_km, office = order_view._select_office_vehicle(
                float(pickup_lat),
                float(pickup_lon),
                required_vehicle_type,
            )
            if vehicle is None:
                raise exceptions.ValidationError(
                    {"vehicle": "No available vehicles of the required type in nearby offices."}
                )
            driver_profile = order_view._available_drivers_queryset(office).first()
            if driver_profile is None:
                raise exceptions.ValidationError(
                    {
                        "driver": (
                            "The nearest office with the requested vehicle type "
                            "has no available driver."
                        ),
                        "office": office.id if office else None,
                    }
                )
        else:
            driver_profile, distance_km, office = order_view._select_office_driver(
                float(pickup_lat),
                float(pickup_lon),
            )
            vehicle = None
            if driver_profile is None:
                raise exceptions.ValidationError({"driver": "No available drivers in nearby offices."})

        if distance_km is None:
            raise exceptions.ValidationError(
                {"office_distance": "Failed to calculate distance to nearest office."}
            )

        workers = order_view._select_office_workers(office, required_workers)
        if required_workers and len(workers) < required_workers:
            raise exceptions.ValidationError(
                {
                    "workers": "The selected office does not have enough available workers.",
                    "required_workers": required_workers,
                    "available_workers": len(workers),
                    "office": office.id if office else None,
                }
            )

        driver_profile.availability = False
        driver_profile.save(update_fields=("availability",))
        if vehicle is not None:
            vehicle.is_available = False
            vehicle.save(update_fields=("is_available",))
        WorkerProfile.objects.filter(user_id__in=[w.user_id for w in workers]).update(
            availability=False
        )
        return driver_profile, vehicle, workers

    def _create_order_from_pending_checkout(self, request, pending_checkout):
        order_serializer = OrderSerializer(
            data=pending_checkout.order_payload,
            context={"request": request},
        )
        order_serializer.is_valid(raise_exception=True)

        order_view = OrderViewSet()
        order_view.request = request
        validated_data = order_serializer.validated_data
        trip_distance_km = order_view._calculate_trip_distance(validated_data)
        vehicle_type = validated_data.get("required_vehicle_type")
        if not vehicle_type and pending_checkout.reserved_vehicle_id:
            vehicle_type = pending_checkout.reserved_vehicle.vehicle_type
        if not vehicle_type:
            raise exceptions.ValidationError(
                {"vehicle": "Vehicle type is required to calculate price."}
            )
        price = order_view._calculate_order_price(validated_data, trip_distance_km, vehicle_type)

        driver_profile = DriverProfile.objects.select_related("user").get(
            user=pending_checkout.reserved_driver
        )
        vehicle = pending_checkout.reserved_vehicle
        workers = list(
            WorkerProfile.objects.select_related("user").filter(
                user__in=pending_checkout.reserved_workers.all()
            )
        )

        order = order_serializer.save(
            customer=request.user,
            driver=driver_profile.user,
            vehicle=vehicle,
            status=Order.Status.IN_PROGRESS,
            estimated_distance_km=trip_distance_km,
            estimated_price=price["total_price"],
        )
        Tracking.objects.get_or_create(
            order=order,
            defaults={"driver": driver_profile.user, "is_active": True},
        )
        for worker_profile in workers:
            OrderWorker.objects.create(
                order=order,
                worker=worker_profile.user,
                status=OrderWorker.WorkerStatus.ASSIGNED,
            )
        transaction.on_commit(
            lambda: order_view._notify_assignment(order, driver_profile.user, workers)
        )
        return order

    def _mark_pending_checkout_paid(self, session):
        pending_id = (session.get("metadata") or {}).get("pending_checkout_id")
        if not pending_id:
            return None
        pending_checkout = PendingOrderCheckout.objects.filter(id=pending_id).first()
        if pending_checkout is None:
            return None
        if pending_checkout.status == PendingOrderCheckout.Status.PENDING:
            pending_checkout.status = PendingOrderCheckout.Status.PAID
        pending_checkout.paid_at = pending_checkout.paid_at or timezone.now()
        pending_checkout.metadata = {
            **pending_checkout.metadata,
            "stripe_session": {
                "id": session.get("id"),
                "payment_status": session.get("payment_status"),
                "status": session.get("status"),
                "amount_total": session.get("amount_total"),
                "currency": session.get("currency"),
            },
        }
        pending_checkout.save(update_fields=("status", "paid_at", "metadata", "updated_at"))
        return pending_checkout

    @action(detail=False, methods=["post"], url_path="paymera/initiate")
    def paymera_initiate(self, request):
        serializer = PaymeraInitiateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        order = serializer.validated_data["order"]
        amount = order.final_price or order.estimated_price

        payment, _ = Payment.objects.update_or_create(
            order=order,
            defaults={
                "amount": amount,
                "currency": getattr(order, "payment_currency", "USD"),
                "method": Payment.Method.PAYMERA,
                "status": Payment.Status.PENDING,
            },
        )

        try:
            gateway_response = initiate_paymera_payment(
                payment=payment,
                success_url=serializer.validated_data["success_url"],
                cancel_url=serializer.validated_data["cancel_url"],
                request=request,
            )
        except PaymeraError as exc:
            return Response(
                {"detail": "Failed to initiate Paymera payment.", "error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        payment.refresh_from_db()
        payment_url = (
            gateway_response.get("payment_url")
            or gateway_response.get("checkout_url")
            or gateway_response.get("redirect_url")
            or gateway_response.get("url")
        )
        return Response(
            {
                "detail": "Paymera payment initiated.",
                "payment": PaymentSerializer(payment).data,
                "payment_url": payment_url,
                "gateway_response": gateway_response,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="paymera/callback")
    def paymera_callback(self, request):
        signature = request.headers.get("X-Paymera-Signature")
        if not verify_paymera_signature(request.body, signature):
            return Response({"detail": "Invalid signature."}, status=status.HTTP_403_FORBIDDEN)

        payload = request.data if isinstance(request.data, dict) else {}
        payment = find_payment_from_callback(payload)
        if payment is None:
            return Response({"detail": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)

        new_status = normalize_callback_status(payload)
        payment.status = new_status
        if new_status == Payment.Status.PAID:
            payment.paid_amount = payment.amount
            payment.paid_at = timezone.now()
        payment.metadata = {
            **payment.metadata,
            "paymera_callback": payload,
        }
        payment.save(update_fields=("status", "paid_amount", "paid_at", "metadata", "updated_at"))

        return Response(
            {"detail": "Callback processed.", "payment": PaymentSerializer(payment).data},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="paymera/verify")
    def paymera_verify(self, request):
        serializer = PaymeraVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payment = serializer.validated_data.get("payment")
        if payment is None:
            payment = Payment.objects.filter(
                transaction_reference=serializer.validated_data["transaction_reference"]
            ).first()
        if payment is None:
            return Response({"detail": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response(
            {"detail": "Payment status loaded.", "payment": PaymentSerializer(payment).data},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="stripe/create-checkout-session")
    def stripe_create_checkout_session(self, request):
        serializer = StripeCheckoutSessionSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        order = serializer.validated_data["order"]
        amount = order.final_price or order.estimated_price
        currency = settings.STRIPE_CURRENCY.lower()

        payment, _ = Payment.objects.update_or_create(
            order=order,
            defaults={
                "amount": amount,
                "currency": currency.upper(),
                "method": Payment.Method.STRIPE,
                "status": Payment.Status.PENDING,
            },
        )

        try:
            stripe = self._get_stripe()
            session = stripe.checkout.Session.create(
                mode="payment",
                payment_method_types=["card"],
                success_url=serializer.validated_data["success_url"],
                cancel_url=serializer.validated_data["cancel_url"],
                line_items=[
                    {
                        "price_data": {
                            "currency": currency,
                            "product_data": {
                                "name": f"MoveLine Order #{order.id}",
                            },
                            "unit_amount": int(amount * 100),
                        },
                        "quantity": 1,
                    }
                ],
                metadata={
                    "payment_id": str(payment.id),
                    "order_id": str(order.id),
                    "customer_id": str(order.customer_id),
                },
            )
        except Exception as exc:
            return Response(
                {"detail": "Failed to create Stripe checkout session.", "error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        payment.transaction_reference = session.id
        payment.metadata = {
            **payment.metadata,
            "stripe_session_id": session.id,
        }
        payment.save(update_fields=("transaction_reference", "metadata", "updated_at"))

        return Response(
            {
                "detail": "Stripe checkout session created.",
                "payment": PaymentSerializer(payment).data,
                "session_id": session.id,
                "checkout_url": session.url,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="stripe/create-order-checkout")
    def stripe_create_order_checkout(self, request):
        self._release_expired_pending_checkouts()
        self._cancel_user_pending_checkouts(request.user)
        order_payload, urls = self._split_order_checkout_payload(request.data)
        order_serializer, price = self._validate_order_payload_and_price(request, order_payload)
        amount = price["total_price"]
        currency = settings.STRIPE_CURRENCY.lower()

        with transaction.atomic():
            driver_profile, vehicle, workers = self._reserve_resources_for_checkout(
                request,
                order_serializer.validated_data,
            )
            pending_checkout = PendingOrderCheckout.objects.create(
                customer=request.user,
                order_payload=order_payload,
                amount=amount,
                currency=currency.upper(),
                reserved_driver=driver_profile.user,
                reserved_vehicle=vehicle,
                expires_at=timezone.now() + timedelta(minutes=10),
                metadata={
                    "reserved_driver_id": driver_profile.user_id,
                    "reserved_vehicle_id": vehicle.id if vehicle else None,
                    "reserved_worker_ids": [worker.user_id for worker in workers],
                    "price_breakdown": {
                        "estimated_distance_km": price["distance_km"],
                        "required_vehicle_type": price["vehicle_type"],
                        "required_workers": int(
                            order_serializer.validated_data.get("required_workers") or 0
                        ),
                        "per_km_rate": str(price["per_km_rate"]),
                        "distance_fee": str(price["distance_fee"]),
                        "workers_fee": str(price["workers_fee"]),
                        "assembly_fee": str(price["assembly_fee"]),
                        "disassembly_fee": str(price["disassembly_fee"]),
                        "floor_fee": str(price["floor_fee"]),
                        "estimated_price": str(price["total_price"]),
                    },
                },
            )
            pending_checkout.reserved_workers.set([worker.user for worker in workers])

        try:
            stripe = self._get_stripe()
            session = stripe.checkout.Session.create(
                mode="payment",
                payment_method_types=["card"],
                success_url=urls["success_url"],
                cancel_url=urls["cancel_url"],
                line_items=[
                    {
                        "price_data": {
                            "currency": currency,
                            "product_data": {"name": "MoveLine Order"},
                            "unit_amount": int(amount * 100),
                        },
                        "quantity": 1,
                    }
                ],
                metadata={
                    "pending_checkout_id": str(pending_checkout.id),
                    "customer_id": str(request.user.id),
                    "flow": "pay_before_order_create",
                },
            )
        except Exception as exc:
            self._release_pending_checkout_resources(pending_checkout)
            pending_checkout.status = PendingOrderCheckout.Status.FAILED
            pending_checkout.metadata = {
                **pending_checkout.metadata,
                "stripe_error": str(exc),
            }
            pending_checkout.save(update_fields=("status", "metadata", "updated_at"))
            return Response(
                {"detail": "Failed to create Stripe checkout session.", "error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        pending_checkout.stripe_session_id = session.id
        pending_checkout.metadata = {
            **pending_checkout.metadata,
            "stripe_session_id": session.id,
        }
        pending_checkout.save(update_fields=("stripe_session_id", "metadata", "updated_at"))

        return Response(
            {
                "detail": "Stripe checkout session created for pending order.",
                "pending_checkout": PendingOrderCheckoutSerializer(pending_checkout).data,
                "session_id": session.id,
                "checkout_url": session.url,
                "estimated_price": str(amount),
                "price_breakdown": pending_checkout.metadata.get("price_breakdown"),
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="stripe/confirm-order-checkout")
    def stripe_confirm_order_checkout(self, request):
        serializer = StripeConfirmOrderCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            stripe = self._get_stripe()
            session = stripe.checkout.Session.retrieve(serializer.validated_data["session_id"])
        except Exception as exc:
            return Response(
                {"detail": "Failed to load Stripe checkout session.", "error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        pending_checkout = PendingOrderCheckout.objects.filter(
            stripe_session_id=session.id
        ).select_related("order", "customer", "reserved_driver", "reserved_vehicle").first()
        if pending_checkout is None:
            return Response(
                {"detail": "Pending checkout not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not request.user.is_staff and pending_checkout.customer_id != request.user.id:
            return Response(
                {"detail": "You can only confirm your own checkout session."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if session.get("payment_status") != "paid":
            return Response(
                {
                    "detail": "Stripe checkout session is not paid yet.",
                    "payment_status": session.get("payment_status"),
                    "session_status": session.get("status"),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if pending_checkout.status in {
            PendingOrderCheckout.Status.CANCELLED,
            PendingOrderCheckout.Status.FAILED,
        }:
            return Response(
                {
                    "detail": "Checkout reservation is no longer active.",
                    "checkout_status": pending_checkout.status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if pending_checkout.order_id:
            payment = Payment.objects.filter(order=pending_checkout.order).first()
            return Response(
                {
                    "detail": "Order was already created for this paid checkout.",
                    "pending_checkout": PendingOrderCheckoutSerializer(pending_checkout).data,
                    "order": OrderSerializer(pending_checkout.order).data,
                    "payment": PaymentSerializer(payment).data if payment else None,
                },
                status=status.HTTP_200_OK,
            )

        with transaction.atomic():
            pending_checkout.status = PendingOrderCheckout.Status.PAID
            pending_checkout.paid_at = pending_checkout.paid_at or timezone.now()
            pending_checkout.save(update_fields=("status", "paid_at", "updated_at"))

            order = self._create_order_from_pending_checkout(request, pending_checkout)
            payment, _ = Payment.objects.update_or_create(
                order=order,
                defaults={
                    "amount": pending_checkout.amount,
                    "currency": pending_checkout.currency,
                    "method": Payment.Method.STRIPE,
                    "status": Payment.Status.PAID,
                    "transaction_reference": session.id,
                    "paid_amount": pending_checkout.amount,
                    "paid_at": timezone.now(),
                    "metadata": {
                        "pending_checkout_id": pending_checkout.id,
                        "stripe_session": {
                            "id": session.id,
                            "payment_status": session.get("payment_status"),
                            "status": session.get("status"),
                            "amount_total": session.get("amount_total"),
                            "currency": session.get("currency"),
                        },
                    },
                },
            )
            pending_checkout.order = order
            pending_checkout.status = PendingOrderCheckout.Status.CREATED
            pending_checkout.metadata = {
                **pending_checkout.metadata,
                "created_order_id": order.id,
            }
            pending_checkout.save(update_fields=("order", "status", "metadata", "updated_at"))

        return Response(
            {
                "detail": "Payment confirmed and order created.",
                "pending_checkout": PendingOrderCheckoutSerializer(pending_checkout).data,
                "order": OrderSerializer(order).data,
                "payment": PaymentSerializer(payment).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="stripe/verify-session")
    def stripe_verify_session(self, request):
        serializer = StripeVerifySessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            stripe = self._get_stripe()
            session = stripe.checkout.Session.retrieve(serializer.validated_data["session_id"])
        except Exception as exc:
            return Response(
                {"detail": "Failed to load Stripe checkout session.", "error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        payment = Payment.objects.filter(transaction_reference=session.id).first()
        if session.get("payment_status") == "paid":
            payment = self._mark_stripe_payment_paid(session) or payment

        return Response(
            {
                "detail": "Stripe checkout session loaded.",
                "session": {
                    "id": session.id,
                    "status": session.get("status"),
                    "payment_status": session.get("payment_status"),
                    "amount_total": session.get("amount_total"),
                    "currency": session.get("currency"),
                },
                "payment": PaymentSerializer(payment).data if payment else None,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="stripe/webhook")
    def stripe_webhook(self, request):
        try:
            stripe = self._get_stripe()
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        payload = request.body
        signature = request.headers.get("Stripe-Signature")
        try:
            if settings.STRIPE_WEBHOOK_SECRET:
                event = stripe.Webhook.construct_event(
                    payload,
                    signature,
                    settings.STRIPE_WEBHOOK_SECRET,
                )
            else:
                event = request.data
        except Exception:
            return Response({"detail": "Invalid Stripe webhook."}, status=status.HTTP_400_BAD_REQUEST)

        if event.get("type") == "checkout.session.completed":
            session = event.get("data", {}).get("object", {})
            if session.get("payment_status") == "paid":
                self._mark_pending_checkout_paid(session) or self._mark_stripe_payment_paid(session)

        return Response({"detail": "Webhook processed."}, status=status.HTTP_200_OK)
