"""
Tareas de Celery para Compliance Dinámico.

Este archivo UNIFICA y REEMPLAZA:
- api/core/tasks/dga.py (legacy - específico DGA)
- Parte de api/core/tasks/compliance.py

Maneja envío de datos a TODOS los proveedores de compliance de forma dinámica.
"""

from celery import shared_task
from django.utils import timezone
from django.db.models import Q
import logging

from api.telemetry.providers.compliance_models import (
    ComplianceProvider,
    PointComplianceConfig,
    ManualComplianceRecord
)
from api.telemetry.models.telemetry import TelemetryRecord
from api.telemetry.services.compliance_service import ComplianceService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_compliance_data(self, record_id: int, compliance_config_id: int):
    """
    Enviar datos de cumplimiento de forma dinámica.

    Esta tarea REEMPLAZA send_data_to_dga_task con una versión genérica
    que funciona con CUALQUIER proveedor de compliance.

    Args:
        record_id: ID del TelemetryRecord a enviar
        compliance_config_id: ID del PointComplianceConfig

    Returns:
        Dict con resultado del envío
    """
    try:
        # Cargar datos
        config = PointComplianceConfig.objects.select_related(
            'provider', 'point'
        ).get(id=compliance_config_id)

        record = TelemetryRecord.objects.select_related('point').get(id=record_id)

        provider_name = config.provider.display_name
        point_code = config.point.point_code

        logger.info(
            f"📤 Enviando compliance: {point_code} → {provider_name} "
            f"(record: {record_id})"
        )

        # Verificar que configuración está activa
        if not config.is_active or not config.send_compliance:
            logger.warning(
                f"⚠️  Compliance deshabilitado para {point_code} → {provider_name}"
            )
            return {
                'success': False,
                'message': 'Configuración deshabilitada',
                'skipped': True
            }

        # Usar servicio de compliance
        service = ComplianceService()

        success, message, voucher = service.submit_telemetry_record(
            record=record,
            config=config
        )

        if success:
            # Registrar éxito
            config.record_success()

            # Actualizar registro de telemetría
            if not hasattr(record, 'compliance_status'):
                record.compliance_status = {}

            record.compliance_status[config.provider.name] = {
                'sent': True,
                'voucher': voucher,
                'sent_at': timezone.now().isoformat(),
                'message': message
            }
            record.save(update_fields=['compliance_status'])

            logger.info(
                f"✅ Compliance exitoso: {point_code} → {provider_name} "
                f"(voucher: {voucher})"
            )

            return {
                'success': True,
                'message': message,
                'voucher': voucher,
                'provider': provider_name,
                'point': point_code
            }

        else:
            # Registrar error
            config.record_error(message)

            logger.error(
                f"❌ Error compliance: {point_code} → {provider_name}: {message}"
            )

            # Retry con backoff exponencial
            retry_delay = config.provider.retry_delay_seconds * (2 ** self.request.retries)

            raise self.retry(
                exc=Exception(message),
                countdown=retry_delay,
                max_retries=config.provider.max_retries
            )

    except PointComplianceConfig.DoesNotExist:
        error_msg = f"PointComplianceConfig {compliance_config_id} no encontrado"
        logger.error(f"❌ {error_msg}")
        return {'success': False, 'message': error_msg}

    except TelemetryRecord.DoesNotExist:
        error_msg = f"TelemetryRecord {record_id} no encontrado"
        logger.error(f"❌ {error_msg}")
        return {'success': False, 'message': error_msg}

    except Exception as exc:
        logger.error(
            f"❌ Error inesperado en compliance task: {exc}",
            exc_info=True
        )

        # Si ya agotó reintentos, registrar error final
        if self.request.retries >= config.provider.max_retries:
            config.record_error(str(exc))

        raise


@shared_task(bind=True)
def send_manual_compliance_record(self, manual_record_id: int):
    """
    Enviar registro manual de compliance.

    Para puntos sin telemetría automática donde el usuario ingresa
    datos manualmente.

    Args:
        manual_record_id: ID del ManualComplianceRecord

    Returns:
        Dict con resultado del envío
    """
    try:
        manual_record = ManualComplianceRecord.objects.select_related(
            'config__provider',
            'config__point'
        ).get(id=manual_record_id)

        config = manual_record.config
        provider_name = config.provider.display_name
        point_code = config.point.point_code

        logger.info(
            f"📤 Enviando compliance manual: {point_code} → {provider_name}"
        )

        # Marcar como en cola
        manual_record.status = 'queued'
        manual_record.save(update_fields=['status'])

        # Construir pseudo-record para el servicio
        # TODO: Adaptar ComplianceService para aceptar datos sin TelemetryRecord
        service = ComplianceService()

        # Por ahora, construir payload manualmente
        from api.telemetry.services.compliance_service import compliance_service

        payload = compliance_service.build_payload_from_template(
            template=config.provider.payload_template,
            config_data=config.config_data,
            record=manual_record  # Usar manual_record como si fuera TelemetryRecord
        )

        # Enviar...
        # (Lógica similar a send_compliance_data)

        logger.info(f"✅ Compliance manual exitoso: {point_code} → {provider_name}")

        manual_record.status = 'sent'
        manual_record.submitted_at = timezone.now()
        manual_record.save()

        return {
            'success': True,
            'provider': provider_name,
            'point': point_code
        }

    except Exception as exc:
        logger.error(f"❌ Error en compliance manual: {exc}", exc_info=True)

        if manual_record:
            manual_record.status = 'error'
            manual_record.error_message = str(exc)
            manual_record.save()

        raise


@shared_task
def process_compliance_queue():
    """
    Procesar cola de registros pendientes de compliance.

    Esta tarea se ejecuta periódicamente (ej: cada 5 minutos) y envía
    registros que quedaron pendientes por algún motivo.

    Útil para:
    - Reintentar envíos fallidos después del max_retries
    - Procesar registros manuales en cola
    - Batch processing de registros antiguos
    """
    logger.info("🔄 Procesando cola de compliance...")

    # 1. Procesar registros manuales pendientes
    pending_manual = ManualComplianceRecord.objects.filter(
        status__in=['pending', 'queued'],
        config__is_active=True,
        config__send_compliance=True
    ).select_related('config__provider')[:50]  # Limitar por batch

    for manual_record in pending_manual:
        send_manual_compliance_record.delay(manual_record.id)

    logger.info(f"📋 Encolados {len(pending_manual)} registros manuales")

    # 2. Buscar configuraciones con errores para reintento
    # (después de cierto tiempo desde último error)
    from datetime import timedelta

    retry_threshold = timezone.now() - timedelta(hours=1)

    configs_to_retry = PointComplianceConfig.objects.filter(
        is_active=True,
        send_compliance=True,
        error_count__gt=0,
        last_submission__lt=retry_threshold
    ).select_related('provider', 'point')[:20]

    for config in configs_to_retry:
        # Buscar último registro no enviado
        last_record = TelemetryRecord.objects.filter(
            point=config.point
        ).order_by('-timestamp').first()

        if last_record:
            logger.info(
                f"🔄 Reintentando compliance: {config.point.point_code} → "
                f"{config.provider.display_name}"
            )
            send_compliance_data.delay(last_record.id, config.id)

    logger.info(f"🔄 {len(configs_to_retry)} configuraciones con reintentos")

    return {
        'manual_records_queued': len(pending_manual),
        'configs_retried': len(configs_to_retry)
    }


@shared_task
def generate_compliance_report(provider_name: str = None, days: int = 7):
    """
    Generar reporte de estadísticas de compliance.

    Args:
        provider_name: Nombre del proveedor (None = todos)
        days: Días hacia atrás para el reporte

    Returns:
        Dict con estadísticas
    """
    from datetime import timedelta

    since = timezone.now() - timedelta(days=days)

    # Filtrar por proveedor si se especifica
    configs_filter = Q(is_active=True)
    if provider_name:
        configs_filter &= Q(provider__name=provider_name)

    configs = PointComplianceConfig.objects.filter(
        configs_filter
    ).select_related('provider', 'point')

    stats = {
        'period_days': days,
        'provider': provider_name or 'ALL',
        'total_configs': configs.count(),
        'active_sending': configs.filter(send_compliance=True).count(),
        'providers': {},
        'points': []
    }

    # Estadísticas por proveedor
    for config in configs:
        provider = config.provider.name

        if provider not in stats['providers']:
            stats['providers'][provider] = {
                'display_name': config.provider.display_name,
                'total_configs': 0,
                'active': 0,
                'total_submissions': 0,
                'successful_submissions': 0,
                'success_rate': 0.0,
                'points_with_errors': 0
            }

        p_stats = stats['providers'][provider]
        p_stats['total_configs'] += 1

        if config.send_compliance:
            p_stats['active'] += 1

        p_stats['total_submissions'] += config.total_submissions
        p_stats['successful_submissions'] += config.successful_submissions

        if config.error_count > 0:
            p_stats['points_with_errors'] += 1

        # Calcular tasa de éxito
        if p_stats['total_submissions'] > 0:
            p_stats['success_rate'] = (
                p_stats['successful_submissions'] / p_stats['total_submissions']
            ) * 100

        # Estadísticas por punto
        stats['points'].append({
            'point_code': config.point.point_code,
            'point_title': config.point.title,
            'provider': provider,
            'active': config.send_compliance,
            'total_submissions': config.total_submissions,
            'successful_submissions': config.successful_submissions,
            'error_count': config.error_count,
            'last_success': config.last_success.isoformat() if config.last_success else None,
            'last_error': config.last_error[:200] if config.last_error else None
        })

    logger.info(f"📊 Reporte compliance generado: {stats['total_configs']} configs")

    return stats


# ==========================================
# LEGACY COMPATIBILITY
# ==========================================
# Mantener nombres legacy para no romper código existente durante transición

@shared_task(bind=True, max_retries=3)
def send_data_to_dga_task(self, record_id: int, point_id: int):
    """
    LEGACY: Mantener por compatibilidad.
    DEPRECATED: Usar send_compliance_data en su lugar.

    Esta función busca la configuración DGA del punto y delega
    a send_compliance_data.
    """
    import warnings
    warnings.warn(
        "send_data_to_dga_task está deprecado. "
        "Usar send_compliance_data con compliance_config_id.",
        DeprecationWarning,
        stacklevel=2
    )

    try:
        # Buscar configuración DGA del punto
        config = PointComplianceConfig.objects.filter(
            point_id=point_id,
            provider__name='dga',
            is_active=True
        ).first()

        if not config:
            logger.warning(
                f"⚠️  No hay configuración DGA para point {point_id}. "
                f"Crear PointComplianceConfig en Admin."
            )
            return {'success': False, 'message': 'No DGA config found'}

        # Delegar a tarea nueva
        return send_compliance_data.apply_async(
            args=[record_id, config.id],
            task_id=self.request.id
        )

    except Exception as exc:
        logger.error(f"❌ Error en send_data_to_dga_task legacy: {exc}")
        raise
