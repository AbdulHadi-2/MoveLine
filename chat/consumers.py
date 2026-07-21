import json
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth import get_user_model
from django.db import models
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

from orders.models import Order
from users.notifications import send_push_to_user

from .models import ChatMessage


User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.order_id = self.scope["url_route"]["kwargs"]["order_id"]
        self.group_name = f"chat_{self.order_id}"
        self.user = await self._authenticate_user()
        if self.user is None:
            await self.close(code=4401)
            return

        has_access = await self._user_has_order_access(self.user.id, self.order_id)
        if not has_access:
            await self.close(code=4403)
            return

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

        chat_message = await self._save_message(message)
        outgoing = await self._serialize_message(chat_message)
        await self._notify_chat_recipients(chat_message.id)

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat.message",
                "payload": outgoing,
            },
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event["payload"], ensure_ascii=False))

    async def _authenticate_user(self):
        query_string = self.scope.get("query_string", b"").decode("utf-8")
        params = parse_qs(query_string)
        token = (params.get("token") or [None])[0]
        if not token:
            return None
        return await self._get_user_from_token(token)

    @database_sync_to_async
    def _get_user_from_token(self, token):
        try:
            access_token = AccessToken(token)
        except (InvalidToken, TokenError):
            return None
        user_id = access_token.get("user_id")
        if not user_id:
            return None
        return User.objects.filter(id=user_id, is_active=True).first()

    @database_sync_to_async
    def _user_has_order_access(self, user_id, order_id):
        user = User.objects.filter(id=user_id).first()
        if user is None:
            return False
        if user.is_staff or user.is_superuser:
            return Order.objects.filter(id=order_id).exists()
        return (
            Order.objects.filter(id=order_id)
            .filter(
                models.Q(customer_id=user_id)
                | models.Q(driver_id=user_id)
                | models.Q(workers__id=user_id)
            )
            .distinct()
            .exists()
        )

    @database_sync_to_async
    def _save_message(self, message):
        return ChatMessage.objects.create(
            order_id=self.order_id,
            sender=self.user,
            message=message,
        )

    @database_sync_to_async
    def _serialize_message(self, chat_message):
        sender_name = chat_message.sender.get_full_name().strip() or chat_message.sender.username
        return {
            "id": chat_message.id,
            "order": chat_message.order_id,
            "sender": chat_message.sender_id,
            "sender_full_name": sender_name,
            "sender_role": chat_message.sender.role,
            "message": chat_message.message,
            "created_at": chat_message.created_at.isoformat(),
        }

    @database_sync_to_async
    def _notify_chat_recipients(self, chat_message_id):
        chat_message = (
            ChatMessage.objects.select_related("order", "sender")
            .prefetch_related("order__workers")
            .get(id=chat_message_id)
        )
        order = chat_message.order
        sender = chat_message.sender
        sender_name = sender.get_full_name().strip() or sender.username
        recipients = []
        if order.customer_id:
            recipients.append(order.customer)
        if order.driver_id:
            recipients.append(order.driver)
        recipients.extend(list(order.workers.all()))

        seen = {sender.id}
        for user in recipients:
            if not user or user.id in seen:
                continue
            seen.add(user.id)
            send_push_to_user(
                user,
                title="New Chat Message",
                body=f"{sender_name}: {chat_message.message[:120]}",
                data={
                    "type": "chat_message",
                    "order_id": order.id,
                    "message_id": chat_message.id,
                    "sender_id": sender.id,
                    "sender_role": sender.role,
                },
            )
