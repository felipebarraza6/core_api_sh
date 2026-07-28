#!/usr/bin/env python3
"""
ANÁLISIS GLOBAL — Puntos que necesitan backfill / compensación de reset
=======================================================================

Detecta tres problemas comunes en telemetría 2026:
1. Resets no compensados: el totalizador bajó y el profile.addition no compensó.
2. Consumo anual negativo o cero en puntos DGA con límite configurado.
3. Huecos de datos en la crisis Redis 17-22 mayo 2026.

USO:
    docker exec -u root -w /app django_api_secure python scripts/analyze_backfill_needed.py

OUTPUT:
    /tmp/backfill_analysis_YYYYMMDD_HHMMSS.csv
    /tmp/backfill_analysis_summary.json
"""

import os
import sys
import json
import csv
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django

django.setup()

import pytz
from django.utils import timezone
from api.core.models import (
    CatchmentPoint,
    DgaDataConfigCatchment,
    InteractionDetail,
    ProfileDataConfigCatchment,
)
from api.cronjobs.telemetry.controllers.backfill_processing import detect_gaps

CHILE_TZ = pytz.timezone("America/Santiago")

# Umbral mínimo de compensación perdida para reportar (m³)
MIN_LOST_OFFSET_M3 = 100


def log(msg):
    print(msg, flush=True)


def get_year_bounds(year):
    start = timezone.make_aware(datetime(year, 1, 1, 0, 0, 0))
    end = timezone.make_aware(datetime(year, 12, 31, 23, 59, 59))
    return start, end


def detect_uncompensated_resets(point, year_start, year_end):
    """
    Detecta resets no compensados en la serie de totales del año.
    Retorna lista de dicts con información de cada reset detectado.
    """
    qs = (
        InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__gte=year_start,
            date_time_medition__lte=year_end,
        )
        .exclude(total__isnull=True)
        .exclude(total="")
        .exclude(total="None")
        .order_by("date_time_medition")
        .values("id", "date_time_medition", "pulses", "total", "total_diff", "is_error")
    )

    records = list(qs)
    if len(records) < 2:
        return []

    profile = point.data_config_profiles.filter(is_telemetry=True).first()
    current_addition = float(profile.addition) if profile and profile.addition else 0.0

    resets = []
    prev = None
    for i, r in enumerate(records):
        try:
            curr_total = float(r["total"] or 0)
            curr_pulses = int(r["pulses"] or 0)
        except (ValueError, TypeError):
            prev = r
            continue

        if prev is not None:
            try:
                prev_total = float(prev["total"] or 0)
                prev_pulses = int(prev["pulses"] or 0)
            except (ValueError, TypeError):
                prev = r
                continue

            # Heurística de reset REAL no compensado:
            # - pulsos bajan a 0 tras tener valor > 0 (o total cae fuerte)
            # - el total nunca se recupera al valor previo en el futuro
            #   (descarta ZERO_KEPT donde el cron mantuvo el total)
            # - el addition del perfil no compensa la caída
            is_zero_reset = curr_pulses == 0 and prev_pulses > 0 and not r["is_error"]
            is_total_drop = curr_total < prev_total * 0.5 and prev_total > 0 and not r["is_error"]

            if is_zero_reset or is_total_drop:
                lost_offset = prev_total

                # Buscar máximo total en el futuro del año
                future = records[i + 1:]
                max_total_after = max(
                    [float(f.get("total") or 0) for f in future] + [curr_total]
                )

                # Si el total se recuperó al 90% o más, fue ZERO_KEPT (no requiere backfill)
                recovered = max_total_after >= prev_total * 0.9

                # Si addition ya compensó al menos la mitad de la caída, no reportar
                addition_compensated = current_addition >= lost_offset * 0.5

                if not recovered and not addition_compensated and lost_offset >= MIN_LOST_OFFSET_M3:
                    resets.append({
                        "reset_dt": r["date_time_medition"],
                        "prev_dt": prev["date_time_medition"],
                        "prev_pulses": prev_pulses,
                        "prev_total": prev_total,
                        "reset_pulses": curr_pulses,
                        "reset_total": curr_total,
                        "lost_offset_m3": lost_offset,
                        "max_total_after": max_total_after,
                        "current_addition": current_addition,
                    })

        prev = r

    return resets


def detect_annual_anomalies(point, year_start, year_end, dga_config):
    """
    Detecta consumo anual negativo o cero en puntos DGA con límite configurado.
    Retorna dict o None.
    """
    qs = (
        InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__gte=year_start,
            date_time_medition__lte=year_end,
            is_error=False,
        )
        .exclude(total__isnull=True)
        .exclude(total="")
        .exclude(total="None")
        .order_by("date_time_medition")
    )

    first = qs.first()
    last = qs.last()
    if not first or not last:
        return None

    try:
        first_total = float(first.total or 0)
        last_total = float(last.total or 0)
    except (ValueError, TypeError):
        return None

    annual = last_total - first_total
    authorized_total = float(dga_config.total_granted_dga) if dga_config and dga_config.total_granted_dga else 0

    if authorized_total <= 0:
        return None

    # Anomalía: consumo negativo o 0 (o muy bajo comparado con límite)
    if annual <= 0 or (annual / authorized_total) < 0.001:
        return {
            "first_dt": first.date_time_medition,
            "first_total": first_total,
            "last_dt": last.date_time_medition,
            "last_total": last_total,
            "annual_m3": annual,
            "authorized_total": authorized_total,
            "pct_consumed": (annual * 100.0 / authorized_total) if authorized_total > 0 else 0,
        }

    return None


def analyze_point(point, year_start, year_end, crisis_start, crisis_end):
    """Analiza un punto y retorna hallazgos."""
    findings = {
        "point_id": point.id,
        "point_name": point.title,
        "project_name": point.project.name if point.project else "",
        "client_name": point.project.client.name if point.project and point.project.client else "",
        "telemetry_provider": _provider_name(point),
        "resets": [],
        "annual_anomaly": None,
        "may_gaps": [],
    }

    # 1. Resets no compensados
    findings["resets"] = detect_uncompensated_resets(point, year_start, year_end)

    # 2. Anomalía anual (solo si tiene config DGA con límite)
    dga_config = DgaDataConfigCatchment.objects.filter(point_catchment=point).first()
    if dga_config and dga_config.total_granted_dga:
        findings["annual_anomaly"] = detect_annual_anomalies(point, year_start, year_end, dga_config)

    # 3. Huecos 17-22 mayo
    try:
        gaps = detect_gaps(point, crisis_start, crisis_end)
        if gaps:
            total_missing = sum(g["missing_count"] for g in gaps)
            # Solo reportar huecos significativos (>12 registros faltantes)
            # o que caigan dentro del núcleo de la crisis 19-22 mayo
            if total_missing > 12:
                findings["may_gaps"] = {
                    "gap_count": len(gaps),
                    "total_missing": total_missing,
                    "first_gap": gaps[0]["start_gap"],
                    "last_gap": gaps[-1]["end_gap"],
                }
    except Exception as e:
        findings["may_gaps_error"] = str(e)

    return findings


def _provider_name(point):
    if point.telemetry_provider:
        return point.telemetry_provider.name
    if point.is_tdata:
        return "TWIN/TDATA"
    if point.is_thethings:
        return "Nettra"
    if point.is_novus:
        return "Novus"
    return "Desconocido"


def main():
    year = 2026
    year_start, year_end = get_year_bounds(year)
    crisis_start = timezone.make_aware(datetime(2026, 5, 17, 0, 0, 0))
    crisis_end = timezone.make_aware(datetime(2026, 5, 23, 0, 0, 0))

    log("=" * 70)
    log("ANÁLISIS GLOBAL — Puntos que necesitan backfill / compensación")
    log("=" * 70)
    log(f"Año: {year}")
    log(f"Crisis Redis: {crisis_start} → {crisis_end}")
    log("")

    points = CatchmentPoint.objects.select_related("project__client").order_by("id")
    total_points = points.count()
    log(f"Puntos a analizar: {total_points}")

    findings_list = []
    points_with_reset = 0
    points_with_annual_anomaly = 0
    points_with_may_gaps = 0

    for idx, point in enumerate(points.iterator(), 1):
        if idx % 50 == 0:
            log(f"  ... analizando {idx}/{total_points}")

        f = analyze_point(point, year_start, year_end, crisis_start, crisis_end)
        has_issue = bool(f["resets"] or f["annual_anomaly"] or f["may_gaps"])
        if not has_issue:
            continue

        if f["resets"]:
            points_with_reset += 1
        if f["annual_anomaly"]:
            points_with_annual_anomaly += 1
        if f["may_gaps"]:
            points_with_may_gaps += 1

        findings_list.append(f)

    # Escribir CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = f"/app/tmp/backfill_analysis_{timestamp}.csv"
    json_path = f"/app/tmp/backfill_analysis_summary_{timestamp}.json"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "point_id", "point_name", "project_name", "client_name", "provider",
            "issue_type", "detail",
            "reset_dt", "prev_total", "lost_offset_m3", "current_addition",
            "annual_m3", "authorized_total", "pct_consumed",
            "may_gaps_count", "may_missing_total", "may_first_gap", "may_last_gap",
        ])
        for f in findings_list:
            base = [
                f["point_id"],
                f["point_name"],
                f["project_name"],
                f["client_name"],
                f["telemetry_provider"],
            ]
            # Una fila por reset
            for r in f["resets"]:
                writer.writerow(base + [
                    "RESET_NO_COMPENSADO",
                    f"Reset en {r['reset_dt']}: pulsos {r['prev_pulses']} -> {r['reset_pulses']} | max_total_after={r['max_total_after']}",
                    r["reset_dt"],
                    r["prev_total"],
                    r["lost_offset_m3"],
                    r["current_addition"],
                    "", "", "",
                    "", "", "", "",
                ])

            # Fila por anomalía anual
            if f["annual_anomaly"]:
                a = f["annual_anomaly"]
                writer.writerow(base + [
                    "CONSUMO_ANUAL_ANOMALO",
                    f"Consumo={a['annual_m3']:.1f} m3 entre {a['first_dt']} y {a['last_dt']}",
                    "", "", "", "",
                    f"{a['annual_m3']:.2f}",
                    a["authorized_total"],
                    f"{a['pct_consumed']:.4f}",
                    "", "", "", "",
                ])

            # Fila por huecos mayo
            if f["may_gaps"]:
                g = f["may_gaps"]
                writer.writerow(base + [
                    "HUECOS_MAYO_CRISIS",
                    f"{g['gap_count']} gaps, {g['total_missing']} registros faltantes",
                    "", "", "", "", "", "", "",
                    g["gap_count"],
                    g["total_missing"],
                    g["first_gap"],
                    g["last_gap"],
                ])

    # Escribir JSON resumen
    summary = {
        "analyzed_at": timestamp,
        "year": year,
        "total_points": total_points,
        "points_with_issues": len(findings_list),
        "points_with_reset": points_with_reset,
        "points_with_annual_anomaly": points_with_annual_anomaly,
        "points_with_may_gaps": points_with_may_gaps,
        "csv_path": csv_path,
        "findings": findings_list,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    log("")
    log("=" * 70)
    log("RESUMEN")
    log("=" * 70)
    log(f"Puntos analizados: {total_points}")
    log(f"Puntos con problemas: {len(findings_list)}")
    log(f"  - Resets no compensados: {points_with_reset}")
    log(f"  - Consumo anual anómalo: {points_with_annual_anomaly}")
    log(f"  - Huecos crisis mayo 17-22: {points_with_may_gaps}")
    log("")
    log(f"CSV:  {csv_path}")
    log(f"JSON: {json_path}")


if __name__ == "__main__":
    main()
