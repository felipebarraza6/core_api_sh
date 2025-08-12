#!/usr/bin/env python3
"""
Cronjob de alertas para monitoreo de puntos de captación
"""

import os
import sys

import django

# Configurar Django
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
django.setup()

import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytz
from django.conf import settings
from django.core.mail import send_mail

from api.core.models import InteractionDetail, NotificationsCatchment

from .config_alerts import ALERT_CONFIG, ALERT_TYPE_MAPPING
from .email_templates import get_email_template


def send_email(subject, alert_type, data, recipients):
    """Enviar correo de alerta usando templates HTML"""
    try:
        # Obtener template HTML
        html_body = get_email_template(alert_type, data)

        # Usar Django send_mail con configuración de settings.py
        send_mail(
            subject=f"🚨 ALERTA SISTEMA: {subject}",
            message="",  # Mensaje plano vacío
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            html_message=html_body,
            fail_silently=False,
        )

        print(f"✅ Correo enviado: {subject}")
        return True

    except Exception as e:
        print(f"❌ Error enviando correo: {e}")
        return False


def check_dga_queue_alert():
    """Verificar si hay muchos registros en cola DGA"""
    alerts = []

    # Obtener puntos a monitorear desde la configuración
    monitored_points = list(ALERT_CONFIG["points_emails"].keys())

    for point_id in monitored_points:
        try:
            # Obtener correos específicos para este punto
            point_emails = ALERT_CONFIG["points_emails"][point_id]

            # Contar registros en cola DGA de las últimas 2 horas
            chile = pytz.timezone("America/Santiago")
            ahora = datetime.now(chile)
            hace_2_horas = ahora - timedelta(hours=2)

            registros_en_cola = InteractionDetail.objects.filter(
                catchment_point_id=point_id, send_dga=True, created__gte=hace_2_horas
            ).count()

            if registros_en_cola >= ALERT_CONFIG["dga_queue_threshold"]:
                # Verificar si ya se envió alerta recientemente
                ultima_alerta = NotificationsCatchment.objects.filter(
                    point_catchment_id=point_id,
                    type_alert=ALERT_TYPE_MAPPING["DGA_QUEUE"],  # Usar mapeo
                    created__gte=hace_2_horas,
                ).first()

                if not ultima_alerta:
                    # Crear alerta
                    alerta = NotificationsCatchment.objects.create(
                        point_catchment_id=point_id,
                        type_alert=ALERT_TYPE_MAPPING["DGA_QUEUE"],  # Usar mapeo
                        message=f"Punto {point_id}: {registros_en_cola} registros en cola DGA",
                        is_active=True,
                    )

                    # Enviar correo a los correos específicos del punto
                    subject = f"Cola DGA Llena - Punto {point_id}"

                    # Preparar datos para el template
                    template_data = {
                        "point_id": point_id,
                        "queue_count": registros_en_cola,
                        "threshold": ALERT_CONFIG["dga_queue_threshold"],
                        "timestamp": ahora.strftime("%Y-%m-%d %H:%M:%S"),
                        "alert_type": "Cola DGA",
                        "notification_type": "DGA_QUEUE",
                        "status": "Crítico",
                        "explanation": f"El sistema DGA no está enviando datos correctamente. Los registros se están acumulando en la cola de envío. Actualmente hay {registros_en_cola} registros pendientes.",
                        "actions": "1. Verificar la conectividad de red<br />2. Revisar las credenciales del servicio DGA<br />3. Comprobar el estado del servidor DGA<br />4. Revisar los logs del sistema",
                    }

                    if send_email(subject, "DGA_QUEUE", template_data, point_emails):
                        alerta.is_sent = True
                        alerta.save()

                    alerts.append(f"Punto {point_id}: {registros_en_cola} en cola DGA")

            # Verificar si se recuperó (menos de 2 registros en cola)
            elif registros_en_cola <= 2:
                # Verificar si había alerta activa
                alerta_activa = NotificationsCatchment.objects.filter(
                    point_catchment_id=point_id,
                    type_alert=ALERT_TYPE_MAPPING["DGA_QUEUE"],
                    is_active=True,
                ).first()

                if alerta_activa:
                    # Marcar como resuelta
                    alerta_activa.is_active = False
                    alerta_activa.save()

                    # Enviar notificación de recuperación
                    subject = f"Recuperación DGA - Punto {point_id}"

                    # Preparar datos para el template
                    template_data = {
                        "point_id": point_id,
                        "queue_count": registros_en_cola,
                        "timestamp": ahora.strftime("%Y-%m-%d %H:%M:%S"),
                        "alert_type": "Recuperación DGA",
                        "notification_type": "DGA_RECOVERY",
                        "status": "Normalizado",
                        "explanation": f"El sistema DGA ha vuelto a funcionar correctamente. Los registros que estaban en cola se están procesando y enviando normalmente al servicio DGA.",
                        "actions": "• Comunicación DGA: ✅ Funcionando<br />• Envío de datos: ✅ Activo<br />• Cola de registros: ✅ Normalizada<br />• Monitoreo: ✅ Continuo",
                    }

                    send_email(subject, "DGA_RECOVERY", template_data, point_emails)

        except Exception as e:
            print(f"❌ Error verificando punto {point_id}: {e}")

    return alerts


def check_disconnection_alert():
    """Verificar desconexiones de puntos"""
    alerts = []

    # Obtener puntos a monitorear desde la configuración
    monitored_points = list(ALERT_CONFIG["points_emails"].keys())

    for point_id in monitored_points:
        try:
            # Obtener correos específicos para este punto
            point_emails = ALERT_CONFIG["points_emails"][point_id]

            # Obtener el último registro
            ultimo_registro = (
                InteractionDetail.objects.filter(catchment_point_id=point_id)
                .order_by("-created")
                .first()
            )

            if ultimo_registro and ultimo_registro.days_not_conection:
                days_disconnected = ultimo_registro.days_not_conection

                if days_disconnected > ALERT_CONFIG["disconnection_threshold"]:
                    # Verificar si ya se envió alerta recientemente
                    chile = pytz.timezone("America/Santiago")
                    ahora = datetime.now(chile)
                    hace_1_hora = ahora - timedelta(hours=1)

                    ultima_alerta = NotificationsCatchment.objects.filter(
                        point_catchment_id=point_id,
                        type_alert=ALERT_TYPE_MAPPING["DISCONNECTION"],  # Usar mapeo
                        created__gte=hace_1_hora,
                    ).first()

                    if not ultima_alerta:
                        # Crear alerta
                        alerta = NotificationsCatchment.objects.create(
                            point_catchment_id=point_id,
                            type_alert=ALERT_TYPE_MAPPING[
                                "DISCONNECTION"
                            ],  # Usar mapeo
                            message=f"Punto {point_id}: {days_disconnected} días desconectado",
                            is_active=True,
                        )

                        # Enviar correo a los correos específicos del punto
                        subject = f"Punto Desconectado - Punto {point_id}"

                        # Preparar datos para el template
                        template_data = {
                            "point_id": point_id,
                            "days_disconnected": days_disconnected,
                            "last_measurement": ultimo_registro.date_time_medition,
                            "timestamp": ahora.strftime("%Y-%m-%d %H:%M:%S"),
                            "alert_type": "Desconexión",
                            "notification_type": "DISCONNECTION",
                            "status": "Crítico",
                            "explanation": f"El punto de captación {point_id} ha estado desconectado por {days_disconnected} días. Esto puede indicar un problema de conectividad o falla en el equipo.",
                            "actions": "1. Verificar la conectividad del punto<br />2. Revisar el estado del equipo<br />3. Comprobar la alimentación eléctrica<br />4. Contactar al técnico de campo",
                        }

                        if send_email(
                            subject, "DISCONNECTION", template_data, point_emails
                        ):
                            alerta.is_sent = True
                            alerta.save()

                        alerts.append(
                            f"Punto {point_id}: {days_disconnected} días desconectado"
                        )

                elif days_disconnected == 0:
                    # Verificar si había alerta activa
                    alerta_activa = NotificationsCatchment.objects.filter(
                        point_catchment_id=point_id,
                        type_alert=ALERT_TYPE_MAPPING["DISCONNECTION"],  # Usar mapeo
                        is_active=True,
                    ).first()

                    if alerta_activa:
                        # Marcar como resuelta
                        alerta_activa.is_active = False
                        alerta_activa.save()

                        # Enviar notificación de recuperación
                        subject = f"Punto Reconectado - Punto {point_id}"

                        # Preparar datos para el template
                        template_data = {
                            "point_id": point_id,
                            "last_measurement": ultimo_registro.date_time_medition,
                            "timestamp": ahora.strftime("%Y-%m-%d %H:%M:%S"),
                            "alert_type": "Reconexión",
                            "notification_type": "RECONNECTION",
                            "status": "Normalizado",
                            "explanation": f"El punto de captación {point_id} se ha reconectado exitosamente. El sistema está funcionando normalmente y enviando datos correctamente.",
                            "actions": "• Conectividad: ✅ Restaurada<br />• Envío de datos: ✅ Activo<br />• Última medición: {ultimo_registro.date_time_medition}<br />• Monitoreo: ✅ Continuo",
                        }

                        send_email(subject, "RECONNECTION", template_data, point_emails)

        except Exception as e:
            print(f"❌ Error verificando desconexión punto {point_id}: {e}")

    return alerts


def run():
    """Ejecutar cronjob de alertas"""
    print("🚨 Iniciando cronjob de alertas...")

    # Verificar alertas de cola DGA
    dga_alerts = check_dga_queue_alert()
    if dga_alerts:
        print(f"📊 Alertas DGA: {len(dga_alerts)}")
        for alert in dga_alerts:
            print(f"   - {alert}")

    # Verificar alertas de desconexión
    disconnection_alerts = check_disconnection_alert()
    if disconnection_alerts:
        print(f"📊 Alertas Desconexión: {len(disconnection_alerts)}")
        for alert in disconnection_alerts:
            print(f"   - {alert}")

    if not dga_alerts and not disconnection_alerts:
        print("✅ No hay alertas activas")

    print("🏁 Cronjob de alertas completado")


if __name__ == "__main__":
    run()
