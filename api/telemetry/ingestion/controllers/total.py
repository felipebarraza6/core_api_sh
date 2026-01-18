"""Procesamiento de totalizados - CON LÓGICA DE RESET."""

import logging

from django.utils import timezone

from api.core.models import NotificationsCatchment, TelemetryRecord, Variable

logger = logging.getLogger(__name__)


def total_m3(
    pulses_factor, value, point_catchment, variable_id=None, return_full_details=False
):
    """
    Calcular total en m3 usando la fórmula: ((pulsos * factor) / 1000) + offset

    LÓGICA DE RESET:
    - Compara el valor actual (pulsos) con el último registrado.
    - Si value < last_value: Detecta reinicio.
    - Acumula el valor perdido en variable.addition (offset).
    - Crea Notificación.
    """
    try:
        if not pulses_factor or pulses_factor <= 0:
            logger.warning(
                f"pulses_factor no válido: {pulses_factor}, usando constante por defecto 1000"
            )
            pulses_factor = 1000

        # Convertir a m3 bruto (sin offset)

        # Convertir a m3 bruto (sin offset)
        try:
            current_pulses = float(value)
        except (ValueError, TypeError):
            current_pulses = 0.0

        # Buscar último registro válido (siempre lo necesitamos para fallback)
        last_record = (
            TelemetryRecord.objects.filter(point_id=point_catchment["id"])
            .order_by("-timestamp")
            .first()
        )

        last_total = (
            float(last_record.data.get("total"))
            if last_record and last_record.data.get("total") is not None
            else None
        )
        last_pulses = (
            float(last_record.data.get("pulses"))
            if last_record and last_record.data.get("pulses") is not None
            else None
        )

        # ✅ CASO CRÍTICO: Pulsos negativos = Error de ingesta
        # Mantener último total válido en lugar de guardar basura
        if current_pulses < 0:
            logger.warning(
                f"🚨 ERROR DE INGESTA: Pulsos negativos ({current_pulses}) en Punto {point_catchment['id']}. "
                f"Manteniendo último total válido."
            )
            fallback_val = int(last_total) if last_total is not None else 0

            if return_full_details:
                return fallback_val, {
                    "raw_pulses": current_pulses,
                    "status": "ERROR_NEGATIVE_PULSES",
                    "logic": "kept_last_valid",
                }
            return fallback_val

        current_raw_m3 = (current_pulses * float(pulses_factor)) / 1000.0

        # -- NUEVA LÓGICA: Usar ProfileDataConfigCatchment para el offset/addition --
        from api.core.models import ProfileDataConfigCatchment

        profile = ProfileDataConfigCatchment.objects.filter(
            point_catchment_id=point_catchment["id"]
        ).first()

        # Recuperar offset actual del perfil (si existe)
        offset = 0
        if profile:
            offset = profile.addition or 0

        # NOTE: Legacy fallback to variable.addition removed as per requirement.
        # offset remains 0 if profile is not found.

        # ====================================================================
        # VALIDACIÓN ANTI-SALTO MASIVO (ANTES DE ACEPTAR NUEVO VALOR)
        # ====================================================================
        MAX_DIFF_M3_PER_HOUR = 500  # Consumo máximo razonable por hora

        if last_total is not None:
            potential_new_total = current_raw_m3 + offset
            diff = potential_new_total - last_total

            # Si el salto es > 500 m³, es sospechoso (probable glitch de sensor)
            if diff > MAX_DIFF_M3_PER_HOUR:
                logger.warning(
                    f"🚨 SALTO MASIVO DETECTADO Punto {point_catchment['id']}: "
                    f"Salto de {diff:.0f} m³ ({last_total:.0f} → {potential_new_total:.0f}). "
                    f"Manteniendo último total válido para evitar corrupción."
                )
                # Retornar el valor anterior sin actualizar nada
                if return_full_details:
                    return int(round(last_total)), {
                        "raw_pulses": current_pulses,
                        "status": "MASSIVE_JUMP_BLOCKED",
                        "diff_detected": diff,
                        "logic": "kept_last_valid",
                    }
                return int(round(last_total))

        # LÓGICA DE RESET (solo si pasó la validación anti-salto)
        if last_pulses is not None:
            try:
                # DETECCIÓN DE REINICIO
                # Caso 1: Glitch de red/sensor (valor 0)
                if current_pulses == 0 and last_pulses > 0:
                    logger.warning(
                        f"⚠️ Posible Glitch (0) en Punto {point_catchment['id']}. Ignorando valor para evitar reinicio falso."
                    )
                    return int(
                        round((last_pulses * float(pulses_factor)) / 1000.0 + offset)
                    )

                # Caso 2: Reinicio Real (0 < actual < anterior)
                elif 0 < current_pulses < last_pulses:
                    logger.warning(
                        f"🚨 RESET REAL DETECTADO Punto {point_catchment['id']}: {last_pulses} -> {current_pulses}"
                    )

                    # Calcular corrección
                    amount_to_add = (last_pulses * float(pulses_factor)) / 1000.0

                    # ACTUALIZACIÓN AUTOMÁTICA DE ADICIÓN EN PERFIL
                    if profile:
                        profile.addition = offset + int(amount_to_add)
                        profile.save()
                        offset = profile.addition  # Actualizar offset local
                    else:
                        logger.error(
                            f"Cannot update addition: ProfileDataConfigCatchment not found for point {point_catchment['id']}"
                        )

                    # Crear Notificación
                    NotificationsCatchment.objects.create(
                        point_catchment_id=point_catchment["id"],
                        title="Reinicio de Contador Detectado",
                        message=f"Se detectó un reinicio en el contador totalizador. Valor anterior: {int(last_pulses)}, Valor actual: {int(current_pulses)}. El sistema ha ajustado la contabilidad automáticamente.",
                        type_variable="TOTALIZADO",
                        type_notification="WARNING",  # Advertencia
                        value=int(current_pulses),
                        is_active=True,
                        start_date=timezone.now().date(),
                    )

            except Exception as e:
                logger.error(f"Error en lógica de reset: {e}")

        # CÁLCULO FINAL: Bruto + Offset
        final_total = current_raw_m3 + offset

        status_flag = "OK"
        if final_total < 0:
            logger.warning(
                f"Total negativo ({final_total}) calculado para Punto {point_catchment['id']}. Clamping a 0."
            )
            final_total = 0
            status_flag = "CLAMPED_ZERO"

        final_int = int(round(final_total))

        if return_full_details:
            metadata = {
                "raw_pulses": current_pulses,
                "offset": offset,
                "raw_m3": current_raw_m3,
                "status": status_flag,
            }
            return final_int, metadata

        return final_int

    except Exception as e:
        logger.error(f"Error en total_m3: {e}")
        if return_full_details:
            return 0, {"error": str(e), "status": "ERROR"}
        return 0


def total_hour(total, point_catchment, current_dt=None):
    """
    Diferencia contra la medición anterior.
    """
    try:
        total_actual = float(total)

        query = TelemetryRecord.objects.filter(point_id=point_catchment["id"])
        if current_dt:
            query = query.filter(timestamp__lt=current_dt)

        prev = query.order_by("-timestamp").first()

        if not prev or prev.data.get("total") is None:
            return 0

        total_anterior = float(prev.data.get("total"))

        diff = total_actual - total_anterior

        # Si diff < 0, algo raro pasó, clamping a 0
        if diff < 0:
            logger.warning(
                f"Diff negativa ({diff}) en Punto {point_catchment['id']}. Clamp a 0."
            )
            return 0

        # ✅ ANTI-RESET RULE
        if diff > 500:
            logger.warning(
                f"🚨 DIFF EXCESIVA ({diff} > 500) en Punto {point_catchment['id']}. "
                "Posible restauración de contador. Clamp a 0."
            )
            return 0

        return int(round(diff))

    except Exception as e:
        logger.error(f"Error total_hour para punto {point_catchment['id']}: {e}")
        return 0


def total_day(point_catchment, current_dt=None, current_total=None):
    """
    Acumulado del día = Total actual - Primer total del día
    """
    try:
        if current_dt:
            dia = current_dt.date()
        else:
            dia = timezone.now().date()

        # Obtener primer registro del día
        primer_total_dia = (
            TelemetryRecord.objects.filter(
                point_id=point_catchment["id"],
                timestamp__date=dia,
            )
            .order_by("timestamp")
            .first()
        )

        if not primer_total_dia or primer_total_dia.data.get("total") is None:
            return 0

        primer_total = float(primer_total_dia.data.get("total"))

        # USAR TOTAL ACTUAL
        if current_total is not None:
            total_actual = float(current_total)
        else:
            # Buscar último total del día en BD (fallback)
            ultimo = (
                TelemetryRecord.objects.filter(
                    point_id=point_catchment["id"],
                    timestamp__date=dia,
                )
                .order_by("-timestamp")
                .first()
            )
            if not ultimo or ultimo.data.get("total") is None:
                return 0
            total_actual = float(ultimo.data.get("total"))

        # Cálculo directo
        diff_dia = total_actual - primer_total

        # Validación
        if diff_dia < 0:
            logger.warning(
                f"Diff día negativo ({diff_dia}) en Punto {point_catchment['id']}. Clamp a 0."
            )
            return 0

        # Validación anti-salto
        if diff_dia > 10000:
            logger.warning(
                f"🚨 DIFF DÍA EXCESIVA ({diff_dia} > 10,000) en Punto {point_catchment['id']}. "
                "Probable error de datos. Clamp a 0."
            )
            return 0

        return int(round(diff_dia))

    except Exception as e:
        logger.error(f"Error total_day para punto {point_catchment['id']}: {e}")
        return 0
