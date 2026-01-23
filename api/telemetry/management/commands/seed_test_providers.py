from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from api.crm.models import Client, Project
from api.telemetry.models import CatchmentPoint, CoreVariable, VariableType
from api.telemetry.providers.models import TelemetryProvider, CatchmentPointProvider
from api.telemetry.providers.mqtt_models import MQTTProviderConfig, PayloadParsingRule

User = get_user_model()

class Command(BaseCommand):
    help = 'Seeds test providers (Nettra, Novus, Twin) for system verification.'

    def handle(self, *args, **options):
        self.stdout.write("Seeding test environment...")

        # 1. Ensure a test user and project exist
        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            self.stdout.write(self.style.ERROR("No admin user found. Create one first."))
            return

        client, _ = Client.objects.get_or_create(name="SmartHydro Test Client")
        project, _ = Project.objects.get_or_create(name="Test Project", client=client)

        # 2. Ensure VariableTypes exist
        flow_type, _ = VariableType.objects.get_or_create(code="CAUDAL", defaults={"name": "Caudal Instantáneo", "default_unit": "L/s"})
        total_type, _ = VariableType.objects.get_or_create(code="TOTALIZADO", defaults={"name": "Volumen Acumulado", "default_unit": "m3"})

        from api.telemetry.models import SamplingFrequency
        freq_15, _ = SamplingFrequency.objects.get_or_create(minutes=15, defaults={"name": "15 minutos", "code": "15"})

        # 3. Create a test Catchment Point
        point, _ = CatchmentPoint.objects.get_or_create(
            point_code="TEST_POINT_01",
            defaults={
                "title": "Punto de Prueba Multi-Provider",
                "project": project,
                "owner_user": admin_user,
                "frequency": freq_15
            }
        )

        # 4. Create internal variables (Logical Level)
        var_caudal, _ = CoreVariable.objects.get_or_create(
            point=point,
            internal_code="flow",
            defaults={"name": "Caudal de Pozo", "type_definition": flow_type, "unit": "L/s"}
        )
        var_total, _ = CoreVariable.objects.get_or_create(
            point=point,
            internal_code="total",
            defaults={"name": "Totalizador Acumulado", "type_definition": total_type, "unit": "m3"}
        )

        # 5. Setup Providers
        
        # PROV 1: Nettra (MQTT)
        nettra_prov, _ = TelemetryProvider.objects.get_or_create(
            name="nettra_mqtt",
            defaults={
                "display_name": "Nettra MQTT (Local)",
                "provider_type": "mqtt_server",
                "auth_method": "none"
            }
        )
        
        MQTTProviderConfig.objects.get_or_create(
            provider=nettra_prov,
            defaults={
                "mqtt_mode": "server",
                "broker_host": "mqtt_broker",
                "broker_port": 1883,
                "subscribe_topic_template": "telemetry/{provider}/{device_id}/data",
                "service_identifier": "nettra",
            }
        )

        PayloadParsingRule.objects.update_or_create(
            provider=nettra_prov,
            name="Nettra Standard JSON",
            defaults={
                "parsing_method": "jsonpath",
                "field_mappings": {
                    "f": {"source": "f", "type": "jsonpath"},
                    "v": {"source": "v", "type": "jsonpath"},
                    "timestamp": {"source": "ts", "type": "jsonpath"}
                },
                "rule_type": "always"
            }
        )

        # PROV 2: Novus (API)
        novus_prov, _ = TelemetryProvider.objects.get_or_create(
            name="novus_api",
            defaults={
                "display_name": "Novus API (Test)",
                "provider_type": "http",
                "base_url": "https://novus.test/api",
                "is_active": True
            }
        )

        # 6. Link Point to Providers with specific Keys (Multi-Provider Support)
        
        # Link Nettra
        CatchmentPointProvider.objects.update_or_create(
            point=point,
            provider=nettra_prov,
            variable=var_caudal,
            defaults={"provider_variable_key": "f", "provider_device_id": "nettra_001"}
        )
        CatchmentPointProvider.objects.update_or_create(
            point=point,
            provider=nettra_prov,
            variable=var_total,
            defaults={"provider_variable_key": "v", "provider_device_id": "nettra_001"}
        )

        from api.telemetry.providers.mqtt_models import CatchmentPointMQTT
        CatchmentPointMQTT.objects.get_or_create(
            point=point,
            provider=nettra_prov,
            defaults={
                "custom_device_id": "nettra_001",
                "is_active": True
            }
        )


        # Novus uses 'flow_rate' and 'volume_total'
        CatchmentPointProvider.objects.get_or_create(
            point=point,
            provider=novus_prov,
            variable=var_caudal,
            defaults={"provider_variable_key": "flow_rate", "provider_device_id": "novus_99"}
        )

        self.stdout.write(self.style.SUCCESS("Test environment seeded successfully."))
        self.stdout.write(f"Point: {point.title} (ID: {point.id})")
        self.stdout.write(f"MQTT Topic (Nettra Simulation): telemetry/nettra_mqtt/nettra_001/data")
