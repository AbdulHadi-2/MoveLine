from rest_framework import serializers

from .models import ChatMessage


class ChatMessageSerializer(serializers.ModelSerializer):
    sender_full_name = serializers.CharField(source="sender.get_full_name", read_only=True)
    sender_role = serializers.CharField(source="sender.role", read_only=True)

    class Meta:
        model = ChatMessage
        fields = (
            "id",
            "order",
            "sender",
            "sender_full_name",
            "sender_role",
            "message",
            "created_at",
        )
        read_only_fields = fields
