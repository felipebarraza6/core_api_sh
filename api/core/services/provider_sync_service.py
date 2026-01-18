"""
Servicio de Sincronización Automática con Proveedores
Permite recuperar datos históricos y mantener sincronización en tiempo real
"""

import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from ..models import (
    EquipmentProvider, ProviderDataSync, IoTDevice,
    DataPoint, DataStream, VariableDefinition
)

logger = logging.getLogger(__name__)


class ProviderSyncService:
    """
    Servicio para sincronización automática de datos con proveedores externos
    """

    def __init__(self):
        self.http_client = None
        self.active_syncs = {}

    async def initialize(self):
        """Inicializar el servicio"""
        if not self.http_client:
            timeout = aiohttp.ClientTimeout(total=30)
            self.http_client = aiohttp.ClientSession(timeout=timeout)

    async def shutdown(self):
        """Cerrar el servicio"""
        if self.http_client:
            await self.http_client.close()

    async def sync_provider_data(self, sync_config: ProviderDataSync) -> Dict[str, Any]:
        """
        Sincronizar datos con un proveedor específico
        """
        try:
            await self.initialize()

            provider = sync_config.provider
            logger.info(f"Starting sync for provider {provider.name} ({sync_config.sync_type})")

            # Actualizar estado
            sync_config.update_sync_status('RUNNING')

            # Ejecutar sincronización según tipo
            if sync_config.sync_type == 'FULL_HISTORICAL':
                result = await self._sync_full_historical(provider, sync_config)
            elif sync_config.sync_type == 'INCREMENTAL':
                result = await self._sync_incremental(provider, sync_config)
            elif sync_config.sync_type == 'REALTIME':
                result = await self._sync_realtime(provider, sync_config)
            else:
                raise ValueError(f"Unsupported sync type: {sync_config.sync_type}")

            # Actualizar estado final
            if result['success']:
                status = 'SUCCESS' if result['records_processed'] > 0 else 'PARTIAL_SUCCESS'
                sync_config.update_sync_status(status, result['records_processed'])
            else:
                sync_config.update_sync_status('FAILED', error_message=result.get('error'))

            logger.info(f"Sync completed for {provider.name}: {result}")
            return result

        except Exception as exc:
            logger.error(f"Sync failed for provider {sync_config.provider.name}: {exc}")
            sync_config.update_sync_status('FAILED', error_message=str(exc))
            return {
                'success': False,
                'error': str(exc),
                'records_processed': 0
            }

    async def _sync_full_historical(self, provider: EquipmentProvider, sync_config: ProviderDataSync) -> Dict[str, Any]:
        """
        Sincronización histórica completa - recupera TODOS los datos históricos
        """
        logger.info(f"Starting full historical sync for {provider.name}")

        # Obtener configuración del proveedor
        base_url = provider.mqtt_broker_host  # Usar como base para APIs
        auth_config = self._get_provider_auth_config(provider)

        # Obtener dispositivos del proveedor
        devices = list(IoTDevice.objects.filter(
            equipment_model__provider=provider
        ).select_related('equipment_model'))

        total_processed = 0
        errors = []

        # Procesar cada dispositivo
        for device in devices:
            try:
                # Calcular fecha desde la que sincronizar
                start_date = self._get_sync_start_date(device, sync_config)

                # Sincronizar datos del dispositivo
                result = await self._sync_device_historical_data(
                    device, start_date, auth_config, sync_config
                )

                total_processed += result.get('processed', 0)

                if result.get('errors'):
                    errors.extend(result['errors'])

            except Exception as exc:
                logger.error(f"Failed to sync device {device.device_id}: {exc}")
                errors.append(f"Device {device.device_id}: {exc}")

        return {
            'success': len(errors) == 0,
            'records_processed': total_processed,
            'errors': errors,
            'devices_processed': len(devices)
        }

    async def _sync_incremental(self, provider: EquipmentProvider, sync_config: ProviderDataSync) -> Dict[str, Any]:
        """
        Sincronización incremental - solo datos nuevos desde última sync
        """
        logger.info(f"Starting incremental sync for {provider.name}")

        # Calcular fecha desde última sincronización exitosa
        if sync_config.last_successful_sync:
            start_date = sync_config.last_successful_sync - timedelta(hours=1)  # 1 hora de buffer
        else:
            start_date = timezone.now() - timedelta(days=7)  # Última semana por defecto

        # Usar la lógica de sync histórica pero con fecha más reciente
        result = await self._sync_full_historical(provider, sync_config)

        # Para incremental, podríamos optimizar consultando solo cambios
        # pero por simplicidad reutilizamos la lógica histórica

        return result

    async def _sync_realtime(self, provider: EquipmentProvider, sync_config: ProviderDataSync) -> Dict[str, Any]:
        """
        Sincronización en tiempo real - mantener conexión abierta
        """
        logger.info(f"Starting realtime sync for {provider.name}")

        # Para realtime, configurar webhooks o mantener conexión MQTT/WebSocket
        # Por ahora, implementar como polling frecuente

        result = await self._sync_incremental(provider, sync_config)

        # Programar siguiente sync en tiempo real
        # En producción, esto sería manejado por un scheduler o WebSocket

        return result

    async def _sync_device_historical_data(self, device: IoTDevice, start_date: datetime,
                                         auth_config: Dict, sync_config: ProviderDataSync) -> Dict[str, Any]:
        """
        Sincronizar datos históricos de un dispositivo específico
        """
        try:
            # Obtener endpoint del proveedor para datos históricos
            endpoint_config = sync_config.sync_config.get('historical_endpoint', {})

            if not endpoint_config:
                return {'processed': 0, 'errors': ['No historical endpoint configured']}

            # Preparar request
            url = endpoint_config.get('url', '').format(device_id=device.device_id)
            method = endpoint_config.get('method', 'GET')
            params = {
                'start_date': start_date.isoformat(),
                'end_date': timezone.now().isoformat(),
                'device_id': device.device_id
            }

            # Hacer request con autenticación
            headers = self._prepare_auth_headers(auth_config)

            async with self.http_client.request(
                method, url, headers=headers, params=params if method == 'GET' else None,
                json=params if method == 'POST' else None
            ) as response:

                if response.status != 200:
                    error_text = await response.text()
                    return {
                        'processed': 0,
                        'errors': [f"HTTP {response.status}: {error_text}"]
                    }

                data = await response.json()

                # Procesar y guardar datos
                processed_count = await self._process_provider_data_response(device, data)

                return {
                    'processed': processed_count,
                    'errors': []
                }

        except Exception as exc:
            logger.error(f"Failed to sync historical data for device {device.device_id}: {exc}")
            return {
                'processed': 0,
                'errors': [str(exc)]
            }

    async def _process_provider_data_response(self, device: IoTDevice, data: Dict) -> int:
        """
        Procesar respuesta de datos del proveedor y guardarlos
        """
        processed_count = 0

        try:
            # Obtener streams del dispositivo
            streams = list(device.data_streams.filter(is_active=True))

            if not streams:
                logger.warning(f"No active streams for device {device.device_id}")
                return 0

            # Procesar cada registro de datos
            records = data.get('records', data.get('data', []))

            for record in records:
                try:
                    await self._process_single_data_record(device, streams, record)
                    processed_count += 1

                except Exception as exc:
                    logger.error(f"Failed to process record for device {device.device_id}: {exc}")

            # Commit transaction
            logger.info(f"Processed {processed_count} records for device {device.device_id}")

        except Exception as exc:
            logger.error(f"Failed to process provider data response: {exc}")

        return processed_count

    async def _process_single_data_record(self, device: IoTDevice, streams: List[DataStream], record: Dict):
        """
        Procesar un registro individual de datos
        """
        # Extraer timestamp
        timestamp_str = record.get('timestamp') or record.get('collected_at')
        if timestamp_str:
            collected_at = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            collected_at = timezone.make_aware(collected_at) if timezone.is_naive(collected_at) else collected_at
        else:
            collected_at = timezone.now()

        # Procesar cada stream
        for stream in streams:
            # Crear DataPoint con el dato crudo
            raw_value = self._extract_raw_value_for_stream(record, stream)

            if raw_value is not None:
                # Aplicar constantes históricas
                processed_value = await self._apply_historical_constants(
                    device, stream, raw_value, collected_at
                )

                # Crear el punto de dato
                await self._create_data_point_async(
                    stream=stream,
                    device=device,
                    collected_at=collected_at,
                    raw_value=str(raw_value),
                    processed_value=processed_value,
                    record_metadata=record
                )

    def _extract_raw_value_for_stream(self, record: Dict, stream: DataStream) -> Any:
        """
        Extraer el valor raw para un stream específico del registro
        """
        # Configuración de mapeo del stream
        field_mapping = stream.transformations.get('field_mapping', {})

        # Buscar el campo correspondiente
        for stream_var in stream.variables.all():
            field_name = field_mapping.get(stream_var.code, stream_var.code.lower())

            if field_name in record:
                return record[field_name]

        # Si no se encuentra mapeo específico, buscar campos comunes
        common_fields = ['value', 'data', 'measurement', stream.name.lower()]
        for field in common_fields:
            if field in record:
                return record[field]

        return None

    async def _apply_historical_constants(self, device: IoTDevice, stream: DataStream,
                                        raw_value: Any, collected_at: datetime) -> Optional[float]:
        """
        Aplicar constantes históricas al valor raw
        """
        try:
            from ..models.constants_system import ConstantDefinition, ConstantApplication

            # Buscar constantes aplicables para este dispositivo/stream/fecha
            applicable_constants = ConstantApplication.objects.filter(
                is_active=True,
                start_date__lte=collected_at,
                end_date__gte=collected_at
            ).filter(
                models.Q(constant__device=device) |
                models.Q(constant__point=device.catchment_point) |
                (models.Q(constant__device__isnull=True) & models.Q(constant__point__isnull=True))
            ).select_related('constant').order_by('-constant__priority')

            # Aplicar constantes en orden de prioridad
            processed_value = float(raw_value) if isinstance(raw_value, (int, float, str)) and str(raw_value).replace('.', '').isdigit() else None

            if processed_value is not None:
                for application in applicable_constants:
                    constant = application.constant

                    if constant.constant_type == 'TOTALIZER_OFFSET':
                        processed_value += float(constant.value_numeric)
                    elif constant.constant_type == 'FLOW_MULTIPLIER':
                        processed_value *= float(constant.value_numeric)
                    elif constant.constant_type == 'LEVEL_OFFSET':
                        processed_value += float(constant.value_numeric)
                    # Agregar más tipos de constantes según necesidad

            return processed_value

        except Exception as exc:
            logger.error(f"Error applying historical constants: {exc}")
            return None

    async def _create_data_point_async(self, stream, device, collected_at, raw_value,
                                     processed_value, record_metadata):
        """
        Crear DataPoint de forma asíncrona
        """
        # En Django, las operaciones de DB son síncronas, pero podemos usar
        # asyncio.to_thread para no bloquear el event loop
        await asyncio.to_thread(
            self._create_data_point_sync,
            stream, device, collected_at, raw_value, processed_value, record_metadata
        )

    def _create_data_point_sync(self, stream, device, collected_at, raw_value,
                               processed_value, record_metadata):
        """
        Crear DataPoint de forma síncrona
        """
        with transaction.atomic():
            DataPoint.objects.create(
                stream=stream,
                device=device,
                point=device.catchment_point,
                collected_at=collected_at,
                received_at=timezone.now(),
                raw_value=raw_value,
                processed_value=processed_value,
                metadata=record_metadata,
                is_valid=True  # Asumir válido inicialmente
            )

    def _get_provider_auth_config(self, provider: EquipmentProvider) -> Dict:
        """Obtener configuración de autenticación del proveedor"""
        # Implementar según el tipo de autenticación del proveedor
        return {
            'type': 'bearer',  # o 'basic', 'api_key', etc.
            'token': getattr(provider, 'api_token', ''),
            'username': getattr(provider, 'api_username', ''),
            'password': getattr(provider, 'api_password', ''),
        }

    def _prepare_auth_headers(self, auth_config: Dict) -> Dict:
        """Preparar headers de autenticación"""
        headers = {}

        auth_type = auth_config.get('type', 'bearer')

        if auth_type == 'bearer':
            headers['Authorization'] = f"Bearer {auth_config.get('token', '')}"
        elif auth_type == 'basic':
            # Implementar basic auth si es necesario
            pass

        headers['Content-Type'] = 'application/json'
        headers['User-Agent'] = 'SmartHydro-Sync/1.0'

        return headers

    def _get_sync_start_date(self, device: IoTDevice, sync_config: ProviderDataSync) -> datetime:
        """Calcular fecha de inicio para sincronización"""
        # Si es primera sync, ir 30 días atrás
        if not sync_config.last_successful_sync:
            return timezone.now() - timedelta(days=30)

        # Si es sync incremental, ir desde última sync con buffer
        buffer_hours = sync_config.sync_config.get('buffer_hours', 1)
        return sync_config.last_successful_sync - timedelta(hours=buffer_hours)


# Instancia global del servicio
provider_sync_service = ProviderSyncService()