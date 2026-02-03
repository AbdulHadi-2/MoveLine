import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from .models import Tracking
from orders.models import Order


class TrackingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.order_id = self.scope["url_route"]["kwargs"]["order_id"]
        self.group_name = f"tracking_{self.order_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        tracking = await self._get_tracking()
        if tracking:
            remaining_km = await self._remaining_distance_km(tracking)
            await self.send(
                text_data=json.dumps(
                    {
                        "order": tracking.order_id,
                        "driver": tracking.driver_id,
                        "current_latitude": str(tracking.current_latitude) if tracking.current_latitude is not None else None,
                        "current_longitude": str(tracking.current_longitude) if tracking.current_longitude is not None else None,
                        "heading": str(tracking.heading) if tracking.heading is not None else None,
                        "speed_kmh": str(tracking.speed_kmh) if tracking.speed_kmh is not None else None,
                        "last_ping_at": tracking.last_ping_at.isoformat() if tracking.last_ping_at else None,
                        "is_active": tracking.is_active,
                        "remaining_distance_km": remaining_km,
                    }
                )
            )

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        payload = json.loads(text_data)

        updated = await self._update_tracking(payload)
        if updated is None:
            return

        remaining_km = await self._remaining_distance_km_from_payload(updated)
        updated["remaining_distance_km"] = remaining_km

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "tracking.update",
                "payload": updated,
            },
        )

    async def tracking_update(self, event):
        await self.send(text_data=json.dumps(event["payload"]))

    @sync_to_async
    def _get_tracking(self):
        try:
            return Tracking.objects.select_related("order", "driver").get(order_id=self.order_id)
        except Tracking.DoesNotExist:
            return None

    @sync_to_async
    def _update_tracking(self, payload):
        try:
            tracking = Tracking.objects.select_related("order", "driver").get(order_id=self.order_id)
        except Tracking.DoesNotExist:
            return None

        fields = {}
        if "current_latitude" in payload:
            fields["current_latitude"] = payload.get("current_latitude")
        if "current_longitude" in payload:
            fields["current_longitude"] = payload.get("current_longitude")
        if "heading" in payload:
            fields["heading"] = payload.get("heading")
        if "speed_kmh" in payload:
            fields["speed_kmh"] = payload.get("speed_kmh")
        if "is_active" in payload:
            fields["is_active"] = payload.get("is_active")

        if fields:
            for key, value in fields.items():
                setattr(tracking, key, value)
            tracking.last_ping_at = timezone.now()
            tracking.save(update_fields=(*fields.keys(), "last_ping_at"))

            order = tracking.order
            if self._is_at_dropoff(order, tracking):
                if order.status != Order.Status.DELIVERED:
                    order.status = Order.Status.DELIVERED
                    order.save(update_fields=("status",))

        return {
            "order": tracking.order_id,
            "driver": tracking.driver_id,
            "current_latitude": str(tracking.current_latitude) if tracking.current_latitude is not None else None,
            "current_longitude": str(tracking.current_longitude) if tracking.current_longitude is not None else None,
            "heading": str(tracking.heading) if tracking.heading is not None else None,
            "speed_kmh": str(tracking.speed_kmh) if tracking.speed_kmh is not None else None,
            "last_ping_at": tracking.last_ping_at.isoformat() if tracking.last_ping_at else None,
            "is_active": tracking.is_active,
        }

    def _is_at_dropoff(self, order, tracking) -> bool:
        if (
            order.dropoff_latitude is None
            or order.dropoff_longitude is None
            or tracking.current_latitude is None
            or tracking.current_longitude is None
        ):
            return False
        try:
            dropoff_lat = round(float(order.dropoff_latitude), 5)
            dropoff_lon = round(float(order.dropoff_longitude), 5)
            current_lat = round(float(tracking.current_latitude), 5)
            current_lon = round(float(tracking.current_longitude), 5)
        except (TypeError, ValueError):
            return False
        return dropoff_lat == current_lat and dropoff_lon == current_lon

    @sync_to_async
    def _remaining_distance_km_from_payload(self, payload):
        try:
            tracking = Tracking.objects.select_related("order").get(order_id=self.order_id)
        except Tracking.DoesNotExist:
            return None
        return self._osrm_distance_to_dropoff(
            tracking,
            payload.get("current_latitude"),
            payload.get("current_longitude"),
        )

    @sync_to_async
    def _remaining_distance_km(self, tracking):
        return self._osrm_distance_to_dropoff(
            tracking,
            str(tracking.current_latitude) if tracking.current_latitude is not None else None,
            str(tracking.current_longitude) if tracking.current_longitude is not None else None,
        )

    def _osrm_distance_to_dropoff(self, tracking, current_lat, current_lon):
        order = tracking.order
        if not (order.dropoff_latitude and order.dropoff_longitude and current_lat and current_lon):
            return None

        base_url = "http://router.project-osrm.org/route/v1/driving/"
        coords = f"{current_lon},{current_lat};{order.dropoff_longitude},{order.dropoff_latitude}"
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
        return round(distance_meters / 1000.0, 2)
