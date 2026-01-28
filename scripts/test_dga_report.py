#!/usr/bin/env python
"""Script temporal para probar el reporte DGA mejorado"""

from datetime import datetime, timedelta
from django.utils import timezone
from api.core.models import DgaDataConfigCatchment, InteractionDetail
from api.core.utils.google_chat import send_dga_chat_message
import pytz

chile_tz = pytz.timezone("America/Santiago")
now = timezone.now()
now_chile = now.astimezone(chile_tz)

# Buscar las últimas 24 horas para el reporte de prueba
window_start = now - timedelta(hours=24)
window_end = now

# Obtener TODOS los puntos que envían a DGA
dga_configs = list(DgaDataConfigCatchment.objects.filter(
    send_dga=True
).select_related(
    'point_catchment',
    'point_catchment__project',
    'point_catchment__project__client'
))

if not dga_configs:
    print("❌ No hay puntos configurados para DGA")
    exit()

point_ids = [c.point_catchment_id for c in dga_configs]
code_map = {c.point_catchment_id: c.code_dga for c in dga_configs}
standard_map = {c.point_catchment_id: c.standard for c in dga_configs}

# Buscar mediciones CON VOUCHER
records = list(InteractionDetail.objects.filter(
    catchment_point_id__in=point_ids,
    date_time_medition__gte=window_start,
    date_time_medition__lt=window_end,
    n_voucher__isnull=False
).select_related(
    'catchment_point',
    'catchment_point__project',
    'catchment_point__project__client'
).order_by(
    'catchment_point__project__name',
    'catchment_point__title'
)[:20])  # Limitar a 20 para el ejemplo

print(f"📊 Encontradas {len(records)} mediciones con voucher")

# Agrupar por punto (última medición por punto)
point_records = {}
for r in records:
    point_id = r.catchment_point_id
    if point_id not in point_records:
        point_records[point_id] = r
    else:
        if r.date_time_medition > point_records[point_id].date_time_medition:
            point_records[point_id] = r

unique_records = list(point_records.values())

# Construir mensaje
date_str = now_chile.strftime("%d/%m/%Y %H:%M")

msg_parts = []
msg_parts.append(f"📊 **REPORTE DGA - CUMPLIMIENTO (PRUEBA)**")
msg_parts.append(f"📅 {date_str}")
msg_parts.append(f"📈 Total puntos con voucher: {len(unique_records)}")
msg_parts.append("")
msg_parts.append("─" * 40)

# Agrupar por proyecto
project_groups = {}
for r in unique_records:
    point = r.catchment_point
    project_name = point.project.name if point.project else "Sin Proyecto"

    if project_name not in project_groups:
        project_groups[project_name] = []
    project_groups[project_name].append(r)

# Mostrar por proyecto
for project_name in sorted(project_groups.keys()):
    project_records = project_groups[project_name]

    msg_parts.append(f"🏗️ **{project_name}**")
    msg_parts.append("")

    for r in project_records:
        point = r.catchment_point
        code_obra = code_map.get(point.id, "N/A")
        standard = standard_map.get(point.id, "N/A")
        voucher_str = str(r.n_voucher)[:36] if r.n_voucher else "Sin voucher"

        medicion_time = r.date_time_medition.astimezone(chile_tz).strftime("%d/%m %H:%M")

        try:
            total_val = "{:,.0f}".format(float(r.total)) if r.total else "-"
        except:
            total_val = str(r.total) if r.total else "-"

        try:
            flow_val = "{:.2f}".format(float(r.flow)) if r.flow else "-"
        except:
            flow_val = str(r.flow) if r.flow else "-"

        msg_parts.append(f"  📍 **{point.title}**")
        msg_parts.append(f"      🏷️ {code_obra} - {standard}")
        msg_parts.append(f"      📅 {medicion_time}")
        msg_parts.append(f"      💧 Caudal: {flow_val} L/s | Total: {total_val} m³")
        msg_parts.append(f"      ✅ Voucher: {voucher_str}")
        msg_parts.append("")

    msg_parts.append("")

msg_parts.append("─" * 40)
msg_parts.append(f"✅ {len(unique_records)} mediciones | {len(project_groups)} proyectos")
msg_parts.append("")
msg_parts.append("_Reporte de prueba - Últimas 24h_")

full_msg = "\n".join(msg_parts)

print("\n" + "="*50)
print("VISTA PREVIA DEL MENSAJE:")
print("="*50)
print(full_msg)
print("="*50)

# Enviar mensaje
try:
    send_dga_chat_message(full_msg)
    print("\n✅ Mensaje enviado a Google Chat DGA!")
except Exception as e:
    print(f"\n❌ Error enviando mensaje: {e}")
