#!/usr/bin/env python3
"""
ENVÍO DE DOCUMENTACIÓN TÉCNICA DEL REPORTE DE CÓDIGOS DE OBRA
==============================================================

Genera un documento Word con la documentación técnica del reporte mensual
y lo envía por correo.

USO:
    python scripts/enviar_documentacion_tecnica_reporte.py --recipient andresnunez@smarthydro.cl
"""

import os
import sys
import argparse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django

django.setup()

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from api.core.reports.work_codes_technical_doc import generate_technical_doc


def send_technical_doc(recipient, output_path=None):
    """Genera y envía la documentación técnica por email."""
    if output_path is None:
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"/tmp/documentacion_tecnica_reporte_codigos_obra_{timestamp}.docx"

    generate_technical_doc(output_path)

    now = timezone.now()
    subject = f"📘 Documentación Técnica - Reporte de Códigos de Obra - {now.strftime('%d/%m/%Y')}"

    body = (
        f"Estimado Andrés,\n\n"
        f"Adjunto encontrará la documentación técnica del nuevo reporte mensual de códigos de obra.\n\n"
        f"El documento describe:\n"
        f"- Componentes creados\n"
        f"- Modelos de datos utilizados\n"
        f"- Fórmulas y cálculos\n"
        f"- Casos edge y estados\n"
        f"- Formato del Excel\n"
        f"- Frecuencia de envío planificada\n"
        f"- Responsabilidades de Soporte\n\n"
        f"Quedo atento a sus comentarios.\n\n"
        f"Saludos,\nAgente de Automatización SmartHydro"
    )

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "soporte@smarthydro.cl"),
        to=[recipient],
    )

    filename = os.path.basename(output_path)
    with open(output_path, "rb") as f:
        email.attach(filename, f.read(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    email.send()
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generar y enviar documentación técnica del reporte")
    parser.add_argument("--recipient", type=str, default="andresnunez@smarthydro.cl", help="Email destinatario")
    parser.add_argument("--output", type=str, default=None, help="Ruta opcional para guardar el Word")
    args = parser.parse_args()

    output_path = send_technical_doc(args.recipient, args.output)
    print(f"✅ Documentación técnica enviada a: {args.recipient}")
    print(f"   Archivo: {output_path}")


if __name__ == "__main__":
    main()
