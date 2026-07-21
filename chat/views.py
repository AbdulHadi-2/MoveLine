from django.db import models
from rest_framework import permissions, viewsets

from .models import ChatMessage
from .serializers import ChatMessageSerializer


class ChatMessageViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ChatMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = ChatMessage.objects.select_related("order", "sender")
        if not (user.is_staff or user.is_superuser):
            queryset = queryset.filter(
                models.Q(order__customer=user)
                | models.Q(order__driver=user)
                | models.Q(order__workers=user)
            ).distinct()

        order_id = self.request.query_params.get("order")
        if order_id:
            queryset = queryset.filter(order_id=order_id)
        return queryset
