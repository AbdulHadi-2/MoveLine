from chat.routing import websocket_urlpatterns as chat_websocket_urlpatterns
from tracking.routing import websocket_urlpatterns as tracking_websocket_urlpatterns

websocket_urlpatterns = tracking_websocket_urlpatterns + chat_websocket_urlpatterns

__all__ = ["websocket_urlpatterns"]
