"""
Servicio de Sincronización Automática con Proveedores (Arquitectura v3)
Permite recuperar datos históricos y mantener sincronización en tiempo real
usando TelemetryProvider y CatchmentPointProvider.
"""

import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from django.db import models

from api.telemetry.providers.models import (
    TelemetryProvider, ProviderDataSync, CatchmentPointProvider
)
from api.telemetry.models import (
    DataPoint, DataStream, VariableDefinition
)
from api.infrastructure.models import Device

logger = logging.getLogger(__name__)


class ProviderSyncService:
    """
    Servicio para sincronización automática de datos con proveedores externos
    (Modelo TelemetryProvider)
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
            logger.info(f"Starting sync for TelemetryProvider {provider.name} ({sync_config.sync_type})")

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

    async def _sync_full_historical(self, provider: TelemetryProvider, sync_config: ProviderDataSync) -> Dict[str, Any]:
        """
        Sincronización histórica completa - recupera datos para todos los Puntos activos
        asociados a este proveedor.
        """
        logger.info(f"Starting full historical sync for {provider.name}")

        # 1. Obtener configuraciones activas (Puntos suscritos a este proveedor)
        point_configs = list(CatchmentPointProvider.objects.filter(
            provider=provider,
            is_active=True
        ).select_related('point', 'device'))

        total_processed = 0
        errors = []

        # 2. Procesar cada punto
        for config in point_configs:
            try:
                # Obtener credenciales efectivas (con override si existe)
                auth_config = config.get_effective_config()
                
                # Calcular fecha desde la que sincronizar
                start_date = self._get_sync_start_date(config, sync_config)

                # Sincronizar datos del punto
                result = await self._sync_point_data(
                    config, start_date, auth_config, sync_config
                )

                total_processed += result.get('processed', 0)

                if result.get('errors'):
                    errors.extend(result['errors'])
                    config.record_error(str(result['errors'][0]))
                else:
                    config.record_success()

            except Exception as exc:
                logger.error(f"Failed to sync point {config.point.point_code}: {exc}")
                errors.append(f"Point {config.point.point_code}: {exc}")
                config.record_error(str(exc))

        return {
            'success': len(errors) == 0,
            'records_processed': total_processed,
            'errors': errors,
            'points_processed': len(point_configs)
        }

    async def _sync_incremental(self, provider: TelemetryProvider, sync_config: ProviderDataSync) -> Dict[str, Any]:
        """
        Sincronización incremental - usa la misma lógica pero se basa en la fecha de última sync.
        """
        # La lógica de fecha se maneja en _get_sync_start_date
        return await self._sync_full_historical(provider, sync_config)

    async def _sync_realtime(self, provider: TelemetryProvider, sync_config: ProviderDataSync) -> Dict[str, Any]:
        """
        Sincronización realtime (polling frecuente).
        Igual que incremental pero pensado para correr cada minuto.
        """
        return await self._sync_incremental(provider, sync_config)

    async def _sync_point_data(self, point_config: CatchmentPointProvider, start_date: datetime,
                             auth_config: Dict, sync_config: ProviderDataSync) -> Dict[str, Any]:
        """
        Sincronizar datos para un Punto específico configuado con este proveedor.
        """
        try:
            provider = point_config.provider
            
            # 1. Construir URL y Payload usando Templates del Proveedor
            # Variables disponibles para el template
            template_vars = {
                'device_id': point_config.provider_device_id, # ID externo
                'point_code': point_config.point.point_code,
                'start_date': start_date.isoformat(),
                'end_date': timezone.now().isoformat(),
            }
            
            try:
                url = provider.build_endpoint_url(**template_vars)
                payload_template = provider.request_template
                # Si hay payload body (POST), construirlo
                json_body = None
                if payload_template:
                   json_body = provider.build_request_payload(**template_vars)
                   
            except ValueError as e:
                return {'processed': 0, 'errors': [f"Template error: {e}"]}

            # 2. Hacer Request
            method = 'POST' if json_body else 'GET'
            headers = provider.get_auth_headers()
            headers['Content-Type'] = 'application/json'
            headers['User-Agent'] = 'SmartHydro-Sync/3.0'

            async with self.http_client.request(
                method, url, headers=headers, json=json_body
            ) as response:

                if response.status not in [200, 201]:
                    error_text = await response.text()
                    return {
                        'processed': 0,
                        'errors': [f"HTTP {response.status}: {error_text}"]
                    }

                data = await response.json()

                # 3. Procesar Respuesta (Mapeo)
                processed_count = await self._process_provider_response(point_config, data)

                return {
                    'processed': processed_count,
                    'errors': []
                }

        except Exception as exc:
            logger.error(f"Failed to sync point {point_config.point.point_code}: {exc}")
            return {
                'processed': 0,
                'errors': [str(exc)]
            }

    async def _process_provider_response(self, point_config: CatchmentPointProvider, data: Dict) -> int:
        """
        Procesar la respuesta cruda del proveedor y guardar DataPoints.
        """
        processed_count = 0
        provider = point_config.provider
        
        # Detectar lista de registros en la respuesta
        # Asumimos que data es lista, o tiene una key 'data' o 'records'
        records = data
        if isinstance(data, dict):
            records = data.get('records', data.get('data', [data]))
            
        if not isinstance(records, list):
            records = [records]

        # Obtener mapeo de respuesta
        response_mapping = provider.response_mapping or {}

        for record in records:
            try:
                await self._process_single_record(point_config, record, response_mapping)
                processed_count += 1
            except Exception as e:
                logger.error(f"Error processing record for {point_config}: {e}")
                
        return processed_count

    async def _process_single_record(self, point_config: CatchmentPointProvider, record: Dict, mapping: Dict):
        """
        Extraer datos de un registro individual y guardar.
        """
        # 1. Extraer Timestamp (usando path 'data.ts' etc)
        timestamp = timezone.now() # Default
        ts_field = mapping.get('timestamp')
        if ts_field and ts_field in record:
            # Parse timestamp (asumimos ISO por ahora, mejorar parsing luego)
            try:
                ts_str = record[ts_field]
                timestamp = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            except:
                pass
                
        # 2. Extraer Valores según Streams del Device (si hay device) o Variables del Punto
        # Por simplicidad en V3, guardamos en TelemetryRecord (JSON) y DataPoint (Granular)
        
        # Preparar data JSON plana
        flat_data = {}
        
        # Iterar keys del record y mapear si es necesario
        for key, value in record.items():
            # Aquí se podría usar mapping inverso para normalizar claves
            flat_data[key] = value
            
        # 3. Guardar (Usando helper sincrono)
        await asyncio.to_thread(
            self._save_telemetry_sync,
            point_config, timestamp, flat_data
        )

    def _save_telemetry_sync(self, point_config, timestamp, data):
        """Guardado síncrono en DB."""
        from api.telemetry.models import TelemetryRecord
        
        with transaction.atomic():
            # 1. Guardar TelemetryRecord (V2 style - Compatible con Dashboard anterior)
            TelemetryRecord.objects.create(
                point=point_config.point,
                timestamp=timestamp,
                data=data,
                metadata={'provider_id': point_config.provider.id, 'source': 'sync_service'}
            )
            
            # 2. Guardar DataPoints (V3 style - Granular)
            # Para esto necesitaríamos mapear Streams. Por ahora V2 es suficiente para prototipo.
            # (El usuario pidió prototipo funcional, y Dashboard V2 usa TelemetryRecord)

    def _get_sync_start_date(self, point_config: CatchmentPointProvider, sync_config: ProviderDataSync) -> datetime:
        """Calcular fecha de inicio."""
        if point_config.last_success:
             # Buffer de seguridad para no perder datos
            return point_config.last_success - timedelta(hours=1)
        
        return timezone.now() - timedelta(days=7) # Default 1 semana atrás


# Instancia global del servicio
provider_sync_service = ProviderSyncService()