from django.contrib import admin

from api.telemetry.models.providers import (
    TelemetryProvider,
    CatchmentPointProvider,
)

@admin.register(TelemetryProvider)
class TelemetryProviderAdmin(admin.ModelAdmin):
    list_display = ("name", "provider_type", "is_active")
    list_filter = ("provider_type", "is_active")
    search_fields = ("name",)

@admin.register(CatchmentPointProvider)
class CatchmentPointProviderAdmin(admin.ModelAdmin):
    list_display = ("point", "provider", "is_active", "priority")
    list_filter = ("provider", "is_active")
    search_fields = ("point__title", "provider__name")
    autocomplete_fields = ("point", "provider")
