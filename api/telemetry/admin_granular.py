from django.contrib import admin
from .models.granular_telemetry import DataStream, DataPoint, VariableDefinition, DataAggregation

@admin.register(DataStream)
class DataStreamAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'device', 'stream_type', 'is_active')
    list_filter = ('stream_type', 'is_active', 'device')
    search_fields = ('name', 'code', 'device__name')
    autocomplete_fields = ('device',)
    readonly_fields = ('created', 'modified')

@admin.register(DataPoint)
class DataPointAdmin(admin.ModelAdmin):
    list_display = ('stream', 'collected_at', 'raw_value', 'processed_value', 'quality', 'is_valid')
    list_filter = ('stream__stream_type', 'quality', 'is_valid', 'collected_at')
    search_fields = ('stream__name', 'raw_value', 'processed_value')
    autocomplete_fields = ('stream', 'device', 'point')
    readonly_fields = ('received_at', 'processed_at', 'created', 'modified')

@admin.register(VariableDefinition)
class VariableDefinitionAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'variable_type', 'unit')
    list_filter = ('variable_type',)
    search_fields = ('name', 'code', 'description')
    readonly_fields = ('created', 'modified')

@admin.register(DataAggregation)
class DataAggregationAdmin(admin.ModelAdmin):
    list_display = ('point', 'variable_definition', 'period', 'period_start', 'avg_value', 'count')
    list_filter = ('period', 'variable_definition', 'period_start')
    search_fields = ('point__title', 'variable_definition__name')
    autocomplete_fields = ('point', 'variable_definition')
    readonly_fields = ('created', 'modified')
