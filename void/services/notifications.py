"""Dispatch de notificaciones para alertas de void."""
import logging
from typing import Any, Dict, List

from django.core.mail import send_mail
from django.utils import timezone

from void.models import AlertTrigger

logger = logging.getLogger(__name__)


class AlertDispatcher:
    """Envía AlertTrigger por los canales configurados."""

    def dispatch(self, trigger: AlertTrigger) -> Dict[str, Any]:
        """Envía un trigger por todos sus canales y retorna resultado."""
        results = {}
        for channel in trigger.channels:
            try:
                results[channel] = self._send_channel(trigger, channel)
            except Exception as exc:
                logger.exception("Error enviando alerta %s por %s: %s", trigger.id, channel, exc)
                results[channel] = {"ok": False, "error": str(exc)}

        all_ok = all(r.get("ok") for r in results.values()) if results else False
        trigger.status = "dispatched" if all_ok else "failed"
        trigger.dispatched_at = timezone.now()
        trigger.dispatch_result = results
        trigger.save(update_fields=["status", "dispatched_at", "dispatch_result"])
        return results

    def dispatch_pending(self, limit: int = 100) -> Dict[str, int]:
        """Procesa triggers pendientes en batch."""
        qs = AlertTrigger.objects.filter(status="pending").select_related("event", "rule")[:limit]
        stats = {"processed": 0, "dispatched": 0, "failed": 0}
        for trigger in qs:
            self.dispatch(trigger)
            stats["processed"] += 1
            if trigger.status == "dispatched":
                stats["dispatched"] += 1
            else:
                stats["failed"] += 1
        return stats

    def _send_channel(self, trigger: AlertTrigger, channel: str) -> Dict[str, Any]:
        recipients = trigger.recipients or {}
        if channel == "email":
            return self._send_email(trigger, recipients.get("emails", []))
        if channel == "sms":
            return self._send_sms(trigger, recipients.get("phones", []))
        if channel == "webhook":
            return self._send_webhook(trigger, recipients.get("webhook_url", ""))
        if channel == "in_app":
            return {"ok": True, "channel": "in_app", "note": "Marcado como in-app"}
        if channel == "push":
            return {"ok": True, "channel": "push", "note": "Push no implementado"}
        return {"ok": False, "error": f"Canal desconocido: {channel}"}

    def _send_email(self, trigger: AlertTrigger, emails: List[str]) -> Dict[str, Any]:
        if not emails:
            return {"ok": False, "error": "No hay destinatarios de email"}
        try:
            sent = send_mail(
                subject=f"Alerta: {trigger.rule.name}",
                message=trigger.message,
                from_email=None,
                recipient_list=emails,
                fail_silently=False,
            )
            return {"ok": sent > 0, "channel": "email", "recipients": emails, "sent_count": sent}
        except Exception as exc:
            return {"ok": False, "channel": "email", "error": str(exc)}

    def _send_sms(self, trigger: AlertTrigger, phones: List[str]) -> Dict[str, Any]:
        if not phones:
            return {"ok": False, "error": "No hay destinatarios de SMS"}
        return {"ok": True, "channel": "sms", "note": "SMS no implementado", "phones": phones}

    def _send_webhook(self, trigger: AlertTrigger, webhook_url: str) -> Dict[str, Any]:
        if not webhook_url:
            return {"ok": False, "error": "No hay webhook_url"}
        return {"ok": True, "channel": "webhook", "note": "Webhook no implementado", "url": webhook_url}
