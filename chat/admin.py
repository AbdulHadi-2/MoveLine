from django.contrib import admin

from .models import ChatMessage


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("order", "sender", "short_message", "created_at")
    list_filter = ("created_at",)
    search_fields = ("order__id", "sender__username", "sender__email", "message")
    autocomplete_fields = ("order", "sender")
    readonly_fields = ("created_at",)

    def short_message(self, obj):
        return obj.message[:80]
