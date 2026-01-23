"""
Exportador de métricas Prometheus para SmartHydro.
Expone métricas de telemetría, DGA, SMA y sistema.
"""
from prometheus_client import Counter, Gauge, Histogram, Info
from django.db.models import Count
from api.telemetry.models import (
    CatchmentPoint,
)
from api.compliance.models import PointComplianceConfig
from api.telemetry.models.telemetry import TelemetryRecord
from api.notifications.models import Notification
from datetime import datetime, timedelta
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


# ============================================
# MÉTRICAS DE TELEMETRÍA
# ============================================

# Contadores de ingestión
telemetry_ingestion_total = Counter(
    'smarthydro_telemetry_ingestion_total',
    'Total de registros de telemetría procesados',
    ['point_id', 'point_name', 'project', 'client', 'frequency', 'provider', 'protocol']
)

telemetry_ingestion_errors = Counter(
    'smarthydro_telemetry_ingestion_errors_total',
    'Errores en el procesamiento de telemetría',
    ['point_id', 'point_name', 'project', 'client', 'error_type', 'protocol']
)

# Gauges para valores actuales
telemetry_flow_current = Gauge(
    'smarthydro_telemetry_flow_liters_per_second',
    'Caudal actual en L/s',
    ['point_id', 'point_name', 'project', 'client', 'frequency']
)

telemetry_total_current = Gauge(
    'smarthydro_telemetry_total_cubic_meters',
    'Total acumulado en m³',
    ['point_id', 'point_name', 'project', 'client', 'frequency']
)

telemetry_nivel_current = Gauge(
    'smarthydro_telemetry_nivel_meters',
    'Nivel actual en metros',
    ['point_id', 'point_name', 'project', 'client', 'frequency']
)

telemetry_daily_consumption = Gauge(
    'smarthydro_telemetry_daily_consumption_cubic_meters',
    'Consumo diario en m³',
    ['point_id', 'point_name', 'project', 'client', 'frequency']
)

# Tiempo desde última recepción
telemetry_last_data_seconds = Gauge(
    'smarthydro_telemetry_last_data_seconds_ago',
    'Segundos desde la última recepción de datos',
    ['point_id', 'point_name', 'project', 'client', 'frequency']
)

# Histograma de latencia de procesamiento
telemetry_processing_duration = Histogram(
    'smarthydro_telemetry_processing_duration_seconds',
    'Tiempo de procesamiento de telemetría',
    ['point_id', 'provider']
)

# ============================================
# MÉTRICAS DGA
# ============================================

dga_transmissions_total = Counter(
    'smarthydro_dga_transmissions_total',
    'Total de transmisiones a DGA',
    ['point_id', 'point_name', 'standard_type', 'status']
)

dga_transmission_errors = Counter(
    'smarthydro_dga_transmission_errors_total',
    'Errores en transmisión DGA',
    ['point_id', 'error_code', 'error_type']
)

dga_vouchers_received = Counter(
    'smarthydro_dga_vouchers_received_total',
    'Total de vouchers DGA recibidos',
    ['point_id', 'point_name']
)

dga_pending_records = Gauge(
    'smarthydro_dga_pending_records',
    'Registros pendientes de enviar a DGA',
    ['point_id', 'point_name', 'standard_type']
)

# ============================================
# MÉTRICAS SMA
# ============================================

sma_transmissions_total = Counter(
    'smarthydro_sma_transmissions_total',
    'Total de transmisiones a SMA',
    ['point_id', 'point_name', 'status']
)

sma_transmission_errors = Counter(
    'smarthydro_sma_transmission_errors_total',
    'Errores en transmisión SMA',
    ['point_id', 'point_name', 'error_type']
)

# ============================================
# MÉTRICAS DE PROVEEDORES
# ============================================

provider_healthy = Gauge(
    'smarthydro_provider_healthy',
    'Estado de salud del proveedor (1=Healthy, 0=Unhealthy)',
    ['point_id', 'point_name', 'provider', 'project', 'client', 'protocol']
)

provider_consecutive_errors = Gauge(
    'smarthydro_provider_consecutive_errors',
    'Conteo de errores consecutivos del proveedor',
    ['point_id', 'point_name', 'provider', 'project', 'client', 'protocol']
)

provider_last_success_timestamp = Gauge(
    'smarthydro_provider_last_success_seconds_ago',
    'Segundos transcurridos desde el último éxito del proveedor',
    ['point_id', 'point_name', 'provider', 'project', 'client', 'protocol']
)

smarthydro_provider_info = Gauge(
    'smarthydro_provider_info',
    'Información de configuración del proveedor',
    ['provider_id', 'provider_name', 'protocol', 'base_url', 'auth_method']
)

# ============================================
# MÉTRICAS DE INFRAESTRUCTURA
# ============================================

database_table_rows = Gauge(
    'smarthydro_database_table_rows',
    'Cantidad de registros por tabla en la base de datos',
    ['table_name']
)

# ============================================
# MÉTRICAS DE ALERTAS
# ============================================

alerts_generated_total = Counter(
    'smarthydro_alerts_generated_total',
    'Total de alertas generadas',
    ['point_id', 'alert_type', 'severity']
)

active_alerts = Gauge(
    'smarthydro_active_alerts',
    'Alertas activas por punto',
    ['point_id', 'point_name', 'project', 'client', 'frequency', 'alert_type']
)

# ============================================
# MÉTRICAS DE SISTEMA
# ============================================

points_total = Gauge(
    'smarthydro_points_total',
    'Total de puntos de captación',
    ['status', 'provider']
)

points_with_data_today = Gauge(
    'smarthydro_points_with_data_today',
    'Puntos que han enviado datos hoy'
)

points_offline = Gauge(
    'smarthydro_points_offline',
    'Puntos sin datos en las últimas 2 horas',
    ['point_id', 'point_name', 'project', 'client', 'frequency']
)

database_records_total = Gauge(
    'smarthydro_database_records_total',
    'Total de registros en base de datos',
    ['table']
)

# Info sobre la aplicación
smarthydro_info = Info(
    'smarthydro_application',
    'Información de la aplicación SmartHydro'
)


# ============================================
# FUNCIONES DE ACTUALIZACIÓN
# ============================================

def update_telemetry_metrics():
    """Actualiza métricas de telemetría desde la base de datos."""
    now = timezone.now()

    # Obtener TODOS los puntos con relaciones necesarias
    points = CatchmentPoint.objects.all().select_related('project', 'project__client')

    for point in points:
        point_name = point.title
        project_name = point.project.name if point.project else "Sin Proyecto"
        client_name = point.project.client.name if (point.project and point.project.client) else "Sin Cliente"
        frequency = str(point.frequency.minutes if point.frequency else "Desconocida")

        # Último registro
        latest_record = TelemetryRecord.objects.filter(
            point=point
        ).order_by('-timestamp').first()

        if latest_record:
            # Valores actuales
            data = latest_record.data or {}
            
            common_labels = {
                'point_id': str(point.id),
                'point_name': str(point_name),
                'project': str(project_name),
                'client': str(client_name),
                'frequency': str(frequency)
            }

            # Caudal
            caudal = data.get('5001') or data.get('caudal') or data.get('flow')
            if caudal is not None:
                try:
                    telemetry_flow_current.labels(**common_labels).set(float(caudal))
                except (ValueError, TypeError):
                    pass

            # Total
            total = data.get('5000') or data.get('total') or data.get('acumulado')
            if total is not None:
                try:
                    telemetry_total_current.labels(**common_labels).set(float(total))
                except (ValueError, TypeError):
                    pass

            # Nivel
            nivel = data.get('nivel') or data.get('level')
            if nivel not in [None, '', '00.00']:
                try:
                    telemetry_nivel_current.labels(**common_labels).set(float(nivel))
                except (ValueError, TypeError):
                    pass

            # Consumo diario
            if 'total_today_diff' in data and data['total_today_diff'] is not None:
                try:
                    telemetry_daily_consumption.labels(**common_labels).set(float(data['total_today_diff']))
                except (ValueError, TypeError):
                    pass

            # Tiempo desde última recepción
            seconds_ago = (now - latest_record.timestamp).total_seconds()
            telemetry_last_data_seconds.labels(**common_labels).set(seconds_ago)

            # Marcar como offline si > 2 horas
            if seconds_ago > 7200:
                points_offline.labels(**common_labels).set(1)
            else:
                points_offline.labels(**common_labels).set(0)


def update_provider_metrics():
    """Actualiza métricas de salud de proveedores."""
    from api.telemetry.providers.models import CatchmentPointProvider
    from django.utils import timezone

    configs = CatchmentPointProvider.objects.filter(
        is_active=True
    ).select_related('point', 'point__project', 'point__project__client', 'provider')

    now = timezone.now()

    for config in configs:
        point = config.point
        project = point.project
        client = project.client if project else None

        common_labels = {
            'point_id': str(point.id),
            'point_name': str(point.title),
            'provider': str(config.provider.name),
            'project': str(project.name if project else "Sin Proyecto"),
            'client': str(client.name if client else "Sin Cliente"),
            'protocol': str(config.provider.provider_type).upper(),
        }

        # Estado de salud (1=Healthy, 0=Unhealthy)
        health = 1 if config.is_healthy else 0
        provider_healthy.labels(**common_labels).set(health)

        # Errores consecutivos
        provider_consecutive_errors.labels(**common_labels).set(config.error_count)

        # Tiempo desde último éxito
        if config.last_success:
            seconds_ago = (now - config.last_success).total_seconds()
            provider_last_success_timestamp.labels(**common_labels).set(seconds_ago)
        else:
            provider_last_success_timestamp.labels(**common_labels).set(999999)

    # 2. Información estática de Proveedores
    from api.telemetry.providers.models import TelemetryProvider
    providers = TelemetryProvider.objects.filter(is_active=True)
    for p in providers:
        smarthydro_provider_info.labels(
            provider_id=str(p.id),
            provider_name=str(p.display_name),
            protocol=str(p.get_provider_type_display()),
            base_url=str(p.base_url),
            auth_method=str(p.get_auth_method_display())
        ).set(1)


def update_dga_metrics():
    """Actualiza métricas de DGA."""
    # Registros pendientes de envío a DGA agrupados por punto
    pending_records = TelemetryRecord.objects.filter(
        compliance_status__dga__sent=False
    ).values('point_id', 'point__title').annotate(count=Count('id'))

    for record in pending_records:
        point_id = record['point_id']
        point_name = record['point__title']
        count = record['count']

        # Obtener tipo de estándar DGA vía Compliance
        compliance_config = PointComplianceConfig.objects.filter(
            point_id=point_id, provider__name="dga", is_active=True
        ).select_related("compliance_standard").first()

        standard_type = compliance_config.compliance_standard.name if compliance_config and compliance_config.compliance_standard else "UNKNOWN"

        dga_pending_records.labels(
            point_id=point_id,
            point_name=point_name,
            standard_type=standard_type
        ).set(count)


def update_alerts_metrics():
    """Actualiza métricas de alertas."""
    now = timezone.now()

    # Alertas activas (últimas 24 horas, no finalizadas)
    active_notifications = Notification.objects.filter(
        created__gte=now - timedelta(hours=24)
    ).exclude(
        end_date__isnull=False
    )

    # Contar por punto y tipo
    alert_counts = active_notifications.values(
        'point_catchment_id',
        'point_catchment__title',
        'type_alert'
    ).annotate(count=Count('id'))

    for alert in alert_counts:
        point_id = alert['point_catchment_id']
        point = CatchmentPoint.objects.filter(id=point_id).select_related('project', 'project__client').first()
        
        if point:
            project_name = point.project.name if point.project else "Sin Proyecto"
            client_name = point.project.client.name if (point.project and point.project.client) else "Sin Cliente"
            frequency = str(point.frequency.minutes if point.frequency else "Desconocida")
            
            active_alerts.labels(
                point_id=str(point_id),
                point_name=str(point.title),
                project=str(project_name),
                client=str(client_name),
                frequency=str(frequency),
                alert_type=str(alert['type_alert'])
            ).set(alert['count'])


def update_system_metrics():
    """Actualiza métricas del sistema e infraestructura."""
    from django.db import connection, transaction
    
    # Conteo de registros en tablas críticas
    tables = [
        ('telemetry_telemetryrecord', 'Telemetría'),
        ('telemetry_dgahistory', 'Historial DGA'),
        ('notifications_notification', 'Notificaciones'),
        ('telemetry_catchmentpoint', 'Puntos de Captación'),
    ]
    
    # 1. Conteo de registros en tablas críticas (Infraestructura)
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                for table_real_name, table_display_name in tables:
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {table_real_name}")
                        count = cursor.fetchone()[0]
                        database_table_rows.labels(table_name=table_display_name).set(count)
                    except Exception as e:
                        logger.warning(f"Error contando filas en {table_real_name}: {e}")
    except Exception as e:
        logger.error(f"Error de transacción en métricas de infraestructura: {e}")

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # 2. Métricas de Negocio (Puntos y Telemetría)
    try:
        with transaction.atomic():
            # Total de puntos por estado
            total_points = CatchmentPoint.objects.count()
            # En la nueva arquitectura, consideramos telemetría si el punto está activo
            telemetry_points = CatchmentPoint.objects.filter(
                is_active=True
            ).count()

            points_total.labels(status='active', provider='all').set(telemetry_points)
            points_total.labels(status='total', provider='all').set(total_points)

            # Puntos con datos hoy
            points_today = TelemetryRecord.objects.filter(
                timestamp__gte=today_start
            ).values('point_id').distinct().count()

            points_with_data_today.set(points_today)

            # Total de registros en base de datos
            telemetry_count = TelemetryRecord.objects.count()
            database_records_total.labels(table='telemetry_records').set(telemetry_count)

            notification_count = Notification.objects.count()
            database_records_total.labels(table='notifications').set(notification_count)
    except Exception as e:
        logger.error(f"Error actualizando métricas de negocio: {e}")


def update_all_metrics():
    """Actualiza todas las métricas (llamar desde endpoint o cronjob)."""
    try:
        update_telemetry_metrics()
        update_provider_metrics()
        update_dga_metrics()
        update_alerts_metrics()
        update_system_metrics()
        
        # Info de la aplicación
        smarthydro_info.info({
            'version': '3.0.0',
            'last_update': datetime.now().isoformat()
        })
        return True
    except Exception as e:
        logger.error(f"Error crítico en lazo de métricas: {e}", exc_info=True)
        return False
