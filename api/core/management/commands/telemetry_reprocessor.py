#!/usr/bin/env python3
"""
TELEMETRY REPROCESSOR — SmartHydro
==================================
Motor granulado de auditoría y corrección local de telemetría.
Sin APIs de terceros. 100% data local. Dry-run por defecto.

PASOS (apretar botones):
------------------------
1. AUDITAR:
   python manage.py telemetry_reprocessor audit --year 2026 --output /app/backups/audit_2026.csv

2. CORREGIR TOTALES (desde pulsos) — para punto específico:
   python manage.py telemetry_reprocessor fix-totals --point-id 146 --start 2026-05-20 --end 2026-05-22
   # Revisar dry-run, luego aplicar:
   python manage.py telemetry_reprocessor fix-totals --point-id 146 --start 2026-05-20 --end 2026-05-22 --apply

3. CORREGIR CAUDAL (flow desde totales):
   python manage.py telemetry_reprocessor fix-flow --point-id 61 --start 2026-05-20 --end 2026-05-22 --apply

4. CORREGIR NIVEL (escalados ×10, interpolar 0s):
   python manage.py telemetry_reprocessor fix-nivel --point-id 61 --start 2026-05-20 --end 2026-05-22 --apply

5. BATCH FIX (aplica correcciones automáticas según reporte de auditoría):
   python manage.py telemetry_reprocessor batch-fix --report /app/backups/audit_2026.csv --apply

REGLAS DE CORRECCIÓN:
---------------------
- TOTALIZADO: recalcula total = prev_total + (pulse_diff * factor / 1000).
              Anti-ruido: decrementos < 10 en pulses se ignoran.
- CAUDAL:     flow = (diff / dt_segundos) * 1000, con clamp a MAX_FLOW_LS.
- NIVEL:      si 100 <= nivel <= 999 y .00 exacto → divide /10.
              si nivel == 0 → interpola lineal entre pre-crisis y post-crisis.
"""

import csv
import os
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import pytz
from django.core.management.base import BaseCommand
from django.db import transaction

from api.core.models import CatchmentPoint, InteractionDetail, Variable

UTC = pytz.UTC
MAX_FLOW_LS = 150.0


def log(msg):
    print(msg, flush=True)


def round_total(val):
    return int(Decimal(str(val)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def safe_float(s, default=0.0):
    try:
        return float(s) if s not in (None, "", "None") else default
    except (ValueError, TypeError):
        return default


def get_factor(point_id: int) -> float:
    var = (
        Variable.objects.filter(
            scheme_catchment__points_catchment__id=point_id,
            type_variable="TOTALIZADO",
        )
        .first()
    )
    return float(var.pulses_factor) if var and var.pulses_factor else 1000.0


class Command(BaseCommand):
    help = "Motor granulado de auditoría y corrección de telemetría"

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)

        # ------------------------------------------------------------------
        # audit
        # ------------------------------------------------------------------
        audit = sub.add_parser("audit", help="Auditar rango de fechas")
        audit.add_argument("--year", type=int, default=2026)
        audit.add_argument("--point-id", type=int, default=None)
        audit.add_argument("--output", type=str, default="/app/backups/audit_report.csv")

        # ------------------------------------------------------------------
        # fix-totals
        # ------------------------------------------------------------------
        ft = sub.add_parser("fix-totals", help="Recalcular total/diff/today desde pulsos")
        ft.add_argument("--point-id", type=int, required=True)
        ft.add_argument("--start", type=str, required=True, help="YYYY-MM-DD")
        ft.add_argument("--end", type=str, required=True, help="YYYY-MM-DD")
        ft.add_argument("--apply", action="store_true", default=False)

        # ------------------------------------------------------------------
        # fix-flow
        # ------------------------------------------------------------------
        ff = sub.add_parser("fix-flow", help="Recalcular caudal desde totales")
        ff.add_argument("--point-id", type=int, required=True)
        ff.add_argument("--start", type=str, required=True)
        ff.add_argument("--end", type=str, required=True)
        ff.add_argument("--apply", action="store_true", default=False)

        # ------------------------------------------------------------------
        # fix-nivel
        # ------------------------------------------------------------------
        fn = sub.add_parser("fix-nivel", help="Corregir nivel escalado o interpolar 0s")
        fn.add_argument("--point-id", type=int, required=True)
        fn.add_argument("--start", type=str, required=True)
        fn.add_argument("--end", type=str, required=True)
        fn.add_argument("--apply", action="store_true", default=False)

        # ------------------------------------------------------------------
        # fix-water-table
        # ------------------------------------------------------------------
        fwt = sub.add_parser("fix-water-table", help="Recalcular nivel freático desde nivel y d3")
        fwt.add_argument("--point-id", type=int, required=True)
        fwt.add_argument("--start", type=str, required=True)
        fwt.add_argument("--end", type=str, required=True)
        fwt.add_argument("--apply", action="store_true", default=False)

        # ------------------------------------------------------------------
        # batch-fix
        # ------------------------------------------------------------------
        bf = sub.add_parser("batch-fix", help="Aplicar fixes automáticos desde reporte CSV")
        bf.add_argument("--report", type=str, required=True)
        bf.add_argument("--apply", action="store_true", default=False)

    # ==================================================================
    # ENTRYPOINT
    # ==================================================================
    def handle(self, *args, **options):
        action = options["action"]
        if action == "audit":
            self.handle_audit(options)
        elif action == "fix-totals":
            self.handle_fix_totals(options)
        elif action == "fix-flow":
            self.handle_fix_flow(options)
        elif action == "fix-nivel":
            self.handle_fix_nivel(options)
        elif action == "fix-water-table":
            self.handle_fix_water_table(options)
        elif action == "batch-fix":
            self.handle_batch_fix(options)

    # ==================================================================
    # AUDIT
    # ==================================================================
    def handle_audit(self, opts):
        year = opts["year"]
        point_id = opts["point_id"]
        output = opts["output"]

        start_dt = UTC.localize(datetime(year, 1, 1, 0, 0, 0))
        end_dt = UTC.localize(datetime(year, 12, 31, 23, 59, 59))

        points = CatchmentPoint.objects.filter(id=point_id) if point_id else CatchmentPoint.objects.all()
        total_points = points.count()
        log(f"🔍 Auditando {total_points} puntos para {year}...")

        issues = []
        for pt in points.order_by("id"):
            issues.extend(self._audit_point(pt, start_dt, end_dt))

        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "point_id", "point_title", "date_time_medition",
                "issue_type", "severity", "field", "old_value", "expected_value", "suggestion"
            ])
            writer.writeheader()
            for row in issues:
                writer.writerow(row)

        log(f"✅ Auditoría completada: {len(issues)} hallazgos")
        log(f"📄 Reporte: {output}")
        if not opts.get("apply"):
            log("💡 Revisa el CSV. Luego usa batch-fix --report para generar/aplicar correcciones.")

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

            # 1. Monotonicidad total
            if prev_total is not None and total < prev_total:
                issues.append({
                    "point_id": point.id, "point_title": point.title,
                    "date_time_medition": dt.isoformat(),
                    "issue_type": "DROP_TOTAL", "severity": "CRITICAL",
                    "field": "total", "old_value": total, "expected_value": prev_total,
                    "suggestion": "fix-totals"
                })

            # 2. total_diff incoherente
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

            # 3. total_today_diff incoherente
            expected_today = max(0, round_total(total) - round_total(first_total_of_day))
            if abs(today - expected_today) > 2:
                issues.append({
                    "point_id": point.id, "point_title": point.title,
                    "date_time_medition": dt.isoformat(),
                    "issue_type": "TODAY_MISMATCH", "severity": "HIGH",
                    "field": "total_today_diff", "old_value": today, "expected_value": expected_today,
                    "suggestion": "fix-totals"
                })

            # 4. Flow = 0 con diff > 0
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

            # 5. Nivel escalado ×10
            if 100 <= nivel <= 999.99 and abs(nivel - round(nivel)) < 0.001:
                issues.append({
                    "point_id": point.id, "point_title": point.title,
                    "date_time_medition": dt.isoformat(),
                    "issue_type": "NIVEL_SCALED", "severity": "HIGH",
                    "field": "nivel", "old_value": nivel, "expected_value": round(nivel / 10.0, 2),
                    "suggestion": "fix-nivel"
                })

            # 6. Nivel = 0 sin ser error
            if nivel == 0.0 and not r["is_error"]:
                issues.append({
                    "point_id": point.id, "point_title": point.title,
                    "date_time_medition": dt.isoformat(),
                    "issue_type": "NIVEL_ZERO", "severity": "MEDIUM",
                    "field": "nivel", "old_value": 0.0, "expected_value": "",
                    "suggestion": "fix-nivel"
                })

            # 7. Capa duplicada (minuto 1/6/11 con diff descomunal o total inflado)
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

    # ==================================================================
    # FIX TOTALS
    # ==================================================================
    def handle_fix_totals(self, opts):
        pid = opts["point_id"]
        start = datetime.strptime(opts["start"], "%Y-%m-%d").replace(tzinfo=UTC)
        end = datetime.strptime(opts["end"], "%Y-%m-%d").replace(tzinfo=UTC) + timedelta(days=1)
        apply = opts["apply"]

        factor = get_factor(pid)
        log(f"🔧 fix-totals punto {pid} | factor={factor} | {start.date()} → {end.date()} | apply={apply}")

        prev = (
            InteractionDetail.objects.filter(
                catchment_point_id=pid, date_time_medition__lt=start
            )
            .exclude(total__isnull=True)
            .exclude(total="")
            .exclude(total="None")
            .order_by("-date_time_medition")
            .values("id", "pulses", "total", "date_time_medition")
            .first()
        )
        if not prev:
            log("⚠️ Sin registro previo válido.")
            return

        records = list(
            InteractionDetail.objects.filter(
                catchment_point_id=pid,
                date_time_medition__gte=prev["date_time_medition"],
                date_time_medition__lte=end,
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

        def _process():
            nonlocal prev_total, prev_pulses, current_day, first_total_of_day, day_first_id
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
                    changes_log.append((rid, changes))
                    if apply:
                        InteractionDetail.objects.filter(id=rid).update(**changes)

                prev_total = new_total
                if not skip_baseline:
                    prev_pulses = cp

        _process()
        log(f"   Registros a ajustar: {len(changes_log)}")
        if changes_log and not apply:
            for rid, ch in changes_log[:5]:
                log(f"      id={rid} → {ch}")
            if len(changes_log) > 5:
                log(f"      ... y {len(changes_log)-5} más")
            log("⚠️  Esto fue simulación. Agrega --apply para ejecutar.")
        elif apply:
            log("✅ Totales corregidos.")

    # ==================================================================
    # FIX FLOW
    # ==================================================================
    def handle_fix_flow(self, opts):
        pid = opts["point_id"]
        start = datetime.strptime(opts["start"], "%Y-%m-%d").replace(tzinfo=UTC)
        end = datetime.strptime(opts["end"], "%Y-%m-%d").replace(tzinfo=UTC) + timedelta(days=1)
        apply = opts["apply"]

        log(f"🔧 fix-flow punto {pid} | {start.date()} → {end.date()} | apply={apply}")

        records = list(
            InteractionDetail.objects.filter(
                catchment_point_id=pid,
                date_time_medition__gte=start,
                date_time_medition__lte=end,
            ).order_by("date_time_medition").values("id", "date_time_medition", "total", "flow")
        )
        if not records:
            log("⚠️ Sin registros en rango.")
            return

        prev = (
            InteractionDetail.objects.filter(
                catchment_point_id=pid, date_time_medition__lt=start
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
                changes_log.append((rid, {"flow": new_flow}))
                if apply:
                    InteractionDetail.objects.filter(id=rid).update(flow=new_flow)

            prev_total = curr_total
            prev_dt = dt

        log(f"   Registros a ajustar: {len(changes_log)}")
        if changes_log and not apply:
            for rid, ch in changes_log[:5]:
                log(f"      id={rid} → {ch}")
            if len(changes_log) > 5:
                log(f"      ... y {len(changes_log)-5} más")
            log("⚠️  Esto fue simulación. Agrega --apply para ejecutar.")
        elif apply:
            log("✅ Flow corregido.")

    # ==================================================================
    # FIX NIVEL
    # ==================================================================
    def handle_fix_nivel(self, opts):
        pid = opts["point_id"]
        start = datetime.strptime(opts["start"], "%Y-%m-%d").replace(tzinfo=UTC)
        end = datetime.strptime(opts["end"], "%Y-%m-%d").replace(tzinfo=UTC) + timedelta(days=1)
        apply = opts["apply"]

        log(f"🔧 fix-nivel punto {pid} | {start.date()} → {end.date()} | apply={apply}")

        records = list(
            InteractionDetail.objects.filter(
                catchment_point_id=pid,
                date_time_medition__gte=start,
                date_time_medition__lte=end,
            ).order_by("date_time_medition").values("id", "date_time_medition", "nivel")
        )
        if not records:
            log("⚠️ Sin registros en rango.")
            return

        prev = (
            InteractionDetail.objects.filter(
                catchment_point_id=pid, date_time_medition__lt=start
            )
            .exclude(nivel__isnull=True)
            .order_by("-date_time_medition")
            .values("date_time_medition", "nivel")
            .first()
        )
        post = (
            InteractionDetail.objects.filter(
                catchment_point_id=pid, date_time_medition__gt=end
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

            # Regla 1: escalado ×10
            if 100 <= old_nivel <= 999.99 and abs(old_nivel - round(old_nivel)) < 0.001:
                new_nivel = round(old_nivel / 10.0, 2)
            # Regla 2: interpolar 0s
            elif old_nivel == 0.0 and prev_nivel is not None and post_nivel is not None and prev_dt and post_dt:
                total_span = (post_dt - prev_dt).total_seconds()
                curr_span = (dt - prev_dt).total_seconds()
                if total_span > 0:
                    ratio = curr_span / total_span
                    new_nivel = round(prev_nivel + (post_nivel - prev_nivel) * ratio, 2)

            if abs(new_nivel - old_nivel) > 0.005:
                changes_log.append((rid, {"nivel": new_nivel}))
                if apply:
                    InteractionDetail.objects.filter(id=rid).update(nivel=new_nivel)

        log(f"   Registros a ajustar: {len(changes_log)}")
        if changes_log and not apply:
            for rid, ch in changes_log[:5]:
                log(f"      id={rid} → {ch}")
            if len(changes_log) > 5:
                log(f"      ... y {len(changes_log)-5} más")
            log("⚠️  Esto fue simulación. Agrega --apply para ejecutar.")
        elif apply:
            log("✅ Nivel corregido.")

    # ==================================================================
    # FIX WATER TABLE
    # ==================================================================
    def handle_fix_water_table(self, opts):
        pid = opts["point_id"]
        start = datetime.strptime(opts["start"], "%Y-%m-%d").replace(tzinfo=UTC)
        end = datetime.strptime(opts["end"], "%Y-%m-%d").replace(tzinfo=UTC) + timedelta(days=1)
        apply = opts["apply"]

        log(f"🔧 fix-water-table punto {pid} | {start.date()} → {end.date()} | apply={apply}")

        profile = ProfileDataConfigCatchment.objects.filter(point_catchment_id=pid).first()
        d3 = float(profile.d3) if profile and profile.d3 else 0.0
        if d3 <= 0:
            log("⚠️ d3 inválido o no configurado.")
            return

        records = list(
            InteractionDetail.objects.filter(
                catchment_point_id=pid,
                date_time_medition__gte=start,
                date_time_medition__lte=end,
            ).values("id", "nivel", "water_table")
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
                changes_log.append((rid, {"water_table": new_wt}))
                if apply:
                    InteractionDetail.objects.filter(id=rid).update(water_table=new_wt)

        log(f"   Registros a ajustar: {len(changes_log)}")
        if changes_log and not apply:
            for rid, ch in changes_log[:5]:
                log(f"      id={rid} → {ch}")
            if len(changes_log) > 5:
                log(f"      ... y {len(changes_log)-5} más")
            log("⚠️  Esto fue simulación. Agrega --apply para ejecutar.")
        elif apply:
            log("✅ Nivel freático corregido.")

    # ==================================================================
    # BATCH FIX
    # ==================================================================
    def handle_batch_fix(self, opts):
        report_path = opts["report"]
        apply = opts["apply"]

        if not os.path.exists(report_path):
            log(f"❌ Reporte no encontrado: {report_path}")
            return

        log(f"📋 Batch-fix desde {report_path} | apply={apply}")

        # Agrupar issues por punto y tipo
        fixes = {}
        with open(report_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pid = int(row["point_id"])
                issue = row["issue_type"]
                suggestion = row["suggestion"]
                if suggestion not in ("fix-totals", "fix-flow", "fix-nivel"):
                    continue
                if pid not in fixes:
                    fixes[pid] = {"fix-totals": [], "fix-flow": [], "fix-nivel": []}
                fixes[pid][suggestion].append(row)

        if not fixes:
            log("✅ No hay fixes automáticos pendientes en el reporte.")
            return

        for pid, groups in fixes.items():
            log(f"\n🔧 Punto {pid}:")
            for fix_type, rows in groups.items():
                if not rows:
                    continue
                # Determinar rango de fechas
                dts = [datetime.fromisoformat(r["date_time_medition"]).date() for r in rows]
                start = min(dts)
                end = max(dts)
                log(f"   {fix_type}: {len(rows)} issues entre {start} y {end}")
                if apply:
                    # Ejecutar directamente llamando al handler correspondiente
                    dummy_opts = {
                        "point_id": pid,
                        "start": str(start),
                        "end": str(end),
                        "apply": True,
                    }
                    if fix_type == "fix-totals":
                        self.handle_fix_totals(dummy_opts)
                    elif fix_type == "fix-flow":
                        self.handle_fix_flow(dummy_opts)
                    elif fix_type == "fix-nivel":
                        self.handle_fix_nivel(dummy_opts)

        if not apply:
            log("\n⚠️  Esto fue simulación. Revisa los rangos arriba y ejecuta con --apply.")
