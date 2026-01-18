"""
Celery Tasks for MQTT Operations
Gestión de conexiones MQTT y procesamiento de mensajes
"""

import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import asyncio

from api.core.services.mqtt_service import mqtt_service
from api.core.models import (
    EquipmentProvider, MQTTConnection, IoTDevice,
    SystemConfiguration
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, retry_backoff=True)
def initialize_mqtt_connections(self):
    """
    Inicializar todas las conexiones MQTT activas
    """
    try:
        logger.info("Initializing MQTT connections...")

        # Ejecutar inicialización async
        asyncio.run(mqtt_service.initialize_connections())

        logger.info("MQTT connections initialization completed")

        return {'status': 'success', 'message': 'MQTT connections initialized'}

    except Exception as exc:
        logger.error(f"MQTT initialization failed: {exc}")
        self.retry(countdown=60, exc=exc)


@shared_task(bind=True, max_retries=2)
def manage_mqtt_connection(self, connection_id: int, action: str):
    """
    Gestionar conexión MQTT específica
    Actions: start, stop, restart, check_status
    """
    try:
        from api.core.models import MQTTConnection

        connection = MQTTConnection.objects.get(id=connection_id)

        if action == 'start':
            asyncio.run(mqtt_service.start_connection(connection))
            message = f"MQTT connection started: {connection.connection_name}"

        elif action == 'stop':
            asyncio.run(mqtt_service.stop_connection(connection))
            message = f"MQTT connection stopped: {connection.connection_name}"

        elif action == 'restart':
            asyncio.run(mqtt_service.stop_connection(connection))
            asyncio.run(mqtt_service.start_connection(connection))
            message = f"MQTT connection restarted: {connection.connection_name}"

        elif action == 'check_status':
            # La verificación se hace automáticamente en los callbacks
            message = f"MQTT connection status: {connection.status}"

        else:
            raise ValueError(f"Unknown action: {action}")

        logger.info(message)
        return {'status': 'success', 'action': action, 'message': message}

    except Exception as exc:
        logger.error(f"MQTT connection management failed: {exc}")
        self.retry(countdown=30, exc=exc)


@shared_task(bind=True)
def monitor_mqtt_connections(self):
    """
    Monitorear estado de todas las conexiones MQTT
    """
    try:
        logger.info("Monitoring MQTT connections...")

        connections = MQTTConnection.objects.filter(is_active=True)

        status_report = {
            'total_connections': connections.count(),
            'connected': 0,
            'disconnected': 0,
            'errors': 0,
            'details': []
        }

        for connection in connections:
            client = mqtt_service.clients.get(connection.client_id)
            is_connected = client is not None and getattr(client, 'is_connected', lambda: False)()

            if is_connected:
                status_report['connected'] += 1
            elif connection.status == 'ERROR':
                status_report['errors'] += 1
            else:
                status_report['disconnected'] += 1

            status_report['details'].append({
                'id': connection.id,
                'name': connection.connection_name,
                'provider': connection.provider.name,
                'status': connection.status,
                'is_connected': is_connected,
                'last_connected': connection.last_connected.isoformat() if connection.last_connected else None,
                'messages_today': connection.messages_received_today
            })

        # Generar alertas si hay problemas
        if status_report['errors'] > 0:
            logger.warning(f"MQTT connections with errors: {status_report['errors']}")

        if status_report['disconnected'] > status_report['connected']:
            logger.warning("More disconnected than connected MQTT connections")

        logger.info(f"MQTT monitoring completed: {status_report['connected']} connected, {status_report['errors']} errors")

        return status_report

    except Exception as exc:
        logger.error(f"MQTT monitoring failed: {exc}")
        return {'status': 'error', 'message': str(exc)}


@shared_task(bind=True)
def send_command_to_device(self, device_id: str, command: str, params: dict = None):
    """
    Enviar comando a dispositivo IoT vía MQTT
    """
    try:
        logger.info(f"Sending command '{command}' to device {device_id}")

        device = IoTDevice.objects.select_related(
            'equipment_model__provider'
        ).get(device_id=device_id)

        # Enviar comando usando el servicio MQTT
        asyncio.run(
            mqtt_service.send_command_to_device(device, command, params)
        )

        logger.info(f"Command '{command}' sent successfully to device {device_id}")

        return {
            'status': 'success',
            'device_id': device_id,
            'command': command,
            'params': params
        }

    except IoTDevice.DoesNotExist:
        error_msg = f"Device not found: {device_id}"
        logger.error(error_msg)
        return {'status': 'error', 'message': error_msg}

    except Exception as exc:
        logger.error(f"Failed to send command to device {device_id}: {exc}")
        self.retry(countdown=30, exc=exc)


@shared_task(bind=True)
def broadcast_to_provider_devices(self, provider_code: str, command: str, params: dict = None):
    """
    Enviar comando broadcast a todos los dispositivos de un proveedor
    """
    try:
        logger.info(f"Broadcasting command '{command}' to provider {provider_code}")

        provider = EquipmentProvider.objects.get(code=provider_code)

        # Obtener todos los dispositivos activos del proveedor
        devices = IoTDevice.objects.filter(
            equipment_model__provider=provider,
            status__in=['ONLINE', 'BATTERY_LOW']
        )

        # Enviar a cada dispositivo
        sent_count = 0
        error_count = 0

        for device in devices:
            try:
                asyncio.run(
                    mqtt_service.send_command_to_device(device, command, params)
                )
                sent_count += 1
            except Exception as exc:
                logger.error(f"Failed to send command to device {device.device_id}: {exc}")
                error_count += 1

        logger.info(f"Broadcast completed: {sent_count} sent, {error_count} errors")

        return {
            'status': 'success',
            'provider': provider_code,
            'command': command,
            'devices_total': devices.count(),
            'sent': sent_count,
            'errors': error_count
        }

    except EquipmentProvider.DoesNotExist:
        error_msg = f"Provider not found: {provider_code}"
        logger.error(error_msg)
        return {'status': 'error', 'message': error_msg}

    except Exception as exc:
        logger.error(f"Broadcast failed for provider {provider_code}: {exc}")
        self.retry(countdown=60, exc=exc)


@shared_task(bind=True)
def sync_device_status(self):
    """
    Sincronizar estado de dispositivos basado en actividad MQTT reciente
    """
    try:
        logger.info("Syncing device status from MQTT activity...")

        # Definir tiempo de inactividad
        offline_threshold = timezone.now() - timedelta(minutes=30)

        # Marcar dispositivos offline si no han enviado datos recientemente
        offline_devices = IoTDevice.objects.filter(
            status__in=['ONLINE', 'BATTERY_LOW'],
            last_seen__lt=offline_threshold
        )

        offline_count = offline_devices.update(status='OFFLINE')

        # Verificar dispositivos que deberían estar online
        potentially_online = IoTDevice.objects.filter(
            status='OFFLINE',
            last_seen__gte=offline_threshold
        )

        online_count = 0
        for device in potentially_online:
            if device.is_online():
                device.status = 'ONLINE'
                device.save()
                online_count += 1

        logger.info(f"Device status sync completed: {offline_count} marked offline, {online_count} marked online")

        return {
            'status': 'success',
            'offline_marked': offline_count,
            'online_marked': online_count
        }

    except Exception as exc:
        logger.error(f"Device status sync failed: {exc}")
        self.retry(countdown=300, exc=exc)


@shared_task(bind=True)
def reset_mqtt_daily_stats(self):
    """
    Reset estadísticas diarias de conexiones MQTT
    """
    try:
        logger.info("Resetting MQTT daily statistics...")

        updated = MQTTConnection.objects.update(
            messages_received_today=0,
            messages_sent_today=0,
            bytes_received_today=0
        )

        logger.info(f"Reset {updated} MQTT connection daily statistics")

        return {'status': 'success', 'connections_reset': updated}

    except Exception as exc:
        logger.error(f"Failed to reset MQTT daily stats: {exc}")
        return {'status': 'error', 'message': str(exc)}


@shared_task(bind=True)
def test_provider_endpoint(self, provider_code: str, test_payload: dict = None):
    """
    Probar endpoint específico de proveedor
    """
    try:
        logger.info(f"Testing provider endpoint: {provider_code}")

        provider = EquipmentProvider.objects.get(code=provider_code)

        # Payload de prueba por defecto
        if test_payload is None:
            test_payload = {
                'device_id': f'test_device_{provider_code}',
                'timestamp': timezone.now().isoformat(),
                'test_data': True,
                'flow': 25.5,
                'level': 12.3
            }

        # Simular procesamiento
        from api.core.mqtt_broker import mqtt_broker

        # Registrar endpoint de prueba si no existe
        if provider_code not in mqtt_broker.provider_endpoints:
            asyncio.run(mqtt_broker.register_provider_endpoint(provider_code, {
                'topics': [f'{provider_code}/test/#'],
                'processors': [{
                    'type': 'telemetry',
                    'topic_pattern': f'{provider_code}/test/',
                    'device_id_extractor': 'payload'
                }]
            }))

        # Procesar mensaje de prueba
        test_topic = f'{provider_code}/test/telemetry'
        asyncio.run(mqtt_broker.process_provider_message(
            provider_code, test_topic, test_payload
        ))

        logger.info(f"Provider endpoint test completed for {provider_code}")

        return {
            'status': 'success',
            'provider': provider_code,
            'test_topic': test_topic,
            'test_payload': test_payload
        }

    except Exception as exc:
        logger.error(f"Provider endpoint test failed: {exc}")
        return {'status': 'error', 'message': str(exc)}