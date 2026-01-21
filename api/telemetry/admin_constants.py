from django.contrib import admin
from .models.constants_system import ConstantDefinition, ConstantApplication

class ConstantApplicationInline(admin.TabularInline):
    model = ConstantApplication
    extra = 1
    fields = ('start_date', 'end_date', 'new_value', 'is_active')

@admin.register(ConstantDefinition)
class ConstantDefinitionAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'constant_type', 'value_numeric', 'point', 'device', 'is_active')
    list_filter = ('constant_type', 'is_active')
    search_fields = ('name', 'code', 'description', 'point__title', 'device__name')
    autocomplete_fields = ('point', 'device')
    readonly_fields = ('created', 'modified')
    inlines = [ConstantApplicationInline]

@admin.register(ConstantApplication)
class ConstantApplicationAdmin(admin.ModelAdmin):
    list_display = ('constant', 'start_date', 'end_date', 'new_value', 'is_active')
    list_filter = ('is_active', 'start_date')
    search_fields = ('constant__name', 'change_reason')
    readonly_fields = ('created', 'modified')
