"""
Reporte Horario DGA MAYOR - Cumplimiento
=========================================
Envío: Cada hora a los :05 minutos (reporta la hora anterior)
Destino: Canal Google Chat DGA

Ejemplo: A las 16:05 reporta mediciones de las 15:00

Contenido:
- Lista de puntos con estándar MAYOR que cargaron mediciones a DGA
- Agrupado por cliente
- Muestra: Punto [Código DGA] | Total | Caudal | Nivel Freático
"""

import logging
from datetime import datetime, timedelta
from django.utils import timezone
from api.core.models import DgaDataConfigCatchment, InteractionDetail
from api.core.utils.google_chat import send_dga_chat_message

logger = logging.getLogger(__name__)


def run():
    """
    Reporte horario de mediciones DGA estándar MAYOR.
    Se ejecuta a los :05 de cada hora y reporta las mediciones de la hora anterior.
    """
    logger.info("Iniciando Reporte Horario DGA MAYOR...")

    try:
        import pytz
        chile_tz = pytz.timezone("America/Santiago")
        now = timezone.now()
        now_chile = now.astimezone(chile_tz)

        # Calcular la hora a reportar (hora anterior)
        # Si estamos a las 16:05, reportamos mediciones de las 15:00
        report_hour = now_chile.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

        # Ventana: desde la hora reportada hasta una hora después
        window_start = report_hour
        window_end = report_hour + timedelta(hours=1)

        # Obtener puntos con estándar MAYOR que envían a DGA
        mayor_configs = list(DgaDataConfigCatchment.objects.filter(
            standard='MAYOR',
            send_dga=True
        ).select_related(
            'point_catchment',
            'point_catchment__project',
            'point_catchment__project__client'
        ))

        if not mayor_configs:
            logger.info("No hay puntos configurados con estándar MAYOR.")
            return

        point_ids = [c.point_catchment_id for c in mayor_configs]
        code_map = {c.point_catchment_id: c.code_dga for c in mayor_configs}

        # Buscar mediciones de la hora reportada QUE SE ENVIARON A DGA
        # Filtramos por send_dga=True para mostrar solo lo realmente enviado
        records = list(InteractionDetail.objects.filter(
            catchment_point_id__in=point_ids,
            date_time_medition__gte=window_start,
            date_time_medition__lt=window_end,
            send_dga=True  # ✅ Solo registros marcados para envío DGA
        ).select_related(
            'catchment_point',
            'catchment_point__project',
            'catchment_point__project__client'
        ).order_by('catchment_point__project__client__name', 'catchment_point__title'))

        if not records:
            logger.info(f"No hay mediciones DGA MAYOR para las {report_hour.strftime('%H:%M')}.")
            return

        # Agrupar por punto (solo un registro por punto)
        seen_points = set()
        unique_records = []
        for r in records:
            if r.catchment_point_id not in seen_points:
                seen_points.add(r.catchment_point_id)
                unique_records.append(r)

        # Construir mensaje con mejor formato
        report_hour_str = report_hour.strftime("%H:%M")
        date_str = now_chile.strftime("%d/%m/%Y")

        msg_parts = []
        msg_parts.append(f"📊 **REPORTE DGA MAYOR**")
        msg_parts.append(f"📅 {date_str} - Mediciones {report_hour_str} hrs")
        msg_parts.append(f"📈 Total puntos: {len(unique_records)}")
        msg_parts.append("")
        msg_parts.append("─" * 35)

        current_client = None
        client_count = 0

        for r in unique_records:
            point = r.catchment_point
            client_name = point.project.client.name if point.project and point.project.client else "N/A"
            code_obra = code_map.get(point.id, "N/A")

            # Nuevo cliente = nueva sección
            if client_name != current_client:
                if current_client is not None:
                    msg_parts.append("")
                msg_parts.append(f"🏢 **{client_name}**")
                msg_parts.append("")
                current_client = client_name
                client_count += 1

            # Formatear valores con manejo seguro
            try:
                total_val = "{:,.0f}".format(float(r.total)) if r.total else "-"
            except (ValueError, TypeError):
                total_val = str(r.total) if r.total else "-"

            try:
                flow_val = "{:.2f}".format(float(r.flow)) if r.flow else "-"
            except (ValueError, TypeError):
                flow_val = str(r.flow) if r.flow else "-"

            try:
                water_val = "{:.2f}".format(float(r.water_table)) if r.water_table else "-"
            except (ValueError, TypeError):
                water_val = str(r.water_table) if r.water_table else "-"

            # Línea del punto
            msg_parts.append(f"  📍 {point.title}")
            msg_parts.append(f"      [{code_obra}]")
            msg_parts.append(f"      Total: {total_val} m³")
            msg_parts.append(f"      Caudal: {flow_val} L/s")
            msg_parts.append(f"      NF: {water_val} m")
            msg_parts.append("")

        msg_parts.append("─" * 35)
        msg_parts.append(f"✅ {len(unique_records)} mediciones | {client_count} clientes")

        # Enviar mensaje
        full_msg = "\n".join(msg_parts)

        # Si el mensaje es muy largo, dividirlo
        if len(full_msg) > 4000:
            parts = [full_msg[i:i+4000] for i in range(0, len(full_msg), 4000)]
            for p in parts:
                send_dga_chat_message(p)
        else:
            send_dga_chat_message(full_msg)

        logger.info(f"Reporte DGA MAYOR enviado: {len(unique_records)} mediciones de las {report_hour_str}.")

    except Exception as e:
        logger.error(f"Error en Reporte DGA MAYOR: {e}", exc_info=True)
