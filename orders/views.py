import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from decimal import Decimal
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import models, transaction
from rest_framework import exceptions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Order, OrderWorker
from .serializers import OrderSerializer, OrderWorkerSerializer
from users.models import DriverProfile, Office, WorkerProfile
from vehicles.models import Vehicle
from tracking.models import Tracking


class OrderViewSet(viewsets.ModelViewSet):
    queryset = (
        Order.objects.select_related("customer", "driver", "vehicle")
        .prefetch_related("order_workers", "items")
        .all()
    )
    serializer_class = OrderSerializer

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

    def _select_office_vehicle_driver(
        self,
        pickup_lat: float,
        pickup_lon: float,
        required_vehicle_type: str,
    ) -> tuple[DriverProfile | None, Vehicle | None, float | None, Office | None]:
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
            if not vehicle:
                continue
            driver_profile = (
                DriverProfile.objects.select_related("user")
                .filter(
                    office=office,
                    availability=True,
                )
                .first()
            )
            if driver_profile:
                return driver_profile, vehicle, distance, office

        return None, None, None, None

    def _select_office_driver(
        self,
        pickup_lat: float,
        pickup_lon: float,
    ) -> tuple[DriverProfile | None, float | None, Office | None]:
        office_distances = self._offices_by_distance(pickup_lat, pickup_lon)
        for distance, office in office_distances:
            driver_profile = (
                DriverProfile.objects.select_related("user")
                .filter(
                    office=office,
                    availability=True,
                )
                .first()
            )
            if driver_profile:
                return driver_profile, distance, office
        return None, None, None

    def _select_office_workers(self, office: Office | None, required_count: int) -> list[WorkerProfile]:
        if required_count <= 0 or office is None:
            return []
        return list(
            WorkerProfile.objects.select_related("user")
            .filter(office=office, availability=True)[:required_count]
        )

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
                continue
            office_distances.append((distance, office))
        office_distances.sort(key=lambda item: item[0])
        return office_distances

    def perform_create(self, serializer):
        pickup_lat = serializer.validated_data.get("pickup_latitude")
        pickup_lon = serializer.validated_data.get("pickup_longitude")
        required_workers = serializer.validated_data.get("required_workers", 0)
        required_vehicle_type = serializer.validated_data.get("required_vehicle_type")
        assembly = serializer.validated_data.get("assembly", False)
        disassembly = serializer.validated_data.get("disassembly", False)
        dropoff_lat = serializer.validated_data.get("dropoff_latitude")
        dropoff_lon = serializer.validated_data.get("dropoff_longitude")
        if pickup_lat is None or pickup_lon is None:
            raise exceptions.ValidationError(
                {"pickup_location": "pickup_latitude and pickup_longitude are required."}
            )
        if dropoff_lat is None or dropoff_lon is None:
            raise exceptions.ValidationError(
                {"dropoff_location": "dropoff_latitude and dropoff_longitude are required."}
            )

        with transaction.atomic():
            if required_vehicle_type:
                driver_profile, vehicle, distance_km, office = self._select_office_vehicle_driver(
                    float(pickup_lat),
                    float(pickup_lon),
                    required_vehicle_type,
                )
                if vehicle is None:
                    raise exceptions.ValidationError(
                        {"vehicle": "No available vehicles of the required type in nearby offices."}
                    )
                if driver_profile is None:
                    raise exceptions.ValidationError(
                        {"driver": "No available drivers in nearby offices."}
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

            trip_distance_km = self._osrm_distance_km(
                float(pickup_lat),
                float(pickup_lon),
                float(dropoff_lat),
                float(dropoff_lon),
            )
            if trip_distance_km is None:
                raise exceptions.ValidationError(
                    {"distance": "Failed to calculate distance between pickup and dropoff."}
                )

            if required_vehicle_type:
                vehicle_type = required_vehicle_type
            elif vehicle is not None:
                vehicle_type = vehicle.vehicle_type
            else:
                raise exceptions.ValidationError(
                    {"vehicle": "Vehicle type is required to calculate price."}
                )

            per_km_rates = {
                Order.VehicleSize.SMALL: Decimal("5.0"),
                Order.VehicleSize.MEDIUM: Decimal("7.5"),
                Order.VehicleSize.LARGE: Decimal("10.0"),
            }
            per_km_rate = per_km_rates.get(vehicle_type)
            if per_km_rate is None:
                raise exceptions.ValidationError({"vehicle": "Unknown vehicle type for pricing."})

            total_cost = (Decimal(str(trip_distance_km)) * per_km_rate).quantize(Decimal("0.01"))
            if required_workers:
                total_cost += Decimal("5.0") * Decimal(required_workers)
            if assembly:
                total_cost += Decimal("10.0")
            if disassembly:
                total_cost += Decimal("10.0")

            order = serializer.save(
                customer=self.request.user,
                driver=driver_profile.user,
                vehicle=vehicle,
                status=Order.Status.IN_PROGRESS,
                estimated_distance_km=trip_distance_km,
                estimated_price=total_cost,
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
                    {"workers": "Not enough available workers in the selected office."}
                )
            for worker_profile in workers:
                OrderWorker.objects.create(
                    order=order,
                    worker=worker_profile.user,
                    status=OrderWorker.WorkerStatus.ASSIGNED,
                )
            WorkerProfile.objects.filter(user_id__in=[w.user_id for w in workers]).update(availability=False)
            transaction.on_commit(
                lambda: self._notify_assignment_emails(order, driver_profile.user, workers)
            )
            return order

    def perform_update(self, serializer):
        with transaction.atomic():
            order = serializer.save()
            return order

    def _notify_assignment_emails(self, order, driver_user, worker_profiles):
        self._send_assignment_email(driver_user, "Driver", order)
        for worker_profile in worker_profiles or []:
            self._send_assignment_email(worker_profile.user, "Worker", order)

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

    @action(detail=True, methods=["post"], url_path="mark-available")
    def mark_available(self, request, pk=None):
        order = self.get_object()
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
            order.save(update_fields=("status",))
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
