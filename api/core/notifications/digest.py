"""
Digest diario de notificaciones de tickets (correo).

Por qué existe
--------------
De los siete correos que dispara el orquestador, dos son de alto volumen y
bajo valor por envío:

* ``Ticket #N cambió a <estado>`` — se dispara desde 3 rutas distintas.
* ``Referenciaron tu ticket``      — uno por comentario con ``#<id>``.

En lugar de mandarlos en caliente se encolan por destinatario y salen
agrupados una vez al día desde el cron ``flush_ticket_digests``.

Garantías (leer antes de modificar)
-----------------------------------
1. **No se pierde ninguna notificación.** ``queue()`` solo devuelve ``True``
   cuando confirma que el índice quedó escrito; si no puede confirmarlo
   devuelve ``False`` y el llamador envía en caliente. Cubre Redis caído,
   ``IGNORE_EXCEPTIONS`` del backend y cualquier excepción.
   El orden de escritura es a propósito: primero los ítems, después el
   índice. Si falla el índice, los ítems quedan huérfanos y expiran solos
   por TTL → no hay doble envío.
2. **Misma política que el orquestador.** Los destinatarios se normalizan
   antes de encolar (``notify_email``, ``NOTIFY_CLIENTS``, whitelist,
   ``SLA_OVERDUE_TEST_ONLY``) y ``notify_email`` se vuelve a comprobar al
   enviar, por si hubo opt-out durante el día.
3. **Sin migraciones.** El estado vive en el cache (Redis) con TTL de 48 h,
   por si un flush falla un día.
4. ``NOTIFICATIONS_DRY_RUN`` corta el encolado (devuelve ``False``) para que
   el llamador siga pasando por ``notify()``, que ya sabe registrar el dry-run.
"""

import json
import logging
from datetime import timedelta
from typing import Iterable, Optional

from django.conf import settings
from django.core.cache import cache
from django.template.loader import render_to_string
from django.utils import timezone

from .orchestrator import (
    _normalize_recipients,
    _send_email,
    _should_send,
    notify,
)

logger = logging.getLogger(__name__)

_KEY_PREFIX = "notif:digest"
_TIMEOUT_SECONDS = 60 * 60 * 48  # 48 h → sobrevive a un flush fallido
# Cuántos días hacia atrás mira el flush. 2 por si el de ayer no corrió.
_FLUSH_LOOKBACK_DAYS = 2


def _date_keys() -> list:
    """Claves de fecha a procesar: hoy y los días previos (más antiguo al final)."""
    today = timezone.localdate()
    return [
        (today - timedelta(days=offset)).isoformat()
        for offset in range(_FLUSH_LOOKBACK_DAYS)
    ]


def _index_key(date_key: str) -> str:
    return f"{_KEY_PREFIX}:index:{date_key}"


def _items_key(date_key: str, email: str) -> str:
    return f"{_KEY_PREFIX}:items:{date_key}:{email.strip().lower()}"


def queue(
    *,
    emails: Iterable[str],
    subject: str,
    summary: str,
    link: Optional[str] = None,
) -> bool:
    """
    Encola un ítem de digest para cada destinatario.

    Devuelve ``True`` si el digest se hace cargo del envío, ``False`` si el
    llamador debe enviar en caliente (dry-run, cache no disponible o fallo).
    """
    emails = [str(e).strip().lower() for e in (emails or []) if str(e).strip()]
    if not emails:
        return False

    if getattr(settings, "NOTIFICATIONS_DRY_RUN", False):
        return False

    date_key = timezone.localdate().isoformat()
    payload = {
        "subject": subject,
        "summary": summary,
        "link": link or "",
        "at": timezone.now().isoformat(),
    }

    try:
        # 1) Ítems por destinatario (por si dos llamadas del día tienen
        #    conjuntos de destinatarios distintos).
        for email in emails:
            key = _items_key(date_key, email)
            items = list(cache.get(key) or [])
            items.append(payload)
            cache.set(key, items, timeout=_TIMEOUT_SECONDS)

        # 2) Índice: la única clave que gobierna el flush.
        index_key = _index_key(date_key)
        index = list(cache.get(index_key) or [])
        changed = False
        for email in emails:
            if email not in index:
                index.append(email)
                changed = True
        if changed:
            cache.set(index_key, index, timeout=_TIMEOUT_SECONDS)

        # 3) Verificación: sin índice legible no hay digest posible.
        if not cache.get(index_key):
            logger.warning(
                "Digest no encolado (índice ilegible) [%s] → envío en caliente",
                subject,
            )
            return False
        return True

    except Exception as exc:  # pragma: no cover - defensa
        logger.error(
            "No se pudo encolar digest [%s]: %s → envío en caliente",
            subject,
            exc,
        )
        return False


def send_or_queue(
    *,
    users: Iterable,
    ticket,
    subject: str,
    message: str,
    html_message: Optional[str],
    summary: str,
    link: Optional[str] = None,
    dedup_key: Optional[str] = None,
) -> bool:
    """
    Envía un correo de alto volumen por digest; si no puede encolarlo, mantiene
    el envío en caliente (comportamiento previo, sin regresión).

    Aplica aquí la política de destinatarios del orquestador, para que un
    destinatario filtrado no aparezca luego en el resumen.

    ``dedup_key`` se evalúa ANTES de encolar: la ventana de 300 s del
    orquestador no se perdía al pasar el correo al digest.
    """
    emails = _normalize_recipients(users, ticket)
    if not emails:
        return False
    if dedup_key and not _should_send(dedup_key):
        logger.debug("Digest [%s] bloqueado por dedup key=%s", subject, dedup_key)
        return True
    if queue(
        emails=emails, subject=subject, summary=summary, link=link
    ):
        logger.debug("Digest [%s] → %d destinatario(s)", subject, len(emails))
        return True
    notify(
        subject=subject,
        message=message,
        recipients=users,
        ticket=ticket,
        html_message=html_message,
        dedup_key=dedup_key,
    )
    return True


def _render(items: list, date_label: str):
    """Devuelve (asunto, texto plano, html) del resumen agrupado."""
    count = len(items)
    plural = "novedades" if count != 1 else "novedad"
    subject = f"📬 Resumen de tickets - {date_label} ({count} {plural})"

    plain_lines = [f"Resumen de tickets del {date_label}:", ""]
    for item in items:
        plain_lines.append(f"* {item['subject']}")
        if item.get("summary"):
            plain_lines.append(f"  {item['summary']}")
        if item.get("link"):
            plain_lines.append(f"  Ver: {item['link']}")
        plain_lines.append("")
    plain = "\n".join(plain_lines).strip()

    html = render_to_string(
        "tickets/daily_digest.html",
        {"date_label": date_label, "items": items, "count": count},
    )
    return subject, plain, html


def flush() -> int:
    """
    Envía todos los digests pendientes (hoy y días previos no procesados).

    Devuelve la cantidad de correos enviados.
    """
    if getattr(settings, "NOTIFICATIONS_DRY_RUN", False):
        logger.info("NOTIFICATIONS_DRY_RUN: digest no enviado")
        return 0

    from django.contrib.auth import get_user_model

    sent = 0
    for date_key in _date_keys():
        index_key = _index_key(date_key)
        try:
            emails = list(cache.get(index_key) or [])
        except Exception as exc:  # pragma: no cover - defensa
            logger.error("No se pudo leer el índice del digest %s: %s", date_key, exc)
            continue
        if not emails:
            continue

        # Opt-out de último momento (alguien pudo apagar el correo hoy).
        User = get_user_model()
        opted_out = set(
            User.objects.filter(
                email__in=emails, notify_email=False
            ).values_list("email", flat=True)
        )
        pending = [e for e in emails if e not in opted_out]

        # Los destinatarios de una misma llamada comparten ítems, así que se
        # agrupan por contenido idéntico: se mantiene UN correo con todos en
        # copia (como hacía notify en caliente), no uno por destinatario.
        groups: dict = {}
        for email in pending:
            try:
                items = list(cache.get(_items_key(date_key, email)) or [])
            except Exception as exc:  # pragma: no cover - defensa
                logger.error("No se pudieron leer los ítems del digest %s: %s", email, exc)
                continue
            if not items:
                continue
            signature = json.dumps(items, sort_keys=True, ensure_ascii=False)
            entry = groups.setdefault(signature, {"items": items, "emails": []})
            entry["emails"].append(email)

        for entry in groups.values():
            subject, plain, html = _render(entry["items"], date_key)
            ok = _send_email(
                subject, plain, entry["emails"], html, None, False
            )
            if ok:
                sent += 1

        # Borra aunque falle: reintentar mandaría el mismo resumen dos veces.
        for email in pending:
            try:
                cache.delete(_items_key(date_key, email))
            except Exception:  # pragma: no cover - defensa
                pass

        try:
            cache.delete(index_key)
        except Exception:  # pragma: no cover - defensa
            pass

        logger.info(
            "Digest %s procesado: %d destinatarios, %d correo(s) "
            "(%d opt-out)",
            date_key,
            len(pending),
            len(groups),
            len(emails) - len(pending),
        )

    return sent


def run():
    """Punto de entrada para el cron de django-crontab."""
    sent = flush()
    print(f"✅ Digest de tickets enviado a {sent} destinatarios")
    return sent
