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
        self.eval_stack = set()  # For cycle detection
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
            # Pre-cargar para lookup eficiente durante recursión
            from api.telemetry.models import CoreVariable
            self.variables = {
                v.internal_code: v 
                for v in CoreVariable.objects.filter(point_id=self.point_id)
                if v.internal_code
            }
            
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
            
            # Reemplazar tokens (con timestamp para recursión)
            processed = self._replace_tokens(formula, current_values, current_timestamp)
            
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
    
    def _replace_tokens(self, formula: str, current_values: Dict[str, Any], current_timestamp: Optional[datetime] = None) -> str:
        """
        Reemplaza todos los tokens por valores. Soporata recursión.
        
        Args:
            formula: Fórmula original
            current_values: Valores actuales de variables
            current_timestamp: Timestamp actual (para recursión)
        
        Returns:
            Fórmula con tokens reemplazados
        """
        processed = formula
        
        # 1. {var_code} -> valor de variable actual
        for match in re.findall(r'\{([a-zA-Z0-9_]+)\}', processed):
            if match in current_values:
                # Caso 1: Valor ya calculado
                val = current_values[match]
            elif match in self.variables:
                # Caso 2: Variable existe pero no calculada -> Recursión
                if match in self.eval_stack:
                    logger.error(f"Ciclo detectado para variable '{match}' en punto {self.point_id}")
                    val = 0
                else:
                    # Calcular recursivamente
                    try:
                        target_var = self.variables[match]
                        # Necesitamos el raw_value de esa variable. 
                        # Si es virtual, raw=0 (o None). Si es sensor, debería estar en inputs.
                        # Asumimos que si no está en current_values es porque:
                        # a) Es virtual dependiente
                        # b) Es un sensor que no llegó (usar 0)
                        
                        self.eval_stack.add(match)
                        val = self.process_variable(
                            target_var, 
                            0, # Raw value placeholder (revisar si podemos obtenerlo)
                            current_values, 
                            current_timestamp
                        )
                        self.eval_stack.remove(match)
                        
                        # Guardar result para futuros usos en esta misma cadena
                        current_values[match] = val
                    except Exception as e:
                        logger.error(f"Error en recursión para '{match}': {e}")
                        if match in self.eval_stack:
                            self.eval_stack.remove(match)
                        val = 0
            else:
                # Caso 3: Variable no existe
                val = 0

            # Reemplazo seguro
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
        1. Assignment temporal vigente (FormulaAssignment)
        2. Fórmula legacy directa (CoreVariable.formula)
        3. Fórmula por defecto del tipo
        
        Args:
            variable: Instancia de CoreVariable
            current_values: Valores actuales
            current_timestamp: Timestamp actual
        
        Returns:
            String con la expresión matemática o None
        """
        # Prioridad 1: Asignación Dinámica Temporal
        formula_def = variable.get_effective_formula(current_timestamp)
        if formula_def:
            return formula_def.expression

        # Prioridad 2: Fórmula legacy
        if variable.formula:
            return variable.formula
        
        # Prioridad 3: Fórmula por defecto del tipo
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
        Procesa una variable usando su fórmula y reglas configuradas.
        Pipeline:
        1. Pre-Processing Rules (Validación/Limpieza Raw)
        2. Fórmula de Cálculo
        3. Post-Processing Rules (Validación Resultado/Reset/Eventos)
        """
        # Contexto base para reglas
        context = {
            'raw_value': raw_value,
            'current_values': current_values,
            'timestamp': current_timestamp,
            'engine': self
        }

        # 1. Obtener reglas vigentes
        active_rules = variable.get_effective_rules(current_timestamp)
        
        # 2. Pre-Processing
        # TODO: Implementar lógica de modificación de raw_value si es necesario
        # Por ahora solo validaciones que podrían lanzar excepción o retornar default
        
        # Agregar valor crudo a current_values si no está
        if variable.internal_code and variable.internal_code not in current_values:
            current_values[variable.internal_code] = raw_value
        
        # Inject standard 'value' token for current variable raw value
        current_values['value'] = raw_value

        # 3. Cálculo (Fórmula)
        result = 0.0
        formula = self.get_formula_for_variable(variable, current_values, current_timestamp)
        
        if not formula:
            # Sin fórmula: aplicar scale_factor y offset directamente (Legacy fallback)
            try:
                calc_val = float(raw_value) if raw_value is not None else 0.0
                result = (calc_val * variable.scale_factor) + variable.offset
            except (ValueError, TypeError):
                result = 0.0
        else:
            # Evaluar fórmula
            result = self.evaluate(formula, current_values, current_timestamp)

        # 4. Post-Processing (Reglas)
        final_result = result
        
        for rule, params in active_rules:
            try:
                # Merge params with defaults
                effective_params = rule.default_parameters.copy()
                effective_params.update(params)
                
                if rule.rule_type == 'MAX_DIFF':
                    # Diff respecto a valor anterior
                    prev_val = self.get_previous_value(
                        self.point_id, variable.internal_code, current_timestamp=current_timestamp
                    )
                    if prev_val is not None:
                        diff = abs(final_result - float(prev_val))
                        limit = float(effective_params.get('limit', 1000))
                        action = effective_params.get('action', 'CLAMP') # CLAMP, REJECT
                        
                        if diff > limit:
                            logger.warning(
                                f"MAX_DIFF excedido en {variable.internal_code}: {diff} > {limit}. Action: {action}"
                            )
                            if action == 'CLAMP':
                                final_result = float(prev_val) # Clamp to previous
                            elif action == 'REJECT':
                                # Throw error or return None? For now, clamp to prev creates continuity
                                final_result = float(prev_val)

                elif rule.rule_type == 'RESET_DETECTOR':
                    # Detectar si el valor cayó significativamente (reinicio de contador)
                    prev_val = self.get_previous_value(
                        self.point_id, variable.internal_code, current_timestamp=current_timestamp
                    )
                    if prev_val is not None:
                         curr = float(final_result)
                         prev = float(prev_val)
                         
                         # Si el valor actual es menor que el anterior Y la diferencia es grande
                         if curr < prev:
                             # Es un reset potencial.
                             # trigger notification?
                             # Logic logic imported from calculate_total_m3 legacy
                             logger.warning(f"Posible Reset en {variable.internal_code}: {prev} -> {curr}")
                             # Aquí podríamos llamar a una lógica de ajuste de offset si fuera necesario
                             # Por ahora solo log y notificación
                             pass
                    
                elif rule.rule_type == 'MIN_VALUE':
                     limit = float(effective_params.get('limit', 0))
                     if final_result < limit:
                         final_result = limit
                         
                elif rule.rule_type == 'MAX_VALUE':
                     limit = float(effective_params.get('limit', 999999))
                     if final_result > limit:
                         final_result = limit

            except Exception as e:
                logger.error(f"Error procesando regla {rule.name} para {variable}: {e}")

        return final_result
    
    # ====================================================================
    # MÉTODOS ESTÁTICOS DE COMPATIBILIDAD (Reemplazan procesadores legacy)
    # ====================================================================
    
    @staticmethod
    def apply_operation(operation: str, values: list) -> float:
        """
        Aplica una operación sobre una lista de valores.

        Args:
            operation: "SUM", "DIFF", "AVG", "MUL", "MIN", "MAX"
            values: Lista de valores numéricos

        Returns:
            Resultado de la operación

        Examples:
            >>> FormulaEngine.apply_operation("SUM", [1, 2, 3])
            6.0
            >>> FormulaEngine.apply_operation("AVG", [10, 20, 30])
            20.0
        """
        try:
            # Filtrar valores None y convertir a float
            numeric_values = []
            for v in values:
                if v is not None:
                    try:
                        numeric_values.append(float(v))
                    except (ValueError, TypeError):
                        continue

            if not numeric_values:
                return 0.0

            if operation == "SUM":
                return sum(numeric_values)
            elif operation == "DIFF":
                # Primer valor menos la suma del resto
                return numeric_values[0] - sum(numeric_values[1:])
            elif operation == "AVG":
                return sum(numeric_values) / len(numeric_values)
            elif operation == "MUL":
                result = 1.0
                for v in numeric_values:
                    result *= v
                return result
            elif operation == "MIN":
                return min(numeric_values)
            elif operation == "MAX":
                return max(numeric_values)
            else:
                logger.error(f"Operación no soportada: {operation}")
                return 0.0
        except Exception as e:
            logger.error(f"Error en apply_operation({operation}): {e}")
            return 0.0

    @staticmethod
    def get_previous_value(
        point_id: int,
        variable_code: str,
        hours_back: int = 1,
        current_timestamp: Optional[datetime] = None
    ) -> Optional[float]:
        """
        Obtiene el valor previo de una variable.

        Útil para cálculos de diferencias (consumos, cambios, etc.)

        Args:
            point_id: ID del punto
            variable_code: Código de la variable
            hours_back: Horas hacia atrás a buscar
            current_timestamp: Timestamp actual (para buscar el anterior)

        Returns:
            Valor previo o None si no existe
        """
        try:
            from datetime import timedelta

            query = TelemetryRecord.objects.filter(point_id=point_id)

            if current_timestamp:
                query = query.filter(timestamp__lt=current_timestamp)
            else:
                cutoff = datetime.now() - timedelta(hours=hours_back)
                query = query.filter(timestamp__lte=cutoff)

            record = query.order_by('-timestamp').first()

            if record and record.data:
                value = record.data.get(variable_code)
                if value is not None:
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        return None
            return None
        except Exception as e:
            logger.error(f"Error en get_previous_value: {e}")
            return None

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
        - Acumula el valor perdido en el punto (addition/offset).
        - Crea Notificación.
        """
        try:
            from django.db import transaction
            from django.utils import timezone
            from api.notifications.models import Notification
            
            point_id = point_catchment["id"]
            point_obj = CatchmentPoint.objects.filter(id=point_id).first()
            
            if not pulses_factor or pulses_factor <= 0:
                pulses_factor = ConfigService.get_float(
                    "telemetry.pulses_factor_default", 1000
                )
            
            try:
                current_pulses = float(value)
            except (ValueError, TypeError):
                current_pulses = 0.0
            
            # Buscar último registro válido
            last_record = (
                TelemetryRecord.objects.filter(point_id=point_id)
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
                fallback_val = int(last_total) if last_total is not None else 0
                if return_full_details:
                    return fallback_val, {
                        "raw_pulses": current_pulses,
                        "status": "ERROR_NEGATIVE_PULSES",
                        "logic": "kept_last_valid",
                    }
                return fallback_val
            
            current_raw_m3 = (current_pulses * float(pulses_factor)) / 1000.0
            
            # Obtener offset del punto (antes estaba en ProfileDataConfigCatchment)
            # Intentamos obtenerlo de configuration_values o del campo directo (si existe)
            offset = 0
            if point_obj:
                # Prioridad 1: Campo addition en el modelo (legacy compatibility or new direct field)
                offset = getattr(point_obj, 'addition', 0) or 0
                
                # Prioridad 2: Configuración dinámica 'addition'
                if not offset:
                    config = point_obj.get_config_dict()
                    offset = int(config.get('addition', 0))
            
            # Validación anti-salto masivo
            max_diff_m3_per_hour = ConfigService.get_float(
                "telemetry.max_diff_m3_per_hour", 500
            )
            
            if last_total is not None:
                potential_new_total = current_raw_m3 + offset
                diff = potential_new_total - last_total
                
                if diff > max_diff_m3_per_hour:
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
                        return int(
                            round((last_pulses * float(pulses_factor)) / 1000.0 + offset)
                        )
                    
                    # Reinicio Real (0 < actual < anterior)
                    elif 0 < current_pulses < last_pulses:
                        amount_to_add = (last_pulses * float(pulses_factor)) / 1000.0
                        
                        with transaction.atomic():
                            if point_obj:
                                # Actualizar offset
                                new_offset = offset + int(amount_to_add)
                                
                                # Si el modelo tiene el campo, usarlo
                                if hasattr(point_obj, 'addition'):
                                    point_obj.addition = new_offset
                                    point_obj.save(update_fields=["addition"])
                                else:
                                    # TODO: Implementar actualización en PointConfigurationValue si no hay campo directo
                                    pass
                                    
                                offset = new_offset
                            
                            Notification.objects.create(
                                point_catchment_id=point_id,
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
    
    @staticmethod
    def evaluate_dynamic_formula(formula: str, context: Dict[str, Any]) -> float:
        """
        Evaluates a dynamic formula replacing {internal_code} with values from context.
        Use this to execute user-defined rules from the database.

        This is a standalone static method for backward compatibility.
        For more complex evaluations with config/system vars, use the instance method evaluate().

        Args:
            formula: String like "({v1} + {v2}) * 0.5"
            context: Dict mapping internal_code to current values

        Returns:
            float: Result of calculation or 0.0 if error
        """
        if not formula:
            return 0.0

        processed_formula = formula
        # Find all {var} patterns
        tokens = re.findall(r"\{([a-zA-Z0-9_]+)\}", formula)

        # Sort tokens by length descending to avoid partial replacement issues (e.g. {v1} and {v11})
        tokens = sorted(list(set(tokens)), key=len, reverse=True)

        for token in tokens:
            # Get value from context, fallback to 0 if not found
            try:
                val = float(context.get(token, 0))
            except (ValueError, TypeError):
                val = 0.0
            processed_formula = processed_formula.replace(f"{{{token}}}", str(val))

        # Whitelist characters for security (allow numbers, operators, dots, parens, spaces)
        # We also allow scientific notation e.g. 1e-5
        if not re.match(r"^[0-9\.\+\-\*\/\(\)\s eE]+$", processed_formula):
            logger.error(
                f"Formula contains insecure characters after processing: {processed_formula} (Original: {formula})"
            )
            return 0.0

        try:
            # Evaluate safely without builtins
            result = eval(processed_formula, {"__builtins__": {}})
            return float(result)
        except ZeroDivisionError:
            logger.warning(f"Division by zero in formula: {formula}")
            return 0.0
        except Exception as e:
            logger.error(f"Error evaluating formula '{formula}' (processed: '{processed_formula}'): {e}")
            return 0.0