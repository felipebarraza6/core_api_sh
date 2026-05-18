#!/usr/bin/env python3
"""
Evaluador de alertas umbral configuradas por usuarios.

Este módulo evalúa las notificaciones de tipo MAX/MIN/EQUALS creadas
por los usuarios contra los últimos valores de telemetría, y envía
correos cuando se cumplen las condiciones.

Se ejecuta desde cron_alerts.py (cada 10 minutos) para no afectar
el rendimiento de la ingesta de telemetría.
"""

import logging
from datetime import datetime, timedelta

import pytz
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from api.core.models import CatchmentPoint, InteractionDetail, NotificationsCatchment

logger = logging.getLogger(__name__)

# Cooldown entre alertas repetidas del mismo umbral (en minutos)
ALERT_COOLDOWN_MINUTES = 60


def _get_numeric_value(interaction, type_variable):
    """
    Extraer el valor numérico de un InteractionDetail según el tipo de variable.

    Returns:
        float or None: El valor numérico, o None si no se puede obtener.
    """
    if not interaction:
        return None

    try:
        if type_variable == "NIVEL":
            return float(interaction.nivel) if interaction.nivel is not None else None

        elif type_variable == "CAUDAL":
            return float(interaction.flow) if interaction.flow is not None else None

        elif type_variable == "CAUDAL PROMEDIO":
            # CAUDAL_PROMEDIO no se persiste directamente en BD;
            # usamos el caudal instantáneo como proxy para alertas umbral.
            return float(interaction.flow) if interaction.flow is not None else None

        elif type_variable == "TOTALIZADO":
            if interaction.total:
                # El campo total es CharField; limpiar posibles comas/puntos
                clean = str(interaction.total).replace(".", "").replace(",", ".")
                return float(clean)
            return None

        elif type_variable == "TODOS":
            # Para "TODOS" devolvemos un dict para evaluación múltiple
            return {
                "NIVEL": float(interaction.nivel) if interaction.nivel is not None else None,
                "CAUDAL": float(interaction.flow) if interaction.flow is not None else None,
                "TOTALIZADO": float(str(interaction.total).replace(".", "").replace(",", ".")) if interaction.total else None,
            }

    except (ValueError, TypeError, AttributeError) as e:
        logger.warning(f"Error extrayendo valor {type_variable} de interaction {interaction.id}: {e}")
        return None

    return None


def _condition_met(type_alert, current_value, threshold):
    """
    Verificar si la condición umbral se cumple.

    Args:
        type_alert: "MAX", "MIN" o "EQUALS"
        current_value: valor actual (float)
        threshold: umbral configurado (int/float)

    Returns:
        bool
    """
    try:
        threshold = float(threshold)
        current_value = float(current_value)
    except (ValueError, TypeError):
        return False

    if type_alert == "MAX":
        return current_value > threshold
    elif type_alert == "MIN":
        return current_value < threshold
    elif type_alert == "EQUALS":
        # Tolerancia para floats
        return abs(current_value - threshold) < 0.01

    return False


import re

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def _get_recipients_for_alert(alerta):
    """
    Obtener lista de destinatarios para una alerta umbral.

    La app usa el campo 'emails' de la alerta para guardar los destinatarios.
    Fallback al campo 'message' para compatibilidad con alertas antiguas.
    SIEMPRE se envia al correo configurado en la alerta, no al owner del punto.

    Jerarquia:
        1. Emails extraidos del campo 'emails' de la alerta (nuevo campo, prioridad)
        2. Email extraido del campo 'message' de la alerta (compatibilidad legacy)
        3. Solo si no hay email en la alerta: fallback a config_alerts.py
        4. Solo si no hay nada: fallback a DEFAULT_FROM_EMAIL
    """
    from .config_alerts import ALERT_CONFIG

    recipients = []

    # 1. Emails en el campo 'emails' de la alerta (prioridad absoluta)
    if alerta.emails:
        for raw in alerta.emails:
            raw = str(raw).strip() if raw else ''
            if raw and EMAIL_REGEX.match(raw):
                recipients.append(raw)

    if recipients:
        return recipients

    # 2. Email en el campo message de la alerta (compatibilidad legacy)
    if alerta.message:
        raw = alerta.message.strip()
        if EMAIL_REGEX.match(raw):
            recipients.append(raw)

    # Si hay email configurado en la alerta, SOLO se envia ahi. Fin.
    if recipients:
        return recipients

    # 2. Fallback: config por punto (solo si no hay email en la alerta)
    point = alerta.point_catchment
    if point:
        point_emails = ALERT_CONFIG.get("points_emails", {}).get(point.id, [])
        for email in point_emails:
            if email not in recipients:
                recipients.append(email)

    if recipients:
        return recipients

    # 3. Fallback final
    recipients.append(getattr(settings, "DEFAULT_FROM_EMAIL", "soporte@smarthydro.cl"))
    return recipients


def _already_alerted_recently(alerta, cooldown_minutes=ALERT_COOLDOWN_MINUTES):
    """
    Verificar si ya se envio una alerta de umbral para este punto/variable/condicion
    en el periodo de cooldown.

    Busca respuestas recientes vinculadas a la alerta original.
    """
    from api.core.models import ResponseNotificationsCatchment
    chile = pytz.timezone("America/Santiago")
    ahora = datetime.now(chile)
    ventana = ahora - timedelta(minutes=cooldown_minutes)

    return ResponseNotificationsCatchment.objects.filter(
        notification=alerta,
        created__gte=ventana,
    ).exists()


def _send_threshold_email(alerta, interaction, current_value, recipients, dry_run=False):
    """
    Enviar correo de alerta umbral.
    """
    chile = pytz.timezone("America/Santiago")
    ahora = datetime.now(chile)

    point = alerta.point_catchment
    point_name = point.title if point.title else f"Punto {point.id}"
    project_name = point.project.name if point.project else "Sin proyecto"

    subject = f"ALERTA UMBRAL: {alerta.type_variable} {alerta.type_alert} {alerta.value} — {point_name}"

    # Calcular diferencia / exceso
    try:
        diff = float(current_value) - float(alerta.value)
        if alerta.type_alert == "MIN":
            diff = float(alerta.value) - float(current_value)
        excess_str = f"{abs(diff):.2f}"
    except Exception:
        excess_str = "N/A"

    medition_time = ""
    if interaction.date_time_medition:
        dt = interaction.date_time_medition
        if hasattr(dt, 'astimezone'):
            dt = dt.astimezone(chile)
        medition_time = dt.strftime("%Y-%m-%d %H:%M:%S") if hasattr(dt, 'strftime') else str(dt)

    logger_time = ""
    if interaction.date_time_last_logger:
        dt = interaction.date_time_last_logger
        if hasattr(dt, 'astimezone'):
            dt = dt.astimezone(chile)
        logger_time = dt.strftime("%Y-%m-%d %H:%M:%S") if hasattr(dt, 'strftime') else str(dt)

    template_data = {
        "point_name": point_name,
        "project_name": project_name,
        "type_variable": alerta.type_variable,
        "type_alert": alerta.type_alert,
        "threshold": alerta.value,
        "current_value": current_value,
        "excess": excess_str,
        "timestamp": ahora.strftime("%Y-%m-%d %H:%M:%S"),
        "medition_time": medition_time,
        "logger_time": logger_time,
        "days_offline": interaction.days_not_conection,
    }

    try:
        html_body = render_to_string("notifieds/threshold_alert.html", template_data)
    except Exception as e:
        logger.error(f"Error renderizando template para alerta umbral: {e}")
        html_body = None

    if dry_run:
        logger.info(f"[DRY RUN] Email umbral: '{subject}' -> {recipients}")
        return True

    try:
        send_mail(
            subject=subject,
            message="",  # texto plano vacío
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "soporte@smarthydro.cl"),
            recipient_list=recipients,
            html_message=html_body,
            fail_silently=False,
        )
        logger.info(f"Email umbral enviado: {subject} -> {recipients}")
        return True
    except Exception as e:
        logger.error(f"Error enviando email umbral: {e}")
        return False


def evaluate_threshold_alerts(dry_run=False):
    """
    Evaluar todas las alertas umbral (MAX/MIN/EQUALS) configuradas por usuarios.

    Args:
        dry_run: Si True, solo loguea sin crear notificaciones ni enviar emails.

    Returns:
        list: Lista de mensajes descriptivos de las alertas disparadas.
    """
    chile = pytz.timezone("America/Santiago")
    ahora = datetime.now(chile)
    hoy = ahora.date()

    results = []

    # Seleccionar alertas configuradas por usuarios:
    # - is_active=True
    # - type_alert en MAX/MIN/EQUALS
    # - type_variable configurado (no null ni vacío)
    # - dentro del rango de fechas si está definido
    alertas = NotificationsCatchment.objects.filter(
        is_active=True,
        type_alert__in=["MAX", "MIN", "EQUALS"],
        type_notification="ALERT",
    ).exclude(
        type_variable__isnull=True
    ).exclude(
        type_variable=""
    ).select_related("point_catchment", "point_catchment__owner_user")

    logger.info(f"Evaluando {alertas.count()} alertas umbral configuradas...")

    for alerta in alertas:
        try:
            # Validar rango de fechas
            if alerta.start_date and hoy < alerta.start_date:
                continue
            if alerta.end_date and hoy > alerta.end_date:
                continue

            point = alerta.point_catchment
            if not point:
                continue

            # Cooldown: evitar spam
            if _already_alerted_recently(alerta):
                continue

            # Obtener último registro de telemetría del punto
            ultimo = InteractionDetail.objects.filter(
                catchment_point=point
            ).order_by("-date_time_medition").first()

            if not ultimo:
                continue

            # Evaluar según type_variable
            type_variable = alerta.type_variable

            if type_variable == "TODOS":
                valores = _get_numeric_value(ultimo, "TODOS")
                if not valores or not isinstance(valores, dict):
                    continue
                # Para TODOS, disparamos si ALGUNA variable cumple
                disparado = False
                valor_disparo = None
                var_disparo = None
                for var, val in valores.items():
                    if val is not None and _condition_met(alerta.type_alert, val, alerta.value):
                        disparado = True
                        valor_disparo = val
                        var_disparo = var
                        break

                if not disparado:
                    continue

                current_value = valor_disparo
                detail_msg = f"{var_disparo}={valor_disparo}"

            else:
                current_value = _get_numeric_value(ultimo, type_variable)
                if current_value is None:
                    continue

                if not _condition_met(alerta.type_alert, current_value, alerta.value):
                    continue

                detail_msg = f"{type_variable}={current_value}"

            # Se cumplió la condición
            msg = (
                f"Punto {point.id} ({point.title or 'N/A'}): "
                f"UMBRAL {alerta.type_alert} {alerta.value} -> {detail_msg}"
            )
            logger.info(f"ALERTA DISPARADA: {msg}")
            results.append(msg)

            if dry_run:
                continue

            # Determinar usuario para la respuesta (owner del punto o fallback)
            response_user = point.owner_user if point.owner_user else None
            if not response_user:
                from api.core.models import User
                response_user = User.objects.filter(is_superuser=True).first() or User.objects.first()

            # Crear respuesta vinculada a la alerta original (organiza el historial)
            from api.core.models import ResponseNotificationsCatchment
            try:
                diff = float(current_value) - float(alerta.value)
                if alerta.type_alert == "MIN":
                    diff = float(alerta.value) - float(current_value)
                excess_str = f"{abs(diff):.2f}"
            except Exception:
                excess_str = "N/A"

            medition_str = ""
            if ultimo.date_time_medition:
                dt = ultimo.date_time_medition
                if hasattr(dt, 'astimezone'):
                    dt = dt.astimezone(chile)
                medition_str = dt.strftime("%Y-%m-%d %H:%M:%S") if hasattr(dt, 'strftime') else str(dt)

            ResponseNotificationsCatchment.objects.create(
                notification=alerta,
                user=response_user,
                response=(
                    f"ALERTA DISPARADA - Variable: {type_variable} | "
                    f"Condicion: {alerta.type_alert} {alerta.value} | "
                    f"Valor medido: {current_value} | "
                    f"Diferencia: {excess_str} | "
                    f"Fecha medicion: {medition_str}"
                ),
            )

            # Enviar email
            recipients = _get_recipients_for_alert(alerta)
            _send_threshold_email(alerta, ultimo, current_value, recipients, dry_run=False)

        except Exception as e:
            logger.error(f"Error evaluando alerta {alerta.id}: {e}", exc_info=True)
            continue

    if not results:
        logger.info("Ninguna alerta umbral disparada.")

    return results
