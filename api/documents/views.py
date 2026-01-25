
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import HttpResponse

from .models import DocumentTemplate, Document
from .engine.generator import DocumentGenerator
from api.core.models.utils import ModelApi

class DocumentTemplateViewSet(viewsets.ModelViewSet):
    """
    CRUD de Plantillas + Endpoint de Previsualización.
    """
    queryset = DocumentTemplate.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    
    # Serializer dummy por brevedad del ejemplo, idealmente crear uno real
    # Pero para preview no lo necesitamos estricto
    def get_serializer_class(self):
        from rest_framework import serializers
        class TemplateSerializer(serializers.ModelSerializer):
            class Meta:
                model = DocumentTemplate
                fields = '__all__'
        return TemplateSerializer

    @action(detail=True, methods=['post'], url_path='preview')
    def preview(self, request, pk=None):
        """
        Retorna el HTML renderizado para previsualizar estilos.
        Body: JSON con el contexto de prueba (ej: {"nombre": "Test"}).
        """
        template = self.get_object()
        context = request.data
        
        if template.engine_type != 'pdf':
            return Response(
                {"error": "Previsualización solo disponible para plantillas PDF/HTML"}, 
                status=400
            )

        try:
            gen = DocumentGenerator(template)
            html_content = gen.render_html(context)
            # Retornamos HTML directo para que el iframe lo muestre
            return HttpResponse(html_content, content_type='text/html')
        except Exception as e:
            return Response(
                {"error": f"Error renderizando template: {str(e)}"}, 
                status=500
            )


class DocumentTypeViewSet(viewsets.ModelViewSet):
    """
    CRUD de Tipos de Documento.
    """
    from .models import DocumentType
    queryset = DocumentType.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        from rest_framework import serializers
        class DocumentTypeSerializer(serializers.ModelSerializer):
            class Meta:
                model = self.queryset.model
                fields = '__all__'
        return DocumentTypeSerializer
