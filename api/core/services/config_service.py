"""
Servicio de Configuración Dinámica del Sistema

Permite leer configuraciones desde SystemConfiguration con fallback a valores por defecto.
Todas las configuraciones hardcodeadas deben migrarse a usar este servicio.
"""

import logging
from typing import Any, Dict, Optional, Union
from django.core.cache import cache

from api.telemetry.models.management_super import SystemConfiguration

logger = logging.getLogger(__name__)


class ConfigService:
    """Servicio centralizado para obtener configuraciones del sistema."""

    CACHE_TIMEOUT = 300  # 5 minutos de cache

    # Valores por defecto para todas las configuraciones
    DEFAULT_CONFIGS = {
        # ===== TELEMETRY - Protecciones Anti-Disparo =====
        'telemetry.max_flow_ls': {
            'value': 150.0,
            'description': 'Máximo caudal razonable en L/s',
            'category': 'TELEMETRY'
        },
        'telemetry.max_time_gap_hours': {
            'value': 2,
            'description': 'Si Δt > X horas, no calcular (reconexión)',
            'category': 'TELEMETRY'
        },
        'telemetry.max_diff_m3_per_hour': {
            'value': 500,
            'description': 'Máximo consumo razonable por hora',
            'category': 'TELEMETRY'
        },
        'telemetry.max_diff_m3_per_day': {
            'value': 10000,
            'description': 'Máximo consumo razonable por día',
            'category': 'TELEMETRY'
        },
        'telemetry.pulses_factor_default': {
            'value': 1000,
            'description': 'Factor de pulsos por defecto',
            'category': 'TELEMETRY'
        },
        'telemetry.max_value_precision': {
            'value': 1000,
            'description': 'Valor máximo para precisión de cálculos',
            'category': 'TELEMETRY'
        },

        # ===== MAINTENANCE - Políticas de Retención =====
        'maintenance.telemetry_retention_days': {
            'value': 90,
            'description': 'Días de retención para datos de telemetría',
            'category': 'PERFORMANCE'
        },
        'maintenance.notifications_retention_days': {
            'value': 180,
            'description': 'Días de retención para notificaciones',
            'category': 'PERFORMANCE'
        },
        'maintenance.backup_keep_count': {
            'value': 7,
            'description': 'Número de backups a mantener',
            'category': 'PERFORMANCE'
        },

        # ===== RETRY - Políticas de Reintento =====
        'retry.max_retries': {
            'value': 3,
            'description': 'Número máximo de reintentos',
            'category': 'PERFORMANCE'
        },
        'retry.backoff_factor': {
            'value': 2,
            'description': 'Factor de espera exponencial',
            'category': 'PERFORMANCE'
        },
        'retry.max_backoff_seconds': {
            'value': 3600,
            'description': 'Tiempo máximo de espera entre reintentos (segundos)',
            'category': 'PERFORMANCE'
        },

        # ===== CACHE =====
        'cache.telemetry_ttl': {
            'value': 900,
            'description': 'TTL para cache de telemetría (segundos)',
            'category': 'PERFORMANCE'
        },
        'cache.config_ttl': {
            'value': 300,
            'description': 'TTL para cache de configuraciones (segundos)',
            'category': 'PERFORMANCE'
        },
    }

    @classmethod
    def get(
        cls,
        key: str,
        default: Optional[Any] = None,
        use_cache: bool = True
    ) -> Any:
        """
        Obtener valor de configuración desde BD o usar default.

        Args:
            key: Clave de configuración (ej: 'telemetry.max_flow_ls')
            default: Valor por defecto si no existe en BD ni en DEFAULT_CONFIGS
            use_cache: Usar cache para mejorar performance

        Returns:
            Valor de configuración (puede ser cualquier tipo JSON)
        """
        # 1. Intentar desde cache
        if use_cache:
            cache_key = f'config:{key}'
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value

        # 2. Intentar desde BD
        try:
            config = SystemConfiguration.objects.filter(key=key).first()
            if config:
                value = config.value
                # Guardar en cache
                if use_cache:
                    cache.set(
                        cache_key,
                        value,
                        cls.CACHE_TIMEOUT
                    )
                return value
        except Exception as e:
            logger.warning(
                "Error obteniendo configuración %s desde BD: %s",
                key,
                e
            )

        # 3. Usar default de DEFAULT_CONFIGS
        if key in cls.DEFAULT_CONFIGS:
            default_value = cls.DEFAULT_CONFIGS[key]['value']
            # Guardar en cache
            if use_cache:
                cache_key = f'config:{key}'
                cache.set(
                    cache_key,
                    default_value,
                    cls.CACHE_TIMEOUT
                )
            return default_value

        # 4. Usar default proporcionado
        if default is not None:
            return default

        # 5. Error: no existe configuración
        logger.warning(
            "Configuración '%s' no encontrada y sin default",
            key
        )
        return None

    @classmethod
    def get_int(
        cls,
        key: str,
        default: Optional[int] = None
    ) -> int:
        """Obtener configuración como entero."""
        value = cls.get(key, default)
        try:
            return int(value)
        except (ValueError, TypeError):
            logger.warning(
                "Configuración '%s' no es un entero válido: %s",
                key,
                value
            )
            return default if default is not None else 0

    @classmethod
    def get_float(
        cls,
        key: str,
        default: Optional[float] = None
    ) -> float:
        """Obtener configuración como float."""
        value = cls.get(key, default)
        try:
            return float(value)
        except (ValueError, TypeError):
            logger.warning(
                "Configuración '%s' no es un float válido: %s",
                key,
                value
            )
            return default if default is not None else 0.0

    @classmethod
    def get_bool(
        cls,
        key: str,
        default: Optional[bool] = None
    ) -> bool:
        """Obtener configuración como booleano."""
        value = cls.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'on')
        return bool(value) if value is not None else (default or False)

    @classmethod
    def set(
        cls,
        key: str,
        value: Any,
        category: str = 'TELEMETRY',
        description: str = '',
        is_encrypted: bool = False
    ) -> SystemConfiguration:
        """
        Crear o actualizar configuración.

        Args:
            key: Clave de configuración
            value: Valor (cualquier tipo JSON)
            category: Categoría de configuración
            description: Descripción
            is_encrypted: Si el valor está encriptado

        Returns:
            SystemConfiguration creado/actualizado
        """
        config, created = SystemConfiguration.objects.update_or_create(
            key=key,
            defaults={
                'value': value,
                'category': category,
                'description': description,
                'is_encrypted': is_encrypted
            }
        )

        # Invalidar cache
        cache_key = f'config:{key}'
        cache.delete(cache_key)

        logger.info(
            "%s configuración '%s'",
            "Creada" if created else "Actualizada",
            key
        )

        return config

    @classmethod
    def initialize_defaults(cls) -> Dict[str, bool]:
        """
        Inicializar todas las configuraciones por defecto en BD.

        Returns:
            Dict con {key: created} indicando qué se creó
        """
        results = {}
        for key, config_data in cls.DEFAULT_CONFIGS.items():
            try:
                config, created = SystemConfiguration.objects.get_or_create(
                    key=key,
                    defaults={
                        'value': config_data['value'],
                        'category': config_data['category'],
                        'description': config_data['description']
                    }
                )
                results[key] = created
            except Exception as e:
                logger.error(
                    "Error inicializando configuración '%s': %s",
                    key,
                    e
                )
                results[key] = False

        logger.info(
            "Inicializadas %d configuraciones por defecto",
            sum(1 for v in results.values() if v)
        )

        return results

    @classmethod
    def clear_cache(cls, key: Optional[str] = None):
        """
        Limpiar cache de configuraciones.

        Args:
            key: Clave específica a limpiar, o None para limpiar todas
        """
        if key:
            cache_key = f'config:{key}'
            cache.delete(cache_key)
        else:
            # Limpiar todas las configuraciones del cache
            # Nota: Esto es costoso, solo usar cuando sea necesario
            for config_key in cls.DEFAULT_CONFIGS.keys():
                cache_key = f'config:{config_key}'
                cache.delete(cache_key)
