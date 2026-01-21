from django.contrib import admin
from .models import Notification, NotificationResponse

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'type_notification', 'point_catchment', 'is_read', 'created')
    list_filter = ('type_notification', 'is_read', 'created')
    search_fields = ('title', 'message', 'point_catchment__title')
    readonly_fields = ('created', 'modified')
    autocomplete_fields = ('point_catchment',)

@admin.register(NotificationResponse)
class NotificationResponseAdmin(admin.ModelAdmin):
    list_display = ('notification', 'user', 'created')
    list_filter = ('user', 'created')
    search_fields = ('notification__title', 'response', 'user__username')
    readonly_fields = ('created', 'modified')
    raw_id_fields = ('user', 'notification')
