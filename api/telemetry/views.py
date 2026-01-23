from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta

from api.telemetry.models import CatchmentPoint, TelemetryRecord
from .serializers import UnifiedCatchmentPointSerializer, UnifiedTelemetryRecordSerializer

class TelemetryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet Unificado de Telemetría.
    Centraliza el acceso a puntos de captación y sus registros históricos.
    """
    queryset = CatchmentPoint.objects.filter(is_active=True).select_related('project')
    serializer_class = UnifiedCatchmentPointSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return self.queryset
        # Filtrado por permisos de usuario
        from django.db.models import Q
        return self.queryset.filter(Q(owner_user=user) | Q(users_viewers=user)).distinct()

    @action(detail=True, methods=['get'])
    def records(self, request, pk=None):
        """
        Retorna los registros de telemetría para un punto específico.
        Soporta parámetros: limit, hours.
        """
        point = self.get_object()
        
        limit = int(request.query_params.get('limit', 100))
        hours = request.query_params.get('hours')
        
        queryset = TelemetryRecord.objects.filter(point=point)
        
        if hours:
            since = timezone.now() - timedelta(hours=int(hours))
            queryset = queryset.filter(timestamp__gte=since)
            
        records = queryset.order_by('-timestamp')[:limit]
        serializer = UnifiedTelemetryRecordSerializer(records, many=True)
        
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def dashboard_summary(self, request):
        """
        Resumen optimizado para el dashboard.
        Simula el comportamiento de v2/dashboard/summary/ pero con lógica centralizada.
        """
        points = self.get_queryset()
        serializer = self.get_serializer(points, many=True)
        
        return Response({
            "points": serializer.data,
            "last_updated": timezone.now().isoformat(),
            "status": "ready"
        })
