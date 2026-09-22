"""Orquestador único de notificaciones por correo.

Política:
- Solo correo (Chat queda fuera de este módulo).
- Clientes (dueño/visor de puntos del ticket) solo si NOTIFY_CLIENTS=True
  o su email está en NOTIFY_CLIENTS_WHITELIST.
- SLA_OVERDUE_TEST_ONLY actúa como lista blanca global.
- NOTIFICATIONS_DRY_RUN registra sin enviar.
- batch_notifications() agrupa por subject y mergea destinatarios.
"""

import logging
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterable, Optional, Union

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

_batch_var: ContextVar = ContextVar("notification_batch", default=None)

RecipientLike = Union[str, object]


def is_client(user, ticket=None) -> bool:
    """True si el usuario es cliente del ticket (dueño o visor de puntos).

    Staff/superuser y operadores de la categoría del ticket nunca son clientes.
    Sin ticket, solo staff cuenta como no-cliente (resto: no-cliente por default
    del orquestador — aquí devolvemos False salvo relación con punto).
    """
    if user is None:
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return False

    if ticket is not None:
        category = ticket.category
        if category is not None and category.operators.filter(id=user.id).exists():
            return False
        for point in ticket.points.all():
            if point.owner_user_id == user.id:
                return True
            if point.users_viewers.filter(id=user.id).exists():
                return True
    return False


def _client_whitelist() -> set:
    return set(getattr(settings, "NOTIFY_CLIENTS_WHITELIST", None) or [])


def _test_only() -> set:
    return set(getattr(settings, "SLA_OVERDUE_TEST_ONLY", None) or [])


def _normalize_recipients(
    recipients: Iterable[RecipientLike], ticket
) -> list:
    """Filtra y normaliza destinatarios a una lista de emails únicos (ordenada)."""
    notify_clients = getattr(settings, "NOTIFY_CLIENTS", False)
    whitelist = _client_whitelist()
    test_only = _test_only()

    emails: list = []
    seen: set = set()

    for entry in recipients or []:
        email = None
        if entry is None:
            continue
        if isinstance(entry, str):
            email = entry.strip()
            if not email:
                continue
        else:
            user = entry
            if not getattr(user, "is_active", False):
                continue
            email = (getattr(user, "email", "") or "").strip()
            if not email:
                continue
            if not getattr(user, "notify_email", True):
                continue
            if not notify_clients and is_client(user, ticket):
                if email not in whitelist:
                    continue

        if email in seen:
            continue
        seen.add(email)
        emails.append(email)

    if test_only:
        allowed = test_only
        emails = [e for e in emails if e in allowed]

    return sorted(emails)


def _should_send(dedup_key: Optional[str]) -> bool:
    if not dedup_key:
        return True
    try:
        from django.core.cache import cache

        # add() es atómico: True si no existía (primer envío).
        return bool(cache.add(f"notif:dedup:{dedup_key}", 1, timeout=300))
    except Exception:
        # Fail-open: si el cache no está disponible, se envía.
        return True


def _send_email(
    subject: str,
    message: str,
    emails: list,
    html_message: Optional[str],
    from_email: Optional[str],
    fail_silently: bool,
) -> bool:
    if not emails:
        return False
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email or getattr(settings, "DEFAULT_FROM_EMAIL", "soporte@smarthydro.cl"),
            recipient_list=list(emails),
            html_message=html_message,
            fail_silently=fail_silently,
        )
        logger.info("Notificación enviada [%s] → %s", subject, ", ".join(emails))
        return True
    except Exception as exc:
        logger.error("Error enviando notificación [%s]: %s", subject, exc)
        return False


def notify(
    *,
    subject: str,
    message: str,
    recipients: Iterable[RecipientLike],
    ticket=None,
    html_message: Optional[str] = None,
    from_email: Optional[str] = None,
    fail_silently: bool = True,
    dedup_key: Optional[str] = None,
) -> bool:
    """Envía (o encola en batch) un correo tras aplicar la política central."""
    emails = _normalize_recipients(recipients, ticket)
    if not emails:
        return False

    if getattr(settings, "NOTIFICATIONS_DRY_RUN", False):
        logger.info("NOTIFICATIONS_DRY_RUN: omitido [%s] → %s", subject, ", ".join(emails))
        return False

    if not _should_send(dedup_key):
        logger.debug("Dedup notificación [%s] key=%s", subject, dedup_key)
        return False

    buffer = _batch_var.get()
    if buffer is not None:
        buffer.append(
            {
                "subject": subject,
                "message": message,
                "html_message": html_message,
                "from_email": from_email,
                "fail_silently": fail_silently,
                "emails": list(emails),
            }
        )
        return True

    return _send_email(subject, message, emails, html_message, from_email, fail_silently)


def _flush_batch(buf: list) -> None:
    groups: "OrderedDict[str, dict]" = OrderedDict()
    for item in buf:
        g = groups.get(item["subject"])
        if g is None:
            g = groups[item["subject"]] = {
                "message": item["message"],
                "html_message": item["html_message"],
                "from_email": item["from_email"],
                "fail_silently": item["fail_silently"],
                "emails": [],
                "seen": set(),
            }
        for email in item["emails"]:
            if email not in g["seen"]:
                g["seen"].add(email)
                g["emails"].append(email)

    for subject, g in groups.items():
        if g["emails"]:
            _send_email(
                subject,
                g["message"],
                g["emails"],
                g["html_message"],
                g["from_email"],
                g["fail_silently"],
            )


@contextmanager
def batch_notifications():
    """Agrupa notify() llamados dentro del bloque y los envía al salir (flush)."""
    token = _batch_var.set([])
    try:
        yield
    finally:
        buf = _batch_var.get()
        _batch_var.reset(token)
        _flush_batch(buf or [])
