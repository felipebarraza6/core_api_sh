"""Procesamiento de totalizados - SIN LÓGICA DE RESET."""

import logging
from api.core.models import InteractionDetail

logger = logging.getLogger(__name__)


def total_m3(pulses_factor, value, point_catchment):
    """
    Calcular total en m3 usando la fórmula simple: (pulsos * constante) / 1000
    SIN LÓGICA DE RESET - Solo procesa pulsos tal como llegan.
    """
    try:
        if not pulses_factor or pulses_factor <= 0:
            logger.warning(
                f"pulses_factor no válido: {pulses_factor}, usando constante por defecto 1000"
            )
            pulses_factor = 1000
        nuevo_total = (float(value) * float(pulses_factor)) / 1000.0
        if nuevo_total < 0:
            logger.error(f"TOTAL NEGATIVO DETECTADO: {nuevo_total}")
            ultimo = (
                InteractionDetail.objects.filter(catchment_point_id=point_catchment["id"])
                .exclude(total__isnull=True)
                .order_by("-date_time_medition").first()
            )
            if ultimo:
                try:
                    return str(int(float(ultimo.total)))
                except Exception:
                    return "0"
            return "0"
        return str(int(round(nuevo_total)))
    except Exception as e:
        logger.error(f"Error en total_m3: {e}")
        try:
            ultimo = (
                InteractionDetail.objects.filter(catchment_point_id=point_catchment["id"])
                .exclude(total__isnull=True)
                .order_by("-date_time_medition").first()
            )
            if ultimo:
                return str(int(float(ultimo.total)))
        except Exception:
            pass
        return "0"


def total_hour(total, point_catchment, current_dt=None):
    """
    Diferencia contra la medición anterior ordenando por created (campo que siempre existe).
    - Si no hay anterior: 0
    - Si hay reset (total_actual < total_anterior): diff = total_actual
    - Si normal: diff = total_actual - total_anterior (clamp >= 0)
    """
    try:
        total_actual = float(total)
        
        # ✅ SOLUCIÓN: Usar campo 'created' que siempre existe
        if current_dt:
            # Si se pasa current_dt, filtrar por fecha
            prev = (
                InteractionDetail.objects.filter(
                    catchment_point_id=point_catchment["id"],
                    created__lt=current_dt,
                )
                .exclude(total__isnull=True)
                .exclude(total="")
                .order_by("-created", "-id")
                .first()
            )
        else:
            # ✅ SOLUCIÓN: Si no hay current_dt, buscar el último registro
            prev = (
                InteractionDetail.objects.filter(
                    catchment_point_id=point_catchment["id"],
                )
                .exclude(total__isnull=True)
                .exclude(total="")
                .order_by("-created", "-id")
                .first()
            )
        
        if not prev:
            logger.info(f"No hay registro anterior para punto {point_catchment['id']}, diff = 0")
            return 0
            
        total_anterior = float(prev.total)
        
        # ✅ LÓGICA CORREGIDA: Manejar reset de contador
        if total_actual < total_anterior:
            logger.info(f"Reset detectado: {total_actual} < {total_anterior}, diff = {total_actual}")
            return int(round(total_actual))
        
        # ✅ CÁLCULO NORMAL: Diferencia entre total actual y anterior
        diff = total_actual - total_anterior
        if diff < 0:
            diff = 0
            
        logger.info(f"Diff calculada: {total_actual} - {total_anterior} = {diff}")
        return int(round(diff))
        
    except Exception as e:
        logger.error(f"Error total_hour para punto {point_catchment['id']}: {e}")
        return 0


def total_day(point_catchment, current_dt=None, current_diff=None):
    """
    🚀 VERSIÓN OPTIMIZADA: Acumulado del día = Total actual - Primer total del día
    Mucho más eficiente que sumar todas las diferencias hora por hora.
    """
    try:
        # ✅ SOLUCIÓN: Si no hay current_dt, usar fecha actual
        if current_dt:
            dia = current_dt.date()
        else:
            from datetime import datetime
            dia = datetime.now().date()
        
        # ✅ BUSQUEDA OPTIMIZADA: Solo el primer total del día
        primer_total_dia = (
            InteractionDetail.objects.filter(
                catchment_point_id=point_catchment["id"],
                created__date=dia,
            )
            .exclude(total__isnull=True)
            .exclude(total="")
            .order_by("created", "id")  # Ordenar ASC para obtener el primero
            .first()
        )
        
        if not primer_total_dia:
            logger.info(f"No hay registros del día para punto {point_catchment['id']}, diff = 0")
            return 0
        
        primer_total = float(primer_total_dia.total)
        
        # ✅ CÁLCULO OPTIMIZADO: Buscar el total actual del día
        ultimo_total_dia = (
            InteractionDetail.objects.filter(
                catchment_point_id=point_catchment["id"],
                created__date=dia,
            )
            .exclude(total__isnull=True)
            .exclude(total="")
            .order_by("-created", "-id")  # Ordenar DESC para obtener el último
            .first()
        )
        
        if not ultimo_total_dia:
            logger.info(f"No hay último registro del día para punto {point_catchment['id']}")
            return 0
        
        total_actual = float(ultimo_total_dia.total)
        
        # ✅ CÁLCULO FINAL: Diferencia entre total actual y primer total del día
        if total_actual < primer_total:
            # Si hay reset de contador, usar el total actual
            logger.info(f"Reset detectado: {total_actual} < {primer_total}, diff = {total_actual}")
            return int(round(total_actual))
        
        diff_dia = total_actual - primer_total
        if diff_dia < 0:
            diff_dia = 0
            
        logger.info(f"Acumulado día optimizado: {total_actual} - {primer_total} = {diff_dia}")
        return int(round(diff_dia))
        
    except Exception as e:
        logger.error(f"Error total_day optimizado para punto {point_catchment['id']}: {e}")
        try:
            cd = int(current_diff) if current_diff else 0
        except Exception:
            cd = 0
        return cd if cd > 0 else 0



