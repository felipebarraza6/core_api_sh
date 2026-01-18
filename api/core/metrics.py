"""
Exportador de métricas Prometheus para SmartHydro
Expone métricas de telemetría, DGA, SMA y sistema
"""
from prometheus_client import Counter, Gauge, Histogram, Info
from django.db.models import Count, Max, Min, Avg
from api.telemetry.models import (
    CatchmentPoint,
    TelemetryRecord,
    NotificationsCatchment,
    ProfileDataConfigCatchment,
)
from datetime import datetime, timedelta
from django.utils import timezone


# ============================================
# MÉTRICAS DE TELEMETRÍA
# ============================================

# Contadores de ingestión
telemetry_ingestion_total = Counter(
    'smarthydro_telemetry_ingestion_total',
    'Total de registros de telemetría ingestados',
    ['point_id', 'point_name', 'provider']
)

telemetry_ingestion_errors = Counter(
    'smarthydro_telemetry_ingestion_errors_total',
    'Total de errores en ingestión de telemetría',
    ['point_id', 'point_name', 'error_type']
)

# Gauges para valores actuales
telemetry_flow_current = Gauge(
    'smarthydro_telemetry_flow_liters_per_second',
    'Caudal actual en L/s',
    ['point_id', 'point_name', 'project']
)

telemetry_total_current = Gauge(
    'smarthydro_telemetry_total_cubic_meters',
    'Total acumulado en m³',
    ['point_id', 'point_name', 'project']
)

telemetry_nivel_current = Gauge(
    'smarthydro_telemetry_nivel_meters',
    'Nivel actual en metros',
    ['point_id', 'point_name', 'project']
)

telemetry_daily_consumption = Gauge(
    'smarthydro_telemetry_daily_consumption_cubic_meters',
    'Consumo diario en m³',
    ['point_id', 'point_name', 'project']
)

# Tiempo desde última recepción
telemetry_last_data_seconds = Gauge(
    'smarthydro_telemetry_last_data_seconds_ago',
    'Segundos desde la última recepción de datos',
    ['point_id', 'point_name']
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
    ['point_id', 'error_type']
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
    ['point_id', 'point_name', 'alert_type']
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
    ['point_id', 'point_name']
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
    """Actualiza métricas de telemetría desde la base de datos"""
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Obtener puntos activos
    points = CatchmentPoint.objects.filter(
        profiledataconfigcatchment__is_telemetry=True
    ).select_related('project', 'profiledataconfigcatchment')

    for point in points:
        point_name = point.title
        project_name = point.project.name if point.project else "Sin Proyecto"

        # Último registro
        latest_record = TelemetryRecord.objects.filter(
            point=point
        ).order_by('-timestamp').first()

        if latest_record:
            # Valores actuales
            data = latest_record.data

            if 'flow' in data and data['flow'] is not None:
                telemetry_flow_current.labels(
                    point_id=point.id,
                    point_name=point_name,
                    project=project_name
                ).set(float(data['flow']))

            if 'total' in data and data['total'] is not None:
                telemetry_total_current.labels(
                    point_id=point.id,
                    point_name=point_name,
                    project=project_name
                ).set(float(data['total']))

            if 'nivel' in data and data['nivel'] not in [None, '', '00.00']:
                try:
                    telemetry_nivel_current.labels(
                        point_id=point.id,
                        point_name=point_name,
                        project=project_name
                    ).set(float(data['nivel']))
                except (ValueError, TypeError):
                    pass

            if 'total_today_diff' in data and data['total_today_diff'] is not None:
                telemetry_daily_consumption.labels(
                    point_id=point.id,
                    point_name=point_name,
                    project=project_name
                ).set(float(data['total_today_diff']))

            # Tiempo desde última recepción
            seconds_ago = (now - latest_record.timestamp).total_seconds()
            telemetry_last_data_seconds.labels(
                point_id=point.id,
                point_name=point_name
            ).set(seconds_ago)

            # Marcar como offline si > 2 horas
            if seconds_ago > 7200:
                points_offline.labels(
                    point_id=point.id,
                    point_name=point_name
                ).set(1)
            else:
                points_offline.labels(
                    point_id=point.id,
                    point_name=point_name
                ).set(0)


def update_dga_metrics():
    """Actualiza métricas de DGA"""
    from api.telemetry.models import DgaDataConfigCatchment

    # Registros pendientes de envío
    pending_records = TelemetryRecord.objects.filter(
        send_dga=False,
        is_error=False
    ).values('point_id', 'point__title').annotate(
        count=Count('id')
    )

    for record in pending_records:
        point_id = record['point_id']
        point_name = record['point__title']
        count = record['count']

        # Obtener tipo de estándar DGA
        dga_config = DgaDataConfigCatchment.objects.filter(
            point_catchment_id=point_id
        ).first()

        standard_type = dga_config.standard if dga_config else "UNKNOWN"

        dga_pending_records.labels(
            point_id=point_id,
            point_name=point_name,
            standard_type=standard_type
        ).set(count)


def update_alerts_metrics():
    """Actualiza métricas de alertas"""
    now = timezone.now()

    # Alertas activas (últimas 24 horas, no finalizadas)
    active_notifications = NotificationsCatchment.objects.filter(
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
        active_alerts.labels(
            point_id=alert['point_catchment_id'],
            point_name=alert['point_catchment__title'],
            alert_type=alert['type_alert']
        ).set(alert['count'])


def update_system_metrics():
    """Actualiza métricas generales del sistema"""
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Total de puntos por estado
    total_points = CatchmentPoint.objects.count()
    telemetry_points = ProfileDataConfigCatchment.objects.filter(
        is_telemetry=True
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

    notification_count = NotificationsCatchment.objects.count()
    database_records_total.labels(table='notifications').set(notification_count)


def update_all_metrics():
    """Actualiza todas las métricas (llamar desde endpoint o cronjob)"""
    try:
        update_telemetry_metrics()
        update_dga_metrics()
        update_alerts_metrics()
        update_system_metrics()

        # Info de la aplicación
        smarthydro_info.info({
            'version': '3.0.0',
            'environment': 'production',
            'database': 'postgresql',
            'last_update': datetime.now().isoformat()
        })

        return True
    except Exception as e:
        print(f"Error updating metrics: {e}")
        return False
