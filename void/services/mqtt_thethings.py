"""
Cliente MQTT para recibir telemetría de TheThings.io sin polling REST.

TheThings.io expone un broker MQTT en mqtt.thethings.io:1883.
Cada thing publica en el topic v2/things/{THING_TOKEN}.
Este cliente se suscribe a todos los tokens activos y guarda los valores
usando la misma lógica de procesamiento unificado que usan los cronjobs.

Referencia:
- https://developers.thethings.io/docs/protocols
- Librería oficial: https://github.com/theThings/thethings.iO-python-library
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import paho.mqtt.client as mqtt
from django.db import close_old_connections
from django.utils import timezone

from api.core.models import CatchmentPoint, InteractionDetail, ProfileDataConfigCatchment
from api.core.models.telemetry_providers import TelemetryProvider
from api.core.serializers import CatchmentPointSerializerDetailCron
from api.cronjobs.telemetry.controllers.unified_processing import (
    process_variable_safely,
    validate_frequency,
)
from api.cronjobs.utils.logging_config import telemetry_logger

logger = logging.getLogger(__name__)

# Configuración del broker
BROKER_HOST = os.environ.get("THETHINGS_MQTT_HOST", "mqtt.thethings.io")
BROKER_PORT = int(os.environ.get("THETHINGS_MQTT_PORT", "1883"))
BROKER_KEEPALIVE = int(os.environ.get("THETHINGS_MQTT_KEEPALIVE", "60"))
RECONNECT_DELAY_SECONDS = int(os.environ.get("THETHINGS_MQTT_RECONNECT_DELAY", "5"))
TOPIC_TEMPLATE = "v2/things/{token}"


def _mask_token(token: str) -> str:
    """Muestra solo los primeros 8 caracteres de un token para logs."""
    if not token:
        return ""
    if len(token) <= 12:
        return "***"
    return f"{token[:8]}..."


def _lookup_point_by_token(token: str) -> Optional[CatchmentPoint]:
    """Busca el punto de captación asociado a un thing token."""
    if not token:
        return None

    # 1. Buscar en ProfileDataConfigCatchment.token_service
    profile = ProfileDataConfigCatchment.objects.filter(
        token_service=token,
        is_telemetry=True,
    ).select_related("point_catchment").first()
    if profile and profile.point_catchment:
        return profile.point_catchment

    # 2. Fallback: buscar en Variable.token_service a través del esquema
    from api.core.models import Variable
    variable = Variable.objects.filter(
        token_service=token,
        provider__handler_name="thethings",
    ).select_related("scheme_catchment").first()
    if variable:
        point = variable.scheme_catchment.points_catchment.filter(is_thethings=True).first()
        if point:
            return point

    return None


def _serialize_point_for_processing(point: CatchmentPoint) -> Optional[Dict[str, Any]]:
    """Devuelve el dict que espera process_variable_safely."""
    serializer = CatchmentPointSerializerDetailCron(point)
    return serializer.data


def _parse_payload(payload: bytes) -> List[Dict[str, Any]]:
    """
    Parsea el payload MQTT de TheThings.io.

    Soporta:
      - {"values": [{"key": "x", "value": 1, "datetime": "..."}, ...]}
      - [{"key": "x", "value": 1, "datetime": "..."}, ...]
    """
    try:
        data = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        telemetry_logger.warning(f"[MQTT] Payload inválido: {e}")
        return []

    if isinstance(data, dict):
        values = data.get("values", [])
    elif isinstance(data, list):
        values = data
    else:
        telemetry_logger.warning(f"[MQTT] Formato de payload inesperado: {type(data)}")
        return []

    if not isinstance(values, list):
        telemetry_logger.warning("[MQTT] 'values' no es una lista")
        return []

    return values


def _to_iso_datetime(dt_str: Optional[str]) -> Optional[str]:
    """Convierte datetime de TheThings.io al formato usado por el procesador."""
    if not dt_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(dt_str, fmt)
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
    return None


def _truncate_meditation(dt_str: str, frequency: str) -> str:
    """Trunca un timestamp al slot de medición según la frecuencia del punto."""
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return dt_str

    if frequency == "60":
        return dt.strftime("%Y-%m-%dT%H:00:00")
    return dt.strftime("%Y-%m-%dT%H:%M:00")


def _ensure_variable_values(record: InteractionDetail) -> None:
    if record.variable_values is None:
        record.variable_values = {}


def _save_mqtt_measurement(
    point_data: Dict[str, Any],
    token: str,
    values: List[Dict[str, Any]],
) -> bool:
    """
    Procesa y guarda una tanda de valores recibidos por MQTT.

    Returns:
        True si se guardó al menos una variable correctamente.
    """
    point_id = point_data["id"]
    profile = point_data.get("profile_data_config", {})
    frequency = point_data.get("frecuency", "60")
    variables = profile.get("scheme", {}).get("variables", [])

    if not variables:
        telemetry_logger.warning(f"[MQTT] Punto {point_id} sin variables configuradas")
        return False

    # Índice de variables por nombre
    var_by_key = {v["str_variable"]: v for v in variables}

    # Determinar el slot de medición a partir del timestamp más reciente del payload
    medition_dt_str = None
    for item in values:
        dt = _to_iso_datetime(item.get("datetime"))
        if dt and (medition_dt_str is None or dt > medition_dt_str):
            medition_dt_str = dt

    if medition_dt_str is None:
        # Si el payload no trae datetime, usamos ahora en UTC y lo convertimos al formato esperado
        medition_dt_str = timezone.now().strftime("%Y-%m-%dT%H:%M:%S")

    medition_str = _truncate_meditation(medition_dt_str, frequency)

    # Recuperar registro existente del mismo slot o crear nuevo
    record, created = InteractionDetail.objects.get_or_create(
        catchment_point_id=point_id,
        date_time_medition=medition_str,
        defaults={
            "variable_values": {},
            "variable_details": [],
            "is_partial": False,
        },
    )
    _ensure_variable_values(record)

    created_register = {
        "date_time_medition": medition_str,
        "variable_values": dict(record.variable_values),
        "variable_details": list(record.variable_details or []),
        "is_partial": record.is_partial,
        "is_error": record.is_error,
        "pulses": record.pulses,
        "total": record.total,
        "total_diff": record.total_diff,
        "total_today_diff": record.total_today_diff,
        "flow": record.flow,
        "nivel": record.nivel,
        "water_table": record.water_table,
        "date_time_last_logger": (
            record.date_time_last_logger.strftime("%Y-%m-%dT%H:%M:%S")
            if record.date_time_last_logger else None
        ),
        "days_not_conection": record.days_not_conection,
    }

    date_time_last_logger_total: Optional[str] = created_register.get("date_time_last_logger")
    processed_any = False
    detail_by_key = {d["str_variable"]: d for d in created_register["variable_details"]}

    for item in values:
        key = item.get("key")
        variable = var_by_key.get(key)
        if not variable:
            telemetry_logger.debug(f"[MQTT] Punto {point_id}: variable '{key}' no configurada")
            continue

        dt = _to_iso_datetime(item.get("datetime")) or medition_dt_str
        data = {"value": item.get("value", 0), "date_time": dt}

        try:
            date_time_last_logger_total, created_register = process_variable_safely(
                variable=variable,
                data=data,
                point_catchment=point_data,
                created_register=created_register,
                date_time_last_logger_total=date_time_last_logger_total,
                medition_str=medition_str,
            )
            processed_any = True

            # Guardar valor crudo
            var_id = variable.get("id")
            if var_id is not None:
                created_register["variable_values"][str(var_id)] = data.get("value")

            # Actualizar detalle de variable
            detail_by_key[key] = {
                "str_variable": key,
                "type_variable": variable.get("type_variable"),
                "value": data.get("value"),
                "success": data.get("date_time") is not None,
            }
        except Exception as e:
            telemetry_logger.error(
                f"[MQTT] Error procesando variable {key} para punto {point_id}: {e}",
                exc_info=True,
            )

    created_register["variable_details"] = list(detail_by_key.values())

    # Determinar send_dga
    try:
        from api.core.models import DgaDataConfigCatchment
        dga_config = DgaDataConfigCatchment.objects.get(point_catchment_id=point_id)
        record_time = datetime.strptime(
            medition_str,
            "%Y-%m-%dT%H:%M:%S" if frequency != "60" else "%Y-%m-%dT%H:00:00",
        )
        created_register["send_dga"] = dga_config.send_dga and validate_frequency(
            point_data, record_time, frequency
        )
    except DgaDataConfigCatchment.DoesNotExist:
        created_register["send_dga"] = False
    except Exception as e:
        telemetry_logger.warning(f"[MQTT] Error DGA config punto {point_id}: {e}")
        created_register["send_dga"] = False

    if not processed_any and created:
        # No se procesó ninguna variable conocida y el registro es nuevo:
        # no dejar registro vacío en BD.
        record.delete()
        return False

    # Los timestamps de TheThings.io vienen en UTC (Z). Asegurar que se guarden
    # como aware UTC para que Django no los convierta a hora local.
    if created_register.get("date_time_last_logger"):
        dt_last = datetime.strptime(
            created_register["date_time_last_logger"], "%Y-%m-%dT%H:%M:%S"
        )
        created_register["date_time_last_logger"] = timezone.make_aware(dt_last, timezone.utc)

    # Guardar
    for field in [
        "total", "total_diff", "total_today_diff", "flow", "nivel",
        "water_table", "pulses", "days_not_conection", "is_partial",
        "is_error", "send_dga", "variable_values", "variable_details",
        "date_time_last_logger",
    ]:
        setattr(record, field, created_register.get(field))

    record.save()
    telemetry_logger.info(
        f"[MQTT] Punto {point_id} guardado | medition={medition_str} | "
        f"total={created_register.get('total')} | flow={created_register.get('flow')} | "
        f"nivel={created_register.get('nivel')}"
    )
    return processed_any


class TheThingsMQTTClient:
    """Cliente MQTT persistente para TheThings.io."""

    def __init__(self):
        # paho-mqtt 1.x (requirements.txt fija <2.0.0)
        self.client = mqtt.Client(client_id=f"smarthydro_mqtt_{int(time.time())}")
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        self.subscribed_tokens: set = set()

    def _active_tokens(self) -> List[str]:
        """Retorna todos los tokens TheThings.io activos."""
        thethings_provider = TelemetryProvider.objects.filter(
            handler_name="thethings", is_active=True
        ).first()

        if not thethings_provider:
            return []

        tokens = set()

        # Tokens a nivel de profile
        profiles = ProfileDataConfigCatchment.objects.filter(
            point_catchment__telemetry_provider=thethings_provider,
            is_telemetry=True,
        ).exclude(token_service__isnull=True).exclude(token_service="")
        for p in profiles:
            tokens.add(p.token_service)

        # Tokens a nivel de variable
        from api.core.models import Variable
        variables = Variable.objects.filter(
            provider=thethings_provider,
        ).exclude(token_service__isnull=True).exclude(token_service="")
        for v in variables:
            tokens.add(v.token_service)

        # Fallback legacy por is_thethings=True
        profiles_legacy = ProfileDataConfigCatchment.objects.filter(
            point_catchment__is_thethings=True,
            is_telemetry=True,
        ).exclude(token_service__isnull=True).exclude(token_service="")
        for p in profiles_legacy:
            tokens.add(p.token_service)

        return list(tokens)

    def _on_connect(self, client, userdata, flags, rc):
        telemetry_logger.info(f"[MQTT] Conectado a {BROKER_HOST}:{BROKER_PORT} (rc={rc})")
        tokens = self._active_tokens()
        telemetry_logger.info(f"[MQTT] Tokens activos encontrados: {len(tokens)}")

        for token in tokens:
            topic = TOPIC_TEMPLATE.format(token=token)
            client.subscribe(topic)
            self.subscribed_tokens.add(token)
            telemetry_logger.info(f"[MQTT] Suscrito a {_mask_token(token)}")

    def _on_disconnect(self, client, userdata, rc):
        telemetry_logger.warning(f"[MQTT] Desconectado (rc={rc}). Reconectando...")

    def _on_message(self, client, userdata, msg):
        try:
            self._process_message(msg.topic, msg.payload)
        except Exception as e:
            telemetry_logger.error(f"[MQTT] Error procesando mensaje: {e}", exc_info=True)
        finally:
            # Cerrar conexiones viejas para evitar leaks en long-running process
            close_old_connections()

    def _process_message(self, topic: str, payload: bytes):
        # Extraer token del topic v2/things/{token}
        parts = topic.split("/")
        if len(parts) < 3:
            telemetry_logger.warning(f"[MQTT] Topic inesperado: {topic}")
            return

        token = parts[-1]
        values = _parse_payload(payload)
        if not values:
            return

        point = _lookup_point_by_token(token)
        if not point:
            telemetry_logger.warning(f"[MQTT] Token no asociado a ningún punto: {_mask_token(token)}")
            return

        point_data = _serialize_point_for_processing(point)
        if not point_data:
            telemetry_logger.warning(f"[MQTT] No se pudo serializar punto para token {_mask_token(token)}")
            return

        _save_mqtt_measurement(point_data, token, values)

    def run(self):
        telemetry_logger.info(
            f"[MQTT] Iniciando cliente TheThings.io en {BROKER_HOST}:{BROKER_PORT}"
        )
        while True:
            try:
                self.client.connect(BROKER_HOST, BROKER_PORT, BROKER_KEEPALIVE)
                self.client.loop_forever()
            except Exception as e:
                telemetry_logger.error(f"[MQTT] Error en loop: {e}", exc_info=True)
            telemetry_logger.warning(
                f"[MQTT] Reintentando en {RECONNECT_DELAY_SECONDS} segundos..."
            )
            time.sleep(RECONNECT_DELAY_SECONDS)
