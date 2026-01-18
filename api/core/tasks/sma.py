"""
Celery Tasks for SMA Data Submission (V3)
Replaces legacy InteractionDetail logic with dynamic TelemetryRecord
"""

import logging
import requests
import pytz
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple

from celery import shared_task
from django.utils import timezone

from api.telemetry.models import DgaDataConfigCatchment, TelemetryRecord

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, retry_backoff=True)
def process_sma_queue(self):
    """
    Process SMA submissions for recently created V3 records
    """
    try:
        logger.info("Starting SMA queue processing V3")
        
        # Define time window (last 2 hours)
        cutoff_time = timezone.now() - timedelta(hours=2)
        
        # Points enabled for SMA
        sma_catchment_points = [1]  # ID 1 as per original script
        
        # Get pending records from V3
        pending_records = TelemetryRecord.objects.filter(
            point_id__in=sma_catchment_points,
            created__gte=cutoff_time,
            n_voucher__isnull=True
        ).order_by("-created")[:50]
        
        if not pending_records.exists():
            logger.info("No pending SMA records found in V3")
            return {'status': 'completed', 'processed': 0}
            
        token = get_sma_token()
        if not token:
            logger.error("Failed to obtain SMA token")
            return {'status': 'failed', 'error': 'Auth failed'}
            
        processed = 0
        successful = 0
        
        for record in pending_records:
            try:
                # Check if it's a 5-minute interval record
                dt = record.timestamp
                if dt.minute % 5 != 0:
                    continue
                    
                processed += 1
                
                dga_config = DgaDataConfigCatchment.objects.filter(
                    point_catchment_id=record.point_id
                ).last()
                
                if not dga_config:
                    continue
                
                payload = prepare_sma_payload(record, dga_config)
                if not payload:
                    continue
                    
                success, message, verification_id = send_to_sma(payload, token, dga_config)
                
                # Update record
                record.return_dga = message
                record.n_voucher = verification_id
                
                if success:
                    record.send_dga = False
                    record.is_error = False
                    successful += 1
                else:
                    record.send_dga = True
                    record.is_error = True
                    
                record.save(update_fields=['return_dga', 'n_voucher', 'send_dga', 'is_error'])
                
            except Exception as exc:
                logger.error(f"Error processing SMA record V3 {record.id}: {exc}")
                
        return {'processed': processed, 'successful': successful}
        
    except Exception as exc:
        logger.error(f"SMA processing failed: {exc}")
        self.retry(countdown=300, exc=exc)


def get_sma_token() -> Optional[str]:
    """Get SMA authentication token"""
    try:
        url = "https://conexiones.sma.gob.cl/api/v1/auth"
        payload = {"usuario": "76006727-K", "password": "{O=+b_k_aD"}
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json().get("token")
    except Exception as exc:
        logger.error(f"Error getting SMA token: {exc}")
        return None


def prepare_sma_payload(record: TelemetryRecord, dga_config: DgaDataConfigCatchment) -> Optional[dict]:
    """Prepare payload for SMA API from V3 record"""
    try:
        chile_tz = pytz.timezone("America/Santiago")
        dt_chile = record.timestamp.astimezone(chile_tz)
        timestamp_str = dt_chile.strftime("%Y-%m-%dT%H:%M:%S")

        params = []
        data = record.data
        
        # Flow (Q)
        flow = data.get('flow', data.get('caudal'))
        if flow is not None:
            params.append({
                "nombre": "Q",
                "valor": str(flow),
                "unidad": "l/s",
                "estampaTiempo": timestamp_str,
            })
            
        # Total (VA)
        total = data.get('total')
        if total is not None:
            params.append({
                "nombre": "VA",
                "valor": str(total),
                "unidad": "m3",
                "estampaTiempo": timestamp_str,
            })
            
        if not params:
            return None
            
        return [{
            "dispositivoId": "12180",
            "parametros": params,
        }]
    except Exception as exc:
        logger.error(f"Error preparing SMA payload: {exc}")
        return None


def send_to_sma(data: list, token: str, dga_config: DgaDataConfigCatchment) -> Tuple[bool, str, str]:
    """Send data to SMA API"""
    try:
        code_dga = dga_config.code_dga
        flow_granted = dga_config.total_granted_dga
        
        if not code_dga or not flow_granted:
            return False, "Missing config", ""
            
        numbers = re.findall(r"\d+", code_dga)
        if not numbers:
            return False, "Invalid code_dga", ""
        uf_id = numbers[0]
        process_id = str(int(flow_granted))
        
        url = f"https://conexiones.sma.gob.cl/api/v1/ufs/{uf_id}/procesos/{process_id}/registros"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            resp_json = response.json()
            return True, resp_json.get("mensaje", "OK"), resp_json.get("IdVerificacion", "")
        else:
            return False, f"HTTP {response.status_code}: {response.text}", ""
    except Exception as exc:
        return False, str(exc), ""
