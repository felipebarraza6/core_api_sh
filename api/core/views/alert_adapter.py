"""
Adapter layer: sincroniza endpoints legacy (NotificationsCatchment)
con el nuevo subsistema de alertas (AlertRule / AlertTrigger).

Objetivo: las apps móviles/frontend siguen usando /api/notifications_catchment/
sin notar que internamente las alertas umbral ahora viven en AlertRule.

Estrategia:
- Las alertas umbral legacy (type_notification=ALERT + type_alert=MAX/MIN/EQUALS)
  se mantienen sincronizadas bidireccionalmente con AlertRule.
- Tickets de soporte (SUPPORT) y anuncios siguen 100% legacy.
- El cron legacy de evaluación está apagado; alert_engine.py evalúa las AlertRule.
- Los disparos (AlertTrigger) se mapean a formato legacy para que el frontend
  siga viendo historial en /api/response_notifications_catchment/.
"""

from decimal import Decimal
from typing import Any

from django.db.models import Count
from django.db.models.functions import ExtractHour
from datetime import timedelta

import pytz
from django.utils import timezone

from api.core.models.alerts import AlertRule, AlertChannel, AlertTrigger
from api.core.models.catchment_points import NotificationsCatchment


# ============================================================================
# MAPEO DE TIPOS
# ============================================================================

ALERT_TYPE_LEGACY_TO_NEW = {
    "MAX": "THRESHOLD_MAX",
    "MIN": "THRESHOLD_MIN",
    "EQUALS": "THRESHOLD_MAX",  # el nuevo sistema no tiene EQUALS
}

ALERT_TYPE_NEW_TO_LEGACY = {
    "THRESHOLD_MAX": "MAX",
    "THRESHOLD_MIN": "MIN",
}

SEVERITY_TO_FREQUENCY = {
    "CRITICAL": 1,
    "ALERT": 5,
    "WARNING": 10,
    "INFO": 60,
}


def is_threshold_alert(data: dict) -> bool:
    """Determina si un dict de entrada corresponde a una alerta umbral."""
    type_notification = data.get("type_notification") if isinstance(data, dict) else getattr(data, "type_notification", None)
    type_alert = data.get("type_alert") if isinstance(data, dict) else getattr(data, "type_alert", None)
    return type_notification == "ALERT" and type_alert in ("MAX", "MIN", "EQUALS")


def _get_emails_from_rule(rule: AlertRule) -> list:
    """Extrae emails de los canales EMAIL de una AlertRule."""
    emails = []
    for ch in rule.channels.filter(channel_type="EMAIL", is_active=True):
        for e in ch.destination.split(","):
            e = e.strip()
            if e and e not in emails:
                emails.append(e)
    return emails


def _build_legacy_dict(rule: AlertRule) -> dict:
    """Construye un dict con los campos de NotificationsCatchment a partir de AlertRule."""
    type_alert = ALERT_TYPE_NEW_TO_LEGACY.get(rule.target_type, "MAX")
    emails = _get_emails_from_rule(rule)
    return {
        "id": rule.legacy_notification_id or -(rule.id),
        "point_catchment": rule.point_catchment_id,
        "point_catchment_id": rule.point_catchment_id,
        "title": rule.name,
        "message": rule.description or rule.name,
        "type_variable": rule.variable_type,
        "value": int(rule.threshold_value) if rule.threshold_value is not None else 0,
        "type_alert": type_alert,
        "type_notification": "ALERT",
        "start_date": rule.start_date,
        "end_date": rule.end_date,
        "is_periodic": False,
        "is_active": rule.is_active,
        "is_read": False,
        "is_response": False,
        "is_wait": False,
        "is_finish": False,
        "status_dga": False,
        "status_sma": False,
        "emails": emails,
        "created": rule.created,
        "modified": rule.modified,
    }


def _build_legacy_response_dict(trigger: AlertTrigger) -> dict:
    """Construye un dict con los campos de ResponseNotificationsCatchment a partir de AlertTrigger."""
    rule = trigger.alert_rule
    point_name = trigger.point_catchment.title if trigger.point_catchment else (rule.point_catchment.title if rule.point_catchment else "Desconocido")
    msg = (
        f"Alerta umbral disparada: {rule.name}\n"
        f"Punto: {point_name}\n"
        f"Variable: {rule.variable_type}\n"
        f"Valor medido: {trigger.value_at_trigger}\n"
        f"Umbral: {trigger.threshold_breached}"
    )
    return {
        "id": -(trigger.id),
        "notification": _build_legacy_dict(rule),
        "notification_id": rule.legacy_notification_id or -(rule.id),
        "user": None,
        "user_id": None,
        "response": msg,
        "created": trigger.triggered_at,
        "modified": trigger.modified,
    }


# ============================================================================
# SINCRONIZACIÓN CREAR / ACTUALIZAR / ELIMINAR
# ============================================================================

def create_alert_rule_from_legacy(data: dict, legacy_instance: NotificationsCatchment) -> AlertRule:
    """
    Crea una AlertRule sincronizada a partir de una NotificationsCatchment recién creada.
    Se llama dentro del post_save o del ViewSet.create().
    """
    target_type = ALERT_TYPE_LEGACY_TO_NEW.get(legacy_instance.type_alert, "THRESHOLD_MAX")
    severity = legacy_instance.type_notification if legacy_instance.type_notification in ("INFO", "WARNING", "ALERT", "CRITICAL") else "WARNING"
    frequency = SEVERITY_TO_FREQUENCY.get(severity, 10)

    rule = AlertRule.objects.create(
        name=legacy_instance.title or f"Alerta {legacy_instance.id}",
        point_catchment=legacy_instance.point_catchment,
        target_type=target_type,
        variable_type=legacy_instance.type_variable,
        threshold_value=Decimal(str(legacy_instance.value)) if legacy_instance.value else Decimal("0"),
        check_frequency_minutes=frequency,
        cooldown_minutes=60,
        is_active=legacy_instance.is_active,
        start_date=legacy_instance.start_date,
        end_date=legacy_instance.end_date,
        legacy_notification_id=legacy_instance.id,
        severity=severity,
    )

    # Crear canales de email
    emails = legacy_instance.emails or []
    if isinstance(emails, str):
        emails = [emails]
    if emails:
        dest = ", ".join(str(e).strip() for e in emails if str(e).strip())
        if dest:
            AlertChannel.objects.create(
                alert_rule=rule,
                channel_type="EMAIL",
                destination=dest,
                is_active=True,
            )

    return rule


def update_alert_rule_from_legacy(legacy_instance: NotificationsCatchment) -> AlertRule | None:
    """
    Actualiza la AlertRule vinculada cuando se modifica el legacy.
    Devuelve la regla actualizada o None si no existe.
    """
    try:
        rule = AlertRule.objects.get(legacy_notification_id=legacy_instance.id)
    except AlertRule.DoesNotExist:
        return None

    target_type = ALERT_TYPE_LEGACY_TO_NEW.get(legacy_instance.type_alert, "THRESHOLD_MAX")
    severity = legacy_instance.type_notification if legacy_instance.type_notification in ("INFO", "WARNING", "ALERT", "CRITICAL") else "WARNING"
    frequency = SEVERITY_TO_FREQUENCY.get(severity, 10)

    rule.name = legacy_instance.title or rule.name
    rule.point_catchment = legacy_instance.point_catchment
    rule.target_type = target_type
    rule.variable_type = legacy_instance.type_variable
    rule.threshold_value = Decimal(str(legacy_instance.value)) if legacy_instance.value else Decimal("0")
    rule.check_frequency_minutes = frequency
    rule.is_active = legacy_instance.is_active
    rule.start_date = legacy_instance.start_date
    rule.end_date = legacy_instance.end_date
    rule.severity = severity
    rule.save()

    # Sincronizar emails
    emails = legacy_instance.emails or []
    if isinstance(emails, str):
        emails = [emails]
    dest = ", ".join(str(e).strip() for e in emails if str(e).strip())

    email_channel = rule.channels.filter(channel_type="EMAIL").first()
    if dest:
        if email_channel:
            email_channel.destination = dest
            email_channel.is_active = True
            email_channel.save(update_fields=["destination", "is_active"])
        else:
            AlertChannel.objects.create(
                alert_rule=rule,
                channel_type="EMAIL",
                destination=dest,
                is_active=True,
            )
    else:
        if email_channel:
            email_channel.is_active = False
            email_channel.save(update_fields=["is_active"])

    return rule


def delete_alert_rule_by_legacy(legacy_instance: NotificationsCatchment) -> bool:
    """
    Elimina la AlertRule vinculada cuando se elimina el legacy.
    Devuelve True si se eliminó algo.
    """
    deleted, _ = AlertRule.objects.filter(legacy_notification_id=legacy_instance.id).delete()
    return deleted > 0


# ============================================================================
# STATS PARA DETALLE DE ALERTA (sustituye / complementa get_stats legacy)
# ============================================================================

def get_alert_rule_stats(rule: AlertRule) -> dict:
    """
    Calcula estadísticas analíticas de una AlertRule a partir de sus AlertTrigger.
    Formato compatible con NotificationsCatchmentDetailSerializer.get_stats().
    """
    triggers = rule.triggers.all().order_by("triggered_at")
    total = triggers.count()

    if total == 0:
        return {
            "total_triggers": 0,
            "first_trigger": None,
            "last_trigger": None,
            "triggers_last_24h": 0,
            "triggers_last_7d": 0,
            "triggers_last_30d": 0,
            "active_days": 0,
            "avg_hours_between_triggers": None,
            "peak_hour": None,
            "last_measured_value": None,
            "history_limit_days": 30,
            "history_limit_records": 50,
            "trigger_history": [],
        }

    chile = pytz.timezone("America/Santiago")
    now = timezone.now().astimezone(chile)
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)
    last_30d = now - timedelta(days=30)

    first = triggers.first()
    last = triggers.last()

    triggers_24h = triggers.filter(triggered_at__gte=last_24h).count()
    triggers_7d = triggers.filter(triggered_at__gte=last_7d).count()
    triggers_30d = triggers.filter(triggered_at__gte=last_30d).count()

    active_days = triggers.datetimes("triggered_at", "day", order="ASC").distinct().count()

    avg_hours = None
    if total >= 2:
        deltas = []
        prev = None
        for t in triggers:
            if prev:
                delta = (t.triggered_at - prev.triggered_at).total_seconds() / 3600
                deltas.append(delta)
            prev = t
        if deltas:
            avg_hours = round(sum(deltas) / len(deltas), 2)

    peak_hour = None
    hour_counts = (
        triggers.annotate(hour=ExtractHour("triggered_at"))
        .values("hour")
        .annotate(count=Count("id"))
        .order_by("-count")
        .first()
    )
    if hour_counts:
        peak_hour = {"hour": hour_counts["hour"], "count": hour_counts["count"]}

    last_value = float(last.value_at_trigger) if last.value_at_trigger is not None else None

    trigger_history = []
    history_limit_days = 30
    history_cutoff = now - timedelta(days=history_limit_days)
    recent_triggers = list(triggers.filter(triggered_at__gte=history_cutoff)[:50])

    for t in recent_triggers:
        trigger_history.append({
            "triggered_at": t.triggered_at.isoformat(),
            "response_text": t.notification_error or f"Valor medido: {t.value_at_trigger}",
            "measured_value": float(t.value_at_trigger) if t.value_at_trigger is not None else None,
            "matched_interaction": None,  # No buscamos InteractionDetail por simplicidad
        })

    return {
        "total_triggers": total,
        "first_trigger": first.triggered_at.isoformat() if first else None,
        "last_trigger": last.triggered_at.isoformat() if last else None,
        "triggers_last_24h": triggers_24h,
        "triggers_last_7d": triggers_7d,
        "triggers_last_30d": triggers_30d,
        "active_days": active_days,
        "avg_hours_between_triggers": avg_hours,
        "peak_hour": peak_hour,
        "last_measured_value": last_value,
        "history_limit_days": history_limit_days,
        "history_limit_records": 50,
        "trigger_history": trigger_history,
    }


# ============================================================================
# LISTADO UNIFICADO DE RESPONSES (disparos)
# ============================================================================

def get_triggers_as_legacy_responses(legacy_notification_id: int | None = None) -> list[dict]:
    """
    Obtiene AlertTrigger mapeados a formato ResponseNotificationsCatchment.
    Si se pasa legacy_notification_id, filtra solo los triggers de esa regla.
    """
    qs = AlertTrigger.objects.select_related("alert_rule", "point_catchment")
    if legacy_notification_id:
        qs = qs.filter(alert_rule__legacy_notification_id=legacy_notification_id)
    else:
        qs = qs.filter(alert_rule__legacy_notification_id__isnull=False)

    results = []
    for trigger in qs.order_by("-triggered_at"):
        results.append(_build_legacy_response_dict(trigger))
    return results
