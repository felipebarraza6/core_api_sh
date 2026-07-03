"""
Telemetry Reprocessor API
=========================
Endpoint REST para ejecutar auditoría, correcciones y backfill histórico
de telemetría desde el frontend o herramientas externas.

Método: POST /api/telemetry-reprocessor/
Body:   {
            "action": "audit|fix-totals|fix-flow|fix-nivel|fix-water-table|backfill",
            "source": "local|providers",
            "point_id": 61,
            "start": "2026-05-20",
            "end": "2026-05-22",
            "apply": false
        }

- Requiere autenticación (staff/admin).
- source="local" por defecto (opera sobre datos ya en BD).
- source="providers" + action="backfill" consulta histórico al proveedor configurado.
- apply=false por defecto (dry-run).
- apply=true requiere permiso explícito y genera backup CSV.
"""

import csv
import io
import os
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

import pytz
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from api.core.models import CatchmentPoint, InteractionDetail, ProfileDataConfigCatchment, Variable
from api.core.services.telemetry_backfill import backfill_point_from_providers


class TelemetryReprocessorRequestSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=[
            ("audit", "audit"),
            ("fix-totals", "fix-totals"),
            ("fix-flow", "fix-flow"),
            ("fix-nivel", "fix-nivel"),
            ("fix-water-table", "fix-water-table"),
            ("backfill", "backfill"),
        ],
        help_text="Acción a ejecutar",
    )
    source = serializers.ChoiceField(
        choices=[
            ("local", "local"),
            ("providers", "providers"),
        ],
        default="local",
        help_text="Fuente de datos: local (BD) o providers (APIs de telemetría). Default: local",
    )
    point_id = serializers.IntegerField(
        required=False, allow_null=True, help_text="ID del punto de captación (obligatorio para fix actions y backfill)"
    )
    start = serializers.DateField(
        required=False, help_text="Fecha inicio (YYYY-MM-DD). Default: 1° enero del año actual"
    )
    end = serializers.DateField(
        required=False, help_text="Fecha fin inclusive (YYYY-MM-DD). Default: 31 diciembre del año actual"
    )
    apply = serializers.BooleanField(
        default=False, help_text="false = dry-run (default). true = aplicar cambios en DB"
    )


class ChangeSampleSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    changes = serializers.DictField(child=serializers.CharField())
    date = serializers.CharField()


class TelemetryReprocessorResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    mode = serializers.CharField(help_text="dry-run | applied | audit", required=False)
    source = serializers.CharField(help_text="local | providers", required=False)
    point_id = serializers.IntegerField(required=False)
    action = serializers.CharField(required=False)
    records_affected = serializers.IntegerField(required=False)
    records_created = serializers.IntegerField(required=False)
    records_updated = serializers.IntegerField(required=False)
    records_failed = serializers.IntegerField(required=False)
    points_audited = serializers.IntegerField(required=False)
    issues_found = serializers.IntegerField(required=False)
    backup_path = serializers.CharField(required=False)
    provider = serializers.CharField(required=False)
    range = serializers.CharField(required=False)
    processing = serializers.DictField(required=False)
    fetch_errors = serializers.ListField(child=serializers.CharField(), required=False)
    sample = ChangeSampleSerializer(many=True, required=False)
    error = serializers.CharField(required=False)
    message = serializers.CharField(required=False)

UTC = pytz.UTC
MAX_FLOW_LS = 150.0


def round_total(val):
    return int(Decimal(str(val)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def safe_float(s, default=0.0):
    try:
        return float(s) if s not in (None, "", "None") else default
    except (ValueError, TypeError):
        return default


def get_factor(point_id: int) -> float:
    var = Variable.objects.filter(
        scheme_catchment__points_catchment__id=point_id,
        type_variable="TOTALIZADO",
    ).first()
    return float(var.pulses_factor) if var and var.pulses_factor else 1000.0


class TelemetryReprocessorView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Auditoría, corrección y backfill de telemetría",
        description=(
            "Ejecuta auditoría, correcciones de telemetría (totales, flow, nivel, water_table) "
            "o backfill histórico desde proveedores. "
            "source=local opera sobre datos en BD; source=providers consulta APIs de telemetría. "
            "Dry-run por defecto; requiere apply=true para modificar la base de datos. "
            "Solo usuarios staff/admin. Ver docs/API_TELEMETRY_REPROCESSOR.md"
        ),
        request=TelemetryReprocessorRequestSerializer,
        responses={
            200: TelemetryReprocessorResponseSerializer,
            400: TelemetryReprocessorResponseSerializer,
        },
        tags=["Telemetry Reprocessor"],
    )
    def post(self, request):
        action = request.data.get("action")
        source = request.data.get("source") or "local"
        point_id = request.data.get("point_id")
        start_str = request.data.get("start")
        end_str = request.data.get("end")
        apply = bool(request.data.get("apply", False))

        # Validaciones
        valid_actions = ("audit", "fix-totals", "fix-flow", "fix-nivel", "fix-water-table", "backfill")
        if action not in valid_actions:
            return Response(
                {"error": f"action inválida. Opciones: {', '.join(valid_actions)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if source not in ("local", "providers"):
            return Response(
                {"error": "source inválida. Opciones: local, providers"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if action in ("backfill",) and source != "providers":
            return Response(
                {"error": "action=backfill requiere source=providers"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if action not in ("audit",) and not point_id:
            return Response(
                {"error": "point_id es obligatorio para fix actions y backfill"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if start_str:
                start_dt = UTC.localize(datetime.strptime(start_str, "%Y-%m-%d"))
            else:
                start_dt = UTC.localize(datetime(datetime.now().year, 1, 1))
            if end_str:
                end_dt = UTC.localize(datetime.strptime(end_str, "%Y-%m-%d")) + timedelta(days=1)
            else:
                end_dt = UTC.localize(datetime(datetime.now().year, 12, 31)) + timedelta(days=1)
        except ValueError:
            return Response(
                {"error": "Formato de fecha inválido. Usar YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Limites de rango
        if action == "audit":
            max_days = 365
        elif action == "backfill":
            max_days = 7
        else:
            max_days = 30
        if (end_dt - start_dt).days > max_days:
            return Response(
                {"error": f"Rango máximo para {action}: {max_days} días"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Ejecutar
        if action == "audit":
            return self._do_audit(point_id, start_dt, end_dt)
        elif action == "backfill":
            return self._do_backfill(point_id, start_dt, end_dt, apply)
        elif action == "fix-totals":
            return self._do_fix_totals(point_id, start_dt, end_dt, apply)
        elif action == "fix-flow":
            return self._do_fix_flow(point_id, start_dt, end_dt, apply)
        elif action == "fix-nivel":
            return self._do_fix_nivel(point_id, start_dt, end_dt, apply)
        elif action == "fix-water-table":
            return self._do_fix_water_table(point_id, start_dt, end_dt, apply)

    # ================================================================
    # BACKFILL FROM PROVIDERS
    # ================================================================
    def _do_backfill(self, point_id, start_dt, end_dt, apply):
        try:
            point = CatchmentPoint.objects.get(id=point_id)
        except CatchmentPoint.DoesNotExist:
            return Response(
                {"error": f"Punto {point_id} no existe"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = backfill_point_from_providers(point, start_dt, end_dt, dry_run=not apply)
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response(
                {"error": f"Error en backfill: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        result["mode"] = "applied" if apply else "dry-run"
        result["source"] = "providers"
        result["action"] = "backfill"
        return Response(result)

    # ================================================================
    # AUDIT
    # ================================================================
    def _do_audit(self, point_id, start_dt, end_dt):
        points = CatchmentPoint.objects.filter(id=point_id) if point_id else CatchmentPoint.objects.all()
        issues = []
        for pt in points.order_by("id"):
            issues.extend(self._audit_point(pt, start_dt, end_dt))

        # Generar CSV en memoria
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            "point_id", "point_title", "date_time_medition",
            "issue_type", "severity", "field", "old_value", "expected_value", "suggestion"
        ])
        writer.writeheader()
        for row in issues:
            writer.writerow(row)

        # Guardar en disco también
        backup_dir = "/app/backups"
        os.makedirs(backup_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"audit_{point_id or 'all'}_{ts}.csv"
        filepath = os.path.join(backup_dir, filename)
        with open(filepath, "w", newline="") as f:
            f.write(output.getvalue())

        return Response({
            "success": True,
            "mode": "audit",
            "points_audited": points.count(),
            "issues_found": len(issues),
            "backup_path": filepath,
            "sample": issues[:20],
        })

    def _audit_point(self, point, start_dt, end_dt):
        issues = []
        records = list(
            InteractionDetail.objects.filter(
                catchment_point=point,
                date_time_medition__gte=start_dt,
                date_time_medition__lte=end_dt,
            ).order_by("date_time_medition").values(
                "id", "date_time_medition", "pulses", "total", "total_diff",
                "total_today_diff", "flow", "nivel", "is_error"
            )
        )
        if not records:
            return issues

        prev_total = None
        prev_dt = None
        first_total_of_day = None
        current_day = None

        for i, r in enumerate(records):
            dt = r["date_time_medition"]
            day = dt.date()
            if day != current_day:
                current_day = day
                first_total_of_day = safe_float(r["total"], 0.0)

            total = safe_float(r["total"], 0.0)
            diff = r["total_diff"] or 0
            today = r["total_today_diff"] or 0
            flow = safe_float(r["flow"], 0.0)
            nivel = safe_float(r["nivel"], 0.0)
            pulses = safe_float(r["pulses"], 0.0)

            if prev_total is not None and total < prev_total:
                issues.append({
                    "point_id": point.id, "point_title": point.title,
                    "date_time_medition": dt.isoformat(),
                    "issue_type": "DROP_TOTAL", "severity": "CRITICAL",
                    "field": "total", "old_value": total, "expected_value": prev_total,
                    "suggestion": "fix-totals"
                })

            if prev_total is not None:
                expected_diff = max(0, round_total(total) - round_total(prev_total))
                if abs(diff - expected_diff) > 2:
                    issues.append({
                        "point_id": point.id, "point_title": point.title,
                        "date_time_medition": dt.isoformat(),
                        "issue_type": "DIFF_MISMATCH", "severity": "HIGH",
                        "field": "total_diff", "old_value": diff, "expected_value": expected_diff,
                        "suggestion": "fix-totals"
                    })

            expected_today = max(0, round_total(total) - round_total(first_total_of_day))
            if abs(today - expected_today) > 2:
                issues.append({
                    "point_id": point.id, "point_title": point.title,
                    "date_time_medition": dt.isoformat(),
                    "issue_type": "TODAY_MISMATCH", "severity": "HIGH",
                    "field": "total_today_diff", "old_value": today, "expected_value": expected_today,
                    "suggestion": "fix-totals"
                })

            if flow == 0.0 and diff > 0 and prev_dt:
                dt_seconds = (dt - prev_dt).total_seconds()
                if dt_seconds > 0:
                    expected_flow = round((diff / dt_seconds) * 1000.0, 2)
                    if 0 < expected_flow <= MAX_FLOW_LS:
                        issues.append({
                            "point_id": point.id, "point_title": point.title,
                            "date_time_medition": dt.isoformat(),
                            "issue_type": "FLOW_ZERO", "severity": "MEDIUM",
                            "field": "flow", "old_value": 0.0, "expected_value": expected_flow,
                            "suggestion": "fix-flow"
                        })

            if 100 <= nivel <= 999.99 and abs(nivel - round(nivel)) < 0.001:
                issues.append({
                    "point_id": point.id, "point_title": point.title,
                    "date_time_medition": dt.isoformat(),
                    "issue_type": "NIVEL_SCALED", "severity": "HIGH",
                    "field": "nivel", "old_value": nivel, "expected_value": round(nivel / 10.0, 2),
                    "suggestion": "fix-nivel"
                })

            if nivel == 0.0 and not r["is_error"]:
                issues.append({
                    "point_id": point.id, "point_title": point.title,
                    "date_time_medition": dt.isoformat(),
                    "issue_type": "NIVEL_ZERO", "severity": "MEDIUM",
                    "field": "nivel", "old_value": 0.0, "expected_value": "",
                    "suggestion": "fix-nivel"
                })

            minute = dt.minute
            if minute % 5 == 1 and prev_total and total > prev_total * 2 and total > 10000:
                issues.append({
                    "point_id": point.id, "point_title": point.title,
                    "date_time_medition": dt.isoformat(),
                    "issue_type": "DUPLICATE_LAYER", "severity": "CRITICAL",
                    "field": "total", "old_value": total, "expected_value": prev_total,
                    "suggestion": "delete-record"
                })

            prev_total = total
            prev_dt = dt

        return issues

    # ================================================================
    # FIX TOTALS
    # ================================================================
    def _do_fix_totals(self, pid, start_dt, end_dt, apply):
        factor = get_factor(pid)
        prev = (
            InteractionDetail.objects.filter(
                catchment_point_id=pid, date_time_medition__lt=start_dt
            )
            .exclude(total__isnull=True)
            .exclude(total="")
            .exclude(total="None")
            .order_by("-date_time_medition")
            .values("id", "pulses", "total", "date_time_medition")
            .first()
        )
        if not prev:
            return Response({"error": "Sin registro previo válido"}, status=status.HTTP_400_BAD_REQUEST)

        records = list(
            InteractionDetail.objects.filter(
                catchment_point_id=pid,
                date_time_medition__gte=prev["date_time_medition"],
                date_time_medition__lte=end_dt,
            ).order_by("date_time_medition").values(
                "id", "date_time_medition", "pulses", "total",
                "total_diff", "total_today_diff"
            )
        )
        records = [r for r in records if r["id"] != prev.get("id")]

        prev_total = safe_float(prev["total"], 0.0)
        prev_pulses = safe_float(prev["pulses"], 0.0)
        current_day = prev["date_time_medition"].date()
        first_total_of_day = prev_total
        day_first_id = None

        changes_log = []

        for r in records:
            rid = r["id"]
            dt = r["date_time_medition"]
            cp = safe_float(r["pulses"], 0.0)
            old_total = safe_float(r["total"], 0.0)
            old_diff = r["total_diff"] or 0
            old_today = r["total_today_diff"] or 0

            if dt.date() != current_day:
                current_day = dt.date()
                first_total_of_day = prev_total
                day_first_id = rid

            if cp == 0:
                pulse_diff = 0
                new_total = prev_total
                skip_baseline = True
            elif cp >= prev_pulses:
                pulse_diff = cp - prev_pulses
                skip_baseline = False
            else:
                if prev_pulses - cp < 10:
                    pulse_diff = 0
                    skip_baseline = True
                else:
                    pulse_diff = cp
                    skip_baseline = False

            new_total = prev_total + (pulse_diff * factor) / 1000.0
            new_total_r = round_total(new_total)
            new_diff = max(0, new_total_r - round_total(prev_total))
            new_today = max(0, new_total_r - round_total(first_total_of_day)) if day_first_id != rid else 0

            changes = {}
            if new_total_r != round_total(old_total):
                changes["total"] = str(new_total_r)
            if new_diff != old_diff:
                changes["total_diff"] = new_diff
            if new_today != old_today:
                changes["total_today_diff"] = new_today

            if changes:
                changes_log.append({"id": rid, "changes": changes, "date": dt.isoformat()})
                if apply:
                    InteractionDetail.objects.filter(id=rid).update(**changes)

            prev_total = new_total
            if not skip_baseline:
                prev_pulses = cp

        return Response({
            "success": True,
            "mode": "applied" if apply else "dry-run",
            "point_id": pid,
            "action": "fix-totals",
            "records_affected": len(changes_log),
            "sample": changes_log[:10],
        })

    # ================================================================
    # FIX FLOW
    # ================================================================
    def _do_fix_flow(self, pid, start_dt, end_dt, apply):
        records = list(
            InteractionDetail.objects.filter(
                catchment_point_id=pid,
                date_time_medition__gte=start_dt,
                date_time_medition__lte=end_dt,
            ).order_by("date_time_medition").values("id", "date_time_medition", "total", "flow")
        )
        if not records:
            return Response({"error": "Sin registros en rango"}, status=status.HTTP_400_BAD_REQUEST)

        prev = (
            InteractionDetail.objects.filter(
                catchment_point_id=pid, date_time_medition__lt=start_dt
            )
            .exclude(total__isnull=True)
            .exclude(total="")
            .exclude(total="None")
            .order_by("-date_time_medition")
            .values("date_time_medition", "total")
            .first()
        )
        prev_total = safe_float(prev["total"], 0.0) if prev else 0.0
        prev_dt = prev["date_time_medition"] if prev else None

        changes_log = []

        for r in records:
            rid = r["id"]
            dt = r["date_time_medition"]
            curr_total = safe_float(r["total"], 0.0)
            old_flow = safe_float(r["flow"], 0.0)

            new_flow = 0.0
            if prev_dt and dt and curr_total >= prev_total:
                dt_seconds = (dt - prev_dt).total_seconds()
                if dt_seconds > 0:
                    diff = curr_total - prev_total
                    if diff >= 0:
                        new_flow = round((diff / dt_seconds) * 1000.0, 2)
                        if new_flow > MAX_FLOW_LS:
                            new_flow = 0.0

            if abs(new_flow - old_flow) > 0.005:
                changes_log.append({"id": rid, "changes": {"flow": new_flow}, "date": dt.isoformat()})
                if apply:
                    InteractionDetail.objects.filter(id=rid).update(flow=new_flow)

            prev_total = curr_total
            prev_dt = dt

        return Response({
            "success": True,
            "mode": "applied" if apply else "dry-run",
            "point_id": pid,
            "action": "fix-flow",
            "records_affected": len(changes_log),
            "sample": changes_log[:10],
        })

    # ================================================================
    # FIX NIVEL
    # ================================================================
    def _do_fix_nivel(self, pid, start_dt, end_dt, apply):
        records = list(
            InteractionDetail.objects.filter(
                catchment_point_id=pid,
                date_time_medition__gte=start_dt,
                date_time_medition__lte=end_dt,
            ).order_by("date_time_medition").values("id", "date_time_medition", "nivel")
        )
        if not records:
            return Response({"error": "Sin registros en rango"}, status=status.HTTP_400_BAD_REQUEST)

        prev = (
            InteractionDetail.objects.filter(
                catchment_point_id=pid, date_time_medition__lt=start_dt
            )
            .exclude(nivel__isnull=True)
            .order_by("-date_time_medition")
            .values("date_time_medition", "nivel")
            .first()
        )
        post = (
            InteractionDetail.objects.filter(
                catchment_point_id=pid, date_time_medition__gt=end_dt
            )
            .exclude(nivel__isnull=True)
            .order_by("date_time_medition")
            .values("date_time_medition", "nivel")
            .first()
        )

        prev_nivel = safe_float(prev["nivel"], None) if prev else None
        post_nivel = safe_float(post["nivel"], None) if post else None
        prev_dt = prev["date_time_medition"] if prev else None
        post_dt = post["date_time_medition"] if post else None

        changes_log = []

        for r in records:
            rid = r["id"]
            dt = r["date_time_medition"]
            old_nivel = safe_float(r["nivel"], 0.0)
            new_nivel = old_nivel

            if 100 <= old_nivel <= 999.99 and abs(old_nivel - round(old_nivel)) < 0.001:
                new_nivel = round(old_nivel / 10.0, 2)
            elif old_nivel == 0.0 and prev_nivel is not None and post_nivel is not None and prev_dt and post_dt:
                total_span = (post_dt - prev_dt).total_seconds()
                curr_span = (dt - prev_dt).total_seconds()
                if total_span > 0:
                    ratio = curr_span / total_span
                    new_nivel = round(prev_nivel + (post_nivel - prev_nivel) * ratio, 2)

            if abs(new_nivel - old_nivel) > 0.005:
                changes_log.append({"id": rid, "changes": {"nivel": new_nivel}, "date": dt.isoformat()})
                if apply:
                    InteractionDetail.objects.filter(id=rid).update(nivel=new_nivel)

        return Response({
            "success": True,
            "mode": "applied" if apply else "dry-run",
            "point_id": pid,
            "action": "fix-nivel",
            "records_affected": len(changes_log),
            "sample": changes_log[:10],
        })

    # ================================================================
    # FIX WATER TABLE
    # ================================================================
    def _do_fix_water_table(self, pid, start_dt, end_dt, apply):
        profile = ProfileDataConfigCatchment.objects.filter(point_catchment_id=pid).first()
        d3 = float(profile.d3) if profile and profile.d3 else 0.0
        if d3 <= 0:
            return Response({"error": "d3 inválido o no configurado"}, status=status.HTTP_400_BAD_REQUEST)

        records = list(
            InteractionDetail.objects.filter(
                catchment_point_id=pid,
                date_time_medition__gte=start_dt,
                date_time_medition__lte=end_dt,
            ).values("id", "date_time_medition", "nivel", "water_table")
        )

        changes_log = []
        for r in records:
            rid = r["id"]
            nivel = float(r["nivel"]) if r["nivel"] is not None else 0.0
            old_wt = float(r["water_table"]) if r["water_table"] is not None else 0.0
            new_wt = d3 - nivel
            if new_wt < 0:
                new_wt = 0.0
            new_wt = round(new_wt, 2)
            if abs(new_wt - old_wt) > 0.005:
                changes_log.append({"id": rid, "changes": {"water_table": new_wt}, "date": r["date_time_medition"].isoformat()})
                if apply:
                    InteractionDetail.objects.filter(id=rid).update(water_table=new_wt)

        return Response({
            "success": True,
            "mode": "applied" if apply else "dry-run",
            "point_id": pid,
            "action": "fix-water-table",
            "records_affected": len(changes_log),
            "sample": changes_log[:10],
        })
