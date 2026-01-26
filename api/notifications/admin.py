"""Notifications Admin Configuration."""

from django.contrib import admin
from api.notifications.models import Notification, NotificationResponse

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "point_catchment", "type_notification", "is_active", "created")
    list_filter = ("type_notification", "is_active", "point_catchment__project__name")
    search_fields = ("title", "message", "point_catchment__title")
    autocomplete_fields = ("point_catchment",)

@admin.register(NotificationResponse)
class NotificationResponseAdmin(admin.ModelAdmin):
    list_display = ("notification", "user", "created")
    search_fields = ("notification__title", "user__username", "response")
    autocomplete_fields = ("notification", "user")
