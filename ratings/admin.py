from django.contrib import admin

from .models import OrderRatingFeedback, PerformanceAlert, Rating


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ("order", "customer", "rated_user", "target_role", "score", "created_at")
    search_fields = ("order__id", "customer__email", "rated_user__email", "feedback")
    list_filter = ("target_role", "score", "created_at")


@admin.register(OrderRatingFeedback)
class OrderRatingFeedbackAdmin(admin.ModelAdmin):
    list_display = ("order", "customer", "created_at", "updated_at")
    search_fields = ("order__id", "customer__email", "feedback")


@admin.register(PerformanceAlert)
class PerformanceAlertAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "target_role",
        "level",
        "status",
        "average_rating",
        "low_rating_count",
        "suspended_until",
        "created_at",
    )
    list_filter = ("target_role", "level", "status", "created_at")
    search_fields = ("user__username", "user__email", "reason")
