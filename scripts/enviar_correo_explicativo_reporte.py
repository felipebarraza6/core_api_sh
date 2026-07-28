#!/usr/bin/env python3
"""
ENVÍO DE CORREO EXPLICATIVO DEL REPORTE DE CÓDIGOS DE OBRA
==========================================================

Envía el correo introductorio/explicativo del reporte mensual de códigos de obra.

USO:
    # Modo preview: enviar solo a Felipe para validación
    python scripts/enviar_correo_explicativo_reporte.py --mode preview --year 2026

    # Modo final: enviar a destinatarios oficiales con CC a Felipe
    python scripts/enviar_correo_explicativo_reporte.py --mode final --year 2026
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
from api.core.reports.work_codes_technical_doc import generate_technical_doc


# Destinatarios oficiales
FINAL_RECIPIENTS = [
    "raymundoanavalon@smarthydro.cl",
    "andresnunez@smarthydro.cl",
]
FINAL_CC = [
    "felipebarraza@smarthydro.cl",
    "carlosyevenes@smarthydro.cl",
]
PREVIEW_RECIPIENTS = [
    "felipebarraza@smarthydro.cl",
]
PREVIEW_CC = []


def build_email_body(year, row_count, superados, proximos, sin_total, sin_caudal, mode="preview"):
    """Construye el cuerpo del correo explicativo."""

    destinatarios_line = ""
    if mode == "preview":
        destinatarios_line = (
            "<p><b>Nota:</b> Este es un correo de validación enviado solo a Felipe. "
            "Una vez aprobado, se enviará a los destinatarios oficiales.</p>"
        )

    return f"""
<p>Estimados Raymundo y equipo de Soporte,</p>

<p>Les escribimos para compartir el nuevo <b>reporte mensual de códigos de obra</b>, diseñado como herramienta de prevención de incumplimiento ante la DGA/SMA.</p>

<p>Este correo y el reporte adjunto son generados automáticamente por el agente de automatización que opera en el servidor de SmartHydro, con el objetivo de entregar una visión clara del estado de consumo y caudal de cada código de obra.</p>

<h3>📊 ¿Qué incluye el reporte?</h3>

<p>Por cada código de obra se entrega:</p>
<ul>
  <li>Cliente, Proyecto y Punto</li>
  <li>Código de obra registrado en la configuración DGA</li>
  <li>Estándar (MAYOR, MEDIO, MENOR, CMP, SIN_ESTÁNDAR)</li>
  <li>Caudal autorizado (lt/s)</li>
  <li>Veces que se superó el caudal en el año</li>
  <li>Caudal promedio del año</li>
  <li>Total autorizado anual (m³)</li>
  <li>Consumo acumulado del año consultado</li>
  <li>% gastado, % disponible y m³ disponibles</li>
  <li>Estado de alerta (OK, PRÓXIMO, SUPERADO, SIN_TOTAL, SIN_CAUDAL)</li>
</ul>

<h3>⚠️ Casos edge y comportamiento esperado</h3>

<ol>
  <li><b>Sin caudal autorizado configurado</b><br>
  Si el campo <i>Caudal autorizado</i> está en 0 o vacío, el sistema no puede determinar si se superó el caudal. Se marca como <b>SIN_CAUDAL</b> y no se contabilizan excesos.
  </li><br>

  <li><b>Sin total autorizado configurado</b><br>
  Si no existe un <i>Total autorizado anual</i>, no se pueden calcular porcentajes de consumo. Se marca como <b>SIN_TOTAL</b>.
  </li><br>

  <li><b>Consumo acumulado mayor al total autorizado</b><br>
  Algunos puntos pueden mostrar <b>% gastado &gt; 100%</b> o valores negativos en <i>m³ disponibles</i>. Esto suele indicar uno de dos problemas:
  <ul>
    <li>El <b>total autorizado</b> está desactualizado o mal configurado.</li>
    <li>Existe un problema en la telemetría (reset de sensor, saltos en el totalizador, duplicados) que infla el consumo acumulado.</li>
  </ul>
  </li><br>

  <li><b>Caudal autorizado = 0</b><br>
  Cualquier medición con caudal mayor a 0 marcaría exceso, por lo que el sistema omite el conteo para evitar falsos positivos.
  </li><br>

  <li><b>Puntos sin telemetría reciente</b><br>
  Si el punto no tiene mediciones en el año consultado, el consumo y caudal promedio serán 0.
  </li>
</ol>

<h3>📋 Resumen del reporte adjunto ({year})</h3>

<ul>
  <li>Total de códigos de obra: <b>{row_count}</b></li>
  <li>Puntos SUPERADOS en total autorizado: <b>{superados}</b></li>
  <li>Puntos PRÓXIMOS a superar total autorizado (≥80%): <b>{proximos}</b></li>
  <li>Puntos SIN_TOTAL configurado: <b>{sin_total}</b></li>
  <li>Puntos SIN_CAUDAL configurado: <b>{sin_caudal}</b></li>
</ul>

<h3>✅ Acción requerida por Soporte</h3>

<p>Para que este reporte sea útil y evitemos alertas de incumplimiento, es <b>responsabilidad del área de Soporte</b> mantener actualizados en cada punto:</p>
<ul>
  <li><b>Caudal autorizado</b> (<code>flow_granted_dga</code>)</li>
  <li><b>Total autorizado anual</b> (<code>total_granted_dga</code>)</li>
</ul>

<p>Recomendamos revisar periódicamente los puntos marcados como <b>SUPERADO</b>, <b>PRÓXIMO</b>, <b>SIN_TOTAL</b> o <b>SIN_CAUDAL</b>.</p>

<h3>📅 Frecuencia de envío</h3>

<p>Este reporte se enviará de forma automática el <b>día 1 de cada mes a las 02:00 AM</b>, comenzando el próximo mes.</p>

{destinatarios_line}

<p>Quedamos atentos a sus comentarios o ajustes.</p>

<p>Saludos cordiales,<br>
Agente de Automatización SmartHydro</p>
"""


def send_explanatory_email(year, mode="preview", output_path=None, doc_path=None):
    """
    Envía el correo explicativo del reporte.

    Args:
        year: Año del reporte adjunto.
        mode: 'preview' envía solo a Felipe, 'final' envía a destinatarios oficiales.
        output_path: Ruta opcional del Excel a adjuntar. Si es None, se genera.
        doc_path: Ruta opcional del Word técnico a adjuntar. Si es None, se genera.

    Returns:
        tuple: (output_path, doc_path, recipients, cc)
    """
    rows = build_work_codes_report(year)

    if output_path is None:
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"/tmp/reporte_codigos_obra_{year}_{timestamp}.xlsx"

    if doc_path is None:
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        doc_path = f"/tmp/documentacion_tecnica_reporte_codigos_obra_{timestamp}.docx"

    generate_work_codes_excel(rows, year, output_path=output_path)
    generate_technical_doc(doc_path)

    if mode == "preview":
        recipients = PREVIEW_RECIPIENTS
        cc = PREVIEW_CC
    else:
        recipients = FINAL_RECIPIENTS
        cc = FINAL_CC

    superados = sum(1 for r in rows if r["estado_total"] == "SUPERADO")
    proximos = sum(1 for r in rows if r["estado_total"] == "PROXIMO")
    sin_total = sum(1 for r in rows if r["estado_total"] == "SIN_TOTAL")
    sin_caudal = sum(1 for r in rows if r["estado_caudal"] == "SIN_CAUDAL")

    now = timezone.now()
    subject = f"📊 Reporte Mensual de Códigos de Obra - Año {year} - Información y Validación de Datos"

    body = build_email_body(year, len(rows), superados, proximos, sin_total, sin_caudal, mode=mode)

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "soporte@smarthydro.cl"),
        to=recipients,
        cc=cc,
    )
    email.content_subtype = "html"

    excel_filename = os.path.basename(output_path)
    with open(output_path, "rb") as f:
        email.attach(excel_filename, f.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    doc_filename = os.path.basename(doc_path)
    with open(doc_path, "rb") as f:
        email.attach(doc_filename, f.read(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    email.send()

    return output_path, doc_path, recipients, cc


def main():
    parser = argparse.ArgumentParser(description="Enviar correo explicativo del reporte de códigos de obra")
    parser.add_argument("--year", type=int, default=2026, help="Año del reporte adjunto")
    parser.add_argument("--mode", choices=["preview", "final"], default="preview", help="Modo de envío")
    parser.add_argument("--output", type=str, default=None, help="Ruta opcional del Excel a adjuntar")
    parser.add_argument("--doc", type=str, default=None, help="Ruta opcional del Word técnico a adjuntar")
    args = parser.parse_args()

    output_path, doc_path, recipients, cc = send_explanatory_email(
        args.year, mode=args.mode, output_path=args.output, doc_path=args.doc
    )

    print(f"✅ Correo explicativo enviado")
    print(f"   Modo: {args.mode}")
    print(f"   Para: {', '.join(recipients)}")
    if cc:
        print(f"   CC: {', '.join(cc)}")
    print(f"   Adjunto Excel: {output_path}")
    print(f"   Adjunto Word:  {doc_path}")


if __name__ == "__main__":
    main()
