"""
Motor de Evaluación de Fórmulas Dinámicas

Reemplaza flow.py, total.py, nivel.py con un sistema unificado
que evalúa fórmulas configurables desde la base de datos.
"""

import logging
import re
from datetime import datetime
from typing import Dict, Any, Optional

import pytz
from django.utils import timezone

from api.core.services.config_service import ConfigService
from api.telemetry.models import TelemetryRecord, CatchmentPoint

logger = logging.getLogger(__name__)

# Zona horaria de Chile
CHILE_TZ = pytz.timezone("America/Santiago")


class FormulaEngine:
    """
    Motor de evaluación de fórmulas dinámicas.
    
    Soporta referencias a:
    - {var_code}: Otras variables del punto
    - {config.code}: Configuración del punto
    - {system.key}: SystemConfiguration
    - {prev.var_code}: Valores anteriores
    - {time.*}: Contexto temporal
    """
    
    def __init__(self, point_id: int):
        """
        Inicializa el motor para un punto específico.
        
        Args:
            point_id: ID del CatchmentPoint
        """
        self.point_id = point_id
        self.point = None
        self.config = {}
        self.system = {}
        self.variables = {}
        self.prev = {}
        self.time = {}
        self._load_context()
    
    def _load_context(self):
        """Carga todas las fuentes de datos para fórmulas."""
        try:
            # 1. Cargar punto
            self.point = CatchmentPoint.objects.select_related(
                'configuration_scheme'
            ).prefetch_related(
                'configuration_values__field'
            ).get(id=self.point_id)
            
            # 2. Configuraciones del punto
            self.config = self.point.get_config_dict()
            
            # 3. Configuraciones del sistema (cacheadas)
            # Se cargan bajo demanda en _replace_tokens
            
            # 4. Variables del punto (para referencias cruzadas)
            # Se cargan bajo demanda cuando se evalúa
            
            # 5. Valores previos (se cargan bajo demanda)
            
            # 6. Contexto temporal (se calcula bajo demanda)
            
        except CatchmentPoint.DoesNotExist:
            logger.error(f"Punto {self.point_id} no encontrado")
            raise
    
    def _load_previous_values(self, current_timestamp: datetime) -> Dict[str, Any]:
        """
        Carga valores anteriores del último registro de telemetría.
        
        Args:
            current_timestamp: Timestamp del registro actual
        
        Returns:
            Dict con valores anteriores
        """
        try:
            last_record = (
                TelemetryRecord.objects.filter(
                    point_id=self.point_id,
                    timestamp__lt=current_timestamp
                )
                .order_by('-timestamp')
                .first()
            )
            
            if last_record:
                return last_record.data.copy()
            return {}
        except Exception as e:
            logger.warning(f"Error cargando valores previos: {e}")
            return {}
    
    def _load_time_context(
        self, 
        current_timestamp: datetime, 
        previous_timestamp: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calcula contexto temporal para fórmulas.
        
        Args:
            current_timestamp: Timestamp actual
            previous_timestamp: Timestamp anterior (opcional)
        
        Returns:
            Dict con valores temporales
        """
        context = {}
        
        try:
            if previous_timestamp:
                diff = (current_timestamp - previous_timestamp).total_seconds()
                context['diff_seconds'] = diff
                context['diff_minutes'] = diff / 60
                context['diff_hours'] = diff / 3600
            else:
                context['diff_seconds'] = 0
                context['diff_minutes'] = 0
                context['diff_hours'] = 0
            
            # Información del timestamp actual
            if current_timestamp.tzinfo is None:
                current_tz = CHILE_TZ.localize(current_timestamp)
            else:
                current_tz = current_timestamp.astimezone(CHILE_TZ)
            
            context['hour'] = current_tz.hour
            context['minute'] = current_tz.minute
            context['day'] = current_tz.day
            context['month'] = current_tz.month
            context['year'] = current_tz.year
            
        except Exception as e:
            logger.warning(f"Error calculando contexto temporal: {e}")
        
        return context
    
    def evaluate(
        self, 
        formula: str, 
        current_values: Dict[str, Any],
        current_timestamp: Optional[datetime] = None
    ) -> float:
        """
        Evalúa una fórmula con el contexto actual.
        
        Args:
            formula: Fórmula con tokens {var}, {config.x}, {system.x}, etc.
            current_values: Valores actuales de variables
            current_timestamp: Timestamp del registro actual (opcional)
        
        Returns:
            Resultado numérico
        """
        if not formula:
            return 0.0
        
        try:
            # Cargar valores previos si hay timestamp
            if current_timestamp:
                self.prev = self._load_previous_values(current_timestamp)
                # Obtener timestamp anterior del último registro
                last_record = (
                    TelemetryRecord.objects.filter(
                        point_id=self.point_id,
                        timestamp__lt=current_timestamp
                    )
                    .order_by('-timestamp')
                    .first()
                )
                prev_timestamp = last_record.timestamp if last_record else None
                self.time = self._load_time_context(current_timestamp, prev_timestamp)
            
            # Reemplazar tokens
            processed = self._replace_tokens(formula, current_values)
            
            # Validar que solo contenga números, operadores y espacios
            if not re.match(r'^[0-9\.\+\-\*\/\(\)\s]+$', processed):
                logger.warning(
                    f"Fórmula procesada contiene caracteres inválidos: {processed}"
                )
                return 0.0
            
            # Construir namespace seguro
            namespace = {
                '__builtins__': {},
                'abs': abs,
                'min': min,
                'max': max,
                'round': round,
                'pow': pow,
            }
            
            # Evaluar de forma segura
            result = eval(processed, namespace)
            
            # Validar resultado
            if not isinstance(result, (int, float)):
                logger.warning(f"Resultado de fórmula no es numérico: {result}")
                return 0.0
            
            return float(result)
            
        except ZeroDivisionError:
            logger.warning(f"División por cero en fórmula: {formula}")
            return 0.0
        except SyntaxError as e:
            logger.error(f"Error de sintaxis en fórmula '{formula}': {e}")
            return 0.0
        except Exception as e:
            logger.error(f"Error evaluando fórmula '{formula}': {e}", exc_info=True)
            return 0.0
    
    def _replace_tokens(self, formula: str, current_values: Dict[str, Any]) -> str:
        """
        Reemplaza todos los tokens por valores.
        
        Args:
            formula: Fórmula original
            current_values: Valores actuales de variables
        
        Returns:
            Fórmula con tokens reemplazados
        """
        processed = formula
        
        # 1. {var_code} -> valor de variable actual
        for match in re.findall(r'\{([a-zA-Z0-9_]+)\}', processed):
            if match in current_values:
                val = current_values[match]
                try:
                    processed = processed.replace(f'{{{match}}}', str(float(val)))
                except (ValueError, TypeError):
                    processed = processed.replace(f'{{{match}}}', '0')
        
        # 2. {config.code} -> valor de configuración del punto
        for match in re.findall(r'\{config\.([a-zA-Z0-9_]+)\}', processed):
            val = self.config.get(match, 0)
            try:
                processed = processed.replace(f'{{config.{match}}}', str(float(val)))
            except (ValueError, TypeError):
                processed = processed.replace(f'{{config.{match}}}', '0')
        
        # 3. {system.key} -> valor de SystemConfiguration
        for match in re.findall(r'\{system\.([a-zA-Z0-9_.]+)\}', processed):
            val = ConfigService.get(match, 0)
            try:
                processed = processed.replace(f'{{system.{match}}}', str(float(val)))
            except (ValueError, TypeError):
                processed = processed.replace(f'{{system.{match}}}', '0')
        
        # 4. {prev.var_code} -> valor anterior
        for match in re.findall(r'\{prev\.([a-zA-Z0-9_]+)\}', processed):
            val = self.prev.get(match, 0)
            try:
                processed = processed.replace(f'{{prev.{match}}}', str(float(val)))
            except (ValueError, TypeError):
                processed = processed.replace(f'{{prev.{match}}}', '0')
        
        # 5. {time.*} -> contexto temporal
        for match in re.findall(r'\{time\.([a-zA-Z0-9_]+)\}', processed):
            val = self.time.get(match, 0)
            try:
                processed = processed.replace(f'{{time.{match}}}', str(float(val)))
            except (ValueError, TypeError):
                processed = processed.replace(f'{{time.{match}}}', '0')
        
        return processed
    
    def get_formula_for_variable(
        self, 
        variable: 'CoreVariable',
        current_values: Dict[str, Any],
        current_timestamp: Optional[datetime] = None
    ) -> Optional[str]:
        """
        Obtiene la fórmula a usar para una variable.
        
        Prioridad:
        1. CoreVariable.formula (si existe)
        2. VariableType.default_formula (si existe)
        3. None (no hay fórmula)
        
        Args:
            variable: Instancia de CoreVariable
            current_values: Valores actuales
            current_timestamp: Timestamp actual
        
        Returns:
            Fórmula a usar o None
        """
        # Prioridad 1: Fórmula específica de la variable
        if variable.formula:
            return variable.formula
        
        # Prioridad 2: Fórmula por defecto del tipo
        if variable.type_definition and variable.type_definition.default_formula:
            return variable.type_definition.default_formula
        
        return None
    
    def process_variable(
        self,
        variable: 'CoreVariable',
        raw_value: Any,
        current_values: Dict[str, Any],
        current_timestamp: Optional[datetime] = None
    ) -> float:
        """
        Procesa una variable usando su fórmula configurada.
        
        Args:
            variable: Instancia de CoreVariable
            raw_value: Valor crudo del proveedor
            current_values: Valores actuales de todas las variables
            current_timestamp: Timestamp del registro
        
        Returns:
            Valor procesado
        """
        # Agregar valor crudo a current_values si no está
        if variable.internal_code and variable.internal_code not in current_values:
            current_values[variable.internal_code] = raw_value
        
        # Obtener fórmula
        formula = self.get_formula_for_variable(variable, current_values, current_timestamp)
        
        if not formula:
            # Sin fórmula: aplicar scale_factor y offset directamente
            try:
                value = float(raw_value) if raw_value is not None else 0.0
                return (value * variable.scale_factor) + variable.offset
            except (ValueError, TypeError):
                return 0.0
        
        # Evaluar fórmula
        return self.evaluate(formula, current_values, current_timestamp)
    
    # ====================================================================
    # MÉTODOS ESTÁTICOS DE COMPATIBILIDAD (Reemplazan procesadores legacy)
    # ====================================================================
    
    @staticmethod
    def calculate_total_m3(
        pulses_factor, value, point_catchment, variable_id=None, return_full_details=False
    ):
        """
        Calcular total en m3 usando la fórmula: ((pulsos * factor) / 1000) + offset
        
        Reemplaza: total.total_m3()
        
        LÓGICA DE RESET:
        - Compara el valor actual (pulsos) con el último registrado.
        - Si value < last_value: Detecta reinicio.
        - Acumula el valor perdido en profile.addition (offset).
        - Crea Notificación.
        """
        try:
            from django.db import transaction
            from django.utils import timezone
            from api.telemetry.models import ProfileDataConfigCatchment
            from api.notifications.models import Notification
            
            if not pulses_factor or pulses_factor <= 0:
                pulses_factor = ConfigService.get_float(
                    "telemetry.pulses_factor_default", 1000
                )
                logger.warning(
                    "pulses_factor no válido, usando valor por defecto: %s", pulses_factor
                )
            
            try:
                current_pulses = float(value)
            except (ValueError, TypeError):
                current_pulses = 0.0
            
            # Buscar último registro válido
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
            
            # Pulsos negativos = Error de ingesta
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
            
            # Obtener offset del perfil
            profile = ProfileDataConfigCatchment.objects.filter(
                point_catchment_id=point_catchment["id"]
            ).first()
            
            offset = 0
            if profile:
                offset = profile.addition or 0
            
            # Validación anti-salto masivo
            max_diff_m3_per_hour = ConfigService.get_float(
                "telemetry.max_diff_m3_per_hour", 500
            )
            
            if last_total is not None:
                potential_new_total = current_raw_m3 + offset
                diff = potential_new_total - last_total
                
                if diff > max_diff_m3_per_hour:
                    logger.warning(
                        f"🚨 SALTO MASIVO DETECTADO Punto {point_catchment['id']}: "
                        f"Salto de {diff:.0f} m³ ({last_total:.0f} → {potential_new_total:.0f}). "
                        f"Manteniendo último total válido para evitar corrupción."
                    )
                    if return_full_details:
                        return int(round(last_total)), {
                            "raw_pulses": current_pulses,
                            "status": "MASSIVE_JUMP_BLOCKED",
                            "diff_detected": diff,
                            "logic": "kept_last_valid",
                        }
                    return int(round(last_total))
            
            # Lógica de reset
            if last_pulses is not None:
                try:
                    # Glitch de red/sensor (valor 0)
                    if current_pulses == 0 and last_pulses > 0:
                        logger.warning(
                            f"⚠️ Posible Glitch (0) en Punto {point_catchment['id']}. Ignorando valor para evitar reinicio falso."
                        )
                        return int(
                            round((last_pulses * float(pulses_factor)) / 1000.0 + offset)
                        )
                    
                    # Reinicio Real (0 < actual < anterior)
                    elif 0 < current_pulses < last_pulses:
                        logger.warning(
                            f"🚨 RESET REAL DETECTADO Punto {point_catchment['id']}: {last_pulses} -> {current_pulses}"
                        )
                        
                        amount_to_add = (last_pulses * float(pulses_factor)) / 1000.0
                        
                        with transaction.atomic():
                            if profile:
                                profile.addition = offset + int(amount_to_add)
                                profile.save(update_fields=["addition", "modified"])
                                offset = profile.addition
                            else:
                                logger.error(
                                    f"Cannot update addition: ProfileDataConfigCatchment not found for point {point_catchment['id']}"
                                )
                            
                            Notification.objects.create(
                                point_catchment_id=point_catchment["id"],
                                title="Reinicio de Contador Detectado",
                                message=f"Se detectó un reinicio en el contador totalizador. Valor anterior: {int(last_pulses)}, Valor actual: {int(current_pulses)}. El sistema ha ajustado la contabilidad automáticamente.",
                                type_variable="TOTALIZADO",
                                type_notification="WARNING",
                                value=int(current_pulses),
                                is_active=True,
                                start_date=timezone.now().date(),
                            )
                
                except Exception as e:
                    logger.error(f"Error en lógica de reset: {e}")
            
            # Cálculo final
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
            logger.error(f"Error en calculate_total_m3: {e}")
            if return_full_details:
                return 0, {"error": str(e), "status": "ERROR"}
            return 0
    
    @staticmethod
    def total_hour(total, point_catchment, current_dt=None):
        """
        Diferencia contra la medición anterior.
        
        Reemplaza: total.total_hour()
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
            
            if diff < 0:
                logger.warning(
                    f"Diff negativa ({diff}) en Punto {point_catchment['id']}. Clamp a 0."
                )
                return 0
            
            # Anti-reset rule
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
    
    @staticmethod
    def total_day(point_catchment, current_dt=None, current_total=None):
        """
        Acumulado del día = Total actual - Primer total del día
        
        Reemplaza: total.total_day()
        """
        try:
            from django.utils import timezone
            
            if current_dt:
                dia = current_dt.date()
            else:
                dia = timezone.now().date()
            
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
            
            if current_total is not None:
                total_actual = float(current_total)
            else:
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
            
            diff_dia = total_actual - primer_total
            
            if diff_dia < 0:
                logger.warning(
                    f"Diff día negativo ({diff_dia}) en Punto {point_catchment['id']}. Clamp a 0."
                )
                return 0
            
            max_diff_m3_per_day = ConfigService.get_float(
                "telemetry.max_diff_m3_per_day", 10000
            )
            if diff_dia > max_diff_m3_per_day:
                logger.warning(
                    "🚨 DIFF DÍA EXCESIVA (%.0f > %.0f) en Punto %s. "
                    "Probable error de datos. Clamp a 0.",
                    diff_dia,
                    max_diff_m3_per_day,
                    point_catchment["id"],
                )
                return 0
            
            return int(round(diff_dia))
        
        except Exception as e:
            logger.error(f"Error total_day para punto {point_catchment['id']}: {e}")
            return 0
    
    @staticmethod
    def instantaneous_flow(value, convert_to_lt, scale_divisor=None):
        """
        Calculate the instantaneous flow based on the given value.
        
        Reemplaza: flow.instantaneous_flow()
        """
        try:
            value = float(value)
            if value < 1.0:
                return 0.0
            
            if scale_divisor and isinstance(scale_divisor, (int, float)) and scale_divisor > 0:
                value = value / float(scale_divisor)
            
            if convert_to_lt:
                value /= 3.6
            
            max_precision = ConfigService.get_float("telemetry.max_value_precision", 1000)
            if abs(value) >= max_precision:
                return 0.0
            return float(f"{value:.2f}")
        except (ValueError, TypeError) as e:
            logger.error(f"Error en instantaneous_flow: {e}")
            return 0.0
    
    @staticmethod
    def average_flow(
        point_catchment, total, date_lg, exclude_id=None, current_logger_dt=None
    ):
        """
        Caudal promedio (L/s) = ((total_actual - total_anterior) / Δt_seg) * 1000
        
        Reemplaza: flow.average_flow()
        """
        try:
            if not isinstance(point_catchment, dict) or "id" not in point_catchment:
                return 0.0
            if not isinstance(total, (int, float)):
                return 0.0
            if not isinstance(date_lg, datetime):
                return 0.0
            
            chile_tz = pytz.timezone("America/Santiago")
            
            if date_lg.tzinfo is None:
                curr_ts = chile_tz.localize(date_lg)
            else:
                curr_ts = date_lg.astimezone(chile_tz)
            
            query = TelemetryRecord.objects.filter(
                point_id=point_catchment["id"], timestamp__lt=date_lg
            )
            if exclude_id:
                query = query.exclude(pk=exclude_id)
            
            get_last = query.order_by("-timestamp").first()
            
            if not get_last or get_last.data.get("total") is None:
                return 0.0
            
            time_difference = 0.0
            last_logger_ts = get_last.metadata.get("last_logger_timestamp")
            
            if current_logger_dt and isinstance(current_logger_dt, datetime) and last_logger_ts:
                try:
                    if current_logger_dt.tzinfo is None:
                        c_log = chile_tz.localize(current_logger_dt)
                    else:
                        c_log = current_logger_dt.astimezone(chile_tz)
                    
                    if isinstance(last_logger_ts, str):
                        try:
                            p_log_dt = datetime.strptime(
                                last_logger_ts, "%Y-%m-%dT%H:%M:%S"
                            )
                            p_log = chile_tz.localize(p_log_dt)
                        except ValueError:
                            p_log = None
                    elif isinstance(last_logger_ts, datetime):
                        p_log = last_logger_ts.astimezone(chile_tz)
                    else:
                        p_log = None
                    
                    if p_log:
                        diff_log = (c_log - p_log).total_seconds()
                        if diff_log > 0:
                            time_difference = diff_log
                except Exception as e:
                    logger.warning(f"Warning: Error calculating logger diff: {e}")
            
            if time_difference <= 0:
                prev_ts = get_last.timestamp
                if prev_ts.tzinfo is None:
                    prev_ts = chile_tz.localize(prev_ts)
                else:
                    prev_ts = prev_ts.astimezone(chile_tz)
                
                time_difference = (curr_ts - prev_ts).total_seconds()
            
            if time_difference <= 0:
                return 0.0
            
            # Validaciones anti-disparo
            max_time_gap_hours = ConfigService.get_float("telemetry.max_time_gap_hours", 2)
            if time_difference > (max_time_gap_hours * 3600):
                logger.info(
                    "⚠️ Punto %s: Gap de tiempo muy grande (%.1fh > %.1fh) - Caudal = 0",
                    point_catchment["id"],
                    time_difference / 3600,
                    max_time_gap_hours,
                )
                return 0.0
            
            days_not_conn = get_last.metadata.get("days_not_connection", 0)
            if days_not_conn and days_not_conn > 0:
                logger.info(
                    f"⚠️ Punto {point_catchment['id']}: Reconexión detectada "
                    f"(días sin conexión anterior: {days_not_conn}) - Caudal = 0"
                )
                return 0.0
            
            last_total = float(get_last.data.get("total", 0))
            diff_cubics = float(total) - last_total
            
            if diff_cubics < 0:
                diff_cubics = float(total)
            
            if diff_cubics <= 0:
                return 0.0
            
            max_diff_m3_per_hour = ConfigService.get_float(
                "telemetry.max_diff_m3_per_hour", 500
            )
            consumption_per_hour = (diff_cubics / time_difference) * 3600
            if consumption_per_hour > max_diff_m3_per_hour:
                logger.warning(
                    "🚨 Punto %s: Consumo por hora excesivo (%.0f m³/h > %.0f) - Caudal = 0",
                    point_catchment["id"],
                    consumption_per_hour,
                    max_diff_m3_per_hour,
                )
                return 0.0
            
            value = round((diff_cubics / time_difference) * 1000.0, 2)
            
            max_flow_ls = ConfigService.get_float("telemetry.max_flow_ls", 150.0)
            if value > max_flow_ls:
                logger.warning(
                    "🚨 Punto %s: Caudal excesivo (%.2f L/s > %.2f) - Caudal = 0",
                    point_catchment["id"],
                    value,
                    max_flow_ls,
                )
                return 0.0
            
            max_precision = ConfigService.get_float("telemetry.max_value_precision", 1000)
            if abs(value) >= max_precision:
                return 0.0
            
            return value
        
        except Exception as e:
            logger.error(
                f"Error in average_flow for point {point_catchment.get('id')}: {str(e)}"
            )
            return 0.0
    
    @staticmethod
    def nivel_mt(value, base, point_catchment_id=None, position=None):
        """
        Calcular nivel en metros
        
        Reemplaza: nivel.nivel_mt()
        """
        try:
            calculate = float(value) / float(base)
            
            if (calculate < 0 or calculate == 0) and point_catchment_id:
                logger.warning(
                    f"Nivel {'negativo' if calculate < 0 else 'cero'} detectado. No se usará corrección para evitar perpetuar datos erróneos."
                )
                return "00.00"
            
            if calculate < 0 or abs(calculate) >= 1000:
                return "00.00"
            return "{:.2f}".format(calculate)
        except (ValueError, ZeroDivisionError) as e:
            logger.error(f"Error en nivel_mt: {e}")
            return "00.00"
    
    @staticmethod
    def water_table(value, position):
        """
        Calcular nivel freático
        
        Reemplaza: nivel.water_table()
        """
        try:
            if not position or float(position if position else 0) <= 0:
                logger.warning(f"Error: posición de nivel (d3) no válida: {position}")
                return "00.00"
            
            calculate = float(position) - float(value)
            if calculate < 0 or abs(calculate) >= 1000:
                return "00.00"
            return "{:.2f}".format(calculate)
        except (ValueError, TypeError) as e:
            logger.error(f"Error en water_table: {e}")
            return "00.00"