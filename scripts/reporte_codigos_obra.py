#!/usr/bin/env python3
"""
REPORTE DE CÓDIGOS DE OBRA — SmartHydro
========================================

Script standalone de consola para validar el reporte de códigos de obra
antes de exponerlo como endpoint o cronjob.

USO:
    python scripts/reporte_codigos_obra.py --year 2026
    python scripts/reporte_codigos_obra.py --year 2025 --project-id 12

OUTPUT:
    Tabla por consola.
"""

import os
import sys
import argparse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django

django.setup()

from api.core.reports.work_codes_calculator import build_work_codes_report


def print_report(rows):
    """Imprime el reporte como tabla de consola."""
    if not rows:
        print("No se encontraron códigos de obra con los filtros indicados.")
        return

    headers = [
        "Cliente",
        "Proyecto",
        "Punto",
        "Código Obra",
        "Estándar",
        "Caudal Aut. (lt/s)",
        "Veces Sup.",
        "Caudal Prom. (lt/s)",
        "Total Aut. (m3)",
        "Consumo Año (m3)",
        "% Gastado",
        "% Disponible",
        "m3 Disponibles",
        "Estado Total",
        "Estado Caudal",
        "Última Medición",
    ]

    # Última medición punto para consola
    display_rows = []
    for r in rows:
        display_rows.append({
            "cliente": r["cliente"],
            "proyecto": r["proyecto"],
            "punto": r["punto"],
            "codigo_obra": r["codigo_obra"],
            "estandar": r["estandar"],
            "caudal_autorizado_lt_s": r["caudal_autorizado_lt_s"] if r["tiene_caudal_configurado"] else "SIN_CONFIG",
            "veces_supero_caudal": r["veces_supero_caudal"],
            "caudal_promedio_lt_s": r["caudal_promedio_lt_s"],
            "total_autorizado_m3": r["total_autorizado_m3"] if r["tiene_total_configurado"] else "SIN_CONFIG",
            "consumo_acumulado_m3": r["consumo_acumulado_m3"],
            "pct_gastado": r["pct_gastado"] if r["pct_gastado"] is not None else "",
            "pct_disponible": r["pct_disponible"] if r["pct_disponible"] is not None else "",
            "m3_disponibles": r["m3_disponibles"] if r["m3_disponibles"] is not None else "",
            "estado_total": r["estado_total"],
            "estado_caudal": r["estado_caudal"],
            "ultima_medicion": r["ultima_medicion_punto"] or r["ultima_medicion_anio"] or "",
        })

    widths = [len(h) for h in headers]
    for r in display_rows:
        values = [str(r[k]) for k in [
            "cliente", "proyecto", "punto", "codigo_obra", "estandar",
            "caudal_autorizado_lt_s", "veces_supero_caudal", "caudal_promedio_lt_s",
            "total_autorizado_m3", "consumo_acumulado_m3", "pct_gastado",
            "pct_disponible", "m3_disponibles", "estado_total", "estado_caudal",
            "ultima_medicion"
        ]]
        widths = [max(w, len(v)) for w, v in zip(widths, values)]

    def fmt_row(values):
        return " | ".join(v.ljust(w) for v, w in zip(values, widths))

    print(fmt_row(headers))
    print("-" * (sum(widths) + 3 * (len(headers) - 1)))
    for r in display_rows:
        values = [str(r[k]) for k in [
            "cliente", "proyecto", "punto", "codigo_obra", "estandar",
            "caudal_autorizado_lt_s", "veces_supero_caudal", "caudal_promedio_lt_s",
            "total_autorizado_m3", "consumo_acumulado_m3", "pct_gastado",
            "pct_disponible", "m3_disponibles", "estado_total", "estado_caudal",
            "ultima_medicion"
        ]]
        print(fmt_row(values))

    print(f"\nTotal filas: {len(rows)}")


def main():
    parser = argparse.ArgumentParser(description="Reporte de códigos de obra")
    parser.add_argument("--year", type=int, required=True, help="Año a consultar (ej: 2026)")
    parser.add_argument("--project-id", type=int, default=None, help="Filtrar por proyecto")
    parser.add_argument("--json", action="store_true", help="Imprimir como JSON en vez de tabla")
    args = parser.parse_args()

    rows = build_work_codes_report(args.year, args.project_id)

    if args.json:
        import json
        print(json.dumps(rows, indent=2, default=str))
    else:
        print_report(rows)


if __name__ == "__main__":
    main()
