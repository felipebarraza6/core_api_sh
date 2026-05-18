#!/usr/bin/env python3
"""
Cronjob de alertas para monitoreo de puntos de captación.
Solo evalúa alertas umbral (MAX/MIN/EQUALS) configuradas por usuarios.
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

from .alert_evaluator import evaluate_threshold_alerts


def run():
    """Ejecutar cronjob de alertas umbral configuradas por usuarios."""
    print("Iniciando cronjob de alertas...")

    try:
        threshold_alerts = evaluate_threshold_alerts(dry_run=False)
        if threshold_alerts:
            print(f"Alertas Umbral: {len(threshold_alerts)}")
            for alert in threshold_alerts:
                print(f"   - {alert}")
        else:
            print("Ninguna alerta umbral disparada.")
    except Exception as e:
        print(f"Error en evaluación de alertas umbral: {e}")

    print("Cronjob de alertas completado")


if __name__ == "__main__":
    run()
