#!/usr/bin/env python3
"""
AUDITORÍA DE COHERENCIA DE TELEMETRÍA
=====================================

Valida que los datos de InteractionDetail sean coherentes:
- Totales monotónicos (sin bajadas injustificadas)
- total_diff = total_actual - total_anterior
- total_today_diff = total_actual - primer_total_del_día
- flow consistente con total_diff y Δt
- Nivel freático coherente (water_table = d3 - nivel)
- Detección de resets no documentados
- Resumen por proyecto/cliente

Uso:
    python scripts/audit_telemetry_coherence.py [--days 7] [--project-id N] [--point-id N]

Ejemplo para revisar la tarde de hoy en Nueva Energía o Iansa:
    python scripts/audit_telemetry_coherence.py --days 1 --project-id 2
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.append('/app')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")

import django
django.setup()

import pytz
from api.core.models import InteractionDetail, CatchmentPoint, ProjectCatchments


class Colors:
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    RESET = "\033[0m"


def color(text, c):
    return f"{c}{text}{Colors.RESET}"


def safe_float(val, default=0.0):
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def audit_point(point, start_dt, end_dt, verbose=False):
    """Audita un punto de captación en un rango de fechas."""
    issues = []
    stats = {
        "records": 0,
        "resets_documented": 0,
        "drops_unexplained": 0,
        "jumps_massive": 0,
        "diff_mismatch": 0,
        "today_diff_mismatch": 0,
        "flow_mismatch": 0,
        "zero_total_with_pulses": 0,
        "negative_pulses": 0,
        "level_incoherent": 0,
        "is_error_but_used": 0,
    }

    records = InteractionDetail.objects.filter(
        catchment_point=point,
        date_time_medition__gte=start_dt,
        date_time_medition__lte=end_dt,
    ).exclude(is_error=True).order_by("date_time_medition")

    stats["records"] = records.count()
    if stats["records"] == 0:
        return issues, stats

    # Perfil del punto (d3 para validar nivel freático)
    d3 = None
    try:
        profile = point.data_config_profiles.first()
        if profile and profile.d3:
            d3 = float(profile.d3)
    except Exception:
        pass

    prev = None
    day_first = None
    current_day = None

    for r in records:
        dt = r.date_time_medition
        total = safe_float(r.total)
        pulses = safe_float(r.pulses)
        total_diff = safe_float(r.total_diff)
        total_today_diff = safe_float(r.total_today_diff)
        flow = safe_float(r.flow)
        nivel = safe_float(r.nivel)
        water_table = safe_float(r.water_table)

        # Detectar día nuevo
        if current_day != dt.date():
            current_day = dt.date()
            day_first = r

        # 1. Total=0 con pulsos>0 (incoherencia grave)
        if total == 0 and pulses > 0:
            issues.append({
                "dt": dt, "type": "ZERO_TOTAL_WITH_PULSES",
                "msg": f"total=0 pero pulses={pulses}", "severity": "CRITICAL"
            })
            stats["zero_total_with_pulses"] += 1

        # 2. Pulsos negativos
        if pulses < 0:
            issues.append({
                "dt": dt, "type": "NEGATIVE_PULSES",
                "msg": f"pulses={pulses}", "severity": "CRITICAL"
            })
            stats["negative_pulses"] += 1

        if prev is not None:
            prev_total = safe_float(prev.total)
            time_delta_hours = max((dt - prev.date_time_medition).total_seconds() / 3600.0, 0.001)

            # 3. Caída inexplicada (sin reset documentado)
            if total < prev_total - 1:  # Tolerancia de 1 m3 por redondeo
                # Buscar si hay notificación de reset
                has_reset_notif = False  # Podríamos validar contra NotificationsCatchment
                issues.append({
                    "dt": dt, "type": "UNEXPLAINED_DROP",
                    "msg": f"total bajó {prev_total:.0f} -> {total:.0f}",
                    "severity": "HIGH" if not has_reset_notif else "INFO"
                })
                stats["drops_unexplained"] += 1

            # 4. Salto masivo
            diff_total = total - prev_total
            if diff_total > 500:  # Umbral de 500 m3 entre lecturas consecutivas
                issues.append({
                    "dt": dt, "type": "MASSIVE_JUMP",
                    "msg": f"salto de {diff_total:.0f} m3 ({prev_total:.0f} -> {total:.0f})",
                    "severity": "HIGH"
                })
                stats["jumps_massive"] += 1

            # 5. Coherencia de total_diff
            expected_diff = total - prev_total
            if expected_diff < 0:
                expected_diff = 0  # diff se clampa a 0 en caídas
            if abs(total_diff - expected_diff) > 2:  # Tolerancia 2 m3 por redondeos
                issues.append({
                    "dt": dt, "type": "DIFF_MISMATCH",
                    "msg": f"total_diff={total_diff} esperado={expected_diff}",
                    "severity": "MEDIUM"
                })
                stats["diff_mismatch"] += 1

            # 6. Coherencia de flow (caudal)
            if flow > 0 and total_diff > 0:
                # flow (L/s) ≈ (total_diff m3 / Δt seg) * 1000
                expected_flow = (total_diff / (time_delta_hours * 3600)) * 1000
                if expected_flow > 0:
                    ratio = flow / expected_flow
                    if ratio < 0.5 or ratio > 2.0:
                        issues.append({
                            "dt": dt, "type": "FLOW_MISMATCH",
                            "msg": f"flow={flow:.2f} L/s, esperado ~{expected_flow:.2f} L/s",
                            "severity": "MEDIUM"
                        })
                        stats["flow_mismatch"] += 1

        # 7. Coherencia de total_today_diff
        if day_first is not None and r.id != day_first.id:
            first_total = safe_float(day_first.total)
            expected_today = total - first_total
            if expected_today < 0:
                expected_today = 0
            if abs(total_today_diff - expected_today) > 2:
                issues.append({
                    "dt": dt, "type": "TODAY_DIFF_MISMATCH",
                    "msg": f"total_today_diff={total_today_diff} esperado={expected_today}",
                    "severity": "MEDIUM"
                })
                stats["today_diff_mismatch"] += 1

        # 8. Coherencia de nivel freático
        if d3 and nivel > 0 and water_table > 0:
            expected_wt = round(d3 - nivel, 2)
            if abs(water_table - expected_wt) > 0.05:
                issues.append({
                    "dt": dt, "type": "LEVEL_INCOHERENT",
                    "msg": f"water_table={water_table} esperado={expected_wt} (d3={d3}, nivel={nivel})",
                    "severity": "LOW"
                })
                stats["level_incoherent"] += 1

        prev = r

    return issues, stats


def main():
    parser = argparse.ArgumentParser(description="Auditoría de coherencia de telemetría")
    parser.add_argument("--days", type=int, default=1, help="Días hacia atrás a auditar")
    parser.add_argument("--project-id", type=int, help="Filtrar por ID de proyecto")
    parser.add_argument("--point-id", type=int, help="Filtrar por ID de punto específico")
    parser.add_argument("--verbose", action="store_true", help="Mostrar todos los registros, no solo issues")
    parser.add_argument("--min-severity", default="MEDIUM", choices=["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                        help="Severidad mínima a reportar")
    args = parser.parse_args()

    chile = pytz.timezone("America/Santiago")
    end_dt = datetime.now(chile)
    start_dt = end_dt - timedelta(days=args.days)

    # Filtrar puntos
    qs = CatchmentPoint.objects.filter(data_config_profiles__is_telemetry=True).distinct()
    if args.project_id:
        qs = qs.filter(project_id=args.project_id)
    if args.point_id:
        qs = qs.filter(id=args.point_id)

    print(color(f"=== AUDITORÍA DE TELEMETRÍA ===", Colors.CYAN))
    print(f"Rango: {start_dt.strftime('%Y-%m-%d %H:%M')} -> {end_dt.strftime('%Y-%m-%d %H:%M')}")
    print(f"Puntos a auditar: {qs.count()}")
    print()

    severity_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    min_rank = severity_rank[args.min_severity]

    total_issues = 0
    project_stats = defaultdict(lambda: {"points": 0, "issues": 0, "records": 0})

    for point in qs.select_related("project", "project__client"):
        project_name = point.project.name if point.project else "Sin proyecto"
        client_name = point.project.client.name if (point.project and point.project.client) else "Sin cliente"

        issues, stats = audit_point(point, start_dt, end_dt, args.verbose)

        # Filtrar por severidad
        filtered = [i for i in issues if severity_rank[i["severity"]] >= min_rank]

        project_stats[project_name]["points"] += 1
        project_stats[project_name]["issues"] += len(filtered)
        project_stats[project_name]["records"] += stats["records"]

        if not filtered and not args.verbose:
            continue

        print(color(f"📍 Punto {point.id}: {point.title} | Proyecto: {project_name} | Cliente: {client_name}", Colors.CYAN))
        print(f"   Registros auditados: {stats['records']}")

        for issue in filtered:
            sev_color = {
                "CRITICAL": Colors.RED,
                "HIGH": Colors.RED,
                "MEDIUM": Colors.YELLOW,
                "LOW": Colors.GREEN,
            }.get(issue["severity"], Colors.RESET)
            print(f"   {color('[' + issue['severity'] + ']', sev_color)} {issue['dt'].strftime('%Y-%m-%d %H:%M')} | {issue['type']}: {issue['msg']}")

        if args.verbose:
            print(f"   Stats: {stats}")
        print()
        total_issues += len(filtered)

    # Resumen por proyecto
    print(color("=== RESUMEN POR PROYECTO ===", Colors.CYAN))
    for project, st in sorted(project_stats.items(), key=lambda x: -x[1]["issues"]):
        status = Colors.GREEN if st["issues"] == 0 else (Colors.YELLOW if st["issues"] < 5 else Colors.RED)
        print(f"{color(project, status)}: {st['points']} puntos, {st['records']} registros, {st['issues']} incoherencias")

    print()
    if total_issues == 0:
        print(color("✅ NO SE DETECTARON INCOHERENCIAS EN EL PERÍODO", Colors.GREEN))
    else:
        print(color(f"⚠️  TOTAL DE INCOHERENCIAS DETECTADAS: {total_issues}", Colors.YELLOW if total_issues < 20 else Colors.RED))

    print(color("=== FIN DE AUDITORÍA ===", Colors.CYAN))


if __name__ == "__main__":
    main()
