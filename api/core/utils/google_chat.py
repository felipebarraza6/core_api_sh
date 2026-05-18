
import requests
import logging
from django.conf import settings
from datetime import datetime

logger = logging.getLogger(__name__)

# LEGACY: Las URLs de webhook ahora se configuran en settings/env.
# Los canales configurables usan AlertChannel desde la BD (ver alert_dispatcher.py).

def send_google_chat_message(text, webhook_url=None):
    """
    Envía un mensaje simple a Google Chat.
    Args:
        text: Mensaje a enviar
        webhook_url: URL del webhook (opcional, usa settings.GOOGLE_CHAT_WEBHOOK_URL)
    """
    url = webhook_url or settings.GOOGLE_CHAT_WEBHOOK_URL
    if not url:
        logger.warning("Google Chat Webhook URL not configured (settings.GOOGLE_CHAT_WEBHOOK_URL).")
        return False

    try:
        response = requests.post(
            url,
            json={"text": text},
            timeout=5
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Error sending Google Chat message: {e}")
        return False


def send_dga_chat_message(text):
    """
    Envía un mensaje al canal de reportes DGA.
    """
    return send_google_chat_message(text, webhook_url=settings.GOOGLE_CHAT_DGA_WEBHOOK_URL)

def check_and_notify_reconnection(point_id, new_days_not_conection, point_name="Unknown", client_name="Unknown",
                                   flow=None, nivel=None, total=None, date_time_medition=None, date_time_last_logger=None,
                                   variable_details=None):
    """
    Verifica si un punto se ha reconectado (estaba desconectado y ahora tiene 0 días sin conexión).
    Si es así, envía una alerta CON DEDUPLICACIÓN (solo 1 vez cada 24h).

    ⚠️ DESACTIVADA (2026-05-17): Migrada al subsistema configurable de alertas.
    Usar AlertRule con target_type='RECONNECTION' en /api/alert_rules/
    """
    logger.info(f"[MIGRADO] check_and_notify_reconnection desactivado para punto {point_id}. "
                f"Use el nuevo subsistema de alertas (AlertRule RECONNECTION).")
    return

    # Código legacy preservado abajo para referencia histórica:
    # pylint: skip-file
    # Solo nos interesa si ahora está conectado
    if new_days_not_conection != 0:
        return

    try:
        from api.core.models import InteractionDetail
        from django_redis import get_redis_connection
        from datetime import datetime
        
        # Deduplicación: verificar si ya notificamos esta reconexión hoy
        today_str = datetime.now().strftime("%Y-%m-%d")
        reconnection_key = f"reconnection:{point_id}:{today_str}"
        
        try:
            con = get_redis_connection("default")
            if con.exists(reconnection_key):
                # Ya notificamos esta reconexión hoy
                return
        except Exception as e:
            logger.warning(f"Redis unavailable for reconnection dedup: {e}")
        
        # Buscar el último registro ANTES de este nuevo procesamiento
        last_record = InteractionDetail.objects.filter(catchment_point_id=point_id).order_by('-date_time_medition').first()
        
        if not last_record:
            return # Primer registro, no hay reconexión
            
        # Si el último registro tenía desconexión (> 0)
        if last_record.days_not_conection > 0:
            # ¡RECONEXIÓN DETECTADA!
            import pytz
            chile_tz = pytz.timezone("America/Santiago")

            # Fecha de procesamiento (ahora)
            now_chile = datetime.now(chile_tz)
            processed_str = now_chile.strftime("%d/%m/%Y %H:%M")

            # Fecha del logger (cuando transmitió)
            logger_str = "N/A"
            if date_time_last_logger:
                if hasattr(date_time_last_logger, 'astimezone'):
                    logger_dt = date_time_last_logger.astimezone(chile_tz)
                else:
                    logger_dt = date_time_last_logger
                logger_str = logger_dt.strftime("%d/%m/%Y %H:%M")

            # Fecha de medición (cuando se tomó el dato)
            medicion_str = "N/A"
            if date_time_medition:
                if hasattr(date_time_medition, 'astimezone'):
                    medicion_dt = date_time_medition.astimezone(chile_tz)
                else:
                    medicion_dt = date_time_medition
                medicion_str = medicion_dt.strftime("%d/%m/%Y %H:%M")

            values_str = ""
            if flow is not None:
                values_str += f"\n💧 Caudal: {flow} L/s"
            if nivel is not None:
                values_str += f"\n📏 Nivel: {nivel} m"
            if total is not None:
                values_str += f"\n📊 Total: {total} m³"

            # Detalles de variables (si existen)
            vars_info = ""
            if variable_details:
                vars_info = "\n\n📋 Detalle por variable:"
                for var in variable_details:
                    status_icon = "✅" if var.get('days', 0) == 0 else "⚠️"
                    days_info = " (conectado)" if var.get('days', 0) == 0 else f" ({var.get('days')} días sin conexión)"
                    vars_info += f"\n{status_icon} {var.get('name')}:{days_info}"

            msg = f"🟢 PUNTO RECONECTADO\n\n📢 Punto: {point_name}\n🏢 Cliente: {client_name}\n🔌 Estado previo: {last_record.days_not_conection} días desconectado\n✅ Estado actual: Conectado\n\n📅 Fecha logger: {logger_str}\n📆 Fecha medición: {medicion_str}\n🕐 Procesado: {processed_str}{values_str}{vars_info}"
            
            logger.info(f"Reconnection detected for point {point_id}. Sending alert.")
            send_google_chat_message(msg)
            
            # Marcar como notificado en Redis (expira en 24h)
            try:
                con = get_redis_connection("default")
                con.setex(reconnection_key, 86400, "1")  # 24 horas
            except:
                pass
            
    except Exception as e:
        logger.error(f"Error checking reconnection for point {point_id}: {e}")


def check_and_notify_disconnection(point_id, new_days_not_conection, point_name="Unknown", client_name="Unknown",
                                    date_time_medition=None, variable_details=None):
    """
    Verifica si un punto se ha desconectado o tiene variables desfasadas.
    Envía una alerta CON DEDUPLICACIÓN (solo 1 vez cada 24h).

    ⚠️ DESACTIVADA (2026-05-17): Migrada al subsistema configurable de alertas.
    Usar AlertRule con target_type='DISCONNECTION' en /api/alert_rules/
    """
    logger.info(f"[MIGRADO] check_and_notify_disconnection desactivado para punto {point_id}. "
                f"Use el nuevo subsistema de alertas (AlertRule DISCONNECTION).")
    return

    # Código legacy preservado abajo para referencia histórica:
    # pylint: skip-file
    try:
        from api.core.models import InteractionDetail
        from django_redis import get_redis_connection
        from datetime import datetime
        import pytz

        # Determinar si hay alguna variable fallando (incluso si el punto en general min_days == 0)
        has_stale_vars = any(v.get('days', 0) > 0 for v in variable_details) if variable_details else False
        
        # Solo procedemos si el punto está desconectado (min_days > 0) o hay variables parciales fallando
        if new_days_not_conection <= 0 and not has_stale_vars:
            return

        # 🛑 EVITAR SPAM:
        # 1. Si es desconexión total y lleva más de 3 días, ignorar.
        if new_days_not_conection > 3:
            return
            
        # 2. Si es parcial (conectado pero con variables malas), verificar si hay alguna falla "NUEVA" (<= 3 días).
        # Si todas las variables malas son antiguas (> 3 días), ignorar.
        if new_days_not_conection == 0 and has_stale_vars:
            # Filtrar variables fallando
            failing_vars = [v for v in variable_details if v.get('days', 0) > 0]
            # Verificar si CUALQUIERA es reciente (<= 3)
            has_new_failure = any(v.get('days', 0) <= 3 for v in failing_vars)
            
            if not has_new_failure:
                return # Solo fallas viejas, no notificar

        # Deduplicación: verificar si ya notificamos esta desconexión hoy
        today_str = datetime.now().strftime("%Y-%m-%d")
        disconnection_key = f"disconnection:{point_id}:{today_str}"

        try:
            con = get_redis_connection("default")
            # ✅ ATOMIC CHECK & SET:
            # Retorna True si se asignó (somos el primero).
            # Retorna None/False si ya existía.
            if con.set(disconnection_key, "1", nx=True, ex=86400):
                logger.info(f"Redis lock acquired for {disconnection_key}. Sending alert.")
            else:
                # Ya existe el lock, ignoramos.
                logger.info(f"Skipping duplicate alert for {disconnection_key}.")
                return
        except Exception as e:
            logger.error(f"Redis unavailable for disconnection dedup: {e}. SUPPRESSING ALERT to prevent spam.")
            # Si Redis falla, asumimos que ya se envió para evitar bombardear al usuario.
            return

        # Determinamos si es una desconexión total o parcial
        # Si new_days_not_conection > 0, significa que TODAS las variables están fallando (es el mínimo)
        # Si es 0 pero has_stale_vars es True, es parcial.
        is_partial = (new_days_not_conection == 0 and has_stale_vars)
        
        chile_tz = pytz.timezone("America/Santiago")
        now_chile = datetime.now(chile_tz)
        detected_str = now_chile.strftime("%d/%m/%Y %H:%M")

        medicion_str = "N/A"
        if date_time_medition:
            if hasattr(date_time_medition, 'astimezone'):
                medicion_dt = date_time_medition.astimezone(chile_tz)
            else:
                medicion_dt = date_time_medition
            medicion_str = medicion_dt.strftime("%d/%m/%Y %H:%M")

        status_header = "🔴 PUNTO DESCONECTADO" if not is_partial else "⚠️ DESCONEXIÓN PARCIAL"
        
        # Detalles de variables
        vars_info = ""
        if variable_details:
            vars_info = "\n\n📋 Detalle por variable:"
            for var in variable_details:
                # Usar iconos descriptivos: ✅ OK, ❌ Fallo
                status_icon = "✅" if var.get('days', 0) == 0 else "❌"
                if var.get('days', 0) == 0:
                    days_txt = " (OK)"
                elif var.get('days', 0) >= 9999:
                    days_txt = " (Sin datos)"
                else:
                    days_txt = f" ({var.get('days')} días sin conexión)"
                
                # Format: ❌ TIPO - Nombre: (días)
                # Esto ayuda a identificar qué es "ai1ActualValue" (ej. CAUDAL)
                var_type = var.get('type', 'VAR')
                var_name = var.get('name', '')
                
                # Evitar redundancia si el nombre es igual al tipo
                if var_name.upper() == var_type.upper():
                    display_name = var_type
                else:
                    display_name = f"{var_type} - {var_name}"
                    
                vars_info += f"\n{status_icon} {display_name}:{days_txt}"

        msg = f"{status_header}\n\n📢 Punto: {point_name}\n🏢 Cliente: {client_name}"
        
        if new_days_not_conection >= 9999:
             msg += f"\n⚠️ Estado: Sin datos recientes (posible fallo de sensor o comunicación)"
        else:
             msg += f"\n⚠️ Días sin conexión: {new_days_not_conection}"
             
        msg += f"\n📅 Última medición (General): {medicion_str}\n🕐 Detectado: {detected_str}{vars_info}"

        logger.info(f"Disconnection/Partial error detected for point {point_id}. Sending alert.")
        try:
            send_google_chat_message(msg)
        except Exception as e:
            logger.error(f"Failed to send Google Chat message: {e}")
            # Opcional: Si falla el envío, ¿borramos la key de Redis para reintentar?
            # Por ahora mantenemos el bloqueo para evitar spam en loops de error.

    except Exception as e:
        logger.error(f"Error checking disconnection for point {point_id}: {e}")


def check_and_notify_error(point_id, error_msg, point_name="Unknown", client_name="Unknown"):
    """
    Verifica si hay un error y envía alerta si es un caso nuevo (no reportado hoy).
    Usa Redis para de-duplicar.
    También guarda el detalle del error para el reporte diario.

    ⚠️ DESACTIVADA (2026-05-17): Migrada al subsistema configurable de alertas.
    Usar AlertRule con target_type='PROCESSING_ERROR' en /api/alert_rules/

    Args:
        point_id (int): ID del punto.
        error_msg (str): Mensaje de error / descripción del problema.
        point_name (str): Nombre del punto.
        client_name (str): Nombre del cliente.
    """
    logger.info(f"[MIGRADO] check_and_notify_error desactivado para punto {point_id}. "
                f"Use el nuevo subsistema de alertas (AlertRule PROCESSING_ERROR).")
    return

    # Código legacy preservado abajo para referencia histórica:
    # pylint: skip-file
    try:
        from django.core.cache import cache
        import hashlib

        # Generar hash único para este error específico en este punto
        error_hash = hashlib.md5(f"{point_id}:{error_msg}".encode()).hexdigest()
        cache_key = f"alert:error:{point_id}:{error_hash}"
        
        # Verificar si ya se reportó en las últimas 24 horas
        if cache.get(cache_key):
            return
            
        # No reportado, enviar alerta
        msg = f"⚠️ ERROR DE MEDICIÓN\\n\\n📢 {point_name} ({client_name})\\n🛑 {error_msg}"
        
        if send_google_chat_message(msg):
            # Marcar como reportado por 24 horas
            cache.set(cache_key, "reported", timeout=86400)
            
            # Guardar en Redis para el reporte diario
            try:
                from django_redis import get_redis_connection
                
                today_str = datetime.now().strftime("%Y-%m-%d")
                
                # Agregar ID al set de errores del día
                daily_errors_key = f"daily_errors:{today_str}"
                con = get_redis_connection("default")
                con.sadd(daily_errors_key, point_id)
                con.expire(daily_errors_key, 86400)
                
                # Guardar el detalle del error (último error para este punto hoy)
                error_detail_key = f"error_detail:{point_id}:{today_str}"
                con.set(error_detail_key, error_msg[:200])  # Truncar a 200 chars
                con.expire(error_detail_key, 86400)
                
            except Exception as redis_err:
                logger.error(f"Error guardando error en Redis: {redis_err}")
                
    except Exception as e:
        logger.error(f"Error checking error alert for point {point_id}: {e}")

