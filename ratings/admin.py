from django.contrib import admin

from .models import Rating


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ("order", "score", "created_at")
    search_fields = ("order__id", "feedback")
    list_filter = ("score", "created_at")
