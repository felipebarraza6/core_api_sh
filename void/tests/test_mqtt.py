"""Tests for void MQTT consumer."""
import json
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from void.models import Device, MqttTopicConfig, Point, Provider, RawReading
from void.services.mqtt import MqttConsumer


class MqttConsumerTests(TestCase):
    def setUp(self):
        self.provider = Provider.objects.create(
            name="Broker MQTT Interno",
            protocol="MQTT",
            base_url="mqtt://broker.smarthydro.cl:1883",
            auth_config={"username": "user", "password": "pass"},
        )
        self.point = Point.objects.create(name="P1")
        self.device = Device.objects.create(
            point=self.point,
            external_id="DEV-001",
            provider=self.provider,
            configuration={"variables": ["pulses"]},
        )
        self.topic_config = MqttTopicConfig.objects.create(
            provider=self.provider,
            name="Pulsos",
            topic_template="devices/{external_id}/pulses",
            qos=1,
            payload_parser={
                "value_field": "v",
                "timestamp_field": "ts",
                "variable_field": "var",
            },
        )

    @patch("void.services.mqtt.mqtt.Client")
    def test_consumer_sets_auth(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        consumer = MqttConsumer(self.provider)
        mock_client.username_pw_set.assert_called_once_with("user", "pass")

    @patch("void.services.mqtt.mqtt.Client")
    def test_process_message_creates_raw_reading(self, mock_client_class):
        consumer = MqttConsumer(self.provider)

        payload = json.dumps({"v": 42, "ts": "2026-01-01T00:00:00Z", "var": "pulses"})
        msg = MagicMock()
        msg.topic = "devices/DEV-001/pulses"
        msg.payload = payload.encode("utf-8")

        consumer._on_message(None, None, msg)

        raw = RawReading.objects.first()
        self.assertIsNotNone(raw)
        self.assertEqual(raw.device, self.device)
        self.assertEqual(raw.variable, "pulses")
        self.assertEqual(raw.raw_value, "42")

    @patch("void.services.mqtt.mqtt.Client")
    def test_topic_matches_wildcard(self, mock_client_class):
        consumer = MqttConsumer(self.provider)
        self.assertTrue(consumer._topic_matches("devices/#", "devices/DEV-001/pulses"))
        self.assertTrue(consumer._topic_matches("devices/+/pulses", "devices/DEV-001/pulses"))
        self.assertFalse(consumer._topic_matches("devices/+/pulses", "devices/DEV-001/pulses/extra"))

    @patch("void.services.mqtt.mqtt.Client")
    def test_resolve_device_from_topic(self, mock_client_class):
        consumer = MqttConsumer(self.provider)
        device = consumer._resolve_device("devices/DEV-001/pulses", self.topic_config)
        self.assertEqual(device, self.device)

    def test_parse_broker(self):
        consumer = MqttConsumer(self.provider)
        host, port = consumer._parse_broker()
        self.assertEqual(host, "broker.smarthydro.cl")
        self.assertEqual(port, 1883)
