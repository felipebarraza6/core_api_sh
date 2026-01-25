from rest_framework import viewsets, permissions, filters, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone

from .models import ComplianceVoucher, PointComplianceConfig, ComplianceProvider
from .serializers import (
    ComplianceVoucherSerializer, 
    PointComplianceConfigSerializer,
    ComplianceProviderSerializer
)

class ComplianceVoucherViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Vista de sólo lectura para consultar la evidencia de reportes (Vouchers).
    Permite filtrar por punto, estado y rango de fechas.
    """
    queryset = ComplianceVoucher.objects.all().order_by('-data_timestamp')
    serializer_class = ComplianceVoucherSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['point', 'provider', 'voucher_status']
    ordering_fields = ['data_timestamp', 'generated_at']

    def get_queryset(self):
        # Allow extra filtering via query params for dates
        qs = super().get_queryset()
        start = self.request.query_params.get('start_date')
        end = self.request.query_params.get('end_date')
        if start:
            qs = qs.filter(data_timestamp__gte=start)
        if end:
            qs = qs.filter(data_timestamp__lte=end)
        return qs

class ComplianceConfigViewSet(viewsets.ModelViewSet):
    """
    Gestión de Configuración de Cumplimiento por Punto.
    Permite activar/desactivar envíos.
    """
    queryset = PointComplianceConfig.objects.all()
    serializer_class = PointComplianceConfigSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['point', 'provider', 'is_active']

class ComplianceDashboardViewSet(viewsets.ViewSet):
    """
    Dashboard de Cumplimiento Normativo.
    Retorna métricas agregadas para la UI.
    """
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def status_summary(self, request):
        """
        Resumen global de estados de envío del día actual.
        """
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Count vouchers today
        stats = ComplianceVoucher.objects.filter(
            data_timestamp__gte=today_start
        ).aggregate(
            total=Count('id'),
            sent=Count('id', filter=Q(voucher_status='SENT')),
            error=Count('id', filter=Q(voucher_status='ERROR')),
            pending=Count('id', filter=Q(voucher_status='PENDING'))
        )
        
        # Calculate health score
        if stats['total'] > 0:
            health = (stats['sent'] / stats['total']) * 100
        else:
            health = 100 # No news is good news? Or N/A. Let's say 100 for optimism if no uploads scheduled.
            
        return Response({
            'period': 'Today',
            'stats': stats,
            'health_score': round(health, 1)
        })

    @action(detail=False, methods=['get'])
    def providers(self, request):
        queryset = ComplianceProvider.objects.filter(is_active=True)
        serializer = ComplianceProviderSerializer(queryset, many=True)
        return Response(serializer.data)
