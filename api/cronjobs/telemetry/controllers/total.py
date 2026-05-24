"""Procesamiento de totalizados - CON LÓGICA DE RESET."""

import logging
from api.core.models import InteractionDetail, Variable, NotificationsCatchment, CounterResetLog
from api.cronjobs.telemetry.utils.audit import emit_system_event
from django.utils import timezone

logger = logging.getLogger(__name__)


def _create_counter_reset_log(
    point_catchment_id,
    reset_type,
    last_pulses,
    current_pulses,
    pulses_factor,
    addition_before=None,
    amount_to_add=None,
    addition_after=None,
    total_before=None,
    total_after=None,
    passed_anti_jump=True,
    reconnection_threshold=None,
    is_reconnection=False,
    days_not_connection=None,
    time_diff_hours=None,
    date_time_medition=None,
):
    """Guarda auditoría de reset de contador. Nunca debe fallar el procesamiento principal."""
    try:
        CounterResetLog.objects.create(
            point_catchment_id=point_catchment_id,
            date_time_medition=date_time_medition or timezone.now(),
            time_diff_hours=time_diff_hours,
            reset_type=reset_type,
            last_pulses=last_pulses,
            current_pulses=current_pulses,
            pulses_factor=pulses_factor,
            addition_before=addition_before,
            amount_to_add=amount_to_add,
            addition_after=addition_after,
            total_before=total_before,
            total_after=total_after,
            passed_anti_jump=passed_anti_jump,
            reconnection_threshold=reconnection_threshold,
            is_reconnection=is_reconnection,
            days_not_connection=days_not_connection,
            detected_by="cron_unified",
        )
    except Exception as e:
        logger.error(f"Error guardando CounterResetLog para punto {point_catchment_id}: {e}")


def total_m3(pulses_factor, value, point_catchment, variable_id=None, return_full_details=False, current_dt=None, frecuency_minutes=None):
    """
    Calcular total en m3 usando la fórmula: ((pulsos * factor) / 1000) + offset

    LÓGICA DE RESET:
    - Compara el valor actual (pulsos) con el último registrado.
    - Si value < last_value: Detecta reinicio.
    - Acumula el valor perdido en variable.addition (offset).
    - Crea Notificación.

    Args:
        current_dt: datetime de la medición actual (para logs precisos y time_diff).
        frecuency_minutes: frecuencia del punto en minutos (para time_diff en reprocesamiento).
    """
    # Fecha real de la medición para logs y cálculos
    current_dt = current_dt or timezone.now()
    # Defensa: si nos pasan un datetime naive, hacerlo aware para evitar crash al restar
    if current_dt.tzinfo is None:
        current_dt = timezone.make_aware(current_dt)

    try:
        if not pulses_factor or pulses_factor <= 0:
            logger.warning(
                f"pulses_factor no válido: {pulses_factor}, usando constante por defecto 1000"
            )
            pulses_factor = 1000

        # Convertir a m3 bruto (sin offset)

        # Convertir a m3 bruto (sin offset)
        # Default time_diff para logs/auditoría (sobrescrito más abajo si hay historial)
        time_diff_hours = 1.0

        try:
            current_pulses = float(value)
        except (ValueError, TypeError):
            current_pulses = 0.0

        # Buscar último registro válido (siempre lo necesitamos para fallback)
        # ✅ MITIGADO: El runner unificado (telemetry_unified.py) usa lock Redis
        # por punto (acquire_point_lock), por lo que dos procesos no pueden
        # procesar el mismo punto simultáneamente. Además, la actualización del
        # offset (addition) en caso de reset SÍ usa select_for_update().
        last_interaction = (
            InteractionDetail.objects.filter(catchment_point_id=point_catchment["id"])
            .exclude(pulses__isnull=True)
            .exclude(total__isnull=True)
            .exclude(total="")
            .exclude(is_error=True)
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
            emit_system_event(
                event_type="MEASUREMENT_ERROR",
                point_id=point_catchment["id"],
                title="Pulsos negativos detectados",
                message=f"Pulsos negativos ({current_pulses}) detectados. Manteniendo último total válido.",
                severity="CRITICAL",
                extra_data={"current_pulses": current_pulses, "last_total": float(last_interaction.total) if last_interaction and last_interaction.total else None, "logic": "kept_last_valid"},
            )
            fallback_val = 0
            if last_interaction and last_interaction.total:
                fallback_val = int(round(float(last_interaction.total)))

            _create_counter_reset_log(
                point_catchment_id=point_catchment["id"],
                reset_type="NEGATIVE_PULSES",
                last_pulses=float(last_interaction.pulses) if last_interaction and last_interaction.pulses is not None else 0,
                current_pulses=current_pulses,
                pulses_factor=pulses_factor,
                total_before=float(last_interaction.total) if last_interaction and last_interaction.total else None,
                total_after=fallback_val,
                passed_anti_jump=True,
                time_diff_hours=time_diff_hours,
                date_time_medition=current_dt,
            )

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

        is_reconnection = False

        if last_interaction and last_interaction.total is not None and last_interaction.total != "":
            try:
                last_total = float(last_interaction.total)
            except (ValueError, TypeError):
                last_total = None
            if last_total is not None:
                potential_new_total = current_raw_m3 + offset
                diff = potential_new_total - last_total

                # Normalizar diff por tiempo transcurrido
                time_diff_hours_real = 1.0
                if last_interaction.date_time_medition:
                    time_delta = current_dt - last_interaction.date_time_medition
                    time_diff_hours_real = max(time_delta.total_seconds() / 3600.0, 0.1)
                    time_diff_hours = time_diff_hours_real

                    # FIX REPROCESAMIENTO HISTÓRICO: Si time_diff es mucho mayor
                    # que la frecuencia del punto, el anti-salto se vuelve inútil.
                    # Usar la frecuencia como base para mantener la protección activa.
                    # ⚠️ PERO: La detección de reconexión debe usar el time_diff REAL,
                    # no el artificial de frecuencia, para evitar bloquear saltos
                    # legítimos tras desconexiones prolongadas.
                    if frecuency_minutes:
                        expected_diff_hours = float(frecuency_minutes) / 60.0
                        if time_diff_hours > expected_diff_hours * 3:
                            logger.info(
                                f"📜 Reprocesamiento histórico Punto {point_catchment['id']}: "
                                f"time_diff real={time_diff_hours:.1f}h, "
                                f"usando frecuencia={expected_diff_hours:.1f}h para anti-salto."
                            )
                            time_diff_hours = expected_diff_hours

                # ================================================================
                # DETECCIÓN DE RECONEXIÓN: Si el sensor estuvo desconectado,
                # el salto acumulado es LEGÍTIMO y NO debe bloquearse.
                # Usamos time_diff_hours_real para no perder la reconexión real
                # cuando el fix de reprocesamiento acorta artificialmente el diff.
                # ================================================================
                is_reconnection = (
                    time_diff_hours_real > reconnection_threshold
                    or last_interaction.days_not_conection > 0
                )

                # ================================================================
                # ANTI-SALTO MASIVO: Solo warning, NUNCA bloquea el total.
                #
                # HISTORIAL: El bloqueo causó efecto cascada catastrófico:
                # una vez que un total quedaba en 0 (por cualquier bug), el
                # anti-salto devolvía last_total=0 permanentemente, congelando
                # el total para SIEMPRE. Todos los puntos afectados quedaban
                # con total=0 sin posibilidad de recuperación.
                #
                # Ahora solo registramos el evento como warning y continuamos
                # con el cálculo normal del total.
                # ================================================================
                m3_per_hour = diff / time_diff_hours
                if is_reconnection and diff > 0:
                    logger.info(
                        f"🔄 RECONEXIÓN Punto {point_catchment['id']}: "
                        f"Salto de {diff:.0f} m³ en {time_diff_hours:.1f} horas. "
                        f"Aceptando nuevo total (reconexión legítima)."
                    )
                elif m3_per_hour > max_diff_m3:
                    # P1.8: BLOQUEO SEGURO sin congelar histórico.
                    # Retornamos last_total con metadata. El caller guardará
                    # el registro con is_error=True, por lo que el siguiente
                    # ciclo saltará este registro al buscar last_interaction
                    # (que ya excluye is_error=True). Recuperación automática.
                    logger.warning(
                        f"⚠️ SALTO MASIVO BLOQUEADO Punto {point_catchment['id']}: "
                        f"Salto de {diff:.0f} m³ en {time_diff_hours:.1f} horas "
                        f"({m3_per_hour:.1f} m³/h). "
                        f"Límite {max_diff_m3} m³/h. "
                        f"Manteniendo último total válido ({last_total:.0f}) "
                        f"y marcando registro como error para no congelar baseline."
                    )
                    emit_system_event(
                        event_type="MASSIVE_JUMP_BLOCKED",
                        point_id=point_catchment["id"],
                        title="Salto masivo bloqueado",
                        message=f"Salto de {diff:.0f} m³ en {time_diff_hours:.1f} horas ({m3_per_hour:.1f} m³/h). Límite {max_diff_m3} m³/h. Manteniendo total={last_total:.0f}.",
                        severity="WARNING",
                        extra_data={"diff_m3": diff, "m3_per_hour": m3_per_hour, "limit_m3_per_hour": max_diff_m3, "time_diff_hours": time_diff_hours, "blocked": True, "kept_total": last_total},
                    )

                    _create_counter_reset_log(
                        point_catchment_id=point_catchment["id"],
                        reset_type="MASSIVE_JUMP",
                        last_pulses=float(last_interaction.pulses) if last_interaction and last_interaction.pulses is not None else 0,
                        current_pulses=current_pulses,
                        pulses_factor=pulses_factor,
                        addition_before=offset,
                        total_before=last_total,
                        total_after=None,
                        passed_anti_jump=True,
                        reconnection_threshold=reconnection_threshold,
                        is_reconnection=is_reconnection,
                        days_not_connection=last_interaction.days_not_conection if last_interaction else None,
                        time_diff_hours=time_diff_hours,
                        date_time_medition=current_dt,
                    )

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
        # ✅ FIX: Detectar reset incluso durante reconexión, pero con umbral más permisivo
        # para evitar falsos positivos cuando el sensor vuelve con datos acumulados.
        if last_interaction and last_interaction.pulses is not None:
            try:
                last_pulses = float(last_interaction.pulses)
                # Fallback seguro por si last_interaction.total era None
                # Defensa: total es CharField; rechazar strings vacíos o no numéricos
                try:
                    last_total_safe = int(round(float(last_interaction.total))) if last_interaction.total is not None else 0
                except (ValueError, TypeError):
                    last_total_safe = 0

                # DETECCIÓN DE REINICIO
                # Caso 1: pulsos=0 con last_pulses>0
                # FIX CRÍTICO: Un valor 0 es casi SIEMPRE error de ingesta
                # (sensor desconectado, getter falló, valor None convertido a 0).
                # NO detectar reset a 0 — mantener total anterior para preservar
                # monotonicidad. Un reset real del contador físico se maneja
                # en reconexión (cuando el sensor vuelve con valor > 0).
                if current_pulses == 0 and last_pulses > 0:
                    logger.warning(
                        f"⚠️  Punto {point_catchment['id']}: pulsos=0 detectado. "
                        f"Tratando como error de ingesta / sensor desconectado. "
                        f"Manteniendo total anterior {last_total_safe}."
                    )
                    emit_system_event(
                        event_type="MEASUREMENT_ERROR",
                        point_id=point_catchment["id"],
                        title="Pulsos cero con histórico previo",
                        message=f"Pulsos=0 detectado con histórico previo ({last_pulses}). Manteniendo total anterior {last_total_safe}.",
                        severity="WARNING",
                        extra_data={"current_pulses": current_pulses, "last_pulses": last_pulses, "total_kept": last_total_safe, "logic": "ZERO_KEPT"},
                    )

                    _create_counter_reset_log(
                        point_catchment_id=point_catchment["id"],
                        reset_type="ZERO_KEPT",
                        last_pulses=last_pulses,
                        current_pulses=current_pulses,
                        pulses_factor=pulses_factor,
                        addition_before=offset,
                        total_before=last_total_safe,
                        total_after=last_total_safe,
                        passed_anti_jump=True,
                        reconnection_threshold=reconnection_threshold,
                        is_reconnection=False,
                        days_not_connection=last_interaction.days_not_conection if last_interaction else None,
                        time_diff_hours=time_diff_hours,
                        date_time_medition=current_dt,
                    )

                    if return_full_details:
                        return last_total_safe, {
                            "raw_pulses": current_pulses,
                            "status": "ZERO_KEPT",
                            "logic": "kept_last_valid"
                        }
                    return last_total_safe

                # Caso 2: Reinicio Real (0 < actual < anterior)
                elif 0 < current_pulses < last_pulses:
                    # PROTECCIÓN ANTI-RESET FALSO PARCIAL
                    # Si la caída es > 90% sin evidencia de desconexión,
                    # es casi siempre truncamiento del getter (ej: 91755 -> 9175).
                    # ✅ FIX: Durante reconexión usar umbral >99% (casi nunca rechazar),
                    # para permitir detectar resets reales que ocurren mientras el sensor
                    # estuvo desconectado.
                    drop_ratio = 1.0 - (current_pulses / last_pulses)
                    # ✅ FIX: Durante reconexión, tratar cualquier caída como reset real
                    # (el sensor probablemente se reinició mientras estaba offline).
                    # Solo rechazar como truncamiento cuando NO es reconexión.
                    if drop_ratio > 0.90 and not is_reconnection:
                        logger.warning(
                            f"⚠️  Punto {point_catchment['id']}: Caída de pulsos {last_pulses:.0f} -> {current_pulses:.0f} "
                            f"({drop_ratio*100:.0f}%) sin desconexión previa. "
                            f"Tratando como error de ingesta (posible truncamiento)."
                        )

                        _create_counter_reset_log(
                            point_catchment_id=point_catchment["id"],
                            reset_type="PARTIAL_REJECTED",
                            last_pulses=last_pulses,
                            current_pulses=current_pulses,
                            pulses_factor=pulses_factor,
                            addition_before=offset,
                            total_before=last_total_safe,
                            total_after=last_total_safe,
                            passed_anti_jump=True,
                            reconnection_threshold=reconnection_threshold,
                            is_reconnection=False,
                            days_not_connection=last_interaction.days_not_conection if last_interaction else None,
                            time_diff_hours=time_diff_hours,
                            date_time_medition=current_dt,
                        )

                        if return_full_details:
                            return last_total_safe, {
                                "raw_pulses": current_pulses,
                                "status": "PARTIAL_WITHOUT_DISCONNECT",
                                "logic": "kept_last_valid"
                            }
                        return last_total_safe

                    logger.warning(
                        f"🚨 RESET REAL DETECTADO Punto {point_catchment['id']}: {last_pulses} -> {current_pulses}"
                    )

                    # Calcular corrección
                    amount_to_add = (last_pulses * float(pulses_factor)) / 1000.0
                    addition_before = offset

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

                    total_after = int(round((current_pulses * float(pulses_factor)) / 1000.0 + offset))

                    emit_system_event(
                        event_type="COUNTER_RESET",
                        point_id=point_catchment["id"],
                        title="Reset de contador detectado",
                        message=f"Reset real detectado: {last_pulses} -> {current_pulses}. Addition ajustado en {amount_to_add:.2f} m³.",
                        severity="CRITICAL",
                        extra_data={"last_pulses": last_pulses, "current_pulses": current_pulses, "amount_to_add": amount_to_add, "addition_before": addition_before, "addition_after": offset, "total_before": last_total_safe, "total_after": total_after},
                    )

                    _create_counter_reset_log(
                        point_catchment_id=point_catchment["id"],
                        reset_type="PARTIAL",
                        last_pulses=last_pulses,
                        current_pulses=current_pulses,
                        pulses_factor=pulses_factor,
                        addition_before=addition_before,
                        amount_to_add=amount_to_add,
                        addition_after=offset,
                        total_before=last_total_safe,
                        total_after=total_after,
                        passed_anti_jump=True,
                        reconnection_threshold=reconnection_threshold,
                        is_reconnection=is_reconnection,
                        days_not_connection=last_interaction.days_not_conection if last_interaction else None,
                        time_diff_hours=time_diff_hours,
                        date_time_medition=current_dt,
                    )

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
                .exclude(is_error=True)
                .order_by("-date_time_medition")
                .first()
            )
        else:
            prev = (
                InteractionDetail.objects.filter(
                    catchment_point_id=point_catchment["id"],
                )
                .exclude(total__isnull=True)
                .exclude(is_error=True)
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
            .exclude(is_error=True)
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
                .exclude(is_error=True)
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



