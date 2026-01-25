from django.contrib import admin
from .models import Document, DocumentType, DocumentTemplate, ScheduledGeneration
from .engine.generator import DocumentGenerator

@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "internal", "created")
    search_fields = ("name",)

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "name", "document_type", "target_entity", "valid_until", "internal_only", "is_active"
    )
    list_filter = ("document_type", "internal_only", "is_active", "created")
    search_fields = ("name", "description", "tags")
    autocomplete_fields = ["created_by", "client", "project", "point_catchment"]
    
    def target_entity(self, obj):
        return str(obj)
    target_entity.short_description = "Entidad"

@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "engine_type", "created")
    list_filter = ("engine_type",)
    search_fields = ("name", "code")

@admin.register(ScheduledGeneration)
class ScheduledGenerationAdmin(admin.ModelAdmin):
    list_display = ("name", "template", "cron_expression", "is_active", "last_run", "next_run")
    list_filter = ("is_active", "template")
    actions = ['run_now']
    
    def run_now(self, request, queryset):
        success = 0
        for task in queryset:
            try:
                # Simular contexto (en prod, esto viene dinámico)
                ctx = task.static_context
                gen = DocumentGenerator(task.template)
                
                # Generar
                path = gen.generate(ctx, output_name=f"{task.name}_manual")
                
                # Crear registro Document
                from django.core.files import File
                doc = Document(
                    name=f"Manual Run: {task.name}",
                    document_type=DocumentType.objects.first(), # Fallback
                    description="Generado manualmente desde admin",
                    internal_only=True
                )
                with open(path, 'rb') as f:
                    doc.file.save(os.path.basename(path), File(f))
                doc.save()
                
                success += 1
            except Exception as e:
                self.message_user(request, f"Error en {task.name}: {e}", level='error')
                
        self.message_user(request, f"Ejecutados {success} trabajos con éxito.")
    run_now.short_description = "⚡ Ejecutar Generación Ahora"

