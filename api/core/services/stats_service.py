"""
Servicio de Estadísticas en Tiempo Real
Proporciona métricas automáticas para el frontend
"""

import time
from datetime import timedelta
from typing import Any, Dict

import psutil
from django.core.cache import cache
from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.utils import timezone

from api.telemetry.models import TelemetryRecord, IoTDevice, MQTTConnection


class StatsService:
    """Servicio para estadísticas del sistema en tiempo real"""

    CACHE_TIMEOUT = 30  # 30 segundos de cache para stats en tiempo real

    @staticmethod
    def get_realtime_stats() -> Dict[str, Any]:
        """
        Obtener estadísticas en tiempo real del sistema
        """
        cache_key = "system_realtime_stats"

        # Intentar obtener de cache primero
        cached_stats = cache.get(cache_key)
        if cached_stats:
            return cached_stats

        # Calcular stats en tiempo real
        stats = {
            "api_performance": StatsService._get_api_performance_stats(),
            "telemetry_health": StatsService._get_telemetry_health_stats(),
            "device_status": StatsService._get_device_status_stats(),
            "mqtt_status": StatsService._get_mqtt_status_stats(),
            "system_resources": StatsService._get_system_resources_stats(),
            "calculated_at": timezone.now().isoformat(),
        }

        # Cache por 30 segundos
        cache.set(cache_key, stats, StatsService.CACHE_TIMEOUT)

        return stats

    @staticmethod
    def get_empty_stats() -> Dict[str, Any]:
        """Retornar estructura vacía de stats para usuarios sin puntos"""
        return {
            "api_performance": {"status": "no_data"},
            "telemetry_health": {"status": "no_points"},
            "device_status": {"status": "no_devices"},
            "mqtt_status": {"status": "no_connections"},
            "system_resources": {"status": "ok"},
            "calculated_at": timezone.now().isoformat(),
        }

    @staticmethod
    def _get_api_performance_stats() -> Dict[str, Any]:
        """Estadísticas de performance de la API"""
        try:
            # Simular métricas de API (en producción usar middleware)
            now = timezone.now()
            one_hour_ago = now - timedelta(hours=1)

            # Contar requests recientes (simulado)
            recent_requests = 0  # Se implementaría con un modelo de logs

            # Calcular tiempos de respuesta promedio (simulado)
            avg_response_time = 0.15  # 150ms promedio

            # Tasa de error (simulado)
            error_rate = 0.02  # 2% de errores

            return {
                "avg_response_time_seconds": avg_response_time,
                "requests_per_minute": recent_requests,
                "error_rate_percent": error_rate * 100,
                "uptime_percent": 99.9,
                "status": "healthy" if error_rate < 0.05 else "warning",
            }

        except Exception as exc:
            return {"error": str(exc), "status": "error"}

    @staticmethod
    def _get_telemetry_health_stats() -> Dict[str, Any]:
        """Estadísticas de salud de la telemetría"""
        try:
            now = timezone.now()
            one_hour_ago = now - timedelta(hours=1)
            one_day_ago = now - timedelta(days=1)

            # Ingestión por hora
            hourly_ingestion = TelemetryRecord.objects.filter(
                timestamp__gte=one_hour_ago
            ).count()

            # Ingestión por día
            daily_ingestion = TelemetryRecord.objects.filter(
                timestamp__gte=one_day_ago
            ).count()

            # Tasa de error
            error_records = TelemetryRecord.objects.filter(
                timestamp__gte=one_hour_ago, is_error=True
            ).count()

            error_rate = (
                (error_records / hourly_ingestion * 100) if hourly_ingestion > 0 else 0
            )

            # Cobertura temporal (cuántos puntos tienen datos recientes)
            active_points_hour = (
                TelemetryRecord.objects.filter(timestamp__gte=one_hour_ago)
                .values("point")
                .distinct()
                .count()
            )

            active_points_day = (
                TelemetryRecord.objects.filter(timestamp__gte=one_day_ago)
                .values("point")
                .distinct()
                .count()
            )

            return {
                "hourly_ingestion_rate": hourly_ingestion,
                "daily_ingestion_rate": daily_ingestion,
                "ingestion_per_minute": hourly_ingestion / 60,
                "error_rate_percent": error_rate,
                "active_points_last_hour": active_points_hour,
                "active_points_last_day": active_points_day,
                "data_quality_score": max(0, 100 - error_rate),
                "status": (
                    "healthy"
                    if error_rate < 5
                    else "warning" if error_rate < 15 else "critical"
                ),
            }

        except Exception as exc:
            return {"error": str(exc), "status": "error"}

    @staticmethod
    def _get_device_status_stats() -> Dict[str, Any]:
        """Estadísticas del estado de dispositivos IoT"""
        try:
            total_devices = IoTDevice.objects.count()

            if total_devices == 0:
                return {"total_devices": 0, "status": "no_devices"}

            # Estado de dispositivos
            device_status = (
                IoTDevice.objects.values("status")
                .annotate(count=Count("id"))
                .order_by("status")
            )

            status_counts = {item["status"]: item["count"] for item in device_status}

            # Dispositivos online (lectura en última hora)
            one_hour_ago = timezone.now() - timedelta(hours=1)
            online_devices = IoTDevice.objects.filter(
                last_seen__gte=one_hour_ago
            ).count()

            # Nivel de batería promedio
            battery_stats = IoTDevice.objects.exclude(
                battery_level__isnull=True
            ).aggregate(
                avg_battery=Avg("battery_level"),
                low_battery_count=Count("id", filter=Q(battery_level__lt=20)),
            )

            # Señal promedio
            signal_stats = IoTDevice.objects.exclude(
                signal_strength__isnull=True
            ).aggregate(
                avg_signal=Avg("signal_strength"),
                poor_signal_count=Count("id", filter=Q(signal_strength__lt=-80)),
            )

            return {
                "total_devices": total_devices,
                "online_devices": online_devices,
                "offline_devices": total_devices - online_devices,
                "status_distribution": status_counts,
                "battery_avg_percent": float(battery_stats["avg_battery"] or 0),
                "low_battery_devices": battery_stats["low_battery_count"] or 0,
                "signal_avg_dbm": float(signal_stats["avg_signal"] or 0),
                "poor_signal_devices": signal_stats["poor_signal_count"] or 0,
                "online_percentage": (
                    (online_devices / total_devices * 100) if total_devices > 0 else 0
                ),
                "status": (
                    "healthy" if online_devices / total_devices > 0.8 else "warning"
                ),
            }

        except Exception as exc:
            return {"error": str(exc), "status": "error"}

    @staticmethod
    def _get_mqtt_status_stats() -> Dict[str, Any]:
        """Estadísticas del estado de conexiones MQTT"""
        try:
            total_connections = MQTTConnection.objects.count()

            if total_connections == 0:
                return {"total_connections": 0, "status": "no_connections"}

            # Estado de conexiones
            connection_status = (
                MQTTConnection.objects.values("status")
                .annotate(count=Count("id"))
                .order_by("status")
            )

            status_counts = {
                item["status"]: item["count"] for item in connection_status
            }

            # Estadísticas de mensajes
            message_stats = MQTTConnection.objects.aggregate(
                total_received=Sum("messages_received_today"),
                total_sent=Sum("messages_sent_today"),
                total_bytes=Sum("bytes_received_today"),
            )

            # Conexiones con errores
            error_connections = MQTTConnection.objects.filter(
                connection_errors__gt=0
            ).count()

            # Uptime de conexiones
            connected_count = status_counts.get("CONNECTED", 0)

            return {
                "total_connections": total_connections,
                "connected_connections": connected_count,
                "disconnected_connections": status_counts.get("DISCONNECTED", 0),
                "error_connections": error_connections,
                "status_distribution": status_counts,
                "messages_received_today": message_stats["total_received"] or 0,
                "messages_sent_today": message_stats["total_sent"] or 0,
                "bytes_received_today": message_stats["total_bytes"] or 0,
                "messages_per_second": (message_stats["total_received"] or 0)
                / 86400,  # promedio diario
                "uptime_percentage": (
                    (connected_count / total_connections * 100)
                    if total_connections > 0
                    else 0
                ),
                "status": (
                    "healthy"
                    if connected_count == total_connections
                    else "warning" if connected_count > 0 else "critical"
                ),
            }

        except Exception as exc:
            return {"error": str(exc), "status": "error"}

    @staticmethod
    def _get_system_resources_stats() -> Dict[str, Any]:
        """Estadísticas de recursos del sistema"""
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=1)

            # Memoria
            memory = psutil.virtual_memory()
            memory_percent = memory.percent

            # Disco
            disk = psutil.disk_usage("/")
            disk_percent = disk.percent

            # Red (simplificado)
            network = psutil.net_io_counters()
            bytes_sent_per_sec = (
                getattr(network, "bytes_sent", 0) / time.time()
                if hasattr(network, "bytes_sent")
                else 0
            )
            bytes_recv_per_sec = (
                getattr(network, "bytes_recv", 0) / time.time()
                if hasattr(network, "bytes_recv")
                else 0
            )

            # Determinar estado general
            if cpu_percent > 80 or memory_percent > 85 or disk_percent > 90:
                status = "critical"
            elif cpu_percent > 60 or memory_percent > 75 or disk_percent > 80:
                status = "warning"
            else:
                status = "healthy"

            return {
                "cpu_usage_percent": cpu_percent,
                "memory_usage_percent": memory_percent,
                "disk_usage_percent": disk_percent,
                "network_bytes_sent_per_sec": bytes_sent_per_sec,
                "network_bytes_recv_per_sec": bytes_recv_per_sec,
                "load_average": (
                    psutil.getloadavg() if hasattr(psutil, "getloadavg") else None
                ),
                "status": status,
            }

        except Exception as exc:
            return {"error": str(exc), "status": "error"}

    @staticmethod
    def get_user_activity_stats(user_id: int) -> Dict[str, Any]:
        """Estadísticas de actividad específicas de un usuario"""
        try:
            # En producción, esto se implementaría con un modelo de auditoría
            # Por ahora, retornar datos básicos
            return {
                "login_count_today": 1,  # Simulado
                "api_calls_today": 0,  # Simulado
                "reports_generated_today": 0,  # Simulado
                "last_activity": timezone.now().isoformat(),
            }

        except Exception as exc:
            return {"error": str(exc), "status": "error"}

    @staticmethod
    def record_api_call(
        endpoint: str, user_id: int, response_time: float, status_code: int
    ):
        """Registrar llamada a API para estadísticas (se llamaría desde middleware)"""
        try:
            # En producción, guardar en base de datos para análisis
            # Por ahora, solo actualizar cache
            cache_key = f"api_stats_{endpoint}"
            current_stats = cache.get(
                cache_key, {"calls": 0, "total_response_time": 0, "errors": 0}
            )

            current_stats["calls"] += 1
            current_stats["total_response_time"] += response_time
            if status_code >= 400:
                current_stats["errors"] += 1

            cache.set(cache_key, current_stats, 3600)  # 1 hora

        except Exception as exc:
            # No fallar si hay error en stats
            pass
