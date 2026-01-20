"""
Unified Compliance Processing Tasks

Celery tasks for processing compliance submissions using the dynamic
ComplianceProvider system. Replaces hardcoded DGA/SMA tasks.
"""

import logging
import time
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from api.telemetry.providers.compliance_models import (
    ComplianceProvider,
    PointComplianceConfig,
    ManualComplianceRecord,
)
from api.telemetry.models import TelemetryRecord
from api.telemetry.services.compliance_service import get_compliance_service

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, retry_backoff=True)
def process_compliance_queue(self, provider_name: str = None, batch_size: int = 50):
    """
    Process compliance submissions for all active providers.
    
    Args:
        provider_name: Optional specific provider to process (e.g., 'dga', 'sma')
        batch_size: Number of records to process per batch
    
    Returns:
        Dict with processing statistics
    """
    start_time = time.time()
    results = {
        'providers_processed': 0,
        'records_submitted': 0,
        'successful': 0,
        'failed': 0,
        'errors': [],
    }

    try:
        logger.info(f"Starting compliance queue processing (provider={provider_name})")
        
        # Get active providers
        providers_qs = ComplianceProvider.objects.filter(is_active=True)
        if provider_name:
            providers_qs = providers_qs.filter(name=provider_name)
        
        service = get_compliance_service()
        
        for provider in providers_qs:
            try:
                provider_results = _process_provider(provider, service, batch_size)
                results['providers_processed'] += 1
                results['records_submitted'] += provider_results['submitted']
                results['successful'] += provider_results['successful']
                results['failed'] += provider_results['failed']
                
            except Exception as exc:
                error_msg = f"Error processing provider {provider.name}: {exc}"
                logger.error(error_msg)
                results['errors'].append(error_msg)

        results['execution_time'] = time.time() - start_time
        logger.info(f"Compliance processing completed: {results}")
        
        return results

    except Exception as exc:
        logger.error(f"Compliance queue processing failed: {exc}")
        self.retry(countdown=300, exc=exc)


def _process_provider(
    provider: ComplianceProvider,
    service,
    batch_size: int
) -> dict:
    """
    Process pending records for a specific provider.
    """
    results = {'submitted': 0, 'successful': 0, 'failed': 0}
    
    # Get active point configurations for this provider
    configs = PointComplianceConfig.objects.filter(
        provider=provider,
        is_active=True,
        send_compliance=True
    ).select_related('point')
    
    for config in configs:
        try:
            # Process based on data source
            if config.data_source in ('telemetry', 'both'):
                telemetry_results = _process_telemetry_records(config, service, batch_size)
                results['submitted'] += telemetry_results['submitted']
                results['successful'] += telemetry_results['successful']
                results['failed'] += telemetry_results['failed']
            
            if config.data_source in ('manual', 'both'):
                manual_results = _process_manual_records(config, service, batch_size)
                results['submitted'] += manual_results['submitted']
                results['successful'] += manual_results['successful']
                results['failed'] += manual_results['failed']
                
        except Exception as exc:
            logger.error(f"Error processing config {config.id}: {exc}")
            results['failed'] += 1
    
    return results


def _process_telemetry_records(
    config: PointComplianceConfig,
    service,
    batch_size: int
) -> dict:
    """
    Process telemetry records for a point compliance configuration.
    """
    results = {'submitted': 0, 'successful': 0, 'failed': 0}
    
    # Get pending records (using send_dga for backward compatibility)
    pending_records = TelemetryRecord.objects.filter(
        point=config.point,
        send_dga=True,
        is_error=False
    ).order_by('timestamp')[:batch_size]
    
    for record in pending_records:
        try:
            with transaction.atomic():
                success, message, voucher = service.submit_telemetry_record(record, config)
                results['submitted'] += 1
                
                if success:
                    record.send_dga = False
                    record.return_dga = message
                    record.n_voucher = voucher
                    record.save(update_fields=['send_dga', 'return_dga', 'n_voucher'])
                    results['successful'] += 1
                    logger.info(f"Record {record.id} submitted to {config.provider.name}")
                else:
                    record.return_dga = message
                    record.is_error = True
                    record.save(update_fields=['return_dga', 'is_error'])
                    results['failed'] += 1
                    logger.warning(f"Record {record.id} failed: {message}")
                    
        except Exception as exc:
            logger.error(f"Error submitting record {record.id}: {exc}")
            results['failed'] += 1
    
    return results


def _process_manual_records(
    config: PointComplianceConfig,
    service,
    batch_size: int
) -> dict:
    """
    Process manual compliance records.
    """
    results = {'submitted': 0, 'successful': 0, 'failed': 0}
    
    # Get pending manual records
    pending_records = ManualComplianceRecord.objects.filter(
        config=config,
        status='pending'
    ).order_by('measurement_timestamp')[:batch_size]
    
    for record in pending_records:
        try:
            with transaction.atomic():
                # Mark as queued
                record.status = 'queued'
                record.save(update_fields=['status'])
                
                success, message, voucher = service.submit_manual_record(record)
                results['submitted'] += 1
                
                record.submitted_at = timezone.now()
                
                if success:
                    record.status = 'sent'
                    record.voucher = voucher
                    record.response_data = {'message': message}
                    results['successful'] += 1
                    logger.info(f"Manual record {record.id} submitted successfully")
                else:
                    record.status = 'error'
                    record.error_message = message
                    results['failed'] += 1
                    logger.warning(f"Manual record {record.id} failed: {message}")
                
                record.save()
                    
        except Exception as exc:
            logger.error(f"Error submitting manual record {record.id}: {exc}")
            record.status = 'error'
            record.error_message = str(exc)
            record.save(update_fields=['status', 'error_message'])
            results['failed'] += 1
    
    return results


@shared_task(bind=True, max_retries=2)
def process_compliance_for_point(self, point_id: int, provider_name: str = None):
    """
    Process compliance for a specific point.
    
    Args:
        point_id: ID of the catchment point
        provider_name: Optional specific provider to process
    """
    try:
        logger.info(f"Processing compliance for point {point_id}")
        
        configs = PointComplianceConfig.objects.filter(
            point_id=point_id,
            is_active=True,
            send_compliance=True
        ).select_related('provider')
        
        if provider_name:
            configs = configs.filter(provider__name=provider_name)
        
        service = get_compliance_service()
        results = {'submitted': 0, 'successful': 0, 'failed': 0}
        
        for config in configs:
            if config.data_source in ('telemetry', 'both'):
                r = _process_telemetry_records(config, service, batch_size=100)
                results['submitted'] += r['submitted']
                results['successful'] += r['successful']
                results['failed'] += r['failed']
        
        logger.info(f"Point {point_id} compliance: {results}")
        return results
        
    except Exception as exc:
        logger.error(f"Error processing compliance for point {point_id}: {exc}")
        self.retry(countdown=60, exc=exc)


@shared_task
def check_compliance_status():
    """
    Check compliance status for all enabled points.
    Generates alerts for points that haven't submitted recently.
    """
    logger.info("Checking compliance status")
    
    alerts_generated = 0
    cutoff_time = timezone.now() - timedelta(hours=24)
    
    configs = PointComplianceConfig.objects.filter(
        is_active=True,
        send_compliance=True
    ).select_related('point', 'provider')
    
    for config in configs:
        # Check if there have been successful submissions in last 24h
        if config.last_success is None or config.last_success < cutoff_time:
            _generate_compliance_alert(config)
            alerts_generated += 1
    
    logger.info(f"Compliance check completed: {alerts_generated} alerts generated")
    return {'alerts_generated': alerts_generated}


def _generate_compliance_alert(config: PointComplianceConfig):
    """
    Generate alert for compliance issues.
    """
    from api.notifications.models import Notification
    
    try:
        Notification.objects.create(
            point_catchment=config.point,
            title=f"Falta envío {config.provider.name.upper()} - {config.point.title}",
            message=f"El punto {config.point.title} no ha enviado datos a "
                    f"{config.provider.display_name} en las últimas 24 horas.",
            type_notification="CRITICAL",
            type_variable="TODOS",
            is_active=True,
            is_read=False,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=1),
            is_periodic=False,
        )
        logger.warning(f"Compliance alert generated for {config.point} → {config.provider}")
        
    except Exception as exc:
        logger.error(f"Failed to generate compliance alert: {exc}")
