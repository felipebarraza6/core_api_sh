"""Procesamiento de totalizados - SIN LÓGICA DE RESET."""

import logging

from api.core.models import InteractionDetail

# Configurar logging para mejor trazabilidad
logger = logging.getLogger(__name__)


def total_m3(pulses_factor, value, point_catchment):
    """
    Calcular total en m3 usando la fórmula simple: (pulsos * constante) / 1000
    SIN LÓGICA DE RESET - Solo procesa pulsos tal como llegan

    Args:
        pulses_factor: Factor de conversión de pulsos a m3
        value: Valor de pulsos del sensor
        point_catchment: Punto de captación

    Returns:
        str: Total calculado en m3 como string
    """
    try:
        # Validar que pulses_factor sea válido
        if not pulses_factor or pulses_factor <= 0:
            logger.warning(
                f"pulses_factor no válido: {pulses_factor}, usando constante por defecto 1000"
            )
            pulses_factor = 1000

        # FÓRMULA SIMPLE: total = (pulsos * constante) / 1000
        nuevo_total = (float(value) * float(pulses_factor)) / 1000.0

        # ✅ PROTECCIÓN: si es negativo, mantener último total válido
        if nuevo_total < 0:
            logger.error(f"🚨 TOTAL NEGATIVO DETECTADO: {nuevo_total}")
            
            # Obtener el último total válido
            ultimo_registro = (
                InteractionDetail.objects.filter(catchment_point_id=point_catchment["id"])
                .exclude(total__isnull=True)
                .order_by("-created")
                .first()
            )
            
            if ultimo_registro:
                ultimo_total = int(float(ultimo_registro.total))
                logger.info(f"🔒 MANTENIENDO ÚLTIMO TOTAL VÁLIDO: {ultimo_total}")
                return str(ultimo_total)
            else:
                logger.warning("🔒 NO HAY TOTAL PREVIO, RETORNANDO 0")
                return "0"

        # ✅ RETORNAR TOTAL CALCULADO (SIN MANIPULACIÓN)
        logger.info(f"📊 TOTAL CALCULADO: {nuevo_total} m³ (pulsos: {value}, factor: {pulses_factor})")
        return str(int(round(nuevo_total)))

    except (ValueError, ZeroDivisionError) as e:
        logger.error(f"Error en cálculo de total_m3: {e}")
        
        # En caso de error, también mantener último total válido
        try:
            ultimo_registro = (
                InteractionDetail.objects.filter(catchment_point_id=point_catchment["id"])
                .exclude(total__isnull=True)
                .order_by("-created")
                .first()
            )
            
            if ultimo_registro:
                ultimo_total = int(float(ultimo_registro.total))
                logger.info(f"🔒 ERROR EN CÁLCULO, MANTENIENDO ÚLTIMO TOTAL: {ultimo_total}")
                return str(ultimo_total)
            else:
                logger.warning("🔒 ERROR EN CÁLCULO Y NO HAY TOTAL PREVIO, RETORNANDO 0")
                return "0"
        except:
            return "0"


def total_hour(total, point_catchment):
    """
    Calcular diferencia entre las dos últimas mediciones (SIN LÓGICA DE RESET)

    Args:
        total: Total actual
        point_catchment: Punto de captación

    Returns:
        int: Diferencia calculada entre mediciones
    """
    try:
        # Obtener los dos registros más recientes
        registros = (
            InteractionDetail.objects.filter(catchment_point_id=point_catchment["id"])
            .exclude(total__isnull=True)
            .order_by("-created")[:2]
        )

        total_actual = float(total)

        if len(registros) >= 2:
            # ✅ SIMPLE: tomar el SEGUNDO registro (el anterior inmediato)
            total_anterior = float(registros[1].total)
            diferencia = total_actual - total_anterior

            # ✅ PROTECCIÓN: NUNCA DIFERENCIAS NEGATIVAS
            if diferencia < 0:
                logger.warning(f"🚨 DIFERENCIA NEGATIVA: {total_actual} - {total_anterior} = {diferencia}")
                diferencia = 0

            logger.info(f"📊 Diferencia: {total_actual} - {total_anterior} = {diferencia}")
            return int(round(diferencia))

        elif len(registros) == 1:
            # Solo hay un registro previo
            total_anterior = float(registros[0].total)
            diferencia = total_actual - total_anterior

            if diferencia < 0:
                logger.warning(f"🚨 DIFERENCIA NEGATIVA: {total_actual} - {total_anterior} = {diferencia}")
                diferencia = 0

            logger.info(f"📊 Diferencia (1 prev): {total_actual} - {total_anterior} = {diferencia}")
            return int(round(diferencia))
        else:
            # Primer registro del punto
            logger.info(f"📊 Primer registro: {total_actual}")
            return int(round(total_actual))
            
    except Exception as e:
        logger.error(f"Error calculando diferencia entre mediciones: {e}")
        return 0


def total_day(total, point_catchment):
    """
    Calcular acumulado de todas las diferencias del día actual (SIN LÓGICA DE RESET)

    Args:
        total: Total actual
        point_catchment: Punto de captación

    Returns:
        int: Acumulado del día
    """
    try:
        # Obtener la fecha actual
        from datetime import datetime
        import pytz

        chile = pytz.timezone("America/Santiago")
        ahora = datetime.now(chile)
        hoy = ahora.date()

        # ✅ SIMPLE: obtener todas las diferencias del día actual
        diferencias_hoy = (
            InteractionDetail.objects.filter(
                catchment_point_id=point_catchment["id"],
                created__date=hoy,
            )
            .exclude(total_diff__isnull=True)
            .values_list("total_diff", flat=True)
        )

        if diferencias_hoy:
            # ✅ Sumar solo diferencias positivas
            suma_diferencias = sum([diff for diff in diferencias_hoy if diff > 0])
            logger.info(f"📊 Acumulado del día: {suma_diferencias}")
            return int(round(suma_diferencias))
        else:
            logger.info("📊 No hay diferencias en el día, total_today_diff = 0")
            return 0

    except Exception as e:
        logger.error(f"Error calculando acumulado del día: {e}")
        return 0

