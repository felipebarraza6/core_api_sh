"""
Motor de Parsing Dinámico para Payloads MQTT.

Permite parsear diferentes formatos de payload usando múltiples métodos:
- Template: Variables simples en strings
- JSONPath: Consultas avanzadas en JSON
- Python: Scripts personalizados
- Regex: Expresiones regulares para texto
"""

import json
import re
import logging
from typing import Dict, Any, Optional, Union, List
from datetime import datetime

logger = logging.getLogger(__name__)


class MQTTPayloadParser:
    """
    Motor de parsing dinámico para payloads MQTT.

    Parsea payloads de diferentes formatos según reglas configurables.
    """

    def __init__(self, mqtt_config: 'MQTTProviderConfig'):
        """
        Inicializar parser con configuración MQTT del proveedor.

        Args:
            mqtt_config: Instancia de MQTTProviderConfig
        """
        self.mqtt_config = mqtt_config
        self.rules = self._load_rules()

    def _load_rules(self) -> List['PayloadParsingRule']:
        """Cargar reglas de parsing activas ordenadas por prioridad."""
        from api.telemetry.providers.mqtt_models import PayloadParsingRule

        rules = PayloadParsingRule.objects.filter(
            provider=self.mqtt_config.provider,
            is_active=True
        ).order_by('-priority')

        return list(rules)
    def extract_device_id_from_topic(self, topic: str) -> Optional[str]:
        """
        Extraer device_id del topic usando el template del proveedor.
        
        Ejemplo: template "telemetry/{provider}/{device_id}/data"
        y topic "telemetry/nettra/station_1/data" -> station_1
        """
        template = self.mqtt_config.subscribe_topic_template
        
        # Convertir template a regex
        # Reemplazar variables {var} por grupos de captura
        import re
        pattern = template.replace('{provider}', '[^/]+')
        pattern = pattern.replace('{point_code}', '[^/]+')
        pattern = pattern.replace('{device_id}', '(?P<device_id>[^/]+)')
        pattern = f"^{pattern}$"
        
        try:
            match = re.match(pattern, topic)
            if match:
                return match.group('device_id')
        except Exception as e:
            logger.debug(f"Error extracting device_id from topic {topic}: {e}")
            
        return None

    def parse(self, topic: str, payload: bytes, device_id: str) -> Dict[str, Any]:
        """
        Parsear payload MQTT usando la regla aplicable.

        Args:
            topic: Topic MQTT del mensaje
            payload: Payload en bytes
            device_id: ID del dispositivo extraído del topic

        Returns:
            Dict con datos parseados en formato estandarizado
        """
        try:
            # 1. Decodificar payload
            decoded_payload = self._decode_payload(payload)

            # 2. Encontrar regla aplicable
            rule = self._find_matching_rule(topic, decoded_payload, device_id)

            if not rule:
                logger.warning(f"No matching parsing rule for topic {topic}")
                return self._parse_generic(decoded_payload)

            # 3. Aplicar método de parsing
            if rule.parsing_method == 'template':
                parsed_data = self._parse_template(decoded_payload, rule)
            elif rule.parsing_method == 'jsonpath':
                parsed_data = self._parse_jsonpath(decoded_payload, rule)
            elif rule.parsing_method == 'python':
                parsed_data = self._parse_python(decoded_payload, rule)
            elif rule.parsing_method == 'regex':
                parsed_data = self._parse_regex(decoded_payload, rule)
            else:
                raise ValueError(f"Unsupported parsing method: {rule.parsing_method}")

            # 4. Aplicar transformaciones
            parsed_data = self._apply_transformations(parsed_data, rule.transformations)

            # 5. Validar datos
            validation_errors = rule.validate_parsed_data(parsed_data)
            if validation_errors:
                logger.warning(f"Validation errors for {topic}: {validation_errors}")
                # No fallar completamente, solo loggear

            # 6. Normalizar formato de salida
            return self._normalize_output(parsed_data, topic, device_id)

        except Exception as e:
            logger.error(f"Error parsing MQTT payload for topic {topic}: {e}")
            return {
                'timestamp': None,
                'value': None,
                'unit': 'unknown',
                'variable_type': 'unknown',
                'metadata': {'error': str(e), 'topic': topic},
                'device_id': device_id
            }

    def _decode_payload(self, payload: bytes) -> Union[dict, str, bytes]:
        """
        Decodificar payload de diferentes formatos.

        Soporta: JSON, texto UTF-8, bytes crudos.
        """
        try:
            # Intentar JSON primero
            text = payload.decode('utf-8')
            return json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            try:
                # Intentar como texto plano
                return payload.decode('utf-8')
            except UnicodeDecodeError:
                # Mantener como bytes
                return payload

    def _find_matching_rule(self, topic: str, payload: Any, device_id: str) -> Optional['PayloadParsingRule']:
        """Encontrar la regla de parsing que aplica al mensaje."""
        for rule in self.rules:
            if rule.matches_condition(topic, payload if isinstance(payload, dict) else {}, device_id):
                return rule
        return None

    def _parse_template(self, payload: Any, rule: 'PayloadParsingRule') -> Dict[str, Any]:
        """
        Parsear usando templates con variables.

        Ejemplo de field_mappings:
        {
            "timestamp": "{payload.ts}",
            "flow": "{payload.data.flow}",
            "total": "{payload.readings.total}"
        }
        """
        result = {}

        if not isinstance(payload, dict):
            raise ValueError("Template parsing requires JSON payload")

        for field_name, template in rule.field_mappings.items():
            try:
                # Reemplazar variables en el template
                value = self._resolve_template_variables(template, {'payload': payload})
                result[field_name] = value
            except Exception as e:
                logger.debug(f"Error parsing template field {field_name}: {e}")
                result[field_name] = None

        return result

    def _resolve_template_variables(self, template: str, context: dict) -> Any:
        """Resolver variables en template usando evaluación segura."""
        if not isinstance(template, str):
            return template

        # Crear namespace seguro
        safe_namespace = {
            'payload': context.get('payload', {}),
            'topic': context.get('topic', ''),
            'device_id': context.get('device_id', ''),
        }

        # Reemplazar variables simples primero
        resolved = template
        for key, value in safe_namespace.items():
            if isinstance(value, dict):
                # Para dicts, permitir acceso con notación de punto
                resolved = self._replace_dict_access(resolved, key, value)
            else:
                resolved = resolved.replace(f"{{{key}}}", str(value))

        # Evaluar expresiones simples si quedan llaves
        if '{' in resolved and '}' in resolved:
            try:
                # Solo permitir expresiones seguras
                allowed_names = {
                    'int': int, 'float': float, 'str': str,
                    'len': len, 'abs': abs, 'round': round
                }
                result = eval(resolved, {"__builtins__": allowed_names}, safe_namespace)
                return result
            except Exception as e:
                logger.debug(f"Could not evaluate template expression: {resolved} ({e})")

        return resolved

    def _replace_dict_access(self, template: str, dict_name: str, data: dict) -> str:
        """Reemplazar acceso a dict en templates (ej: {payload.ts} -> valor)."""
        import re

        def replace_match(match):
            path = match.group(1)
            if path.startswith(f"{dict_name}."):
                keys = path[len(dict_name) + 1:].split('.')
                current = data
                try:
                    for key in keys:
                        current = current[key]
                    return str(current)
                except (KeyError, TypeError):
                    return "None"
            return match.group(0)

        return re.sub(r'\{([^}]+)\}', replace_match, template)

    def _parse_jsonpath(self, payload: Any, rule: 'PayloadParsingRule') -> Dict[str, Any]:
        """
        Parsear usando JSONPath/JMESPath.

        Requiere instalar jmespath: pip install jmespath

        Ejemplo de field_mappings:
        {
            "timestamp": {
                "source": "$.timestamp",
                "type": "jsonpath",
                "transform": "unix_to_datetime"
            },
            "flow": {
                "source": "$.data.flow",
                "type": "jsonpath"
            }
        }
        """
        try:
            import jmespath
        except ImportError:
            raise ImportError("JMESPath parsing requires 'jmespath' package. Install with: pip install jmespath")

        result = {}

        for field_name, config in rule.field_mappings.items():
            try:
                if isinstance(config, dict) and config.get('type') == 'jsonpath':
                    source = config['source']
                    value = jmespath.search(source, payload)

                    # Aplicar transformación específica del campo si existe
                    if 'transform' in config:
                        value = self._apply_transform(value, config['transform'])

                    result[field_name] = value
                else:
                    # Fallback a búsqueda directa
                    result[field_name] = jmespath.search(str(config), payload)

            except Exception as e:
                logger.debug(f"Error parsing JSONPath field {field_name}: {e}")
                result[field_name] = None

        return result

    def _parse_python(self, payload: Any, rule: 'PayloadParsingRule') -> Dict[str, Any]:
        """
        Parsear usando código Python personalizado.

        Ejemplo de field_mappings:
        {
            "timestamp": "parse_timestamp(payload.get('ts'))",
            "flow": "float(payload['data']['flow']) if payload.get('data') else None"
        }
        """
        result = {}

        # Crear contexto seguro para ejecución de código
        context = {
            'payload': payload,
            'json': json,
            're': re,
            'datetime': datetime,
        }

        # Funciones de utilidad comunes
        context.update({
            'int': int,
            'float': float,
            'str': str,
            'len': len,
            'abs': abs,
            'round': round,
            'parse_timestamp': self._parse_timestamp,
        })

        for field_name, code in rule.field_mappings.items():
            try:
                # Ejecutar código Python de forma segura
                compiled_code = compile(code, '<string>', 'eval')
                value = eval(compiled_code, {"__builtins__": {}}, context)
                result[field_name] = value

            except Exception as e:
                logger.debug(f"Error executing Python code for field {field_name}: {e}")
                result[field_name] = None

        return result

    def _parse_regex(self, payload: Any, rule: 'PayloadParsingRule') -> Dict[str, Any]:
        """
        Parsear usando expresiones regulares.

        Requiere que payload sea string.

        Ejemplo de field_mappings:
        {
            "flow": {
                "pattern": "flow:(\\d+\\.?\\d*)",
                "group": 1,
                "type": "float"
            },
            "timestamp": {
                "pattern": "time:(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2})",
                "group": 1
            }
        }
        """
        result = {}

        # Convertir payload a string si no lo es
        if isinstance(payload, dict):
            text = json.dumps(payload)
        elif isinstance(payload, bytes):
            text = payload.decode('utf-8', errors='ignore')
        else:
            text = str(payload)

        for field_name, config in rule.field_mappings.items():
            try:
                if isinstance(config, dict):
                    pattern = config['pattern']
                    group = config.get('group', 0)
                    value_type = config.get('type', 'str')

                    match = re.search(pattern, text)
                    if match:
                        value = match.group(group)

                        # Convertir tipo si especificado
                        if value_type == 'int':
                            value = int(value)
                        elif value_type == 'float':
                            value = float(value)
                        elif value_type == 'bool':
                            value = value.lower() in ('true', '1', 'yes')

                        result[field_name] = value
                    else:
                        result[field_name] = None
                else:
                    # Fallback a búsqueda simple
                    match = re.search(str(config), text)
                    result[field_name] = match.group(0) if match else None

            except Exception as e:
                logger.debug(f"Error parsing regex field {field_name}: {e}")
                result[field_name] = None

        return result

    def _parse_generic(self, payload: Any) -> Dict[str, Any]:
        """Parseo genérico cuando no hay regla específica."""
        result = {
            'timestamp': None,
            'value': None,
            'unit': 'unknown',
            'variable_type': 'unknown',
            'metadata': {}
        }

        if isinstance(payload, dict):
            # Buscar campos comunes
            for ts_field in ['timestamp', 'time', 'datetime', 'ts']:
                if ts_field in payload:
                    result['timestamp'] = self._parse_timestamp(payload[ts_field])
                    break

            for val_field in ['value', 'val', 'data', 'reading']:
                if val_field in payload:
                    result['value'] = payload[val_field]
                    break

            # Agregar metadata adicional
            result['metadata'] = {k: v for k, v in payload.items()
                                if k not in ['timestamp', 'time', 'datetime', 'ts', 'value', 'val', 'data', 'reading']}

        return result

    def _apply_transformations(self, data: Dict[str, Any], transformations: List[Dict]) -> Dict[str, Any]:
        """Aplicar transformaciones a los datos parseados."""
        result = data.copy()

        for transform in transformations:
            field = transform.get('field')
            transform_type = transform.get('type')

            if field not in result or result[field] is None:
                continue

            try:
                if transform_type == 'unix_to_datetime':
                    if isinstance(result[field], (int, float)):
                        result[field] = datetime.fromtimestamp(result[field])

                elif transform_type == 'string_to_datetime':
                    if isinstance(result[field], str):
                        # Intentar varios formatos comunes
                        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%fZ']:
                            try:
                                result[field] = datetime.strptime(result[field], fmt)
                                break
                            except ValueError:
                                continue

                elif transform_type == 'unit_conversion':
                    from_unit = transform.get('from')
                    to_unit = transform.get('to')
                    result[field] = self._convert_units(result[field], from_unit, to_unit)

                elif transform_type == 'scale':
                    factor = transform.get('factor', 1.0)
                    offset = transform.get('offset', 0.0)
                    result[field] = result[field] * factor + offset

                elif transform_type == 'round':
                    decimals = transform.get('decimals', 2)
                    result[field] = round(float(result[field]), decimals)

            except Exception as e:
                logger.debug(f"Error applying transformation {transform_type} to field {field}: {e}")

        return result

    def _apply_transform(self, value: Any, transform_type: str) -> Any:
        """Aplicar transformación individual."""
        if transform_type == 'unix_to_datetime' and isinstance(value, (int, float)):
            return datetime.fromtimestamp(value)
        elif transform_type == 'to_int':
            return int(value)
        elif transform_type == 'to_float':
            return float(value)
        elif transform_type == 'to_string':
            return str(value)
        else:
            return value

    def _convert_units(self, value: float, from_unit: str, to_unit: str) -> float:
        """Convertir unidades de medida."""
        conversions = {
            ('m3/h', 'L/s'): lambda x: x * 1000 / 3600,
            ('L/s', 'm3/h'): lambda x: x * 3600 / 1000,
            ('celsius', 'fahrenheit'): lambda x: x * 9/5 + 32,
            ('fahrenheit', 'celsius'): lambda x: (x - 32) * 5/9,
            ('meters', 'feet'): lambda x: x * 3.28084,
            ('feet', 'meters'): lambda x: x / 3.28084,
        }

        key = (from_unit.lower(), to_unit.lower())
        if key in conversions:
            return conversions[key](value)

        logger.warning(f"No conversion available for {from_unit} to {to_unit}")
        return value

    def _parse_timestamp(self, value: Any) -> Optional[datetime]:
        """Parsear timestamp en múltiples formatos."""
        if value is None:
            return None

        if isinstance(value, datetime):
            return value

        if isinstance(value, (int, float)):
            # Unix timestamp
            if value > 1e12:  # Milisegundos
                return datetime.fromtimestamp(value / 1000)
            return datetime.fromtimestamp(value)

        if isinstance(value, str):
            # Intentar formatos comunes
            formats = [
                '%Y-%m-%dT%H:%M:%S.%fZ',
                '%Y-%m-%dT%H:%M:%SZ',
                '%Y-%m-%dT%H:%M:%S.%f',
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d',
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(value.replace('Z', ''), fmt)
                except ValueError:
                    continue

            # Intentar parseo ISO
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                pass

        logger.debug(f"Could not parse timestamp: {value}")
        return None

    def _normalize_output(self, data: Dict[str, Any], topic: str, device_id: str) -> Dict[str, Any]:
        """Normalizar formato de salida para el sistema de telemetría."""
        result = {
            'timestamp': data.get('timestamp'),
            'value': data.get('value'),
            'unit': data.get('unit', 'unknown'),
            'variable_type': data.get('variable_type', 'unknown'),
            'device_id': device_id,
            'metadata': {
                'topic': topic,
                'parsing_method': getattr(self._find_matching_rule(topic, data, device_id), 'parsing_method', 'generic') if self._find_matching_rule(topic, data, device_id) else 'generic',
                'raw_data': data
            }
        }

        # Agregar campos adicionales del parsing
        for key, value in data.items():
            if key not in ['timestamp', 'value', 'unit', 'variable_type']:
                result['metadata'][key] = value

        return result