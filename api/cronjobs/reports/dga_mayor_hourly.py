"""
Reporte Horario DGA - Estado por Proyecto (Catastro)
====================================================
Envío: Cada hora a los :05 minutos
Destino: Canal Google Chat DGA

Contenido:
- Catastro completo DGA por PROYECTO
- Muestra TODOS los puntos independiente del estándar
- Última medición enviada de cada punto (con voucher)
- Los MAYOR cambian hora a hora, los MEDIO se mantienen todo el día
- Alerta visual si superó el caudal autorizado
"""

import logging
from datetime import datetime, timedelta
from django.utils import timezone
from api.core.models import DgaDataConfigCatchment, InteractionDetail
from api.core.utils.google_chat import send_dga_chat_message

logger = logging.getLogger(__name__)


def run():
    """
    Reporte DGA - Catastro completo por proyecto.
    Muestra la última medición enviada de cada punto (con voucher).
    Incluye TODOS los estándares: MAYOR cambian hora a hora, MEDIO se mantienen.
    """
    logger.info("Iniciando Reporte DGA - Catastro por Proyecto...")

    try:
        import pytz
        chile_tz = pytz.timezone("America/Santiago")
        now = timezone.now()
        now_chile = now.astimezone(chile_tz)

        # Obtener TODOS los puntos que envían a DGA (todos los estándares)
        dga_configs = list(DgaDataConfigCatchment.objects.filter(
            send_dga=True
        ).select_related(
            'point_catchment',
            'point_catchment__project',
            'point_catchment__project__client'
        ))

        if not dga_configs:
            logger.info("No hay puntos configurados para envío DGA.")
            return

        point_ids = [c.point_catchment_id for c in dga_configs]
        code_map = {c.point_catchment_id: c.code_dga for c in dga_configs}
        standard_map = {c.point_catchment_id: c.standard for c in dga_configs}
        flow_granted_map = {c.point_catchment_id: c.flow_granted_dga for c in dga_configs}

        # Obtener la ÚLTIMA medición con voucher de cada punto (sin filtro de tiempo)
        # Esto permite ver el estado actual completo: MAYOR recientes + MEDIO del día
        point_records = {}
        for point_id in point_ids:
            # Buscar última medición con voucher para este punto
            last_record = InteractionDetail.objects.filter(
                catchment_point_id=point_id,
                n_voucher__isnull=False
            ).select_related(
                'catchment_point',
                'catchment_point__project',
                'catchment_point__project__client'
            ).order_by('-date_time_medition').first()

            if last_record:
                point_records[point_id] = last_record

        unique_records = list(point_records.values())

        if not unique_records:
            logger.info("No hay mediciones DGA confirmadas.")
            return

        # Construir mensaje agrupado por PROYECTO
        date_str = now_chile.strftime("%d/%m/%Y %H:%M")

        msg_parts = []
        msg_parts.append(f"📊 **CATASTRO DGA POR PROYECTO**")
        msg_parts.append(f"📅 {date_str}")
        msg_parts.append(f"📈 Puntos activos: {len(unique_records)}")
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

        # Ordenar proyectos alfabéticamente
        for project_name in sorted(project_groups.keys()):
            project_records = project_groups[project_name]

            # Encabezado del proyecto
            msg_parts.append(f"🏗️ **{project_name}**")
            msg_parts.append("")

            # Puntos del proyecto
            for r in project_records:
                point = r.catchment_point
                code_obra = code_map.get(point.id, "N/A")
                standard = standard_map.get(point.id, "N/A")
                voucher_str = str(r.n_voucher)[:36] if r.n_voucher else "Sin voucher"
                flow_granted = flow_granted_map.get(point.id, None)

                # Fecha de la medición
                medicion_time = r.date_time_medition.astimezone(chile_tz).strftime("%d/%m %H:%M")

                # Formatear valores con manejo seguro
                # Total siempre con punto como separador de miles (100.000)
                try:
                    if r.total is not None:
                        total_num = float(r.total)
                        total_val = "{:,.0f}".format(total_num).replace(",", ".")
                    else:
                        total_val = "-"
                except (ValueError, TypeError):
                    total_val = "-"

                # Caudal: mostrar 0.0 si es 0.0, nunca nulo
                try:
                    if r.flow is not None:
                        flow_num = float(r.flow)
                        flow_val = "{:.2f}".format(flow_num)
                    else:
                        flow_num = None
                        flow_val = "-"
                except (ValueError, TypeError):
                    flow_num = None
                    flow_val = "-"

                # Verificar si excede el caudal autorizado
                exceeds_flow = False
                if flow_num is not None and flow_granted is not None:
                    try:
                        if flow_num > float(flow_granted):
                            exceeds_flow = True
                    except (ValueError, TypeError):
                        pass

                # Indicador visual si excede
                status_icon = "⚠️ " if exceeds_flow else ""

                # Determinar si es caudal o caudal medio según estándar
                # MAYOR = caudal instantáneo (cada hora)
                # MEDIO, MENOR, etc = caudal medio (promedio diario)
                is_instantaneous = (standard == "MAYOR")
                caudal_label = "Caudal" if is_instantaneous else "Caudal Medio"

                # Línea del punto con información completa
                msg_parts.append(f"  📍 {status_icon}**{point.title}**")
                msg_parts.append(f"      🏷️ {code_obra} - {standard}")
                msg_parts.append(f"      📅 {medicion_time}")

                # Mostrar caudal con alerta si excede
                if exceeds_flow:
                    msg_parts.append(f"      💧 {caudal_label}: {flow_val} L/s ⚠️ (Autorizado: {flow_granted} L/s)")
                else:
                    msg_parts.append(f"      💧 {caudal_label}: {flow_val} L/s | Total: {total_val} m³")

                msg_parts.append(f"      ✅ Voucher: {voucher_str}")
                msg_parts.append("")

            msg_parts.append("")

        msg_parts.append("─" * 40)
        msg_parts.append(f"✅ {len(unique_records)} mediciones | {len(project_groups)} proyectos")

        # Enviar mensaje
        full_msg = "\n".join(msg_parts)

        # Si el mensaje es muy largo, dividirlo
        if len(full_msg) > 4000:
            parts = [full_msg[i:i+4000] for i in range(0, len(full_msg), 4000)]
            for p in parts:
                send_dga_chat_message(p)
        else:
            send_dga_chat_message(full_msg)

        logger.info(f"Catastro DGA enviado: {len(unique_records)} puntos de {len(project_groups)} proyectos.")

    except Exception as e:
        logger.error(f"Error en Catastro DGA: {e}", exc_info=True)
