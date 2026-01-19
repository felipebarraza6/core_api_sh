from django.contrib import admin
from .models import Document, DocumentType

@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "internal")
    search_fields = ("name",)

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("name", "document_type", "get_relation", "valid_until", "internal_only", "is_active", "created_at")
    list_filter = ("document_type", "internal_only", "is_active", "client", "project", "point_catchment")
    search_fields = ("name", "description", "tags")
    date_hierarchy = "created"
    
    fieldsets = (
        (None, {
            'fields': ('name', 'document_type', 'file', 'description', 'tags', 'is_active', 'internal_only', 'valid_until')
        }),
        ('Relación con Entidad (Opcional)', {
            'fields': ('client', 'project', 'point_catchment', 'technical_survey', 'crm_task'),
            'description': 'Relacione este documento con una entidad específica. Seleccione solo una si es un documento específico.'
        }),
        ('Metadata', {
            'fields': ('created_by',),
            'classes': ('collapse',),
        }),
    )

    def get_relation(self, obj):
        if obj.point_catchment: return f"Punto: {obj.point_catchment}"
        if obj.project: return f"Proyecto: {obj.project}"
        if obj.client: return f"Cliente: {obj.client}"
        if obj.technical_survey: return f"Levantamiento: {obj.technical_survey}"
        if obj.crm_task: return f"Tarea: {obj.crm_task}"
        return "General"
    get_relation.short_description = 'Relacionado con'

    def created_at(self, obj):
        return obj.created
    created_at.short_description = 'Fecha Creación'

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
