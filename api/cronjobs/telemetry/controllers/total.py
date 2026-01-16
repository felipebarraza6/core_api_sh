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

    # LÓGICA DE RESET

        # -- NUEVA LÓGICA: Usar ProfileDataConfigCatchment para el offset/addition --
        from api.core.models import ProfileDataConfigCatchment
        
        profile = ProfileDataConfigCatchment.objects.filter(point_catchment_id=point_catchment["id"]).first()
        
        # Recuperar offset actual del perfil (si existe)
        offset = 0
        if profile:
            offset = profile.addition or 0
        
        # NOTE: Legacy fallback to variable.addition removed as per requirement.
        # offset remains 0 if profile is not found.

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


def total_day(point_catchment, current_dt=None, current_diff=None):
    """
    Acumulado del día = Total actual - Primer total del día
    """
    try:
        if current_dt:
            dia = current_dt.date()
        else:
            dia = timezone.now().date()
        
        # Primer total del día
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
        total_actual = float(current_diff) if current_diff else 0 # Wait, current_diff argument is ambiguous in call signature vs usage
        
        # REVISAR: total_day se llama con (point, None, created_register["total_diff"]) en los cronjobs?
        # NO, se llama con total_today_diff = total_day(point, None, total_diff)??
        # ERROR en lógica anterior: usaba DB para buscar "ultimo_total_dia", pero estamos CALCULANDO el último
        # Debemos usar el 'total' que acabamos de calcular, pero no lo pasamos como argumento.
        # En los cronjobs: created_register["total_today_diff"] = total_day(point_catchment, None, created_register["total_diff"])
        # El 3er argumento es 'current_diff' (consumo hora), NO el total acumulado.
        
        # CORRECCIÓN: Necesitamos el TOTAL ACUMULADO ACTUAL para hacer (Total Actual - Primer Total Día).
        # Como no lo recibimos, debemos buscarlo o cambiar la firma.
        # OPCIÓN SEGURA: Sumar los 'total_diff' del día. Es más robusto si 'total' tiene saltos.
        
        # Vamos a sumar los total_diff del día + el actual
        suma_previos = (
            InteractionDetail.objects.filter(
                catchment_point_id=point_catchment["id"],
                created__date=dia,
            ).exclude(total_diff__isnull=True)
            .values_list('total_diff', flat=True)
        )
        accum = sum([float(x) for x in suma_previos])
        
        # Sumar el diff actual que se está procesando (si no se ha guardado aun en DB)
        try:
            current_d = float(current_diff) if current_diff is not None else 0
        except:
            current_d = 0
            
        return int(round(accum + current_d))
        
    except Exception as e:
        logger.error(f"Error total_day optimizado para punto {point_catchment['id']}: {e}")
        try:
            return int(float(current_diff)) if current_diff else 0
        except:
            return 0



