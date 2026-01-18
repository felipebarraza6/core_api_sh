"""
Celery Tasks para Sincronización con Proveedores
Gestión automática de recuperación de datos históricos
"""

import logging
from celery import shared_task
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
import asyncio

from api.core.services.provider_sync_service import provider_sync_service
from api.core.models import ProviderDataSync, EquipmentProvider

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, retry_backoff=True)
def sync_provider_data(self, provider_code: str):
    """
    Sincronizar datos con un proveedor específico
    """
    try:
        logger.info(f"Starting provider sync for {provider_code}")

        # Obtener configuración de sync activa
        sync_configs = ProviderDataSync.objects.filter(
            provider__code=provider_code,
            is_active=True
        ).select_related('provider')

        if not sync_configs.exists():
            logger.info(f"No active sync configuration found for provider {provider_code}")
            return {'status': 'skipped', 'reason': 'no_active_config'}

        total_processed = 0
        total_errors = 0

        # Ejecutar sync para cada configuración
        for sync_config in sync_configs:
            try:
                # Verificar si se puede ejecutar
                if not sync_config.can_run_sync():
                    logger.info(f"Sync for {provider_code} not ready (interval check)")
                    continue

                # Ejecutar sincronización
                result = asyncio.run(
                    provider_sync_service.sync_provider_data(sync_config)
                )

                if result['success']:
                    total_processed += result.get('records_processed', 0)
                else:
                    total_errors += 1
                    logger.error(f"Sync failed for {provider_code}: {result.get('error')}")

            except Exception as exc:
                logger.error(f"Error in sync config {sync_config.id}: {exc}")
                total_errors += 1

        logger.info(f"Provider sync completed for {provider_code}: {total_processed} records, {total_errors} errors")

        return {
            'status': 'completed',
            'provider': provider_code,
            'records_processed': total_processed,
            'errors': total_errors
        }

    except Exception as exc:
        logger.error(f"Provider sync task failed for {provider_code}: {exc}")
        self.retry(countdown=300, exc=exc)


@shared_task(bind=True, max_retries=2)
def sync_all_active_providers(self):
    """
    Sincronizar datos con todos los proveedores activos
    """
    try:
        logger.info("Starting sync for all active providers")

        # Obtener proveedores con sync activo
        active_syncs = ProviderDataSync.objects.filter(
            is_active=True
        ).select_related('provider').distinct('provider')

        if not active_syncs.exists():
            logger.info("No active provider syncs found")
            return {'status': 'completed', 'providers': 0}

        # Ejecutar sync para cada proveedor
        provider_tasks = []
        for sync_config in active_syncs:
            provider_tasks.append(
                sync_provider_data.s(sync_config.provider.code)
            )

        # Ejecutar en paralelo
        from celery import group
        job = group(provider_tasks)
        results = job.apply_async().get(timeout=1800)  # 30 minutos timeout

        # Agregar resultados
        total_processed = sum(r.get('records_processed', 0) for r in results)
        total_errors = sum(r.get('errors', 0) for r in results)

        logger.info(f"All providers sync completed: {len(results)} providers, {total_processed} records, {total_errors} errors")

        return {
            'status': 'completed',
            'providers_synced': len(results),
            'total_records_processed': total_processed,
            'total_errors': total_errors,
            'results': results
        }

    except Exception as exc:
        logger.error(f"All providers sync failed: {exc}")
        self.retry(countdown=600, exc=exc)


@shared_task(bind=True)
def sync_provider_historical_data(self, provider_code: str, start_date: str = None, end_date: str = None):
    """
    Sincronizar datos históricos específicos de un proveedor
    """
    try:
        logger.info(f"Starting historical sync for {provider_code}")

        # Parsear fechas
        start_dt = None
        if start_date:
            start_dt = timezone.datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            start_dt = timezone.make_aware(start_dt) if timezone.is_naive(start_dt) else start_dt

        end_dt = None
        if end_date:
            end_dt = timezone.datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            end_dt = timezone.make_aware(end_dt) if timezone.is_naive(end_dt) else end_dt

        # Obtener configuración de sync
        sync_configs = ProviderDataSync.objects.filter(
            provider__code=provider_code,
            is_active=True
        ).select_related('provider')

        if not sync_configs.exists():
            return {'status': 'error', 'message': 'No active sync config found'}

        total_processed = 0

        for sync_config in sync_configs:
            try:
                # Modificar configuración temporalmente para historical sync
                original_type = sync_config.sync_type
                sync_config.sync_type = 'FULL_HISTORICAL'

                # Agregar configuración de fechas
                sync_config.sync_config['historical_start_date'] = start_dt.isoformat() if start_dt else None
                sync_config.sync_config['historical_end_date'] = end_dt.isoformat() if end_dt else None

                # Ejecutar sync
                result = asyncio.run(
                    provider_sync_service.sync_provider_data(sync_config)
                )

                if result['success']:
                    total_processed += result.get('records_processed', 0)

                # Restaurar configuración original
                sync_config.sync_type = original_type
                sync_config.save()

            except Exception as exc:
                logger.error(f"Historical sync failed for config {sync_config.id}: {exc}")

        logger.info(f"Historical sync completed for {provider_code}: {total_processed} records")

        return {
            'status': 'completed',
            'provider': provider_code,
            'records_processed': total_processed,
            'start_date': start_date,
            'end_date': end_date
        }

    except Exception as exc:
        logger.error(f"Historical sync task failed: {exc}")
        self.retry(countdown=300, exc=exc)


@shared_task(bind=True)
def initialize_provider_sync(self, provider_code: str, sync_type: str = 'INCREMENTAL'):
    """
    Inicializar configuración de sincronización para un proveedor
    """
    try:
        logger.info(f"Initializing sync for provider {provider_code}")

        provider = EquipmentProvider.objects.get(code=provider_code)

        # Verificar si ya existe configuración
        existing_sync = ProviderDataSync.objects.filter(provider=provider).first()

        if existing_sync:
            return {
                'status': 'exists',
                'message': f'Sync config already exists for {provider_code}',
                'config_id': existing_sync.id
            }

        # Crear nueva configuración
        sync_config = ProviderDataSync.objects.create(
            provider=provider,
            sync_type=sync_type,
            sync_config={
                'auto_initialize': True,
                'default_interval': 60,  # minutos
                'retry_attempts': 3,
                'batch_size': 1000
            }
        )

        logger.info(f"Sync configuration initialized for {provider_code}")

        return {
            'status': 'created',
            'config_id': sync_config.id,
            'provider': provider_code,
            'sync_type': sync_type
        }

    except EquipmentProvider.DoesNotExist:
        return {
            'status': 'error',
            'message': f'Provider {provider_code} not found'
        }
    except Exception as exc:
        logger.error(f"Failed to initialize provider sync: {exc}")
        return {
            'status': 'error',
            'message': str(exc)
        }


@shared_task(bind=True)
def monitor_provider_sync_health(self):
    """
    Monitorear la salud de las sincronizaciones con proveedores
    """
    try:
        logger.info("Monitoring provider sync health")

        # Obtener todas las configuraciones activas
        sync_configs = ProviderDataSync.objects.filter(is_active=True)

        health_report = {
            'total_configs': sync_configs.count(),
            'healthy': 0,
            'warning': 0,
            'critical': 0,
            'details': []
        }

        for config in sync_configs:
            health_status = 'healthy'
            issues = []

            # Verificar estado
            if config.current_status == 'FAILED':
                health_status = 'critical'
                issues.append('Última sincronización falló')

            # Verificar fallos consecutivos
            if config.consecutive_failures > 3:
                health_status = 'critical'
                issues.append(f'{config.consecutive_failures} fallos consecutivos')

            # Verificar última sincronización
            if config.last_successful_sync:
                hours_since_last_sync = (timezone.now() - config.last_successful_sync).total_seconds() / 3600
                expected_interval = config.sync_interval_minutes / 60

                if hours_since_last_sync > expected_interval * 2:
                    if health_status == 'healthy':
                        health_status = 'warning'
                    issues.append(
                        f"No se sincroniza hace {hours_since_last_sync:.1f}h "
                        f"(esperado cada {expected_interval:.1f}h)"
                    )
            else:
                # Nunca se sincronizó exitosamente
                if health_status == 'healthy':
                    health_status = 'warning'
                issues.append('Nunca se sincronizó exitosamente')

            # Contabilizar
            if health_status == 'healthy':
                health_report['healthy'] += 1
            elif health_status == 'warning':
                health_report['warning'] += 1
            else:
                health_report['critical'] += 1

            # Agregar detalles
            health_report['details'].append({
                'provider': config.provider.name,
                'status': health_status,
                'last_sync': config.last_successful_sync.isoformat() if config.last_successful_sync else None,
                'consecutive_failures': config.consecutive_failures,
                'issues': issues
            })

        # Generar alertas para problemas críticos
        critical_configs = [d for d in health_report['details'] if d['status'] == 'critical']
        if critical_configs:
            logger.warning(f"Critical sync issues found: {len(critical_configs)} providers")
            # Aquí se podría enviar alerta al sistema de monitoreo

        logger.info(f"Sync health monitoring completed: {health_report['healthy']} healthy, {health_report['warning']} warning, {health_report['critical']} critical")

        return health_report

    except Exception as exc:
        logger.error(f"Provider sync health monitoring failed: {exc}")
        return {'status': 'error', 'message': str(exc)}


@shared_task(bind=True)
def cleanup_failed_sync_attempts(self):
    """
    Limpiar y resetear intentos de sincronización fallidos
    """
    try:
        logger.info("Cleaning up failed sync attempts")

        # Resetear contadores de fallos para syncs que tuvieron éxito recientemente
        successful_syncs = ProviderDataSync.objects.filter(
            last_successful_sync__gte=timezone.now() - timedelta(hours=24),
            consecutive_failures__gt=0
        )

        successful_count = successful_syncs.update(consecutive_failures=0)

        # Marcar como inactivos syncs con muchos fallos consecutivos
        failed_syncs = ProviderDataSync.objects.filter(
            consecutive_failures__gte=10,
            is_active=True
        )

        deactivated_count = failed_syncs.update(is_active=False)

        # Limpiar mensajes de error antiguos (más de 7 días)
        old_errors = ProviderDataSync.objects.filter(
            current_status='FAILED',
            last_sync_attempt__lt=timezone.now() - timedelta(days=7)
        )

        cleared_errors_count = old_errors.update(
            last_error_message='',
            current_status='IDLE'
        )

        logger.info(f"Cleanup completed: {successful_count} failures reset, {deactivated_count} syncs deactivated, {cleared_errors_count} errors cleared")

        return {
            'status': 'completed',
            'failures_reset': successful_count,
            'syncs_deactivated': deactivated_count,
            'errors_cleared': cleared_errors_count
        }

    except Exception as exc:
        logger.error(f"Failed sync cleanup failed: {exc}")
        return {'status': 'error', 'message': str(exc)}
