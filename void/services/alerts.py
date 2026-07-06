"""Motor de alertas para void.

Evalúa DeviceEvent contra AlertRule y genera AlertTrigger.
"""
import logging
from datetime import timedelta
from typing import List

from django.db import transaction
from django.utils import timezone

from void.models import AlertRule, AlertTrigger, Device, DeviceEvent

logger = logging.getLogger(__name__)


class AlertEngine:
    """Evalúa eventos contra reglas y crea triggers pendientes."""

    def evaluate_event(self, event: DeviceEvent) -> List[AlertTrigger]:
        """Crea triggers para todas las reglas que matcheen el evento."""
        if event.is_dispatched:
            return []

        rules = AlertRule.objects.filter(is_active=True)
        triggers = []
        for rule in rules:
            if self._matches(rule, event) and self._cooldown_ok(rule, event):
                trigger = self._create_trigger(rule, event)
                if trigger:
                    triggers.append(trigger)

        if triggers:
            event.is_dispatched = True
            event.dispatched_at = timezone.now()
            event.save(update_fields=["is_dispatched", "dispatched_at"])

        return triggers

    def _matches(self, rule: AlertRule, event: DeviceEvent) -> bool:
        if rule.event_types and event.event_type not in rule.event_types:
            return False
        if rule.severities and event.severity not in rule.severities:
            return False
        if rule.variables and event.variable not in rule.variables:
            return False
        if rule.device_ids and event.device_id not in rule.device_ids:
            return False
        if rule.point_ids:
            point_id = getattr(event.device, "point_id", None)
            if point_id not in rule.point_ids:
                return False
        return True

    def _cooldown_ok(self, rule: AlertRule, event: DeviceEvent) -> bool:
        if not rule.cooldown_minutes:
            return True
        cutoff = timezone.now() - timedelta(minutes=rule.cooldown_minutes)
        return not AlertTrigger.objects.filter(
            rule=rule,
            event__device=event.device,
            event__variable=event.variable,
            created__gte=cutoff,
        ).exists()

    def _create_trigger(self, rule: AlertRule, event: DeviceEvent) -> AlertTrigger:
        message = self._render_message(rule, event)
        try:
            with transaction.atomic():
                trigger = AlertTrigger.objects.create(
                    rule=rule,
                    event=event,
                    channels=rule.channels or ["in_app"],
                    recipients=rule.recipients or {},
                    message=message,
                    status="pending",
                )
            return trigger
        except Exception as exc:
            logger.exception("Error creando AlertTrigger para evento %s: %s", event.id, exc)
            return None

    def _render_message(self, rule: AlertRule, event: DeviceEvent) -> str:
        template = rule.message_template or self._default_template()
        try:
            device_str = str(event.device)
        except Exception:
            device_str = f"device-{event.device_id}"

        point_str = ""
        try:
            point = getattr(event.device, "point", None)
            if point:
                point_str = str(point)
        except Exception:
            pass

        return template.format(
            event_type=event.event_type,
            device=device_str,
            variable=event.variable,
            severity=event.severity,
            message=event.message or "",
            timestamp=event.timestamp.isoformat() if event.timestamp else "",
            point=point_str,
        )

    @staticmethod
    def _default_template() -> str:
        return (
            "[{severity}] {event_type} en {device} / {variable}: {message}"
        )
