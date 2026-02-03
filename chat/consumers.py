import json

from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.order_id = self.scope["url_route"]["kwargs"]["order_id"]
        self.group_name = f"chat_{self.order_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        payload = json.loads(text_data)
        message = payload.get("message")
        if not message:
            return

        outgoing = {
            "order": int(self.order_id),
            "message": message,
            "sent_at": timezone.now().isoformat(),
        }

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat.message",
                "payload": outgoing,
            },
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event["payload"], ensure_ascii=False))
