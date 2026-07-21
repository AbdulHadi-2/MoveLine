import json
import math
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from decimal import Decimal
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import models, transaction
from django.utils import timezone
from rest_framework import exceptions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Order, OrderWorker
from .serializers import (
    OrderAssignmentNotificationSerializer,
    OrderSerializer,
    OrderStatusNotificationSerializer,
    OrderWorkerSerializer,
)
from .signals import notify_order_status_changed
from .worker_estimator import estimate_minimum_workers
from users.models import DriverProfile, Office, WorkerProfile
from users.notifications import send_push_to_user
from vehicles.models import Vehicle
from tracking.models import Tracking


class OrderViewSet(viewsets.ModelViewSet):
    queryset = (
        Order.objects.select_related("customer", "driver", "vehicle")
        .prefetch_related("order_workers", "items")
        .all()
    )
    serializer_class = OrderSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return queryset
        return (
            queryset.filter(
                models.Q(customer=user)
                | models.Q(driver=user)
                | models.Q(workers=user)
            )
            .distinct()
        )

    def _haversine_distance_km(
        self,
        pickup_lat: float,
        pickup_lon: float,
        dropoff_lat: float,
        dropoff_lon: float,
    ) -> float:
        earth_radius_km = 6371.0
        lat1 = math.radians(pickup_lat)
        lon1 = math.radians(pickup_lon)
        lat2 = math.radians(dropoff_lat)
        lon2 = math.radians(dropoff_lon)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        straight_distance = earth_radius_km * c
        return straight_distance * 1.25

    def _osrm_distance_km(self, pickup_lat: float, pickup_lon: float, dropoff_lat: float, dropoff_lon: float) -> float | None:
        base_url = "http://router.project-osrm.org/route/v1/driving/"
        coords = f"{pickup_lon},{pickup_lat};{dropoff_lon},{dropoff_lat}"
        query = urlencode({"overview": "false"})
        url = f"{base_url}{coords}?{query}"
        try:
            request = Request(url, headers={"User-Agent": "MoveLine/1.0"})
            with urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return None

        routes = payload.get("routes", [])
        if not routes:
            return None
        distance_meters = routes[0].get("distance")
        if distance_meters is None:
            return None
        return distance_meters / 1000.0

    def _available_drivers_queryset(self, office: Office):
        return (
            DriverProfile.objects.select_related("user")
            .filter(
                office=office,
                availability=True,
            )
            .filter(
                models.Q(suspended_until__isnull=True)
                | models.Q(suspended_until__lte=timezone.now())
            )
        )

    def _available_workers_queryset(self, office: Office):
        return (
            WorkerProfile.objects.select_related("user")
            .filter(office=office, availability=True)
            .filter(
                models.Q(suspended_until__isnull=True)
                | models.Q(suspended_until__lte=timezone.now())
            )
        )

    def _select_office_vehicle(
        self,
        pickup_lat: float,
        pickup_lon: float,
        required_vehicle_type: str,
    ) -> tuple[Vehicle | None, float | None, Office | None]:
        office_distances = self._offices_by_distance(pickup_lat, pickup_lon)
        for distance, office in office_distances:
            vehicle = (
                Vehicle.objects.select_related("office")
                .filter(
                    office=office,
                    vehicle_type=required_vehicle_type,
                    is_available=True,
                )
                .first()
            )
            if vehicle:
                return vehicle, distance, office

        return None, None, None

    def _select_office_driver(
        self,
        pickup_lat: float,
        pickup_lon: float,
    ) -> tuple[DriverProfile | None, float | None, Office | None]:
        office_distances = self._offices_by_distance(pickup_lat, pickup_lon)
        for distance, office in office_distances:
            driver_profile = self._available_drivers_queryset(office).first()
            if driver_profile:
                return driver_profile, distance, office
        return None, None, None

    def _select_office_workers(self, office: Office | None, required_count: int) -> list[WorkerProfile]:
        if required_count <= 0 or office is None:
            return []
        return list(self._available_workers_queryset(office)[:required_count])

    def _offices_by_distance(self, pickup_lat: float, pickup_lon: float) -> list[tuple[float, Office]]:
        office_distances = []
        for office in Office.objects.all():
            distance = self._osrm_distance_km(
                pickup_lat,
                pickup_lon,
                float(office.latitude),
                float(office.longitude),
            )
            if distance is None:
                distance = self._haversine_distance_km(
                    pickup_lat,
                    pickup_lon,
                    float(office.latitude),
                    float(office.longitude),
                )
            office_distances.append((distance, office))
        office_distances.sort(key=lambda item: item[0])
        return office_distances

    def _floor_fee(self, validated_data, required_workers: int) -> Decimal:
        if required_workers <= 0:
            return Decimal("0.00")

        pickup_floor = int(validated_data.get("pickup_floor") or 0)
        dropoff_floor = int(validated_data.get("dropoff_floor") or 0)
        pickup_has_elevator = bool(validated_data.get("pickup_has_elevator", False))
        dropoff_has_elevator = bool(validated_data.get("dropoff_has_elevator", False))

        floors_without_elevator = 0
        if not pickup_has_elevator:
            floors_without_elevator += pickup_floor
        if not dropoff_has_elevator:
            floors_without_elevator += dropoff_floor

        return Decimal(floors_without_elevator) * Decimal(required_workers) * Decimal("2.00")

    def _calculate_order_price(
        self,
        validated_data,
        trip_distance_km: float,
        vehicle_type: str,
    ) -> dict:
        required_workers = int(validated_data.get("required_workers") or 0)
        assembly = validated_data.get("assembly", False)
        disassembly = validated_data.get("disassembly", False)

        per_km_rates = {
            Order.VehicleSize.SMALL: Decimal("5.0"),
            Order.VehicleSize.MEDIUM: Decimal("7.5"),
            Order.VehicleSize.LARGE: Decimal("10.0"),
        }
        per_km_rate = per_km_rates.get(vehicle_type)
        if per_km_rate is None:
            raise exceptions.ValidationError({"vehicle": "Unknown vehicle type for pricing."})

        distance_fee = (Decimal(str(trip_distance_km)) * per_km_rate).quantize(Decimal("0.01"))
        workers_fee = Decimal("5.0") * Decimal(required_workers)
        assembly_fee = Decimal("10.0") if assembly else Decimal("0.00")
        disassembly_fee = Decimal("10.0") if disassembly else Decimal("0.00")
        floor_fee = self._floor_fee(validated_data, required_workers)
        total_cost = distance_fee + workers_fee + assembly_fee + disassembly_fee + floor_fee

        return {
            "distance_km": round(float(trip_distance_km), 2),
            "vehicle_type": vehicle_type,
            "per_km_rate": per_km_rate,
            "distance_fee": distance_fee,
            "workers_fee": workers_fee,
            "assembly_fee": assembly_fee,
            "disassembly_fee": disassembly_fee,
            "floor_fee": floor_fee,
            "total_price": total_cost.quantize(Decimal("0.01")),
        }

    def _validate_worker_count(self, validated_data):
        requested_workers = int(validated_data.get("required_workers") or 0)
        items = validated_data.get("items") or []
        minimum_workers = estimate_minimum_workers(
            items=items,
            vehicle_type=validated_data.get("required_vehicle_type"),
            pickup_floor=validated_data.get("pickup_floor") or 0,
            pickup_has_elevator=validated_data.get("pickup_has_elevator", False),
            dropoff_floor=validated_data.get("dropoff_floor") or 0,
            dropoff_has_elevator=validated_data.get("dropoff_has_elevator", False),
            assembly=validated_data.get("assembly", False),
            disassembly=validated_data.get("disassembly", False),
        )
        if requested_workers < minimum_workers:
            raise exceptions.ValidationError(
                {
                    "required_workers": "Selected worker count is too low for this move.",
                    "minimum_required_workers": minimum_workers,
                    "requested_workers": requested_workers,
                }
            )

    def _validate_locations(self, validated_data):
        pickup_lat = validated_data.get("pickup_latitude")
        pickup_lon = validated_data.get("pickup_longitude")
        dropoff_lat = validated_data.get("dropoff_latitude")
        dropoff_lon = validated_data.get("dropoff_longitude")
        if pickup_lat is None or pickup_lon is None:
            raise exceptions.ValidationError(
                {"pickup_location": "pickup_latitude and pickup_longitude are required."}
            )
        if dropoff_lat is None or dropoff_lon is None:
            raise exceptions.ValidationError(
                {"dropoff_location": "dropoff_latitude and dropoff_longitude are required."}
            )
        return pickup_lat, pickup_lon, dropoff_lat, dropoff_lon

    def _calculate_trip_distance(self, validated_data):
        pickup_lat, pickup_lon, dropoff_lat, dropoff_lon = self._validate_locations(validated_data)
        trip_distance_km = self._osrm_distance_km(
            float(pickup_lat),
            float(pickup_lon),
            float(dropoff_lat),
            float(dropoff_lon),
        )
        if trip_distance_km is None:
            trip_distance_km = self._haversine_distance_km(
                float(pickup_lat),
                float(pickup_lon),
                float(dropoff_lat),
                float(dropoff_lon),
            )
        return trip_distance_km

    def _create_order_from_serializer(self, serializer):
        pickup_lat = serializer.validated_data.get("pickup_latitude")
        pickup_lon = serializer.validated_data.get("pickup_longitude")
        required_workers = serializer.validated_data.get("required_workers", 0)
        required_vehicle_type = serializer.validated_data.get("required_vehicle_type")
        assembly = serializer.validated_data.get("assembly", False)
        disassembly = serializer.validated_data.get("disassembly", False)
        self._validate_worker_count(serializer.validated_data)
        self._validate_locations(serializer.validated_data)

        with transaction.atomic():
            if required_vehicle_type:
                vehicle, distance_km, office = self._select_office_vehicle(
                    float(pickup_lat),
                    float(pickup_lon),
                    required_vehicle_type,
                )
                if vehicle is None:
                    raise exceptions.ValidationError(
                        {"vehicle": "No available vehicles of the required type in nearby offices."}
                    )
                driver_profile = self._available_drivers_queryset(office).first()
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
                driver_profile, distance_km, office = self._select_office_driver(
                    float(pickup_lat),
                    float(pickup_lon),
                )
                vehicle = None
                if driver_profile is None:
                    raise exceptions.ValidationError(
                        {"driver": "No available drivers in nearby offices."}
                    )
            if distance_km is None:
                raise exceptions.ValidationError(
                    {"office_distance": "Failed to calculate distance to nearest office."}
                )

            trip_distance_km = self._calculate_trip_distance(serializer.validated_data)

            if required_vehicle_type:
                vehicle_type = required_vehicle_type
            elif vehicle is not None:
                vehicle_type = vehicle.vehicle_type
            else:
                raise exceptions.ValidationError(
                    {"vehicle": "Vehicle type is required to calculate price."}
                )

            price = self._calculate_order_price(
                serializer.validated_data,
                trip_distance_km,
                vehicle_type,
            )

            order = serializer.save(
                customer=self.request.user,
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
            driver_profile.availability = False
            driver_profile.save(update_fields=("availability",))
            if vehicle is not None:
                vehicle.is_available = False
                vehicle.save(update_fields=("is_available",))

            workers = self._select_office_workers(office, required_workers)
            if required_workers and len(workers) < required_workers:
                raise exceptions.ValidationError(
                    {
                        "workers": (
                            "The selected office does not have enough available workers."
                        ),
                        "required_workers": required_workers,
                        "available_workers": len(workers),
                        "office": office.id if office else None,
                    }
                )
            for worker_profile in workers:
                OrderWorker.objects.create(
                    order=order,
                    worker=worker_profile.user,
                    status=OrderWorker.WorkerStatus.ASSIGNED,
                )
            WorkerProfile.objects.filter(user_id__in=[w.user_id for w in workers]).update(availability=False)
            transaction.on_commit(
                lambda: self._notify_assignment(order, driver_profile.user, workers)
            )
            return order

    def perform_create(self, serializer):
        return self._create_order_from_serializer(serializer)

    def perform_update(self, serializer):
        with transaction.atomic():
            order = serializer.save()
            return order

    def _notify_assignment(self, order, driver_user, worker_profiles):
        self._send_assignment_email(driver_user, "Driver", order)
        self._send_assignment_push(driver_user, "Driver", order)
        for worker_profile in worker_profiles or []:
            self._send_assignment_email(worker_profile.user, "Worker", order)
            self._send_assignment_push(worker_profile.user, "Worker", order)

    def _send_assignment_push(self, user, role_label: str, order: Order):
        title = "New Order Assigned"
        body = f"Order #{order.id} assigned to you as {role_label}."
        data = {
            "type": "order_assigned",
            "order_id": order.id,
            "role": role_label.lower(),
        }
        return send_push_to_user(user, title=title, body=body, data=data)

    def _order_users(self, order: Order):
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

    def _notify_order_status(self, order: Order):
        status_messages = {
            Order.Status.DELIVERED: (
                "Order Delivered",
                f"Order #{order.id} has reached the dropoff location.",
                "order_delivered",
            ),
            Order.Status.COMPLETED: (
                "Order Completed",
                f"Order #{order.id} has been completed.",
                "order_completed",
            ),
            Order.Status.CANCELLED: (
                "Order Cancelled",
                f"Order #{order.id} has been cancelled.",
                "order_cancelled",
            ),
            Order.Status.IN_PROGRESS: (
                "Order In Progress",
                f"Order #{order.id} is now in progress.",
                "order_in_progress",
            ),
        }
        message = status_messages.get(order.status)
        if not message:
            return

        title, body, event_type = message
        data = {
            "type": event_type,
            "order_id": order.id,
            "status": order.status,
        }
        for user in self._order_users(order):
            send_push_to_user(user, title=title, body=body, data=data)

    def _send_assignment_email(self, user, role_label: str, order: Order):
        recipient_email = (user.email or "").strip()
        if not recipient_email:
            return

        subject = "New MoveLine order assigned"
        full_name = user.get_full_name().strip() or user.username
        message = (
            "Hello,"
            "A new MoveLine order has been assigned to you."
            f"Role: {role_label}"
            f"Order ID: {order.id}"
            f"Pickup: {order.pickup_address}"
            f"Dropoff: {order.dropoff_address}"
            "Please check your app for details."
            "MoveLine Support"
        )
        html_message = f"""
<div style="font-family: Arial, sans-serif; background:#f5f7fb; padding: 24px;">
  <div style="max-width: 520px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
    <h2 style="margin: 0 0 8px; color:#111827;">New Order Assigned</h2>
    <p style="margin: 0 0 16px; color:#374151;">Hello {full_name},</p>
    <p style="margin: 0 0 16px; color:#374151;">A new MoveLine order has been assigned to you.</p>
    <div style="background:#f3f4f6; padding: 16px; border-radius: 10px; margin-bottom: 16px;">
      <div style="font-size: 12px; letter-spacing: 1px; color:#6b7280; text-transform: uppercase;">Order Details</div>
      <div style="font-size: 14px; color:#374151; margin-top: 6px;">Role: {role_label}</div>
      <div style="font-size: 14px; color:#374151; margin-top: 6px;">Order ID: {order.id}</div>
      <div style="font-size: 14px; color:#374151; margin-top: 6px;">Pickup: {order.pickup_address}</div>
      <div style="font-size: 14px; color:#374151; margin-top: 6px;">Dropoff: {order.dropoff_address}</div>
    </div>
    <p style="margin: 0; color:#6b7280;">Please check your app for details.</p>
    <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;" />
    <p style="margin: 0; color:#9ca3af; font-size: 12px;">MoveLine Support</p>
  </div>
</div>
"""
        email = EmailMultiAlternatives(subject, message, settings.DEFAULT_FROM_EMAIL, [recipient_email])
        email.attach_alternative(html_message, "text/html")
        email.send()

    @action(detail=False, methods=["post"], url_path="calculate-price")
    def calculate_price(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        self._validate_worker_count(validated_data)

        vehicle_type = validated_data.get("required_vehicle_type")
        if not vehicle_type:
            raise exceptions.ValidationError(
                {"required_vehicle_type": "This field is required to calculate price."}
            )

        trip_distance_km = self._calculate_trip_distance(validated_data)
        price = self._calculate_order_price(validated_data, trip_distance_km, vehicle_type)
        return Response(
            {
                "estimated_distance_km": price["distance_km"],
                "required_vehicle_type": price["vehicle_type"],
                "required_workers": int(validated_data.get("required_workers") or 0),
                "price_breakdown": {
                    "per_km_rate": str(price["per_km_rate"]),
                    "distance_fee": str(price["distance_fee"]),
                    "workers_fee": str(price["workers_fee"]),
                    "assembly_fee": str(price["assembly_fee"]),
                    "disassembly_fee": str(price["disassembly_fee"]),
                    "floor_fee": str(price["floor_fee"]),
                },
                "estimated_price": str(price["total_price"]),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="mark-available")
    def mark_available(self, request, pk=None):
        order = self.get_object()
        was_completed = order.status == Order.Status.COMPLETED
        with transaction.atomic():
            if order.driver_id:
                DriverProfile.objects.filter(user_id=order.driver_id).update(availability=True)
            if order.vehicle_id:
                Vehicle.objects.filter(id=order.vehicle_id).update(is_available=True)
            order.workers.through.objects.filter(order=order).update(status=OrderWorker.WorkerStatus.COMPLETED)
            WorkerProfile.objects.filter(
                user_id__in=order.workers.values_list("id", flat=True)
            ).update(availability=True)
            order.status = Order.Status.COMPLETED
            order._skip_status_notification = True
            order.save(update_fields=("status",))
            if not was_completed:
                transaction.on_commit(
                    lambda: notify_order_status_changed(
                        order,
                        status_value=Order.Status.COMPLETED,
                    )
                )
        return Response({"detail": "Availability updated."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="mark-delivered")
    def mark_delivered(self, request, pk=None):
        order = self.get_object()
        if order.status == Order.Status.COMPLETED:
            return Response(
                {"detail": "Order is already completed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order.status = Order.Status.DELIVERED
        order.save(update_fields=("status",))
        return Response({"detail": "Order marked as delivered."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="send-status-notification")
    def send_status_notification(self, request, pk=None):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response(
                {"detail": "Only admins can send manual order status notifications."},
                status=status.HTTP_403_FORBIDDEN,
            )

        order = self.get_object()
        serializer = OrderStatusNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        status_value = serializer.validated_data["status"]
        notify_order_status_changed(order, status_value=status_value)
        return Response(
            {
                "detail": "Order status notification sent.",
                "order": order.id,
                "status": status_value,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="send-assignment-notification")
    def send_assignment_notification(self, request, pk=None):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response(
                {"detail": "Only admins can send manual assignment notifications."},
                status=status.HTTP_403_FORBIDDEN,
        )

        order = self.get_object()
        notification_data = request.data.copy()
        if "role" not in notification_data and "state" in notification_data:
            notification_data["role"] = notification_data["state"]
        serializer = OrderAssignmentNotificationSerializer(data=notification_data)
        serializer.is_valid(raise_exception=True)
        role = serializer.validated_data["role"]

        recipients = []
        if role in {"driver", "all"} and order.driver_id:
            recipients.append((order.driver, "Driver"))
        if role in {"worker", "all"}:
            recipients.extend((worker, "Worker") for worker in order.workers.all())

        sent_count = 0
        for user, role_label in recipients:
            sent_count += self._send_assignment_push(user, role_label, order)

        return Response(
            {
                "detail": "Order assignment notification requested.",
                "order": order.id,
                "role": role,
                "recipient_count": len(recipients),
                "sent_count": sent_count,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="my-orders")
    def my_orders(self, request):
        user = request.user
        qs = (
            self.get_queryset()
            .filter(
                models.Q(customer=user)
                | models.Q(driver=user)
                | models.Q(workers=user)
            )
            .distinct()
        )
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="my-driver-orders")
    def my_driver_orders(self, request):
        user = request.user
        qs = self.get_queryset().filter(driver=user)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="my-worker-orders")
    def my_worker_orders(self, request):
        user = request.user
        qs = self.get_queryset().filter(workers=user).distinct()
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OrderWorkerViewSet(viewsets.ModelViewSet):
    queryset = OrderWorker.objects.select_related("order", "worker").all()
    serializer_class = OrderWorkerSerializer
