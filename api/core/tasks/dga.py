"""
Celery Tasks for DGA Processing
Replaces cronjobs/dga/ with scalable task-based processing
"""

import logging
import time
from datetime import datetime, timedelta

import requests
from celery import shared_task
from django.db import transaction
from django.utils import timezone

from api.telemetry.models import DgaDataConfigCatchment, TelemetryRecord
from api.telemetry.services.telemetry_service import TelemetryService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, retry_backoff=True)
def process_dga_queue(self):
    """
    Process pending DGA submissions (V3)
    """
    start_time = time.time()
    processed = 0
    errors = 0

    try:
        logger.info("Starting DGA queue processing (V3)")

        # Get pending DGA records (limit batch size)
        pending_records = (
            TelemetryRecord.objects.filter(send_dga=True, is_error=False)
            .select_related("point__dga_config")
            .order_by("timestamp")[:50]
        )

        if not pending_records.exists():
            logger.info("No pending DGA records to process")
            return {"status": "completed", "processed": 0, "errors": 0}

        # Process each record
        for record in pending_records:
            try:
                with transaction.atomic():
                    success = submit_to_dga(record)
                    if success:
                        # Mark as processed and remove send_dga flag
                        record.send_dga = False
                        record.save(update_fields=["send_dga"])
                        processed += 1
                    else:
                        errors += 1

            except Exception as exc:
                logger.error(f"Failed to process DGA for record {record.id}: {exc}")
                errors += 1

        execution_time = time.time() - start_time

        logger.info(
            f"DGA processing completed: {processed} processed, "
            f"{errors} errors, {execution_time:.2f}s"
        )

        return {
            "status": "completed",
            "processed": processed,
            "errors": errors,
            "execution_time": execution_time,
            "batch_size": len(pending_records),
        }

    except Exception as exc:
        logger.error(f"DGA queue processing failed: {exc}")
        self.retry(countdown=300, exc=exc)  # Retry in 5 minutes


def submit_to_dga(record):
    """
    Submit telemetry record to DGA service (V3)
    """
    try:
        dga_config = getattr(record.point, "dga_config", None)

        if not dga_config or not dga_config.send_dga:
            logger.warning(f"No DGA config or disabled for point {record.point.id}")
            return False

        # Prepare DGA data payload
        payload = prepare_dga_payload(record, dga_config)

        if not payload:
            logger.error(f"Failed to prepare DGA payload for record {record.id}")
            return False

        # Submit to DGA service
        success, response_data = send_dga_request(payload, dga_config)

        if success:
            # Update record with DGA response
            record.return_dga = response_data.get("response", "")
            record.n_voucher = response_data.get("voucher", "")
            record.save(update_fields=["return_dga", "n_voucher"])

            logger.info(f"Successfully submitted to DGA for record {record.id}")
            return True
        else:
            # Log error but don't mark as error (will retry)
            record.return_dga = response_data.get("error", "Submission failed")
            record.save(update_fields=["return_dga"])

            logger.warning(
                f"DGA submission failed for record {record.id}: {response_data}"
            )
            return False

    except Exception as exc:
        logger.error(f"Error submitting to DGA for record {record.id}: {exc}")
        return False


def prepare_dga_payload(record, dga_config):
    """
    Prepare data payload for DGA submission (V3)
    """
    try:
        data = record.data

        payload = {
            "codigo_obra": dga_config.code_dga,
            "fecha_medicion": record.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "caudal_litro_segundo": float(data.get("flow", data.get("caudal", 0))),
            "volumen_total_m3": float(data.get("total", 0)),
            "nivel_mt": float(data.get("nivel", 0)),
            "informante_rut": dga_config.rut_report_dga,
            "informante_nombre": dga_config.name_informant,
            "sector_hidrologico": dga_config.shac or "",
            "region": dga_config.region_dga or "",
            "tipo_agua": dga_config.type_dga,
            "caudal_otorgado": float(dga_config.flow_granted_dga or 0),
            "volumen_otorgado": dga_config.total_granted_dga or 0,
        }

        # Validate required fields
        required_fields = ["codigo_obra", "fecha_medicion", "caudal_litro_segundo"]
        for field in required_fields:
            if not payload.get(field):
                logger.error(f"Missing required DGA field: {field}")
                return None

        return payload

    except Exception as exc:
        logger.error(f"Error preparing DGA payload: {exc}")
        return None


def send_dga_request(payload, dga_config):
    """
    Send HTTP request to DGA service
    Returns (success, response_data)
    """
    try:
        # DGA service endpoint (configure in settings)
        dga_endpoint = getattr(
            dga_config, "dga_endpoint", "https://dga.cl/api/telemetria"
        )

        # Get authentication
        password = dga_config.get_dga_password()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {password}",
            "User-Agent": "SmartHydro/2.0",
        }

        # Send request with timeout
        response = requests.post(
            dga_endpoint, json=payload, headers=headers, timeout=30  # 30 second timeout
        )

        if response.status_code == 200:
            response_data = response.json()
            return True, {
                "response": response_data.get("mensaje", "OK"),
                "voucher": response_data.get("comprobante", ""),
                "timestamp": timezone.now().isoformat(),
            }
        else:
            return False, {
                "error": f"HTTP {response.status_code}: {response.text}",
                "timestamp": timezone.now().isoformat(),
            }

    except requests.exceptions.Timeout:
        return False, {
            "error": "DGA service timeout",
            "timestamp": timezone.now().isoformat(),
        }
    except requests.exceptions.RequestException as exc:
        return False, {
            "error": f"Network error: {exc}",
            "timestamp": timezone.now().isoformat(),
        }
    except Exception as exc:
        return False, {
            "error": f"Unexpected error: {exc}",
            "timestamp": timezone.now().isoformat(),
        }


@shared_task(bind=True, max_retries=2)
def submit_dga_for_point(self, point_id, start_date=None, end_date=None):
    """
    Submit DGA data for a specific point within date range (V3)
    """
    try:
        logger.info(f"Submitting DGA data for point {point_id} (V3)")

        # Get records to submit
        records_query = TelemetryRecord.objects.filter(
            point_id=point_id, send_dga=True, is_error=False
        )

        if start_date:
            records_query = records_query.filter(timestamp__gte=start_date)
        if end_date:
            records_query = records_query.filter(timestamp__lte=end_date)

        records = records_query.order_by("timestamp")[:100]  # Limit batch

        # Process records
        successful = 0
        failed = 0

        for record in records:
            if submit_to_dga(record):
                successful += 1
            else:
                failed += 1

        logger.info(
            f"DGA submission completed for point {point_id}: {successful} success, {failed} failed"
        )

        return {
            "point_id": point_id,
            "successful": successful,
            "failed": failed,
            "total_processed": successful + failed,
        }

    except Exception as exc:
        logger.error(f"DGA submission failed for point {point_id}: {exc}")
        self.retry(countdown=60, exc=exc)


@shared_task(bind=True)
def check_dga_compliance_status(self):
    """
    Check compliance status for all DGA-enabled points (V3)
    """
    try:
        logger.info("Checking DGA compliance status (V3)")

        # Get all DGA-enabled points
        dga_points = DgaDataConfigCatchment.objects.filter(
            send_dga=True
        ).select_related("point_catchment")

        alerts_generated = 0

        for dga_config in dga_points:
            point = dga_config.point_catchment

            # Check recent submissions in V3
            recent_submissions = (
                TelemetryRecord.objects.filter(
                    point=point, timestamp__gte=timezone.now() - timedelta(hours=24)
                )
                .exclude(n_voucher__isnull=True)
                .exclude(n_voucher="")
            )

            if not recent_submissions.exists():
                # Generate compliance alert
                generate_compliance_alert(point, dga_config)
                alerts_generated += 1

        logger.info(f"Compliance check completed: {alerts_generated} alerts generated")

        return {"alerts_generated": alerts_generated, "points_checked": len(dga_points)}

    except Exception as exc:
        logger.error(f"Compliance check failed: {exc}")
        self.retry(countdown=300, exc=exc)


def generate_compliance_alert(point, dga_config):
    """
    Generate alert for DGA compliance issues
    """
    from api.telemetry.models import NotificationsCatchment, ResponseNotificationsCatchment

    try:
        alert = NotificationsCatchment.objects.create(
            point_catchment=point,
            title=f"Falta envío DGA - {point.title}",
            message=f"El punto {point.title} no ha enviado datos a DGA en las últimas 24 horas. "
            f"Código obra: {dga_config.code_dga}",
            type_notification="CRITICAL",
            type_variable="TODOS",
            is_active=True,
            is_read=False,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=1),
            is_periodic=False,
        )

        logger.warning(f"Compliance alert generated for point {point.id}")

    except Exception as exc:
        logger.error(f"Failed to generate compliance alert for point {point.id}: {exc}")
