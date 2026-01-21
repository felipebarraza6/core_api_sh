"""
Celery Tasks for DGA Processing
Replaces legacy DgaDataConfigCatchment with dynamic ComplianceService.
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
def process_dga_queue(self):
    """
    Process pending DGA submissions (V3) using dynamic ComplianceService.
    """
    try:
        logger.info("Starting DGA queue processing V3")
        
        # Get active DGA configs
        dga_configs = PointComplianceConfig.objects.filter(
            provider__name='dga',
            is_active=True,
            send_compliance=True
        ).select_related('point', 'provider')

        if not dga_configs.exists():
            logger.info("No active DGA configurations found")
            return {'status': 'completed', 'processed': 0}

        service = get_compliance_service()
        processed = 0
        successful = 0
        
        # Look back 1 hour for pending records
        cutoff_time = timezone.now() - timedelta(hours=1)

        for config in dga_configs:
            pending_records = TelemetryRecord.objects.filter(
                point=config.point,
                timestamp__gte=cutoff_time
            ).order_by("-timestamp")

            for record in pending_records:
                # Skip if already sent
                if record.compliance_status.get('dga', {}).get('sent'):
                    continue
                
                # Check frequency/standard
                if not service.should_submit(config, record.timestamp):
                    continue
                
                processed += 1
                success, message, voucher = service.submit_telemetry_record(record, config)
                
                if not isinstance(record.compliance_status, dict):
                    record.compliance_status = {}
                
                record.compliance_status['dga'] = {
                    'sent': success,
                    'message': message,
                    'voucher': voucher,
                    'timestamp': timezone.now().isoformat()
                }
                
                if success:
                    successful += 1
                
                record.save(update_fields=['compliance_status'])

        return {'processed': processed, 'successful': successful}
        
    except Exception as exc:
        logger.error(f"DGA processing failed: {exc}")
        self.retry(countdown=300, exc=exc)

@shared_task(bind=True)
def submit_dga_for_point(self, point_id, start_date=None, end_date=None):
    """
    Manual re-submission of DGA data for a specific point.
    """
    try:
        config = PointComplianceConfig.objects.filter(
            point_id=point_id,
            provider__name='dga'
        ).first()

        if not config:
            return f"No DGA config found for point {point_id}"

        records = TelemetryRecord.objects.filter(point_id=point_id)
        if start_date:
            records = records.filter(timestamp__gte=start_date)
        if end_date:
            records = records.filter(timestamp__lte=end_date)
            
        service = get_compliance_service()
        count = 0
        for record in records:
            success, _, _ = service.submit_telemetry_record(record, config)
            if success:
                count += 1
        
        return f"Successfully re-submitted {count} records to DGA"
    except Exception as exc:
        logger.error(f"Manual DGA re-submission failed: {exc}")
        return str(exc)
