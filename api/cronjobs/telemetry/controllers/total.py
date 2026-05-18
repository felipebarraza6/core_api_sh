"""Procesamiento de totalizados - CON LÓGICA DE RESET."""

import logging
from api.core.models import InteractionDetail, Variable, NotificationsCatchment
from django.utils import timezone

logger = logging.getLogger(__name__)


def total_m3(pulses_factor, value, point_catchment, variable_id=None, return_full_details=False):
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
        last_interaction = (
            InteractionDetail.objects.filter(catchment_point_id=point_catchment["id"])
            .exclude(pulses__isnull=True)
            .exclude(total__isnull=True)
            .order_by("-date_time_medition")
            .first()
        )

        # ✅ CASO CRÍTICO: Pulsos negativos = Error de ingesta
        # Mantener último total válido en lugar de guardar basura
        if current_pulses < 0:
            logger.warning(
                f"🚨 ERROR DE INGESTA: Pulsos negativos ({current_pulses}) en Punto {point_catchment['id']}. "
                f"Manteniendo último total válido."
            )
            fallback_val = 0
            if last_interaction and last_interaction.total:
                fallback_val = int(float(last_interaction.total))

            if return_full_details:
                return fallback_val, {
                    "raw_pulses": current_pulses,
                    "status": "ERROR_NEGATIVE_PULSES",
                    "logic": "kept_last_valid"
                }
            return fallback_val

        current_raw_m3 = (current_pulses * float(pulses_factor)) / 1000.0

        # =====================================================================
        # LEER CONFIGURACIÓN DEL PERFIL (desde dict serializado para evitar N+1)
        # =====================================================================
        profile_data = point_catchment.get("profile_data_config", {}) if isinstance(point_catchment, dict) else {}

        offset = float(profile_data.get("addition", 0) or 0)
        max_diff_m3 = float(profile_data.get("max_diff_m3_per_hour", 500) or 500)
        reconnection_threshold = float(profile_data.get("reconnection_threshold_hours", 2) or 2)

        # Fallback a query directa si no hay profile serializado (raro, pero seguro)
        if not profile_data:
            from api.core.models import ProfileDataConfigCatchment
            profile = ProfileDataConfigCatchment.objects.filter(point_catchment_id=point_catchment["id"]).first()
            if profile:
                offset = float(profile.addition or 0)
                max_diff_m3 = float(profile.max_diff_m3_per_hour) if profile.max_diff_m3_per_hour else 500.0
                reconnection_threshold = float(profile.reconnection_threshold_hours) if profile.reconnection_threshold_hours else 2.0

        # =====================================================================
        # VALIDACIÓN ANTI-SALTO MASIVO (NORMAlIZADA POR TIEMPO)
        # =====================================================================

        if last_interaction and last_interaction.total is not None:
            last_total = float(last_interaction.total)
            potential_new_total = current_raw_m3 + offset
            diff = potential_new_total - last_total

            # Normalizar diff por tiempo transcurrido
            time_diff_hours = 1.0 # Default fallback
            if last_interaction.date_time_medition:
                now = timezone.now()
                time_delta = now - last_interaction.date_time_medition
                time_diff_hours = max(time_delta.total_seconds() / 3600.0, 0.1)

            # ================================================================
            # DETECCIÓN DE RECONEXIÓN: Si el sensor estuvo desconectado,
            # el salto acumulado es LEGÍTIMO y NO debe bloquearse.
            # Sin esta lógica, el total queda congelado PARA SIEMPRE.
            # ================================================================
            is_reconnection = (
                time_diff_hours > reconnection_threshold
                or last_interaction.days_not_conection > 0
            )

            if is_reconnection and diff > 0:
                # Reconexión detectada: aceptar el nuevo total
                logger.info(
                    f"🔄 RECONEXIÓN Punto {point_catchment['id']}: "
                    f"Salto de {diff:.0f} m³ en {time_diff_hours:.1f} horas. "
                    f"Aceptando nuevo total (reconexión legítima)."
                )
                # No bloquear, continuar al cálculo final
            else:
                m3_per_hour = diff / time_diff_hours

                # Si el salto es > límite m³ por hora EN OPERACIÓN NORMAL, es sospechoso
                if m3_per_hour > max_diff_m3:
                    logger.warning(
                        f"🚨 SALTO MASIVO DETECTADO Punto {point_catchment['id']}: "
                        f"Salto de {diff:.0f} m³ en {time_diff_hours:.1f} horas ({m3_per_hour:.1f} m³/h). "
                        f"Límite {max_diff_m3} m³/h. Manteniendo último total válido."
                    )
                    # Retornar el valor anterior sin actualizar nada
                    if return_full_details:
                        return int(round(last_total)), {
                            "raw_pulses": current_pulses,
                            "status": "MASSIVE_JUMP_BLOCKED",
                            "diff_detected": diff,
                            "m3_per_hour": m3_per_hour,
                            "logic": "kept_last_valid"
                        }
                    return int(round(last_total))

        # LÓGICA DE RESET (solo si pasó la validación anti-salto)
        if last_interaction and last_interaction.pulses is not None:
            try:
                last_pulses = float(last_interaction.pulses)

                # DETECCIÓN DE REINICIO
                # Caso 1: Reset a 0 (corte de energía, mantenimiento)
                if current_pulses == 0 and last_pulses > 0:
                    amount_to_add = (last_pulses * float(pulses_factor)) / 1000.0
                    new_addition = offset + amount_to_add

                    from django.db import transaction
                    from django.db.models import F
                    from api.core.models import ProfileDataConfigCatchment
                    with transaction.atomic():
                        profile_obj = ProfileDataConfigCatchment.objects.select_for_update().filter(
                            point_catchment_id=point_catchment["id"]
                        ).first()
                        if profile_obj:
                            profile_obj.addition = F("addition") + amount_to_add
                            profile_obj.save(update_fields=["addition"])
                            profile_obj.refresh_from_db()
                            offset = float(profile_obj.addition)
                        else:
                            logger.error(f"Cannot update addition: ProfileDataConfigCatchment not found for point {point_catchment['id']}")
                            offset = float(new_addition)

                    logger.info(
                        f"🔄 RESET a 0 detectado Punto {point_catchment['id']}: "
                        f"addition += {amount_to_add:.3f} -> {offset:.3f}"
                    )

                    # Crear Notificación
                    NotificationsCatchment.objects.create(
                        point_catchment_id=point_catchment["id"],
                        title="Reinicio de Contador Detectado",
                        message=f"Reset a 0 detectado. Pulsos anteriores: {int(last_pulses)}. Addition ajustada a {offset:.3f} m³.",
                        type_variable="TOTALIZADO",
                        type_notification="WARNING",
                        value=int(current_pulses),
                        is_active=True,
                        start_date=timezone.now().date()
                    )

                    # El total actual es solo el offset (pulsos=0 -> bruto=0)
                    final_total = offset
                    final_int = int(round(final_total))
                    if return_full_details:
                        return final_int, {
                            "raw_pulses": current_pulses,
                            "offset": offset,
                            "raw_m3": 0.0,
                            "status": "RESET_ZERO"
                        }
                    return final_int

                # Caso 2: Reinicio Real (0 < actual < anterior)
                elif 0 < current_pulses < last_pulses:
                    logger.warning(
                        f"🚨 RESET REAL DETECTADO Punto {point_catchment['id']}: {last_pulses} -> {current_pulses}"
                    )

                    # Calcular corrección
                    amount_to_add = (last_pulses * float(pulses_factor)) / 1000.0

                    # ACTUALIZACIÓN ATÓMICA DE ADICIÓN EN PERFIL
                    from django.db import transaction
                    from django.db.models import F
                    from api.core.models import ProfileDataConfigCatchment
                    with transaction.atomic():
                        profile_obj = ProfileDataConfigCatchment.objects.select_for_update().filter(
                            point_catchment_id=point_catchment["id"]
                        ).first()
                        if profile_obj:
                            profile_obj.addition = F("addition") + amount_to_add
                            profile_obj.save(update_fields=["addition"])
                            profile_obj.refresh_from_db()
                            offset = float(profile_obj.addition)
                        else:
                            logger.error(f"Cannot update addition: ProfileDataConfigCatchment not found for point {point_catchment['id']}")
                            offset = offset + amount_to_add

                    # Crear Notificación
                    NotificationsCatchment.objects.create(
                        point_catchment_id=point_catchment["id"],
                        title="Reinicio de Contador Detectado",
                        message=f"Se detectó un reinicio en el contador totalizador. Valor anterior: {int(last_pulses)}, Valor actual: {int(current_pulses)}. El sistema ha ajustado la contabilidad automáticamente.",
                        type_variable="TOTALIZADO",
                        type_notification="WARNING",
                        value=int(current_pulses),
                        is_active=True,
                        start_date=timezone.now().date()
                    )

            except Exception as e:
                logger.error(f"Error en lógica de reset: {e}")

        # CÁLCULO FINAL: Bruto + Offset
        final_total = current_raw_m3 + offset

        status_flag = "OK"
        if final_total < 0:
            logger.warning(f"Total negativo ({final_total}) calculado para Punto {point_catchment['id']}. Clamping a 0.")
            final_total = 0
            status_flag = "CLAMPED_ZERO"

        final_int = int(round(final_total))

        if return_full_details:
             metadata = {
                 "raw_pulses": current_pulses,
                 "offset": offset,
                 "raw_m3": current_raw_m3,
                 "status": status_flag
             }
             return final_int, metadata

        return final_int

    except Exception as e:
        import traceback, sys
        tb = traceback.format_exc()
        # Escribir a archivo para debug
        with open('/tmp/total_m3_errors.log', 'a') as f:
            f.write(f"Error en total_m3 punto {point_catchment.get('id', '?')}: {e}\n{tb}\n")
            # Imprimir tipos de variables clave
            frame = sys.exc_info()[2].tb_frame
            locals_dict = frame.f_locals
            for var in ['offset', 'current_raw_m3', 'last_total', 'potential_new_total', 'diff', 'amount_to_add', 'new_addition', 'final_total', 'profile']:
                val = locals_dict.get(var, 'NO_EXISTE')
                f.write(f"  {var}: {type(val).__name__} = {val}\n")
            f.write(f"{'='*40}\n")
        logger.error(f"Error en total_m3: {e}")
        if return_full_details:
             return 0, {"error": str(e), "status": "ERROR"}
        return 0


def total_hour(total, point_catchment, current_dt=None):
    """
    Diferencia contra la medición anterior.
    Ahora asumimos que 'total' es monotónico gracias a la corrección en total_m3.
    """
    try:
        total_actual = float(total)

        if current_dt:
            prev = (
                InteractionDetail.objects.filter(
                    catchment_point_id=point_catchment["id"],
                    date_time_medition__lt=current_dt,
                )
                .exclude(total__isnull=True)
                .order_by("-date_time_medition")
                .first()
            )
        else:
            prev = (
                InteractionDetail.objects.filter(
                    catchment_point_id=point_catchment["id"],
                )
                .exclude(total__isnull=True)
                .order_by("-date_time_medition")
                .first()
            )

        if not prev:
            return 0

        total_anterior = float(prev.total)

        diff = total_actual - total_anterior

        # Si diff < 0, algo raro pasó (quizás edición manual de offset a la baja), clamping a 0
        if diff < 0:
            logger.warning(f"Diff negativa ({diff}) en Punto {point_catchment['id']}. Clamp a 0.")
            return 0

        return int(round(diff))

    except Exception as e:
        logger.error(f"Error total_hour para punto {point_catchment['id']}: {e}")
        return 0


def total_day(point_catchment, current_dt=None, current_total=None):
    """
    Acumulado del día = Total actual - Primer total del día

    ✅ CORRECCIÓN CRÍTICA: Recibe current_total (no current_diff).
    Método más robusto y coherente que sumar diffs (que pueden estar clampeados).
    """
    try:
        if current_dt:
            dia = current_dt.date()
        else:
            dia = timezone.now().date()

        # Obtener primer registro del día
        primer_total_dia = (
            InteractionDetail.objects.filter(
                catchment_point_id=point_catchment["id"],
                date_time_medition__date=dia,
            )
            .exclude(total__isnull=True)
            .order_by("date_time_medition")
            .first()
        )

        if not primer_total_dia:
            return 0

        primer_total = float(primer_total_dia.total)

        # USAR TOTAL ACTUAL (no diff)
        if current_total is not None:
            total_actual = float(current_total)
        else:
            # Buscar último total del día en BD (fallback)
            ultimo = (
                InteractionDetail.objects.filter(
                    catchment_point_id=point_catchment["id"],
                    date_time_medition__date=dia,
                )
                .exclude(total__isnull=True)
                .order_by("-date_time_medition")
                .first()
            )
            if not ultimo:
                return 0
            total_actual = float(ultimo.total)

        # Cálculo directo: Total actual - Primer total del día
        diff_dia = total_actual - primer_total

        # Validación: No puede ser negativo
        if diff_dia < 0:
            logger.warning(f"Diff día negativo ({diff_dia}) en Punto {point_catchment['id']}. Clamp a 0.")
            return 0

        return int(round(diff_dia))

    except Exception as e:
        logger.error(f"Error total_day para punto {point_catchment['id']}: {e}")
        return 0



