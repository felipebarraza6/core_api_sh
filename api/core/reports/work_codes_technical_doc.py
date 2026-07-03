"""
Generador de documentación técnica en Word para el reporte de códigos de obra.
"""

from django.utils import timezone
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH


def add_heading(doc, text, level=1):
    """Agrega un título al documento."""
    heading = doc.add_heading(level=level)
    run = heading.add_run(text)
    run.font.color.rgb = RGBColor(31, 78, 120)
    return heading


def add_paragraph(doc, text, bold=False):
    """Agrega un párrafo al documento."""
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    return p


def add_code_block(doc, code):
    """Agrega un bloque de código monoespaciado."""
    p = doc.add_paragraph()
    run = p.add_run(code)
    run.font.name = "Courier New"
    run.font.size = Pt(9)
    p.paragraph_format.left_indent = Inches(0.25)
    p.paragraph_format.space_after = Pt(6)
    return p


def generate_technical_doc(output_path):
    """Genera el documento Word con la documentación técnica."""
    doc = Document()

    # Título
    title = doc.add_heading("Documentación Técnica - Reporte de Códigos de Obra", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title.runs[0]
    title_run.font.size = Pt(18)
    title_run.font.color.rgb = RGBColor(31, 78, 120)

    doc.add_paragraph(f"Generado: {timezone.now().strftime('%d/%m/%Y %H:%M')}")
    doc.add_paragraph("Sistema: SmartHydro")
    doc.add_paragraph("")

    # 1. Resumen
    add_heading(doc, "1. Resumen", level=1)
    add_paragraph(doc,
        "El presente documento describe la implementación técnica del reporte mensual de códigos de obra, "
        "una herramienta automatizada de prevención de incumplimiento ante la DGA/SMA. "
        "El reporte consolida, por cada código de obra configurado en la plataforma, información de caudal autorizado, "
        "consumo acumulado, excesos de caudal y disponibilidad de volumen anual."
    )

    # 2. Componentes creados
    add_heading(doc, "2. Componentes del Sistema", level=1)
    add_paragraph(doc, "Se crearon los siguientes archivos:", bold=True)
    components = [
        ("api/core/reports/work_codes_calculator.py", "Helper central con la lógica de cálculo del reporte."),
        ("api/core/reports/work_codes_excel.py", "Generador de archivos Excel (.xlsx) con formato y colores."),
        ("api/core/reports/work_codes_technical_doc.py", "Generador de documentación técnica en Word."),
        ("scripts/reporte_codigos_obra.py", "Script de consola para validación manual."),
        ("scripts/enviar_reporte_codigos_obra.py", "Script para generar y enviar el reporte por email."),
        ("scripts/enviar_correo_explicativo_reporte.py", "Script para enviar el correo introductorio/explicativo."),
        ("scripts/enviar_documentacion_tecnica_reporte.py", "Script para generar y enviar esta documentación."),
    ]
    for name, desc in components:
        p = doc.add_paragraph(style="List Bullet")
        p.add_run(f"{name}: ").bold = True
        p.add_run(desc)

    # 3. Modelos de datos
    add_heading(doc, "3. Modelos de Datos Utilizados", level=1)
    add_paragraph(doc, "El reporte utiliza principalmente dos modelos:", bold=True)

    add_heading(doc, "3.1 DgaDataConfigCatchment", level=2)
    add_paragraph(doc, "Almacena la configuración DGA de cada punto de captación. Campos relevantes:")
    fields_dga = [
        "point_catchment → ForeignKey a CatchmentPoint",
        "code_dga → Código de obra (ej: OB-1603-26)",
        "standard → Estándar DGA (MAYOR, MEDIO, MENOR, CAUDALES_MUY_PEQUENOS, SIN_ESTANDAR)",
        "flow_granted_dga → Caudal autorizado en litros por segundo (lt/s)",
        "total_granted_dga → Total autorizado anual en metros cúbicos (m³)",
        "send_dga → Flag de activación de cumplimiento",
    ]
    for f in fields_dga:
        doc.add_paragraph(f, style="List Bullet")

    add_heading(doc, "3.2 InteractionDetail", level=2)
    add_paragraph(doc, "Almacena cada registro de telemetría recibido. Campos relevantes:")
    fields_interaction = [
        "catchment_point → Punto de captación",
        "flow → Caudal instantáneo (lt/s)",
        "total_diff → Diferencia de consumo en la medición (m³/h aprox.)",
        "date_time_medition → Fecha/hora de la medición",
    ]
    for f in fields_interaction:
        doc.add_paragraph(f, style="List Bullet")

    add_heading(doc, "3.3 Jerarquía Cliente → Proyecto → Punto", level=2)
    add_paragraph(doc,
        "Para obtener cliente y proyecto se navega desde DgaDataConfigCatchment "
        "hacia CatchmentPoint → ProjectCatchments → Client."
    )

    # 4. Cálculos
    add_heading(doc, "4. Cálculos y Fórmulas", level=1)

    add_heading(doc, "4.1 Filtro base", level=2)
    add_paragraph(doc, "Se consideran solo configuraciones DGA con code_dga no nulo y no vacío.")
    add_code_block(doc,
        "DgaDataConfigCatchment.objects\n"
        "    .filter(code_dga__isnull=False)\n"
        "    .exclude(code_dga='')"
    )

    add_heading(doc, "4.2 Consumo acumulado del año", level=2)
    add_paragraph(doc, "Se calcula como la suma de total_diff de todas las mediciones del año.")
    add_code_block(doc,
        "InteractionDetail.objects.filter(\n"
        "    catchment_point=point,\n"
        "    date_time_medition__year=year\n"
        ").aggregate(consumo=Sum('total_diff'))"
    )

    add_heading(doc, "4.3 Veces que se superó el caudal", level=2)
    add_paragraph(doc,
        "Contador de mediciones del año donde flow > flow_granted_dga. "
        "Si el caudal autorizado es 0 o no está configurado, el conteo se omite para evitar falsos positivos."
    )
    add_code_block(doc,
        ".aggregate(\n"
        "    veces_supero=Count('id', filter=Q(flow__gt=flow_granted_dga))\n"
        ")"
    )

    add_heading(doc, "4.4 Caudal promedio", level=2)
    add_paragraph(doc, "Promedio aritmético del campo flow de todas las mediciones del año.")
    add_code_block(doc,
        ".aggregate(caudal_promedio=Avg('flow'))"
    )

    add_heading(doc, "4.5 Porcentajes de consumo", level=2)
    add_paragraph(doc, "Solo se calculan si existe total_granted_dga configurado.")
    add_code_block(doc,
        "% gastado = (consumo_acumulado / total_autorizado) * 100\n"
        "% disponible = 100 - % gastado\n"
        "m3_disponibles = total_autorizado - consumo_acumulado"
    )

    # 5. Casos edge
    add_heading(doc, "5. Casos Edge y Estados", level=1)
    cases = [
        ("OK", "El punto tiene caudal y total configurados, y no supera umbrales críticos."),
        ("SUPERADO", "El consumo acumulado superó el total autorizado (≥100%) o se detectaron excesos de caudal."),
        ("PROXIMO", "El consumo acumulado alcanzó al menos el 80% del total autorizado."),
        ("SIN_TOTAL", "No se ha configurado total_granted_dga. No se pueden calcular porcentajes."),
        ("SIN_CAUDAL", "No se ha configurado flow_granted_dga o es 0. No se contabilizan excesos de caudal."),
    ]
    for state, desc in cases:
        p = doc.add_paragraph(style="List Bullet")
        p.add_run(f"{state}: ").bold = True
        p.add_run(desc)

    # 6. Formato del Excel
    add_heading(doc, "6. Formato del Excel Generado", level=1)
    add_paragraph(doc,
        "El archivo Excel incluye encabezados con fondo azul, filtros automáticos, "
        "primera fila congelada y formato condicional por fila:"
    )
    formats = [
        "Rojo: filas con estado SUPERADO (total o caudal).",
        "Amarillo: filas con estado PRÓXIMO.",
        "Gris: filas SIN_TOTAL o SIN_CAUDAL.",
    ]
    for f in formats:
        doc.add_paragraph(f, style="List Bullet")

    # 7. Envío y frecuencia
    add_heading(doc, "7. Envío y Frecuencia", level=1)
    add_paragraph(doc,
        "Actualmente el reporte se genera y envía de forma manual mediante scripts. "
        "La siguiente fase contempla registrar un cronjob en api/settings.py para envío automático "
        "el día 1 de cada mes a las 02:00 AM."
    )
    add_code_block(doc,
        "(# Ejemplo de cronjob mensual)\n"
        "('0 2 1 * *', 'api.cronjobs.reports.work_codes_monthly.run', ...)"
    )

    # 8. Responsabilidades de Soporte
    add_heading(doc, "8. Responsabilidades del Área de Soporte", level=1)
    add_paragraph(doc,
        "Para que el reporte sea útil y se pueda prevenir el incumplimiento, "
        "el área de Soporte debe mantener actualizados los siguientes campos en cada punto DGA:"
    )
    resp = [
        "Caudal autorizado (flow_granted_dga)",
        "Total autorizado anual (total_granted_dga)",
        "Verificar que el código de obra (code_dga) sea correcto",
        "Revisar periódicamente puntos marcados como SUPERADO, PRÓXIMO, SIN_TOTAL o SIN_CAUDAL",
    ]
    for r in resp:
        doc.add_paragraph(r, style="List Number")

    # 9. Notas técnicas
    add_heading(doc, "9. Notas Técnicas", level=1)
    notes = [
        "El reporte es de solo lectura: no modifica modelos, telemetría ni configuraciones.",
        "Las agregaciones utilizan índices existentes en InteractionDetail (catchment_point, date_time_medition).",
        "El conteo de excesos de caudal se basa en el campo flow almacenado. Para estándar MEDIO, donde el caudal real se calcula como promedio 24h, el contador es una aproximación.",
        "Los puntos con dga_aggregate_points no se consolidan en esta versión; cada configuración DGA se reporta de forma independiente.",
    ]
    for n in notes:
        doc.add_paragraph(n, style="List Bullet")

    doc.save(output_path)
    return output_path
