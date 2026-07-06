"""MQTT consumer for void telemetry."""
import json
import logging
from typing import Optional
from urllib.parse import urlparse

import paho.mqtt.client as mqtt
from django.utils import timezone

from void.models import Device, MqttTopicConfig, RawReading

logger = logging.getLogger(__name__)


class MqttConsumer:
    """Consumidor MQTT genérico para proveedores void.

    Se conecta al broker definido en Provider.base_url, se autentica con
    Provider.auth_config y se suscribe a los MqttTopicConfig activos.
    Cada mensaje se parsea y se convierte en RawReading.

    Uso:
        consumer = MqttConsumer(provider)
        consumer.run_forever()
    """

    def __init__(self, provider: "void.Provider"):
        self.provider = provider
        self.client = mqtt.Client()
        self._setup_auth()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def _setup_auth(self):
        auth_config = self.provider.auth_config or {}
        username = auth_config.get("username")
        password = auth_config.get("password")
        if username:
            self.client.username_pw_set(username, password)

    def _parse_broker(self) -> tuple:
        """Parsea base_url tipo mqtt://host:1883 o tcp://host:1883."""
        url = self.provider.base_url or "mqtt://localhost:1883"
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 1883
        return host, port

    def _on_connect(self, client, userdata, flags, rc):
        if rc != 0:
            logger.error("MQTT connect failed for provider %s, rc=%s", self.provider.id, rc)
            return
        logger.info("MQTT connected for provider %s", self.provider.id)
        topics = self.provider.mqtt_topics.filter(is_active=True)
        for topic_config in topics:
            self.client.subscribe(topic_config.topic_template, qos=topic_config.qos)
            logger.info("Subscribed to %s (qos=%s)", topic_config.topic_template, topic_config.qos)

    def _on_disconnect(self, client, userdata, rc):
        logger.warning("MQTT disconnected for provider %s, rc=%s", self.provider.id, rc)

    def _on_message(self, client, userdata, msg):
        logger.debug("MQTT message on %s: %s", msg.topic, msg.payload)
        try:
            self._process_message(msg.topic, msg.payload)
        except Exception:
            logger.exception("Error processing MQTT message on %s", msg.topic)

    def _process_message(self, topic: str, payload: bytes):
        """Busca el topic config correspondiente, parsea y crea RawReading."""
        # Buscar config por matching exacto o wildcard.
        # Simplificación: buscamos configs que terminen con #/+ o coincidan exacto.
        configs = self.provider.mqtt_topics.filter(is_active=True)
        # Encontrar config que resuelva un device para este topic.
        # Esto funciona con templates exactos, wildcards (#/+) y placeholders ({external_id}).
        config = None
        device = None
        for candidate in configs:
            if self._topic_matches(candidate.topic_template, topic):
                resolved = self._resolve_device(topic, candidate)
                if resolved:
                    config = candidate
                    device = resolved
                    break
            else:
                # Fallback: probar si el topic encaja en la estructura del template.
                resolved = self._resolve_device(topic, candidate)
                if resolved:
                    config = candidate
                    device = resolved
                    break

        if config is None or device is None:
            logger.warning("No MQTT config matches topic %s", topic)
            return

        parser = config.payload_parser or {}
        value_field = parser.get("value_field", "value")
        timestamp_field = parser.get("timestamp_field", "ts")
        unit_field = parser.get("unit_field", "unit")
        variable_field = parser.get("variable_field", "variable")

        try:
            data = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Payload no JSON: tratar como valor crudo
            data = {value_field: payload.decode("utf-8", errors="ignore")}

        variable = self._extract(data, variable_field) or self._variable_from_topic(topic, config)
        value = self._extract(data, value_field)
        unit = self._extract(data, unit_field) or ""
        timestamp = self._parse_timestamp(self._extract(data, timestamp_field))

        if value is None or variable is None:
            logger.warning("MQTT message missing value/variable on %s", topic)
            return

        RawReading.objects.create(
            device=device,
            variable=variable,
            timestamp=timestamp or timezone.now(),
            raw_value=str(value),
            unit=unit,
            provider_payload={"topic": topic, "payload": data},
        )
        logger.info("RawReading created from MQTT: device=%s variable=%s", device.id, variable)

    def _topic_matches(self, template: str, topic: str) -> bool:
        """Matching básico de topic MQTT."""
        if template == topic:
            return True
        if "#" in template:
            prefix = template.split("#")[0]
            return topic.startswith(prefix)
        if "+" in template:
            t_parts = topic.split("/")
            tmpl_parts = template.split("/")
            if len(t_parts) != len(tmpl_parts):
                return False
            return all(t == "+" or t == p for t, p in zip(tmpl_parts, t_parts))
        return False

    def _variable_from_topic(self, topic: str, config: MqttTopicConfig) -> Optional[str]:
        """Intenta extraer variable del topic comparando con el template."""
        t_parts = topic.split("/")
        tmpl_parts = config.topic_template.split("/")
        if len(t_parts) != len(tmpl_parts):
            return None
        for tmpl, part in zip(tmpl_parts, t_parts):
            if tmpl == "{variable}":
                return part
        return None

    def _resolve_device(self, topic: str, config: MqttTopicConfig) -> Optional[Device]:
        """Resuelve el device a partir del topic (external_id)."""
        t_parts = topic.split("/")
        tmpl_parts = config.topic_template.split("/")
        if len(t_parts) != len(tmpl_parts):
            return None
        external_id = None
        for tmpl, part in zip(tmpl_parts, t_parts):
            if tmpl == "{external_id}":
                external_id = part
                break
        if not external_id:
            return None
        try:
            return Device.objects.get(
                provider=self.provider,
                external_id=external_id,
                is_active=True,
            )
        except Device.DoesNotExist:
            return None

    @staticmethod
    def _extract(data, field: str):
        if not field:
            return None
        if isinstance(data, dict):
            return data.get(field)
        return None

    @staticmethod
    def _parse_timestamp(value):
        from django.utils.dateparse import parse_datetime
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return timezone.datetime.fromtimestamp(value, tz=timezone.utc)
        if isinstance(value, str):
            return parse_datetime(value.replace("Z", "+00:00"))
        return None

    def run_forever(self):
        host, port = self._parse_broker()
        logger.info("Connecting to MQTT broker %s:%s for provider %s", host, port, self.provider.id)
        self.client.connect(host, port, keepalive=60)
        self.client.loop_forever()

    def run_non_blocking(self):
        """Inicia conexión en modo no bloqueante (útil para Celery/Cron)."""
        host, port = self._parse_broker()
        self.client.connect_async(host, port, keepalive=60)
        self.client.loop_start()
