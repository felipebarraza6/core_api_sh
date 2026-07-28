#!/usr/bin/env python3
"""
ENVÍO DE REPORTE DE CÓDIGOS DE OBRA POR EMAIL
==============================================

Genera un Excel con el reporte de códigos de obra y lo envía por correo.

USO:
    python scripts/enviar_reporte_codigos_obra.py --year 2026 --recipient felipebarraza@smarthydro.cl
    python scripts/enviar_reporte_codigos_obra.py --year 2025 --recipient felipebarraza@smarthydro.cl --output /tmp/reporte_2025.xlsx
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

from api.core.reports.work_codes_calculator import build_work_codes_report
from api.core.reports.work_codes_excel import generate_work_codes_excel


def generate_work_codes_excel_file(year, output_path=None):
    """Genera solo el archivo Excel y retorna (path, rows)."""
    rows = build_work_codes_report(year)

    if output_path is None:
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"/tmp/reporte_codigos_obra_{year}_{timestamp}.xlsx"

    generate_work_codes_excel(rows, year, output_path=output_path)
    return output_path, rows


def send_work_codes_report(year, recipient, rows, output_path):
    """
    Envía por email un Excel ya generado.

    Args:
        year: Año del reporte.
        recipient: Email del destinatario.
        rows: Filas del reporte.
        output_path: Ruta del Excel a adjuntar.

    Returns:
        int: Número de filas enviadas.
    """
    now = timezone.now()
    subject = f"📊 Reporte Códigos de Obra - Año {year} - {now.strftime('%d/%m/%Y %H:%M')}"

    body = (
        f"Estimado(a),\n\n"
        f"Adjunto encontrará el reporte de códigos de obra correspondiente al año {year}.\n\n"
        f"Resumen:\n"
        f"- Total de códigos de obra: {len(rows)}\n"
        f"- Con caudal autorizado configurado: {sum(1 for r in rows if r['tiene_caudal_configurado'])}\n"
        f"- Con total autorizado configurado: {sum(1 for r in rows if r['tiene_total_configurado'])}\n"
        f"- Con al menos un exceso de caudal: {sum(1 for r in rows if r['veces_supero_caudal'] > 0)}\n"
        f"- Con consumo superado (>=100%): {sum(1 for r in rows if r['estado_total'] == 'SUPERADO')}\n"
        f"- Próximos a superar total (>=80%): {sum(1 for r in rows if r['estado_total'] == 'PROXIMO')}\n\n"
        f"Saludos,\nSistema SmartHydro"
    )

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "soporte@smarthydro.cl"),
        to=[recipient],
    )

    filename = os.path.basename(output_path)
    with open(output_path, "rb") as f:
        email.attach(filename, f.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    email.send()
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Generar y enviar reporte de códigos de obra")
    parser.add_argument("--year", type=int, required=True, help="Año a consultar (ej: 2026)")
    parser.add_argument("--recipient", type=str, default="felipebarraza@smarthydro.cl", help="Email destinatario")
    parser.add_argument("--output", type=str, default=None, help="Ruta opcional para guardar el Excel")
    parser.add_argument("--no-send", action="store_true", help="Generar el Excel pero no enviar email")
    args = parser.parse_args()

    output_path, rows = generate_work_codes_excel_file(args.year, args.output)
    print(f"✅ Excel generado: {output_path} ({len(rows)} filas)")

    if args.no_send:
        print("📧 Envío omitido por --no-send")
        return

    send_work_codes_report(args.year, args.recipient, rows, output_path)
    print(f"📧 Reporte enviado a: {args.recipient}")


if __name__ == "__main__":
    main()
