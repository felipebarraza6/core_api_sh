"""
Envío de notificaciones push.

Diseño **fail-open**: este módulo jamás lanza una excepción hacia afuera.
Sirve para que el dispatcher de alertas, las señales de tickets o cualquier
vista puedan llamarla sin riesgo de romper su flujo principal.

Si `pywebpush` no está instalado, si `PUSH_ENABLED` es False o si faltan las
claves VAPID, el envío simplemente se omite y se loguea un warning.
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# Categorías de evento — deben calzar con los flags `User.push_*`.
CATEGORY_TICKETS = "tickets"
CATEGORY_ALERTS = "alerts"
CATEGORY_ANNOUNCEMENTS = "announcements"

# Mapa categoría → atributo de preferencia en User.
_CATEGORY_ATTR = {
    CATEGORY_TICKETS: "push_tickets",
    CATEGORY_ALERTS: "push_alerts",
    CATEGORY_ANNOUNCEMENTS: "push_announcements",
}

# Códigos de respuesta del proveedor de push que significan
# "esta suscripción ya no existe" → se desactiva, no se reintenta.
_DEAD_STATUSES = (404, 410)


def push_available() -> bool:
    """True sólo si el push está habilitado en settings y hay clave VAPID."""
    return bool(
        getattr(settings, "PUSH_ENABLED", False)
        and getattr(settings, "VAPID_PRIVATE_KEY", "")
        and getattr(settings, "VAPID_PUBLIC_KEY", "")
    )


def _load_pywebpush():
    """Import perezoso de pywebpush. Devuelve (webpush, WebPushException)."""
    try:
        from pywebpush import webpush, WebPushException  # noqa: WPS433
        return webpush, WebPushException
    except ImportError:
        return None, None


def user_can_receive_push(user, category: str) -> bool:
    """
    ¿Este usuario quiere recibir push de esta categoría?

    No considera el permiso del navegador (eso lo decide el cliente al
    suscribirse); sólo las preferencias guardadas en la BD.
    """
    if user is None or not getattr(user, "is_active", False):
        return False
    if not getattr(user, "notify_push", False):
        return False
    attr = _CATEGORY_ATTR.get(category)
    if not attr:
        return False
    return bool(getattr(user, attr, False))


def prune_dead_subscription(subscription) -> None:
    """Marca la suscripción como inactiva si el proveedor ya no la conoce."""
    try:
        if subscription.is_active:
            subscription.is_active = False
            subscription.save(update_fields=["is_active", "modified"])
            logger.info(
                "Suscripción push desactivada (proveedor la rechazó): user=%s endpoint=…%s",
                subscription.user_id,
                str(subscription.endpoint)[-12:],
            )
    except Exception as exc:  # pragma: no cover - defensa
        logger.warning("No se pudo desactivar suscripción push: %s", exc)


def send_webpush(
    user,
    title: str,
    body: str,
    url: str = None,
    data: dict = None,
    category: str = CATEGORY_ALERTS,
) -> bool:
    """
    Envía un push a todos los dispositivos activos de `user`.

    Devuelve True si al menos un envío tuvo éxito. Nunca lanza excepciones.
    """
    try:
        if not push_available():
            logger.debug("Push deshabilitado (PUSH_ENABLED o claves VAPID ausentes); envío omitido.")
            return False

        if not user_can_receive_push(user, category):
            return False

        webpush, WebPushException = _load_pywebpush()
        if webpush is None:
            logger.warning("pywebpush no está instalado; envío de push omitido.")
            return False

        subscriptions = list(
            user.push_subscriptions.filter(is_active=True)
        )
        if not subscriptions:
            return False

        payload = {
            "title": title,
            "body": body,
            "url": url or "/",
            "tag": category,
            "category": category,
        }
        if data:
            payload["data"] = data

        claims = {"sub": "mailto:%s" % getattr(settings, "VAPID_CLAIM_EMAIL", "soporte@smarthydro.cl")}
        vapid_key = settings.VAPID_PRIVATE_KEY

        sent = 0
        for subscription in subscriptions:
            # Solo canal WEB usa el protocolo Web Push estándar. El canal FCM
            # (app móvil nativa) requiere un sender distinto: ver docs/WEB_PUSH.md.
            if subscription.channel_type != "WEB":
                continue

            sub_info = {
                "endpoint": subscription.endpoint,
                "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
            }
            try:
                webpush(
                    subscription_info=sub_info,
                    data=json_dumps(payload),
                    vapid_private_key=vapid_key,
                    vapid_claims=claims,
                    timeout=10,
                )
                sent += 1
            except WebPushException as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status in _DEAD_STATUSES:
                    prune_dead_subscription(subscription)
                else:
                    logger.warning(
                        "Fallo push a user=%s (status=%s): %s",
                        subscription.user_id, status, exc,
                    )
            except Exception as exc:
                logger.warning("Fallo push inesperado a user=%s: %s", subscription.user_id, exc)

        return sent > 0

    except Exception as exc:  # pragma: no cover - defensa final
        logger.error("send_webpush falló de forma inesperada: %s", exc, exc_info=True)
        return False


def send_webpush_to_users(users, title: str, body: str, url: str = None,
                          data: dict = None, category: str = CATEGORY_ALERTS) -> dict:
    """
    Envía el mismo push a una lista de usuarios.

    Returns:
        {"attempted": n_usuarios_filtrados, "delivered": n_envíos_ok}
    """
    stats = {"attempted": 0, "delivered": 0}
    try:
        for user in users or []:
            if not user_can_receive_push(user, category):
                continue
            stats["attempted"] += 1
            if send_webpush(user, title=title, body=body, url=url, data=data, category=category):
                stats["delivered"] += 1
    except Exception as exc:  # pragma: no cover - defensa final
        logger.error("send_webpush_to_users falló: %s", exc, exc_info=True)
    return stats


def json_dumps(payload: dict) -> str:
    """Serialización a JSON tolerante a fallos (nunca debe romper un envío)."""
    import json
    try:
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        return json.dumps({"title": str(payload.get("title", "")),
                           "body": str(payload.get("body", ""))})
