"""
Endpoint de Backfill Histórico On-Demand (modo seguro)
======================================================

POST /api/ik/telemetry/backfill/

Consulta datos históricos de providers (TWIN/NOVUS/Tago) para un punto y rango.
Por defecto opera en **dry-run** y **modo seguro**:

- dry_run=true (default): no escribe; reporta por hora qué insertaría / actualizaría / omitiría.
- safe=true (default): solo inserta horas faltantes y actualiza filas is_error o
  réplicas congeladas; NUNCA toca filas con comprobante DGA (n_voucher).
- apply=true (o dry_run=false): escribe los cambios permitidos por safe.
- Recálculo de totales/caudal/nivel solo sobre filas tocadas.
- send_dga y n_voucher nunca se modifican (no se encola envío a DGA).
- Hora del logger: UTC de Tago convertida a hora de Chile.

Seguridad:
- Auth requerida (Token)
- Rate limit: 5/min por usuario
- Solo staff o owner/viewer del punto pueden ejecutar
- Rango máximo: 30 días
"""

from datetime import datetime

import pytz
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from api.core.models import CatchmentPoint
from api.core.services.telemetry_backfill import (
    backfill_point_from_providers,
    get_provider_history_func,
)

from .throttles import BackfillRateThrottle


def _as_bool(value, default=False):
    """Parsea bool desde JSON/form (acepta true/false, 1/0, yes/no)."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "si", "sí", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return default


class TelemetryBackfillView(APIView):
    """
    POST /api/ik/telemetry/backfill/

    Body:
    {
        "point_id": 94,
        "start": "2026-09-18T00:00:00",
        "end": "2026-10-02T18:00:00",
        "dry_run": true,   // default true — no escribe
        "apply": false,    // alias: apply=true equivale a dry_run=false
        "safe": true       // default true — no toca voucher DGA ni filas válidas
    }
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [BackfillRateThrottle]
    MAX_RANGE_DAYS = 30

    def post(self, request):
        user = request.user
        data = request.data

        point_id = data.get("point_id")
        start_str = data.get("start")
        end_str = data.get("end")

        # dry_run default ON; apply=true fuerza escritura
        if "apply" in data and data.get("apply") is not None:
            apply = _as_bool(data.get("apply"), default=False)
            dry_run = not apply
        elif "dry_run" in data and data.get("dry_run") is not None:
            dry_run = _as_bool(data.get("dry_run"), default=True)
        else:
            dry_run = True

        safe = _as_bool(data.get("safe"), default=True)

        # Validaciones básicas
        if not point_id or not start_str or not end_str:
            return Response(
                {"success": False, "error": "point_id, start y end son requeridos"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            point_id = int(point_id)
        except (ValueError, TypeError):
            return Response(
                {"success": False, "error": "point_id debe ser un entero"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Parsear fechas
        chile_tz = pytz.timezone("America/Santiago")
        try:
            start_dt = chile_tz.localize(datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S"))
            end_dt = chile_tz.localize(datetime.strptime(end_str, "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            return Response(
                {"success": False, "error": "Formato de fecha inválido. Use YYYY-MM-DDTHH:MM:SS"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if end_dt <= start_dt:
            return Response(
                {"success": False, "error": "end debe ser mayor que start"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if (end_dt - start_dt).days > self.MAX_RANGE_DAYS:
            return Response(
                {"success": False, "error": f"Rango máximo permitido: {self.MAX_RANGE_DAYS} días"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verificar que el punto existe
        try:
            point = CatchmentPoint.objects.get(id=point_id)
        except CatchmentPoint.DoesNotExist:
            return Response(
                {"success": False, "error": f"Punto {point_id} no existe"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Verificar permisos
        if not (user.is_staff or user.is_superuser):
            has_access = (
                point.owner_user_id == user.id
                or point.users_viewers.filter(id=user.id).exists()
            )
            if not has_access:
                return Response(
                    {"success": False, "error": "No tienes permiso para acceder a este punto"},
                    status=status.HTTP_403_FORBIDDEN
                )

        # Verificar que el punto tenga al menos una variable con histórico soportado
        handler_name, history_func, _ = get_provider_history_func(point)
        if not history_func:
            return Response(
                {"success": False, "error": "El punto no usa un provider con soporte de histórico (TWIN o NOVUS)"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Ejecutar backfill (dry-run por defecto)
        try:
            result = backfill_point_from_providers(
                point, start_dt, end_dt, dry_run=dry_run, safe=safe
            )

            processing = result.get("processing") or {}

            return Response({
                "success": True,
                "point_id": point_id,
                "point_name": point.title,
                "range": f"{start_str} → {end_str}",
                "dry_run": dry_run,
                "safe": safe,
                "mode": result.get("mode") or ("dry-run" if dry_run else "applied"),
                "records_created": result["records_created"],
                "records_updated": result["records_updated"],
                "records_skipped": result.get("records_skipped", 0),
                "records_failed": result["records_failed"],
                "by_reason": result.get("by_reason") or {},
                "processing": {
                    "totals_updated": processing.get("totals_updated", 0),
                    "flow_updated": processing.get("flow_updated", 0),
                    "nivel_updated": processing.get("nivel_updated", 0),
                    "avg_flow_updated": processing.get("avg_flow_updated", 0),
                    "total_diff_updated": processing.get("diff_updated", 0),
                    "total_today_diff_updated": processing.get("today_diff_updated", 0),
                },
                "hours": result.get("hours") or [],
                "sample": result.get("sample") or [],
                "dga_note": result.get("dga_note"),
                "details": {
                    "provider": result.get("provider") or handler_name,
                    "fetch_errors": result.get("fetch_errors") or [],
                }
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response({
                "success": False,
                "error": str(e),
            }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({
                "success": False,
                "error": str(e),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
