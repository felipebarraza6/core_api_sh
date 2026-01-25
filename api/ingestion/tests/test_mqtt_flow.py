
from django.test import TestCase
from django.utils import timezone
from unittest.mock import MagicMock, patch
import json
import asyncio

from api.telemetry.models import CatchmentPoint, TelemetryRecord, CoreVariable
from api.telemetry.providers.models import TelemetryProvider, CatchmentPointProvider
from api.telemetry.providers.mqtt_models import MQTTProviderConfig, PayloadParsingRule
from api.ingestion.mqtt.handler import DynamicMQTTHandler

class MQTTIntegrationTest(TestCase):
    def setUp(self):
        # 1. Crear Estructura Base (Variable, Punto)
        self.variable = CoreVariable.objects.create(
            variable_code="caudal",
            name="Caudal Instantáneo",
            unit="L/s"
        )
        
        self.point = CatchmentPoint.objects.create(
            point_code="POZO-TEST-01",
            title="Pozo de Prueba",
            lat=-33.0,
            lng=-70.0
        )
        
        # 2. Crear Proveedor MQTT
        self.provider = TelemetryProvider.objects.create(
            name="mqtt_test_provider",
            display_name="Test MQTT Broker",
            provider_type="mqtt_client",
            base_url="mqtt://test.mosquitto.org",
            is_active=True
        )
        
        # 3. Configurar MQTT Específico
        self.mqtt_config = MQTTProviderConfig.objects.create(
            provider=self.provider,
            broker_host="test.mosquitto.org",
            broker_port=1883,
            subscribe_topic_template="telemetry/{device_id}/data",
            service_identifier="TEST_MQTT"
        )
        
        # 4. Vincular Punto con Proveedor
        self.cp_provider = CatchmentPointProvider.objects.create(
            point=self.point,
            provider=self.provider,
            variable=self.variable,
            point_code="DEVICE-001",
            is_active=True
        )
        
        # 5. Crear Regla de Parsing (Simple JSON)
        self.rule = PayloadParsingRule.objects.create(
            provider=self.provider,
            name="Regla Simple JSON",
            topic_pattern="telemetry/+/data",
            parsing_method="jsonpath",
            field_mappings={
                "value": "$.flow",
                "timestamp": "$.ts",
                "variable_type": "caudal" # Hardcoded for test
            },
            priority=100,
            is_active=True
        )

    @patch("api.ingestion.mqtt.handler.mqtt.Client")
    def test_mqtt_message_processing_flow(self, mock_mqtt):
        """
        Prueba que un mensaje MQTT crudo se convierte en un TelemetryRecord.
        """
        # A. Instanciar Handler
        handler = DynamicMQTTHandler(self.provider)
        
        # B. Simular Payload
        payload_dict = {
            "flow": 45.5,
            "ts": timezone.now().timestamp(),
            "status": "ok"
        }
        payload_bytes = json.dumps(payload_dict).encode('utf-8')
        
        # C. Simular Mensaje MQTT (Objeto Mock)
        mock_msg = MagicMock()
        mock_msg.topic = "telemetry/DEVICE-001/data"
        mock_msg.payload = payload_bytes
        mock_msg.qos = 1
        mock_msg.retain = False
        
        # D. Ejecutar callback _on_message manualmente
        # Nota: DynamicMQTTHandler usa asyncio.create_task, por lo que 
        # en entorno síncrono de test necesitamos correr el loop o mockear el task.
        
        # Hack para testear lógica interna sin asyncio complex
        # Llamamos directamente a la lógica de parsing y guardado si es posible,
        # o usamos un runner.
        
        # 1. Parsing (Unitario)
        device_id = handler._extract_device_id_from_topic(mock_msg.topic)
        self.assertEqual(device_id, "DEVICE-001")
        
        parsed = handler.parser.parse(mock_msg.topic, mock_msg.payload, device_id)
        self.assertEqual(parsed['value'], 45.5)
        
        # 2. Guardado (Integration)
        # Forzamos la ejecución síncrona de _process_parsed_message
        asyncio.run(handler._process_parsed_message(device_id, parsed))
        
        # E. Verificar DB
        record = TelemetryRecord.objects.filter(catchment_point=self.point).last()
        self.assertIsNotNone(record, "El registro de telemetría no fue creado")
        self.assertEqual(record.value, 45.5)
        self.assertEqual(record.variable.variable_code, "caudal")
