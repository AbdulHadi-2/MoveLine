from django.urls import re_path

from .consumers import TrackingConsumer

websocket_urlpatterns = [
    re_path(r"ws/tracking/(?P<order_id>\d+)/$", TrackingConsumer.as_asgi()),
]
