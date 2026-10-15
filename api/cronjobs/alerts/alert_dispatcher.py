"""
Dispatcher de notificaciones para el subsistema de alertas.

Procesa AlertTrigger pendientes y envía notificaciones vía los
AlertChannel configurados para cada regla.
"""

import logging
from typing import Optional

import requests
from django.core.mail import send_mail
from django.utils import timezone

from api.core.models.alerts import AlertTrigger, AlertChannel
from api.core.models import InteractionDetail
from api.core.utils.google_chat import send_google_chat_message
from api.cronjobs.alerts.ai_diagnosis import generate_disconnection_diagnosis
from api.cronjobs.utils.logging_config import telemetry_logger
from api.cronjobs.utils.locks import cron_job_lock

logger = logging.getLogger(__name__)


@cron_job_lock("alert_dispatcher", timeout=120)
def run_dispatcher(dry_run: bool = False, max_triggers: int = 50) -> dict:
    """
    Procesa AlertTrigger pendientes y envía notificaciones.

    Args:
        dry_run: Si True, solo loguea sin enviar.
        max_triggers: Límite de triggers a procesar por ejecución.

    Returns:
        Dict con estadísticas.
    """
    stats = {"processed": 0, "sent": 0, "errors": 0, "channels": 0, "dry_run": dry_run}

    pending = (
        AlertTrigger.objects.filter(notification_sent=False, is_acknowledged=False)
        .select_related("alert_rule", "alert_rule__point_catchment")
        .prefetch_related("alert_rule__channels")
        .order_by("triggered_at")[:max_triggers]
    )

    telemetry_logger.info(f"[ALERT_DISPATCHER] Triggers pendientes a procesar (max={max_triggers}): {len(pending)}")

    for trigger in pending:
        try:
            channels = [c for c in trigger.alert_rule.channels.all() if c.is_active]
            if not channels:
                telemetry_logger.warning(
                    f"[ALERT_DISPATCHER] Trigger {trigger.id} sin canales activos. Marcando como enviado."
                )
                if not dry_run:
                    trigger.notification_sent = True
                    trigger.notification_sent_at = __import__("django.utils.timezone").utils.timezone.now()
                    trigger.save(update_fields=["notification_sent", "notification_sent_at"])
                stats["processed"] += 1
                continue

            # Generar diagnóstico IA para alertas de desconexión (antes de enviar)
            if not dry_run and trigger.alert_rule.target_type == "DISCONNECTION" and not trigger.ai_diagnosis:
                try:
                    point = trigger.point_catchment or trigger.alert_rule.point_catchment
                    if point:
                        last_record = None
                        if trigger.interaction_detail_id:
                            last_record = InteractionDetail.objects.filter(
                                id=trigger.interaction_detail_id
                            ).first()
                        trigger.ai_diagnosis = generate_disconnection_diagnosis(
                            point=point,
                            last_record=last_record,
                            days_disconnected=trigger.value_at_trigger or 0,
                        )
                        trigger.save(update_fields=["ai_diagnosis"])
                except Exception as e:
                    telemetry_logger.warning(f"[ALERT_DISPATCHER] Error generando IA diagnosis para trigger {trigger.id}: {e}")

            channel_errors = []
            for channel in channels:
                stats["channels"] += 1
                ok, err = _send_via_channel(trigger, channel, dry_run)
                if ok:
                    stats["sent"] += 1
                else:
                    stats["errors"] += 1
                    channel_errors.append(f"{channel.channel_type}: {err}")

            if not dry_run:
                trigger.notification_sent = True
                trigger.notification_sent_at = timezone.now()
                if channel_errors:
                    trigger.notification_error = " | ".join(channel_errors)
                trigger.save(update_fields=["notification_sent", "notification_sent_at", "notification_error"])

            stats["processed"] += 1

        except Exception as e:
            stats["errors"] += 1
            telemetry_logger.error(f"[ALERT_DISPATCHER] Error procesando trigger {trigger.id}: {e}", exc_info=True)

    telemetry_logger.info(
        f"[ALERT_DISPATCHER] Fin | Procesados={stats['processed']} | "
        f"Enviados={stats['sent']} | Errores={stats['errors']}"
    )
    return stats


def _send_via_channel(trigger, channel: AlertChannel, dry_run: bool) -> tuple:
    """
    Envía una notificación a través de un canal específico.

    Returns:
        (success: bool, error_message: str or None)
    """
    message = _build_message(trigger)

    if dry_run:
        telemetry_logger.info(
            f"[ALERT_DISPATCHER] DRY-RUN envío a {channel.channel_type} → {channel.destination[:50]}"
        )
        return True, None

    try:
        if channel.channel_type == "EMAIL":
            _send_email(channel.destination, message)
        elif channel.channel_type == "GOOGLE_CHAT":
            send_google_chat_message(message, webhook_url=channel.destination)
        elif channel.channel_type == "WEBHOOK":
            _send_webhook(channel.destination, trigger, message)
        elif channel.channel_type == "SMS":
            # TODO: Integrar con servicio SMS cuando esté disponible
            telemetry_logger.warning(f"[ALERT_DISPATCHER] SMS no implementado aún: {channel.destination}")
            return False, "SMS no implementado"
        else:
            return False, f"Canal desconocido: {channel.channel_type}"

        return True, None

    except Exception as e:
        err_msg = str(e)
        telemetry_logger.error(
            f"[ALERT_DISPATCHER] Fallo envío {channel.channel_type} a {channel.destination[:50]}: {err_msg}"
        )
        return False, err_msg


def _build_message(trigger: AlertTrigger) -> str:
    """Construye el mensaje de notificación para un trigger."""
    rule = trigger.alert_rule
    # Usar el punto específico que disparó el trigger (soporta M2M y globales)
    point = trigger.point_catchment or rule.point_catchment
    point_name = point.title if point else "Global"
    client_name = point.project.client.name if point and point.project and point.project.client else "N/A"

    lines = [
        f"🚨 ALERTA: {rule.name}",
        f"📍 Punto: {point_name}",
        f"🏢 Cliente: {client_name}",
        f"📋 Tipo: {rule.get_target_type_display()}",
    ]

    if trigger.value_at_trigger is not None:
        lines.append(f"📊 Valor: {trigger.value_at_trigger}")
    if trigger.threshold_breached is not None:
        lines.append(f"⚠️ Umbral: {trigger.threshold_breached}")

    lines.append(f"🕐 Fecha: {trigger.triggered_at.strftime('%d/%m/%Y %H:%M')}")

    # Incluir diagnóstico IA si existe
    if trigger.ai_diagnosis:
        lines.append("")
        lines.append("🤖 Análisis técnico:")
        lines.append(trigger.ai_diagnosis)
        lines.append("")
        lines.append("📌 Asignado a: <users/andresnunez@smarthydro>")

    return "\n".join(lines)


def _send_email(destination: str, message: str):
    """Envía email vía Django send_mail."""
    rule_name = message.split("\n")[0].replace("🚨 ALERTA: ", "")
    send_mail(
        subject=f"[SmartHydro] Alerta: {rule_name}",
        message=message,
        from_email=None,  # Usa DEFAULT_FROM_EMAIL de settings
        recipient_list=[d.strip() for d in destination.split(",")],
        fail_silently=False,
    )


def _send_webhook(destination: str, trigger: AlertTrigger, message: str):
    """Envía payload JSON a un webhook."""
    point = trigger.point_catchment or trigger.alert_rule.point_catchment
    payload = {
        "alert_name": trigger.alert_rule.name,
        "point_id": point.id if point else None,
        "point_name": point.title if point else None,
        "target_type": trigger.alert_rule.target_type,
        "value_at_trigger": str(trigger.value_at_trigger) if trigger.value_at_trigger else None,
        "threshold_breached": str(trigger.threshold_breached) if trigger.threshold_breached else None,
        "triggered_at": trigger.triggered_at.isoformat(),
        "message": message,
    }
    resp = requests.post(destination, json=payload, timeout=10)
    resp.raise_for_status()
