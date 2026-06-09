#!/usr/bin/env python3
"""
Configuración de alertas legacy.

⚠️  Este archivo solo es usado por alert_evaluator.py (subsistema legacy
    cuyo cron está APAGADO). El motor nuevo de alertas (AlertRule / AlertTrigger)
    no lee esta configuración.

Todos los valores se leen desde variables de entorno. No agregar credenciales
en texto plano en este archivo.
"""

import json
import os


# Emails por punto: espera JSON en env, ej: '{"1": ["a@b.com"]}'
_points_emails_raw = os.environ.get("ALERT_POINTS_EMAILS", "{}").strip()
try:
    _points_emails = json.loads(_points_emails_raw)
    if not isinstance(_points_emails, dict):
        _points_emails = {}
except Exception:
    _points_emails = {}

ALERT_CONFIG = {
    # Configuración por punto: ID -> [correos]
    "points_emails": _points_emails,
    # Umbrales
    "dga_queue_threshold": int(os.environ.get("ALERT_DGA_QUEUE_THRESHOLD", "5")),
    "disconnection_threshold": int(os.environ.get("ALERT_DISCONNECTION_THRESHOLD", "1")),
    # Configuración SMTP legacy (no usada por el motor nuevo)
    "smtp_server": os.environ.get("ALERT_SMTP_SERVER", ""),
    "smtp_port": int(os.environ.get("ALERT_SMTP_PORT", "465")),
    "smtp_user": os.environ.get("ALERT_SMTP_USER", ""),
    "smtp_password": os.environ.get("ALERT_SMTP_PASSWORD", ""),
}

# MAPEO DE TIPOS DE ALERTA DEL SISTEMA A VALORES DEL MODELO
ALERT_TYPE_MAPPING = {
    "DGA_QUEUE": "MAX",
    "DISCONNECTION": "MIN",
    "RECONNECTION": "EQUALS",
}
