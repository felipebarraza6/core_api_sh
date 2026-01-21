"""
Celery Tasks for SMA Data Submission (V3)
Replaces legacy hardcoded SMA logic with dynamic ComplianceService.
"""

import logging
from datetime import timedelta
from celery import shared_task
from django.utils import timezone

from api.telemetry.models import TelemetryRecord
from api.telemetry.providers.compliance_models import PointComplianceConfig
from api.telemetry.services.compliance_service import get_compliance_service

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, retry_backoff=True)
def process_sma_queue(self):
    """
    Process SMA submissions for recently created V3 records using dynamic ComplianceService.
    """
    try:
        logger.info("Starting dynamic SMA queue processing V3")
        
        # Define time window (last 2 hours)
        cutoff_time = timezone.now() - timedelta(hours=2)
        
        # Get point compliance configs for SMA that are active and enabled
        sma_configs = PointComplianceConfig.objects.filter(
            provider__name='sma',
            is_active=True,
            send_compliance=True
        ).select_related('point', 'provider')

        if not sma_configs.exists():
            logger.info("No active SMA configurations found")
            return {'status': 'completed', 'processed': 0}

        service = get_compliance_service()
        processed = 0
        successful = 0
        
        for config in sma_configs:
            # Get pending records for this point
            pending_records = TelemetryRecord.objects.filter(
                point=config.point,
                created__gte=cutoff_time
            ).order_by("-timestamp")[:50]

            for record in pending_records:
                # 1. Skip if already sent to SMA (check compliance_status JSON)
                if record.compliance_status.get('sma', {}).get('sent'):
                    continue
                
                # 2. Check frequency (e.g. 5-minute interval for SMA)
                if not service.should_submit(config, record.timestamp):
                    continue
                
                # 3. Submit!
                processed += 1
                success, message, voucher = service.submit_telemetry_record(record, config)
                
                # 4. Update record compliance status
                if not isinstance(record.compliance_status, dict):
                    record.compliance_status = {}
                
                record.compliance_status['sma'] = {
                    'sent': success,
                    'message': message,
                    'voucher': voucher,
                    'timestamp': timezone.now().isoformat()
                }
                
                if success:
                    successful += 1
                    record.is_error = False
                else:
                    record.is_error = True
                    
                record.save(update_fields=['compliance_status', 'is_error'])

        return {'processed': processed, 'successful': successful}
        
    except Exception as exc:
        logger.error(f"SMA processing failed: {exc}")
        self.retry(countdown=300, exc=exc)
