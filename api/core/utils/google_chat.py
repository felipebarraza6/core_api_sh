
import requests
import logging
from django.conf import settings
from datetime import datetime

logger = logging.getLogger(__name__)

# Webhooks configurados desde settings
WEBHOOK_URL = getattr(settings, "GOOGLE_CHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/AAQAm9y1FaI/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=IMIDu11REWEYRywIk-zC_QFo5tPi04IqvY1ToNuk9Vo")
WEBHOOK_DGA_URL = getattr(settings, "GOOGLE_CHAT_WEBHOOK_DGA_URL", "https://chat.googleapis.com/v1/spaces/AAQAuNyVmJc/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=vGilyWJuJR8AKXYSobhQYLYNalVAqtUwyiEpm6iLGhU")

def send_google_chat_message(text, webhook_url=None):
    """Envía un mensaje simple a Google Chat."""
    url = webhook_url or WEBHOOK_URL
    if not url:
        logger.warning("Google Chat Webhook URL not configured.")
        return False

    try:
        response = requests.post(url, json={"text": text}, timeout=5)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Error sending Google Chat message: {e}")
        return False

def send_dga_chat_message(text):
    """Envía un mensaje al canal de reportes DGA."""
    return send_google_chat_message(text, webhook_url=WEBHOOK_DGA_URL)

def check_and_notify_reconnection(point_id, new_days_not_conection, point_name="Unknown", client_name="Unknown",
                                   flow=None, nivel=None, total=None, date_time_medition=None, date_time_last_logger=None,
                                   variable_details=None):
    """Verifica si un punto se ha reconectado (V3)."""
    if new_days_not_conection != 0:
        return

    try:
        from api.telemetry.models import TelemetryRecord
        from django_redis import get_redis_connection
        from datetime import datetime
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        reconnection_key = f"reconnection:v3:{point_id}:{today_str}"
        
        try:
            con = get_redis_connection("default")
            if con.exists(reconnection_key): return
        except Exception as e:
            logger.warning(f"Redis unavailable for reconnection dedup: {e}")
        
        # Buscar el último registro ANTES de este nuevo procesamiento
        last_record = TelemetryRecord.objects.filter(point_id=point_id).order_by('-timestamp').first()
        if not last_record: return
            
        # En V3 usamos is_error o metadata para detectar desconexión previa
        if last_record.is_error or last_record.metadata.get('days_not_connection', 0) > 0:
            import pytz
            chile_tz = pytz.timezone("America/Santiago")
            now_chile = datetime.now(chile_tz)
            processed_str = now_chile.strftime("%d/%m/%Y %H:%M")

            logger_str = "N/A"
            if date_time_last_logger:
                logger_dt = date_time_last_logger.astimezone(chile_tz) if hasattr(date_time_last_logger, 'astimezone') else date_time_last_logger
                logger_str = logger_dt.strftime("%d/%m/%Y %H:%M")

            medicion_str = "N/A"
            if date_time_medition:
                medicion_dt = date_time_medition.astimezone(chile_tz) if hasattr(date_time_medition, 'astimezone') else date_time_medition
                medicion_str = medicion_dt.strftime("%d/%m/%Y %H:%M")

            values_str = ""
            if flow is not None: values_str += f"\n💧 Caudal: {flow} L/s"
            if nivel is not None: values_str += f"\n📏 Nivel: {nivel} m"
            if total is not None: values_str += f"\n📊 Total: {total} m³"

            vars_info = ""
            if variable_details:
                vars_info = "\n\n📋 Detalle por variable:"
                for var in variable_details:
                    status_icon = "✅" if var.get('days', 0) == 0 else "⚠️"
                    days_info = " (conectado)" if var.get('days', 0) == 0 else f" ({var.get('days')} días sin conexión)"
                    vars_info += f"\n{status_icon} {var.get('name')}:{days_info}"

            msg = f"🟢 PUNTO RECONECTADO (V3)\n\n📢 Punto: {point_name}\n🏢 Cliente: {client_name}\n✅ Estado actual: Conectado\n\n📅 Fecha logger: {logger_str}\n📆 Fecha medición: {medicion_str}\n🕐 Procesado: {processed_str}{values_str}{vars_info}"
            
            logger.info(f"Reconnection V3 detected for point {point_id}. Sending alert.")
            send_google_chat_message(msg)
            
            try:
                con = get_redis_connection("default")
                con.setex(reconnection_key, 86400, "1")
            except: pass
            
    except Exception as e:
        logger.error(f"Error checking reconnection for point {point_id}: {e}")

def check_and_notify_disconnection(point_id, new_days_not_conection, point_name="Unknown", client_name="Unknown",
                                    date_time_medition=None, variable_details=None):
    """Verifica si un punto se ha desconectado (V3)."""
    try:
        from django_redis import get_redis_connection
        from datetime import datetime
        import pytz

        has_stale_vars = any(v.get('days', 0) > 0 for v in variable_details) if variable_details else False
        if new_days_not_conection <= 0 and not has_stale_vars: return

        if new_days_not_conection > 3: return
            
        if new_days_not_conection == 0 and has_stale_vars:
            failing_vars = [v for v in variable_details if v.get('days', 0) > 0]
            has_new_failure = any(v.get('days', 0) <= 3 for v in failing_vars)
            if not has_new_failure: return

        today_str = datetime.now().strftime("%Y-%m-%d")
        disconnection_key = f"disconnection:v3:{point_id}:{today_str}"

        try:
            con = get_redis_connection("default")
            if not con.set(disconnection_key, "1", nx=True, ex=86400): return
        except Exception as e:
            logger.error(f"Redis unavailable for disconnection dedup: {e}")
            return

        is_partial = (new_days_not_conection == 0 and has_stale_vars)
        chile_tz = pytz.timezone("America/Santiago")
        now_chile = datetime.now(chile_tz)
        detected_str = now_chile.strftime("%d/%m/%Y %H:%M")

        medicion_str = "N/A"
        if date_time_medition:
            medicion_dt = date_time_medition.astimezone(chile_tz) if hasattr(date_time_medition, 'astimezone') else date_time_medition
            medicion_str = medicion_dt.strftime("%d/%m/%Y %H:%M")

        status_header = "🔴 PUNTO DESCONECTADO (V3)" if not is_partial else "⚠️ DESCONEXIÓN PARCIAL (V3)"
        
        vars_info = ""
        if variable_details:
            vars_info = "\n\n📋 Detalle por variable:"
            for var in variable_details:
                status_icon = "✅" if var.get('days', 0) == 0 else "❌"
                days_txt = " (OK)" if var.get('days', 0) == 0 else (f" ({var.get('days')} días sin conexión)" if var.get('days', 0) < 9999 else " (Sin datos)")
                display_name = f"{var.get('type', 'VAR')} - {var.get('name', '')}"
                vars_info += f"\n{status_icon} {display_name}:{days_txt}"

        msg = f"{status_header}\n\n📢 Punto: {point_name}\n🏢 Cliente: {client_name}"
        msg += f"\n⚠️ Días sin conexión: {new_days_not_conection if new_days_not_conection < 9999 else 'Sin datos'}"
        msg += f"\n📅 Última medición: {medicion_str}\n🕐 Detectado: {detected_str}{vars_info}"

        logger.info(f"Disconnection V3 detected for point {point_id}. Sending alert.")
        send_google_chat_message(msg)

    except Exception as e:
        logger.error(f"Error checking disconnection for point {point_id}: {e}")

def check_and_notify_error(point_id, error_msg, point_name="Unknown", client_name="Unknown"):
    """Verifica si hay un error y envía alerta (V3)."""
    try:
        from django.core.cache import cache
        import hashlib
        
        error_hash = hashlib.md5(f"{point_id}:{error_msg}".encode()).hexdigest()
        cache_key = f"alert:error:v3:{point_id}:{error_hash}"
        
        if cache.get(cache_key): return
            
        msg = f"⚠️ ERROR DE MEDICIÓN (V3)\n\n📢 {point_name} ({client_name})\n🛑 {error_msg}"
        if send_google_chat_message(msg):
            cache.set(cache_key, "reported", timeout=86400)
    except Exception as e:
        logger.error(f"Error checking error alert for point {point_id}: {e}")
