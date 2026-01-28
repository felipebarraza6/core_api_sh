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

        # -- NUEVA LÓGICA: Usar ProfileDataConfigCatchment para el offset/addition --
        from api.core.models import ProfileDataConfigCatchment
        
        profile = ProfileDataConfigCatchment.objects.filter(point_catchment_id=point_catchment["id"]).first()
        
        # Recuperar offset actual del perfil (si existe)
        offset = 0
        if profile:
            offset = profile.addition or 0
        
        # NOTE: Legacy fallback to variable.addition removed as per requirement.
        # offset remains 0 if profile is not found.

        # ====================================================================
        # VALIDACIÓN ANTI-SALTO MASIVO (NORMAlIZADA POR TIEMPO)
        # ====================================================================
        MAX_DIFF_M3_PER_HOUR = 500  # Consumo máximo razonable por hora
        
        if last_interaction and last_interaction.total is not None:
            last_total = float(last_interaction.total)
            potential_new_total = current_raw_m3 + offset
            diff = potential_new_total - last_total
            
            # Normalizar diff por tiempo transcurrido
            time_diff_hours = 1.0 # Default fallback
            if last_interaction.date_time_medition:
                now = timezone.now()
                # Usar la hora del registro si la tenemos, si no, usar now
                time_delta = now - last_interaction.date_time_medition
                time_diff_hours = max(time_delta.total_seconds() / 3600.0, 1.0) # Al menos 1 hora para evitar división por cero
            
            m3_per_hour = diff / time_diff_hours

            # Si el salto es > 500 m³ por hora, es sospechoso
            if m3_per_hour > MAX_DIFF_M3_PER_HOUR:
                logger.warning(
                    f"🚨 SALTO MASIVO DETECTADO Punto {point_catchment['id']}: "
                    f"Salto de {diff:.0f} m³ en {time_diff_hours:.1f} horas ({m3_per_hour:.1f} m³/h). "
                    f"Límite {MAX_DIFF_M3_PER_HOUR} m³/h. Manteniendo último total válido."
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
                # Caso 1: Glitch de red/sensor (valor 0)
                if current_pulses == 0 and last_pulses > 0:
                     logger.warning(
                         f"⚠️ Posible Glitch (0) en Punto {point_catchment['id']}. Ignorando valor para evitar reinicio falso."
                     )
                     return int(round((last_pulses * float(pulses_factor)) / 1000.0 + offset))

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
                        offset = profile.addition # Actualizar offset local
                    else:
                        logger.error(f"Cannot update addition: ProfileDataConfigCatchment not found for point {point_catchment['id']}")

                    # Crear Notificación
                    NotificationsCatchment.objects.create(
                        point_catchment_id=point_catchment["id"],
                        title="Reinicio de Contador Detectado",
                        message=f"Se detectó un reinicio en el contador totalizador. Valor anterior: {int(last_pulses)}, Valor actual: {int(current_pulses)}. El sistema ha ajustado la contabilidad automáticamente.",
                        type_variable="TOTALIZADO",
                        type_notification="WARNING", # Advertencia
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
                    created__lt=current_dt,
                )
                .exclude(total__isnull=True)
                .order_by("-created", "-id")
                .first()
            )
        else:
            prev = (
                InteractionDetail.objects.filter(
                    catchment_point_id=point_catchment["id"],
                )
                .exclude(total__isnull=True)
                .order_by("-created", "-id")
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
            
        # ✅ ANTI-RESET RULE: Si la diferencia es absurda (> 500 m3/h), asumimos restauración de contador
        if diff > 500:
             logger.warning(
                 f"🚨 DIFF EXCESIVA ({diff} > 500) en Punto {point_catchment['id']}. "
                 "Posible restauración de contador (0 -> Valor Real). Clamp a 0 para no alterar histórico."
             )
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
                created__date=dia,
            )
            .exclude(total__isnull=True)
            .order_by("created", "id")
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
                    created__date=dia,
                )
                .exclude(total__isnull=True)
                .order_by("-created", "-id")
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
        
        # Validación anti-salto: No puede ser > 10,000 m³
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



