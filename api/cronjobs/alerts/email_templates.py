#!/usr/bin/env python3
"""
Templates de correo para alertas del sistema
"""

import os

from django.conf import settings
from django.template.loader import render_to_string


def get_email_template(alert_type, data):
    """Obtener template de correo según el tipo de alerta"""

    # Mapeo de tipos de alerta a templates HTML
    template_mapping = {
        "DGA_QUEUE": "notifieds/warning.html",
        "DGA_RECOVERY": "notifieds/notification.html",
        "DISCONNECTION": "notifieds/error.html",
        "RECONNECTION": "notifieds/notification.html",
    }

    # Obtener el template correspondiente
    template_name = template_mapping.get(alert_type, "notifieds/notification.html")

    try:
        # Renderizar el template HTML con los datos
        html_content = render_to_string(template_name, data)
        return html_content
    except Exception as e:
        print(f"Error renderizando template {template_name}: {e}")
        # Fallback: template genérico
        return get_generic_fallback_template(data)


def get_generic_fallback_template(data):
    """Template de fallback en caso de error"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Alerta del Sistema</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .alert {{ background-color: #f8d7da; border: 1px solid #dc3545; padding: 15px; border-radius: 5px; }}
            .info {{ background-color: #d1ecf1; border: 1px solid #17a2b8; padding: 15px; border-radius: 5px; margin-top: 15px; }}
        </style>
    </head>
    <body>
        <div class="alert">
            <h2>Alerta del Sistema</h2>
            <p>Se ha detectado una alerta en el sistema.</p>
        </div>
        <div class="info">
            <p><strong>Punto:</strong> {data.get('point_id', 'N/A')}</p>
            <p><strong>Hora:</strong> {data.get('timestamp', 'N/A')}</p>
            <p><strong>Tipo:</strong> {data.get('alert_type', 'General')}</p>
        </div>
        <p>© 2025 SmartHydro - Sistema de Monitoreo Hidrológico</p>
    </body>
    </html>
    """
