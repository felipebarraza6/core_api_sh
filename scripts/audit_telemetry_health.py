#!/usr/bin/env python3
"""
AUDITORÍA DE SALUD TELEMETRÍA — SmartHydro
============================================

Analiza todos los puntos y genera un reporte de salud con:
- Puntos sin datos (sensor nunca funcionó)
- Puntos con gaps (periodos sin datos)
- Puntos con totales NULL
- Saltos anómalos en totales
- Monotonicidad rota
- Puntos sin variable TOTALIZADO

USO:
    docker exec -u root -w /app django_api_secure python scripts/audit_telemetry_health.py
    docker exec -u root -w /app django_api_secure python scripts/audit_telemetry_health.py --days 30
    docker exec -u root -w /app django_api_secure python scripts/audit_telemetry_health.py --point-id 78

OUTPUT: JSON estructurado para análisis automatizado.
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta, timezone
from collections import defaultdict

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

from django.db import connection


def log(msg):
    print(msg, flush=True)


def run_audit(days_back=90, point_id=None):
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")

    cursor = connection.cursor()

    # ============================================================
    # 1. MAPEO DE TODOS LOS PUNTOS
    # ============================================================
    cursor.execute("""
        SELECT 
            cp.id,
            cp.title,
            CASE 
                WHEN cp.is_tdata THEN 'TWIN'
                WHEN cp.is_novus THEN 'NOVUS'
                WHEN cp.is_thethings THEN 'NETTRA'
                ELSE 'OTHER'
            END as provider,
            cp.frecuency,
            COUNT(v.id) as num_vars,
            STRING_AGG(DISTINCT v.type_variable, ', ' ORDER BY v.type_variable) as var_types
        FROM core_catchmentpoint cp
        LEFT JOIN core_schemescatchment_points_catchment scp ON scp.catchmentpoint_id = cp.id
        LEFT JOIN core_variable v ON v.scheme_catchment_id = scp.schemescatchment_id
        WHERE cp.id = COALESCE(%s, cp.id)
        GROUP BY cp.id, cp.title, cp.is_tdata, cp.is_novus, cp.is_thethings, cp.frecuency
        ORDER BY cp.id
    """, [point_id])

    points = {}
    for row in cursor.fetchall():
        points[row[0]] = {
            "id": row[0],
            "title": row[1],
            "provider": row[2],
            "frequency": row[3],
            "num_vars": row[4] or 0,
            "var_types": row[5] or "",
            "has_totalizado": "TOTALIZADO" in (row[5] or ""),
            "issues": [],
            "severity": "OK",
        }

    # ============================================================
    # 2. ESTADÍSTICAS DE REGISTROS POR PUNTO
    # ============================================================
    cursor.execute("""
        SELECT 
            cp.id,
            COUNT(id.id) as total_regs,
            COUNT(id.id) FILTER (WHERE id.date_time_medition >= %s) as recent_regs,
            COUNT(id.id) FILTER (WHERE id.total IS NULL OR id.total = '' OR id.total = 'None') as total_null,
            COUNT(id.id) FILTER (WHERE id.total IS NOT NULL AND id.total != '' AND id.total != 'None' AND id.total != '0') as total_valid,
            MAX(id.pulses) as max_pulses,
            MAX(id.date_time_medition) as last_medition,
            MIN(id.date_time_medition) as first_medition
        FROM core_catchmentpoint cp
        LEFT JOIN core_interactiondetail id ON id.catchment_point_id = cp.id
        WHERE cp.id = COALESCE(%s, cp.id)
        GROUP BY cp.id
    """, [since_str, point_id])

    for row in cursor.fetchall():
        pid = row[0]
        if pid not in points:
            continue
        p = points[pid]
        p["stats"] = {
            "total_regs": row[1] or 0,
            "recent_regs": row[2] or 0,
            "total_null": row[3] or 0,
            "total_valid": row[4] or 0,
            "max_pulses": row[5],
            "last_medition": row[6].isoformat() if row[6] else None,
            "first_medition": row[7].isoformat() if row[7] else None,
        }

        # Clasificar salud
        if p["stats"]["max_pulses"] is None or p["stats"]["max_pulses"] == 0:
            if p["has_totalizado"]:
                p["issues"].append("SENSOR_NEVER_WORKED")
                p["severity"] = "CRITICAL"
            else:
                p["issues"].append("NO_TOTALIZADO_VAR")
                p["severity"] = "INFO"
        elif p["stats"]["total_null"] > 0:
            p["issues"].append(f"NULL_TOTALS:{p['stats']['total_null']}")
            if p["stats"]["total_null"] > 100:
                p["severity"] = "HIGH"
            else:
                p["severity"] = max_severity(p["severity"], "MEDIUM")

    # ============================================================
    # 3. GAPS RECIENTES (periodos sin datos)
    # ============================================================
    cursor.execute("""
        WITH ordered AS (
            SELECT 
                cp.id,
                id.date_time_medition,
                LAG(id.date_time_medition) OVER (PARTITION BY cp.id ORDER BY id.date_time_medition) as prev_dt
            FROM core_catchmentpoint cp
            JOIN core_interactiondetail id ON id.catchment_point_id = cp.id
            WHERE id.date_time_medition >= %s
              AND cp.id = COALESCE(%s, cp.id)
        )
        SELECT id, MAX(EXTRACT(EPOCH FROM (date_time_medition - prev_dt)) / 3600.0) as max_gap_hours
        FROM ordered
        WHERE prev_dt IS NOT NULL
        GROUP BY id
        HAVING MAX(EXTRACT(EPOCH FROM (date_time_medition - prev_dt)) / 3600.0) > 3
    """, [since_str, point_id])

    for row in cursor.fetchall():
        pid = row[0]
        if pid in points:
            gap_hours = float(row[1])
            points[pid]["issues"].append(f"GAP:{gap_hours:.1f}h")
            if gap_hours > 24:
                points[pid]["severity"] = max_severity(points[pid]["severity"], "HIGH")
            else:
                points[pid]["severity"] = max_severity(points[pid]["severity"], "MEDIUM")

    # ============================================================
    # 4. SALTOS ANÓMALOS EN TOTALES (> 500 m3 en 1h)
    # ============================================================
    cursor.execute("""
        WITH ordered AS (
            SELECT 
                cp.id,
                id.date_time_medition,
                id.total::numeric as total_num,
                LAG(id.total::numeric) OVER (PARTITION BY cp.id ORDER BY id.date_time_medition) as prev_total
            FROM core_interactiondetail id
            JOIN core_catchmentpoint cp ON cp.id = id.catchment_point_id
            WHERE id.date_time_medition >= %s
              AND id.total IS NOT NULL AND id.total != '' AND id.total != 'None'
              AND cp.id = COALESCE(%s, cp.id)
        )
        SELECT id, COUNT(*) as jump_count, MAX(total_num - prev_total) as max_jump
        FROM ordered
        WHERE prev_total IS NOT NULL 
          AND total_num > prev_total + 500
        GROUP BY id
    """, [since_str, point_id])

    for row in cursor.fetchall():
        pid = row[0]
        if pid in points:
            jump_count = row[1]
            max_jump = float(row[2])
            points[pid]["issues"].append(f"JUMPS:{jump_count}(max={max_jump:.0f})")
            points[pid]["severity"] = max_severity(points[pid]["severity"], "HIGH")

    # ============================================================
    # 5. MONOTONICIDAD ROTA (total decrece)
    # ============================================================
    cursor.execute("""
        WITH ordered AS (
            SELECT 
                cp.id,
                id.total::numeric as total_num,
                LAG(id.total::numeric) OVER (PARTITION BY cp.id ORDER BY id.date_time_medition) as prev_total
            FROM core_interactiondetail id
            JOIN core_catchmentpoint cp ON cp.id = id.catchment_point_id
            WHERE id.date_time_medition >= %s
              AND id.total IS NOT NULL AND id.total != '' AND id.total != 'None'
              AND cp.id = COALESCE(%s, cp.id)
        )
        SELECT id, COUNT(*) as decrements
        FROM ordered
        WHERE prev_total IS NOT NULL AND total_num < prev_total AND total_num > 0
        GROUP BY id
        HAVING COUNT(*) > 0
    """, [since_str, point_id])

    for row in cursor.fetchall():
        pid = row[0]
        if pid in points:
            decrements = row[1]
            points[pid]["issues"].append(f"DECREMENT:{decrements}")
            points[pid]["severity"] = max_severity(points[pid]["severity"], "HIGH")

    # ============================================================
    # REPORTE
    # ============================================================
    severity_order = {"OK": 0, "INFO": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
    sorted_points = sorted(points.values(), key=lambda x: (-severity_order[x["severity"]], x["id"]))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days_back": days_back,
        "total_points": len(sorted_points),
        "summary": {
            "OK": sum(1 for p in sorted_points if p["severity"] == "OK"),
            "INFO": sum(1 for p in sorted_points if p["severity"] == "INFO"),
            "MEDIUM": sum(1 for p in sorted_points if p["severity"] == "MEDIUM"),
            "HIGH": sum(1 for p in sorted_points if p["severity"] == "HIGH"),
            "CRITICAL": sum(1 for p in sorted_points if p["severity"] == "CRITICAL"),
        },
        "critical_points": [p for p in sorted_points if p["severity"] == "CRITICAL"],
        "high_points": [p for p in sorted_points if p["severity"] == "HIGH"],
        "medium_points": [p for p in sorted_points if p["severity"] == "MEDIUM"],
        "all_points": sorted_points,
    }

    return report


def max_severity(a, b):
    order = {"OK": 0, "INFO": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
    return a if order.get(a, 0) >= order.get(b, 0) else b


def print_report(report):
    log("=" * 70)
    log("AUDITORÍA DE SALUD TELEMETRÍA — SmartHydro")
    log(f"Generado: {report['generated_at']}")
    log(f"Ventana: últimos {report['days_back']} días")
    log("=" * 70)
    log("")

    s = report["summary"]
    log(f"RESUMEN: {report['total_points']} puntos auditados")
    log(f"  🟢 OK:       {s['OK']}")
    log(f"  🔵 INFO:     {s['INFO']}")
    log(f"  🟡 MEDIUM:   {s['MEDIUM']}")
    log(f"  🟠 HIGH:     {s['HIGH']}")
    log(f"  🔴 CRITICAL: {s['CRITICAL']}")
    log("")

    if report["critical_points"]:
        log("🔴 CRITICAL — Requieren atención inmediata:")
        for p in report["critical_points"]:
            log(f"  [{p['provider']}] #{p['id']} {p['title']} | {', '.join(p['issues'])}")
        log("")

    if report["high_points"]:
        log("🟠 HIGH — Problemas significativos:")
        for p in report["high_points"]:
            stats = p.get("stats", {})
            nulls = stats.get("total_null", 0)
            log(f"  [{p['provider']}] #{p['id']} {p['title']} | {', '.join(p['issues'])} | nulls={nulls}")
        log("")

    if report["medium_points"]:
        log("🟡 MEDIUM — Problemas menores:")
        for p in report["medium_points"]:
            log(f"  [{p['provider']}] #{p['id']} {p['title']} | {', '.join(p['issues'])}")
        log("")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90, help="Días hacia atrás")
    parser.add_argument("--point-id", type=int, default=None, help="Auditar solo un punto")
    parser.add_argument("--json", action="store_true", help="Output en JSON")
    args = parser.parse_args()

    report = run_audit(days_back=args.days, point_id=args.point_id)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report)


if __name__ == "__main__":
    main()
