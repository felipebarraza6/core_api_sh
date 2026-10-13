"""
Endpoints de notificaciones push para la app de escritorio / móvil.

Todos estos endpoints son **aditivos**: no modifican ninguna respuesta
existente. Están pensados para que una app consuma:

  - la suscripción push del dispositivo
  - las preferencias de notificación (con desactivación individual)
  - un feed unificado de notificaciones (tickets, alertas, avisos)

Documentación de integración completa en `docs/WEB_PUSH.md`.
"""

import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from api.core.models import (
    WebPushSubscription,
    TicketNotification,
    AlertTrigger,
    SystemEvent,
)
from api.core.utils.webpush import (
    CATEGORY_ALERTS,
    CATEGORY_ANNOUNCEMENTS,
    CATEGORY_TICKETS,
    push_available,
    send_webpush,
)
from .throttles import DashboardRateThrottle

logger = logging.getLogger(__name__)

# Límite de dispositivos suscritos por usuario. Si se supera, se desactivan
# primero las inactivas; si siguiendo sobra, se borran las más antiguas.
MAX_SUBSCRIPTIONS_PER_USER = 10

# Máximo de filas que se escanean por fuente al armar el feed unificado.
# Es un tope de seguridad: el feed nunca dispara una consulta pesada.
FEED_SCAN_LIMIT = 200

VALID_CATEGORIES = (CATEGORY_TICKETS, CATEGORY_ALERTS, CATEGORY_ANNOUNCEMENTS)


def _accessible_point_ids(user):
    """IDs de puntos visibles para el usuario (mismo criterio que tickets)."""
    from .views_tickets import _get_accessible_point_ids
    return _get_accessible_point_ids(user)


# ============================================================================
# CONFIGURACIÓN
# ============================================================================

class PushConfigView(APIView):
    """
    GET /api/ik/me/push/config/

    Devuelve todo lo que el cliente necesita para suscribirse:
    el interruptor global y la clave pública VAPID.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [DashboardRateThrottle]

    def get(self, request):
        from django.conf import settings
        user = request.user
        return Response({
            "enabled": push_available(),
            "vapidPublicKey": getattr(settings, "VAPID_PUBLIC_KEY", ""),
            "user": {
                "notify_push": bool(getattr(user, "notify_push", False)),
                "push_tickets": bool(getattr(user, "push_tickets", False)),
                "push_alerts": bool(getattr(user, "push_alerts", False)),
                "push_announcements": bool(getattr(user, "push_announcements", False)),
            },
            "subscription_count": WebPushSubscription.objects.filter(
                user=user, is_active=True
            ).count(),
        })


# ============================================================================
# SUSCRIPCIÓN / DESUSCRIPCIÓN
# ============================================================================

class PushSubscribeView(APIView):
    """
    POST   /api/ik/me/push/subscribe/  → guarda/actualiza la suscripción
    DELETE /api/ik/me/push/subscribe/  → la elimina (logout / desactivar)

    Body POST:
      {
        "endpoint": "https://fcm.../abc",
        "keys": {"p256dh": "...", "auth": "..."},
        "user_agent": "Chrome 129 / Linux",
        "channel_type": "WEB"          // opcional, default WEB
      }
    Body DELETE: {"endpoint": "https://fcm.../abc"}
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [DashboardRateThrottle]

    def post(self, request):
        endpoint = str(request.data.get("endpoint") or "").strip()
        keys = request.data.get("keys") or {}
        p256dh = str(keys.get("p256dh") or "").strip()
        auth = str(keys.get("auth") or "").strip()
        user_agent = str(request.data.get("user_agent") or "")[:300]
        channel_type = str(request.data.get("channel_type") or "WEB").upper()

        if not endpoint:
            return Response({"error": "endpoint es requerido."},
                            status=status.HTTP_400_BAD_REQUEST)
        if not endpoint.startswith("https://"):
            return Response({"error": "El endpoint debe ser https://."},
                            status=status.HTTP_400_BAD_REQUEST)
        if len(endpoint) > 1000:
            return Response({"error": "Endpoint demasiado largo."},
                            status=status.HTTP_400_BAD_REQUEST)
        if channel_type not in ("WEB", "FCM"):
            return Response({"error": "channel_type debe ser WEB o FCM."},
                            status=status.HTTP_400_BAD_REQUEST)
        if channel_type == "WEB" and (not p256dh or not auth):
            return Response(
                {"error": "Para canal WEB se requieren keys.p256dh y keys.auth."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        now = timezone.now()
        try:
            subscription, created = WebPushSubscription.objects.update_or_create(
                endpoint=endpoint,
                defaults={
                    "user": user,
                    "channel_type": channel_type,
                    "p256dh": p256dh,
                    "auth": auth,
                    "user_agent": user_agent,
                    "is_active": True,
                    "last_seen_at": now,
                },
            )
            self._enforce_limit(user)

            logger.info(
                "Suscripción push %s: user=%s endpoint=…%s",
                "creada" if created else "actualizada",
                user.id, endpoint[-12:],
            )
            return Response({
                "ok": True,
                "id": subscription.id,
                "created": created,
                "enabled": push_available(),
            }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

        except Exception as exc:
            logger.error("Error guardando suscripción push: %s", exc, exc_info=True)
            return Response({"error": "No se pudo guardar la suscripción."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request):
        endpoint = str(request.data.get("endpoint") or "").strip()
        if not endpoint:
            return Response({"error": "endpoint es requerido."},
                            status=status.HTTP_400_BAD_REQUEST)
        deleted, _ = WebPushSubscription.objects.filter(
            user=request.user, endpoint=endpoint
        ).delete()
        return Response({"ok": True, "deleted": deleted})

    @staticmethod
    def _enforce_limit(user):
        """Mantiene el tope de dispositivos por usuario."""
        qs = WebPushSubscription.objects.filter(user=user).order_by("-last_seen_at", "-created")
        total = qs.count()
        if total <= MAX_SUBSCRIPTIONS_PER_USER:
            return
        # Primero descartar inactivas.
        inactive_ids = list(
            qs.filter(is_active=False).values_list("id", flat=True)
        )[: total - MAX_SUBSCRIPTIONS_PER_USER]
        if inactive_ids:
            WebPushSubscription.objects.filter(id__in=inactive_ids).delete()
            total = qs.count()
        # Si aún sobra, borrar las más antiguas.
        if total > MAX_SUBSCRIPTIONS_PER_USER:
            extra_ids = list(qs.values_list("id", flat=True))[MAX_SUBSCRIPTIONS_PER_USER:]
            if extra_ids:
                WebPushSubscription.objects.filter(id__in=extra_ids).delete()


# ============================================================================
# PREFERENCIAS (desactivación individual por tipo de evento)
# ============================================================================

class PushPreferenceView(APIView):
    """
    GET  /api/ik/me/push/preferences/  → estado actual
    POST /api/ik/me/push/preferences/  → actualiza (parcial)

    Body:
      {
        "notify_push": true,          // interruptor general
        "push_tickets": true,         // respuestas / cambios de ticket
        "push_alerts": false,         // alertas de telemetría
        "push_announcements": true    // avisos generales
      }
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [DashboardRateThrottle]

    FIELDS = ("notify_push", "push_tickets", "push_alerts", "push_announcements")

    def get(self, request):
        user = request.user
        return Response({f: bool(getattr(user, f, False)) for f in self.FIELDS})

    def post(self, request):
        user = request.user
        updated = {}
        for field in self.FIELDS:
            if field in request.data:
                value = request.data.get(field)
                if not isinstance(value, bool):
                    return Response(
                        {"error": f"{field} debe ser booleano."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                setattr(user, field, value)
                updated[field] = value

        if updated:
            user.save(update_fields=list(updated.keys()))
            logger.info("Preferencias push actualizadas para user=%s: %s", user.id, updated)

        return Response({"ok": True, **{f: bool(getattr(user, f, False)) for f in self.FIELDS}})


# ============================================================================
# ENVÍO DE PRUEBA (auto-diagnóstico del cliente)
# ============================================================================

class PushTestView(APIView):
    """
    POST /api/ik/me/push/test/  → envía un push de prueba a ESTE usuario.

    Body opcional: {"category": "tickets" | "alerts" | "announcements"}
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [DashboardRateThrottle]

    def post(self, request):
        category = str(request.data.get("category") or CATEGORY_ALERTS)
        if category not in VALID_CATEGORIES:
            return Response(
                {"error": f"category debe ser uno de {VALID_CATEGORIES}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        subs = WebPushSubscription.objects.filter(user=user, is_active=True).count()

        if not push_available():
            return Response({
                "ok": False,
                "sent": False,
                "reason": "push_deshabilitado_en_backend",
                "detail": "El backend no tiene PUSH_ENABLED ni claves VAPID configuradas.",
                "active_subscriptions": subs,
            }, status=status.HTTP_409_CONFLICT)

        if not user.notify_push:
            return Response({
                "ok": False,
                "sent": False,
                "reason": "preferencia_general_desactivada",
                "active_subscriptions": subs,
            }, status=status.HTTP_409_CONFLICT)

        if not getattr(user, f"push_{category}", True):
            return Response({
                "ok": False,
                "sent": False,
                "reason": f"preferencia_{category}_desactivada",
                "active_subscriptions": subs,
            }, status=status.HTTP_409_CONFLICT)

        sent = send_webpush(
            user,
            title="✅ Prueba de notificación",
            body="Si ves esto, las notificaciones push funcionan en este dispositivo.",
            url="/",
            category=category,
        )
        return Response({
            "ok": True,
            "sent": sent,
            "active_subscriptions": subs,
            "reason": None if sent else "sin_suscripciones_activas_o_fallo_envio",
        })


# ============================================================================
# FEED UNIFICADO — lo que consume la app
# ============================================================================

def _iso(dt):
    return dt.isoformat() if dt else None


class MyNotificationsFeedView(APIView):
    """
    GET /api/ik/me/notifications/

    Feed unificado y paginado de las notificaciones del usuario.

    Filtros:
      ?source=all|tickets|alerts|events   (default all)
      ?unread_only=true
      ?limit=30&offset=0

    Respuesta:
      {
        "count": 12,
        "next": "...", "previous": null,
        "unread_count": {"total": 5, "tickets": 3, "alerts": 2, "events": 0},
        "results": [
          {"id": "ticket-42", "source": "ticket", "type": "REPLY",
           "title": "...", "message": "...", "created": "...",
           "is_read": false, "link": "/tickets/42"}
        ]
      }

    Sólo lectura: nunca modifica estado. Para marcar leídas usar
    /api/ik/tickets/notifications/mark-read/ y para descartar alertas
    /api/alert_triggers/<id>/ con {"is_acknowledged": true}.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [DashboardRateThrottle]

    def get(self, request):
        user = request.user
        source = (request.query_params.get("source") or "all").lower()
        unread_only = str(request.query_params.get("unread_only", "")).lower() in ("1", "true", "yes")
        try:
            limit = min(max(int(request.query_params.get("limit", 30)), 1), 100)
        except (TypeError, ValueError):
            limit = 30
        try:
            offset = max(int(request.query_params.get("offset", 0)), 0)
        except (TypeError, ValueError):
            offset = 0

        unread = self._unread_counts(user)
        items = []
        if source in ("all", "tickets"):
            items.extend(self._ticket_items(user, unread_only))
        if source in ("all", "alerts"):
            items.extend(self._alert_items(user, unread_only))
        if source in ("all", "events"):
            items.extend(self._event_items(user, unread_only))
        if source in ("all", "announcements"):
            items.extend(self._announcement_items(user, unread_only))

        items.sort(key=lambda x: x["_sort"], reverse=True)
        total = len(items)
        page = items[offset: offset + limit]
        for item in page:
            item.pop("_sort", None)

        # Siguiente offset, si lo hay (sin depender de paginator de DRF).
        next_offset = offset + limit
        base = request.build_absolute_uri().split("?")[0]
        next_url = f"{base}?limit={limit}&offset={next_offset}" if next_offset < total else None

        return Response({
            "count": total,
            "next": next_url,
            "previous": None,
            "unread_count": unread,
            "results": page,
        })

    # -- fuentes -------------------------------------------------------------

    @staticmethod
    def _unread_counts(user):
        tickets = TicketNotification.objects.filter(user=user, is_read=False).count()
        point_ids = _accessible_point_ids(user)
        alerts = AlertTrigger.objects.filter(
            point_catchment_id__in=point_ids, is_acknowledged=False
        ).count() if point_ids else 0
        events = SystemEvent.objects.filter(
            point_catchment_id__in=point_ids
        ).count() if point_ids else 0
        return {
            "tickets": tickets,
            "alerts": alerts,
            "events": events,
            "total": tickets + alerts,
        }

    def _ticket_items(self, user, unread_only):
        qs = TicketNotification.objects.filter(user=user).select_related("ticket", "comment")
        if unread_only:
            qs = qs.filter(is_read=False)
        items = []
        for n in qs.order_by("-created")[:FEED_SCAN_LIMIT]:
            items.append({
                "id": f"ticket-{n.id}",
                "source": "ticket",
                "type": n.notification_type,
                "title": f"Ticket #{n.ticket_id}",
                "message": n.message,
                "created": _iso(n.created),
                "is_read": n.is_read,
                "link": f"/tickets/{n.ticket_id}",
                "_sort": n.created,
            })
        return items

    def _alert_items(self, user, unread_only):
        point_ids = _accessible_point_ids(user)
        if not point_ids:
            return []
        qs = AlertTrigger.objects.filter(
            point_catchment_id__in=point_ids
        ).select_related("alert_rule", "point_catchment")
        if unread_only:
            qs = qs.filter(is_acknowledged=False)
        items = []
        for t in qs.order_by("-triggered_at")[:FEED_SCAN_LIMIT]:
            rule = t.alert_rule
            point = t.point_catchment or (rule.point_catchment if rule else None)
            # AlertTrigger no guarda texto libre: se arma el mensaje con la
            # regla + el valor observado al momento del disparo.
            parts = [rule.name if rule else "Alerta"]
            if t.value_at_trigger is not None:
                parts.append(f"valor {t.value_at_trigger}")
            if t.threshold_breached is not None:
                parts.append(f"umbral {t.threshold_breached}")
            items.append({
                "id": f"alert-{t.id}",
                "source": "alert",
                "type": (rule.target_type if rule else "ALERT"),
                "title": (rule.name if rule else "Alerta"),
                "message": " — ".join(str(p) for p in parts if p),
                "created": _iso(t.triggered_at),
                "is_read": bool(t.is_acknowledged),
                "link": f"/alerts/{t.id}",
                "_sort": t.triggered_at,
                "severity": (rule.severity if rule else None),
                "point": getattr(point, "title", None),
            })
        return items

    def _announcement_items(self, user, unread_only):
        """
        Avisos generales: `NotificationsCatchment` sin punto de captación.

        No entran en `unread_count` porque `is_read` es un flag GLOBAL del
        modelo, no por usuario: contarlos inflaría el badge permanentemente.
        """
        from api.core.models import NotificationsCatchment

        # Sin estado de lectura por usuario: en modo "solo no leídas" se omiten.
        if unread_only:
            return []

        qs = NotificationsCatchment.objects.filter(
            point_catchment__isnull=True, is_active=True
        ).order_by("-created")[:50]
        items = []
        for n in qs:
            items.append({
                "id": f"announcement-{n.id}",
                "source": "announcement",
                "type": n.type_notification,
                "title": n.title,
                "message": n.message,
                "created": _iso(n.created),
                "is_read": False,
                "link": "/avisos",
                "_sort": n.created,
            })
        return items

    def _event_items(self, user, unread_only):
        point_ids = _accessible_point_ids(user)
        if not point_ids:
            return []
        # SystemEvent no tiene flag de leído: se listan los últimos N y, en
        # "unread_only", sólo los que no tienen ticket asociado (aún sin gestionar).
        qs = SystemEvent.objects.filter(point_catchment_id__in=point_ids).select_related(
            "point_catchment"
        ).order_by("-created")[:FEED_SCAN_LIMIT]
        items = []
        for e in qs:
            items.append({
                "id": f"event-{e.id}",
                "source": "event",
                "type": e.event_type,
                "title": e.title,
                "message": e.message,
                "created": _iso(e.created),
                "is_read": False,
                "link": f"/points/{e.point_catchment_id}",
                "_sort": e.created,
                "severity": e.severity,
                "point": getattr(e.point_catchment, "title", None),
            })
        return items
