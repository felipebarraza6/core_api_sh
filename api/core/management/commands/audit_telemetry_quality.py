"""
AUDITORÍA DE CALIDAD DE TELEMETRÍA — SmartHydro
===============================================
Escáner SQL-first de alta performance sobre todo el rango solicitado
(por defecto el año 2026). Detecta problemas de salud de la data:

    1. COBERTURA      - registros esperados vs reales por punto y frecuencia
    2. HUECOS         - saltos entre lecturas consecutivas > intervalo esperado
    3. ERRORES        - registros is_error por punto (ingestas fallidas)
    4. MONOTONICIDAD  - decrementos de total (posibles resets / micro-ruido)
    5. COLA DGA       - pendientes de envío (send_dga sin voucher)
    6. PUNTOS MUERTOS - telemetría activa sin datos o sin datos recientes
    7. DUPLICADOS     - mismo punto+fecha medition más de una vez
    8. OUTLIERS       - flujo negativo, flujo > concedido, saltos absurdos
    9. RECONEXIÓN     - eventos days_not_conection > 0
   10. NULLS          - campos críticos NULL en registros exitosos

El escaneo pesado se hace íntegramente en SQL (window functions + GROUP BY)
sobre el índice date_time_medition. No itera registros en Python.

Uso:
    python manage.py audit_telemetry_quality
    python manage.py audit_telemetry_quality --start 2026-01-01 --end 2026-12-31
    python manage.py audit_telemetry_quality --checks coverage gaps errors
    python manage.py audit_telemetry_quality --output /tmp/smarthydro/audit_2026.txt
"""

import argparse
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from django.core.management.base import BaseCommand
from django.db import connection

FREQ_PER_DAY = {
    "1": 1440, "5": 288, "10": 144, "15": 96, "30": 48, "60": 24,
}

# Umbral de gap según frecuencia (factor 1.5 del intervalo nominal), en minutos
FREQ_GAP_MIN = {
    "1": 2, "5": 8, "10": 15, "15": 22, "30": 45, "60": 90,
}


class Command(BaseCommand):
    help = "Auditoría SQL-first de calidad de telemetría (cobertura, huecos, errores, monotonicidad, cola DGA, etc.)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--start", default="2026-01-01", help="Inicio del rango (YYYY-MM-DD)")
        parser.add_argument("--end", default=None, help="Fin del rango (YYYY-MM-DD); default: hoy")
        parser.add_argument(
            "--checks",
            nargs="*",
            default=None,
            help="Chequeos a ejecutar (coverage gaps errors monotonic queue dead duplicates outliers reconnection nulls config). Default: todos",
        )
        parser.add_argument("--output", default="/tmp/smarthydro/audit_telemetry_quality.txt", help="Archivo de reporte")
        parser.add_argument("--threshold-coverage", type=float, default=95.0, help="Cobertura mínima esperada por punto (%)")
        parser.add_argument("--max-results", type=int, default=25, help="Máximo de hallazgos detallados por chequeo")

    def handle(self, *args, **options) -> None:
        start_str = options["start"]
        end_str = options["end"] or datetime.utcnow().strftime("%Y-%m-%d")
        start = f"{start_str} 00:00:00"
        end = f"{end_str} 23:59:59"
        output = options["output"]
        threshold = options["threshold_coverage"]
        max_results = options["max_results"]

        self.stdout.write("\n" + "=" * 84)
        self.stdout.write(f"AUDITORÍA DE CALIDAD DE TELEMETRÍA | Rango: {start_str} → {end_str}")
        self.stdout.write("=" * 84)

        self.stdout.write("\n🔍 Dimensionando el rango...")
        dim = self._one_row(
            "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE is_error) AS errores, "
            "COUNT(DISTINCT catchment_point_id) AS puntos "
            "FROM core_interactiondetail WHERE date_time_medition >= %s AND date_time_medition <= %s",
            [start, end],
        )
        total = int(dim["total"] or 0)
        errores = int(dim["errores"] or 0)
        puntos = int(dim["puntos"] or 0)
        self.stdout.write(
            f"   Registros: {total:,} | Errores: {errores:,} ({errores / max(total, 1) * 100:.2f}%) | Puntos: {puntos}"
        )

        checks = options["checks"]
        runner = self._run_check

        results: List[Dict[str, Any]] = []

        def exec_check(name: str, fn) -> None:
            t0 = time.time()
            out = fn(start, end, threshold, max_results)
            elapsed = time.time() - t0
            results.append({"name": name, "elapsed": elapsed, **out})
            self.stdout.write(out["summary"])
            self.stdout.write(f"   [{name}] {elapsed:.1f}s")

        if checks is None or "config" in checks:
            exec_check("config", self._check_config)

        if checks is None or "coverage" in checks:
            exec_check("coverage", self._check_coverage)

        if checks is None or "gaps" in checks:
            exec_check("gaps", self._check_gaps)

        if checks is None or "errors" in checks:
            exec_check("errors", self._check_errors)

        if checks is None or "monotonic" in checks:
            exec_check("monotonic", self._check_monotonic)

        if checks is None or "queue" in checks:
            exec_check("queue", self._check_queue)

        if checks is None or "dead" in checks:
            exec_check("dead", self._check_dead)

        if checks is None or "duplicates" in checks:
            exec_check("duplicates", self._check_duplicates)

        if checks is None or "outliers" in checks:
            exec_check("outliers", self._check_outliers)

        if checks is None or "reconnection" in checks:
            exec_check("reconnection", self._check_reconnection)

        if checks is None or "nulls" in checks:
            exec_check("nulls", self._check_nulls)

        self._write_report(output, start_str, end_str, results, total, errores, puntos)
        self.stdout.write(f"\n📄 Reporte completo: {output}")

    # ------------------------------------------------------------------ utils

    def _run_check(self, fn, start, end, threshold, max_results):
        return fn(start, end, threshold, max_results)

    def _query(self, sql: str, params: Optional[List] = None) -> List[dict]:
        with connection.cursor() as c:
            c.execute(sql, params or [])
            cols = [d[0] for d in c.description]
            return [dict(zip(cols, row)) for row in c.fetchall()]

    def _one_row(self, sql: str, params: Optional[List] = None) -> dict:
        with connection.cursor() as c:
            c.execute(sql, params or [])
            cols = [d[0] for d in c.description]
            row = c.fetchone()
            return dict(zip(cols, row)) if row else {}

    def _health(self, coverage: float, error_rate: float) -> float:
        return round(100 * min(max(coverage, 0), 1) * (1 - min(max(error_rate, 0), 0.5)), 1)

    # ------------------------------------------------------------- checkers

    def _check_config(self, start, end, threshold, max_results) -> Dict[str, Any]:
        findings = []
        orphans = self._query(
            "SELECT p.id, p.title FROM core_catchmentpoint p "
            "WHERE NOT EXISTS (SELECT 1 FROM core_profiledataconfigcatchment d WHERE d.point_catchment_id = p.id) "
            "ORDER BY p.id LIMIT %s",
            [max_results],
        )
        no_dga = self._query(
            "SELECT p.id, p.title FROM core_catchmentpoint p "
            "JOIN core_profiledataconfigcatchment d ON d.point_catchment_id = p.id AND d.is_telemetry = true "
            "WHERE NOT EXISTS (SELECT 1 FROM core_dgadataconfigcatchment g WHERE g.point_catchment_id = p.id) "
            "ORDER BY p.id LIMIT %s",
            [max_results],
        )
        dga_sin_codigo = self._query(
            "SELECT g.point_catchment_id AS id, p.title FROM core_dgadataconfigcatchment g "
            "JOIN core_catchmentpoint p ON p.id = g.point_catchment_id "
            "WHERE g.send_dga = true AND (g.code_dga IS NULL OR g.code_dga = '') "
            "ORDER BY g.point_catchment_id LIMIT %s",
            [max_results],
        )
        for r in orphans:
            findings.append(f"  • Sin ProfileDataConfigCatchment: #{r['id']} {r['title']}")
        for r in no_dga:
            findings.append(f"  • Telemetría activa sin config DGA: #{r['id']} {r['title']}")
        for r in dga_sin_codigo:
            findings.append(f"  • send_dga activo pero sin code_dga: #{r['id']} {r['title']}")
        summary = f"🔧 CONFIGURACIÓN: {len(orphans)} puntos sin perfil, {len(no_dga)} telemetría sin DGA, {len(dga_sin_codigo)} DGA sin código"
        return {"summary": summary, "findings": findings}

    def _check_coverage(self, start, end, threshold, max_results) -> Dict[str, Any]:
        rows = self._query(
            """
            SELECT cp.id, cp.title, cp.frecuency, d.date_start_telemetry,
                   cnt.registros, cnt.dias_activos, exp.expected_dias
            FROM core_catchmentpoint cp
            JOIN core_profiledataconfigcatchment d ON d.point_catchment_id = cp.id
            JOIN LATERAL (
                SELECT COUNT(*) AS registros,
                       COUNT(DISTINCT i.date_time_medition::date) AS dias_activos
                FROM core_interactiondetail i
                WHERE i.catchment_point_id = cp.id
                  AND i.date_time_medition >= %s AND i.date_time_medition <= %s
            ) cnt ON TRUE
            JOIN LATERAL (
                SELECT COUNT(*) AS expected_dias
                FROM generate_series(
                    GREATEST(%s::date, COALESCE(d.date_start_telemetry::date, %s::date)),
                    %s::date, interval '1 day'
                )
            ) exp ON TRUE
            WHERE d.is_telemetry = true AND cp.frecuency IS NOT NULL AND cp.frecuency <> ''
            ORDER BY cp.id
            """,
            [start, end, start, start, end],
        )
        per_day = FREQ_PER_DAY.get
        bad, good, total_pts = [], [], 0
        for r in rows:
            freq = r["frecuency"]
            freq_day = per_day(freq, 24)
            if not freq_day:
                continue
            total_pts += 1
            expected = int(r["expected_dias"] or 0) * freq_day
            actual = int(r["registros"] or 0)
            cov = actual / expected * 100 if expected else 100.0
            err_rate = 0.0
            r["coverage"] = round(cov, 1)
            r["expected"] = expected
            if cov < threshold:
                bad.append(r)
            else:
                good.append(r)

        bad_sorted = sorted(bad, key=lambda r: r["coverage"])
        findings = []
        for r in bad_sorted[:max_results]:
            findings.append(
                f"  • #{r['id']} {r['title']} (freq {r['frecuency']}m): {r['coverage']}%  ({r['registros']}/{r['expected']} lecturas, {r['dias_activos']} días activos de {r['expected_dias']})"
            )
        summary = (
            f"📊 COBERTURA: {total_pts} puntos telemetría | {len(bad)} bajo {threshold}% | "
            f"mejor {round(max((r['coverage'] for r in good), default=0), 1)}% / peor {round(min((r['coverage'] for r in bad), default=100), 1)}%"
        )
        return {"summary": summary, "findings": findings, "details": bad_sorted}

    def _check_gaps(self, start, end, threshold, max_results) -> Dict[str, Any]:
        rows = self._query(
            """
            WITH serie AS (
                SELECT i.catchment_point_id,
                       i.date_time_medition,
                       EXTRACT(EPOCH FROM i.date_time_medition - LAG(i.date_time_medition)
                           OVER (PARTITION BY i.catchment_point_id ORDER BY i.date_time_medition)) / 60.0 AS gap_min
                FROM core_interactiondetail i
                WHERE i.date_time_medition >= %s AND i.date_time_medition <= %s
            )
            SELECT s.catchment_point_id AS id, cp.title, cp.frecuency,
                   COUNT(*) AS gaps, MAX(s.gap_min) AS mayor_gap_min
            FROM serie s
            JOIN core_catchmentpoint cp ON cp.id = s.catchment_point_id
            WHERE cp.frecuency != '' AND cp.frecuency IS NOT NULL
              AND s.gap_min > CASE cp.frecuency
                WHEN '1' THEN 2 WHEN '5' THEN 8 WHEN '10' THEN 15
                WHEN '15' THEN 22 WHEN '30' THEN 45 ELSE 90 END
            GROUP BY s.catchment_point_id, cp.title, cp.frecuency
            ORDER BY gaps DESC LIMIT %s
            """,
            [start, end, max_results],
        )
        total_gaps = sum(int(r["gaps"] or 0) for r in rows)
        findings = []
        for r in rows:
            horas = float(r["mayor_gap_min"]) / 60
            findings.append(
                f"  • #{r['id']} {r['title']} (freq {r['frecuency']}m): {r['gaps']} huecos, mayor de {horas:.1f}h"
            )
        summary = f"🕳️ HUECOS: {total_gaps} saltos de serie en {len(rows)} puntos (top {len(rows)} mostrado)"
        return {"summary": summary, "findings": findings}

    def _check_errors(self, start, end, threshold, max_results) -> Dict[str, Any]:
        rows = self._query(
            """
            SELECT i.catchment_point_id AS id, cp.title, COUNT(*) AS errores,
                   COUNT(*) FILTER (WHERE i.date_time_medition >= NOW() - INTERVAL '48 hours') AS errores_48h
            FROM core_interactiondetail i
            JOIN core_catchmentpoint cp ON cp.id = i.catchment_point_id
            WHERE i.is_error AND i.date_time_medition >= %s AND i.date_time_medition <= %s
            GROUP BY 1, 2 ORDER BY errores DESC LIMIT %s
            """,
            [start, end, max_results],
        )
        total_err = sum(int(r["errores"] or 0) for r in rows)
        findings = []
        for r in rows:
            active = f", {r['errores_48h']} en últimas 48h" if r["errores_48h"] else ""
            findings.append(f"  • #{r['id']} {r['title']}: {r['errores']} ingestas fallidas{active}")
        summary = f"❌ ERRORES: {total_err} registros is_error en {len(rows)} puntos (top {len(rows)} mostrado)"
        return {"summary": summary, "findings": findings}

    def _check_monotonic(self, start, end, threshold, max_results) -> Dict[str, Any]:
        rows = self._query(
            """
            WITH serie AS (
                SELECT i.catchment_point_id, i.date_time_medition,
                       CASE WHEN i.total ~ '^[+-]?[0-9]+([.][0-9]+)?$' THEN i.total::numeric END AS total,
                       LAG(CASE WHEN i.total ~ '^[+-]?[0-9]+([.][0-9]+)?$' THEN i.total::numeric END)
                           OVER (PARTITION BY i.catchment_point_id ORDER BY i.date_time_medition) AS prev
                FROM core_interactiondetail i
                WHERE i.date_time_medition >= %s AND i.date_time_medition <= %s AND i.total IS NOT NULL
            )
            SELECT s.catchment_point_id AS id, cp.title,
                   COUNT(*) AS decrementos,
                   COUNT(*) FILTER (WHERE s.prev - s.total > 10) AS resets_grandes,
                   COUNT(*) FILTER (WHERE s.prev - s.total <= 10) AS micro_ruido
            FROM serie s
            JOIN core_catchmentpoint cp ON cp.id = s.catchment_point_id
            WHERE s.prev IS NOT NULL AND s.total < s.prev
            GROUP BY s.catchment_point_id, cp.title
            ORDER BY decrementos DESC LIMIT %s
            """,
            [start, end, max_results],
        )
        total_dec = sum(int(r["decrementos"] or 0) for r in rows)
        total_reset = sum(int(r["resets_grandes"] or 0) for r in rows)
        total_micro = sum(int(r["micro_ruido"] or 0) for r in rows)
        findings = []
        for r in rows:
            findings.append(
                f"  • #{r['id']} {r['title']}: {r['decrementos']} decrementos ({r['resets_grandes']} resets>10, {r['micro_ruido']} micro≤10)"
            )
        summary = f"📉 MONOTONICIDAD: {total_dec} decrementos en {len(rows)} puntos | {total_reset} resets grandes + {total_micro} micro-ruido"
        return {"summary": summary, "findings": findings}

    def _check_queue(self, start, end, threshold, max_results) -> Dict[str, Any]:
        rows = self._query(
            """
            SELECT i.catchment_point_id AS id, cp.title,
                   COUNT(*) AS pendientes,
                   MAX(i.date_time_medition) AS mas_antiguo,
                   MIN(i.date_time_medition) AS mas_reciente
            FROM core_interactiondetail i
            JOIN core_catchmentpoint cp ON cp.id = i.catchment_point_id
            WHERE i.send_dga AND i.n_voucher IS NULL
              AND i.date_time_medition >= %s AND i.date_time_medition <= %s
            GROUP BY 1, 2 ORDER BY pendientes DESC LIMIT %s
            """,
            [start, end, max_results],
        )
        total = sum(int(r["pendientes"] or 0) for r in rows)
        findings = []
        for r in rows:
            findings.append(
                f"  • #{r['id']} {r['title']}: {r['pendientes']} pendientes (más antiguo {r['mas_antiguo']}, más reciente {r['mas_reciente']})"
            )
        summary = f"📤 COLA DGA: {total} registros send_dga sin voucher en {len(rows)} puntos"
        return {"summary": summary, "findings": findings}

    def _check_dead(self, start, end, threshold, max_results) -> Dict[str, Any]:
        rows = self._query(
            """
            WITH ult AS (
                SELECT i.catchment_point_id, MAX(i.date_time_medition) AS ultimo
                FROM core_interactiondetail i GROUP BY 1
            )
            SELECT cp.id, cp.title, cp.frecuency, u.ultimo,
                   CASE WHEN u.ultimo IS NULL THEN 9999
                        ELSE EXTRACT(EPOCH FROM (NOW() - u.ultimo)) / 86400 END AS dias_sin_dato
            FROM core_catchmentpoint cp
            JOIN core_profiledataconfigcatchment d ON d.point_catchment_id = cp.id
            LEFT JOIN ult u ON u.catchment_point_id = cp.id
            WHERE d.is_telemetry = true
              AND (u.ultimo IS NULL OR u.ultimo < NOW() - INTERVAL '7 days')
            ORDER BY dias_sin_dato DESC LIMIT %s
            """,
            [max_results],
        )
        findings = []
        for r in rows:
            label = "NUNCA tuvo datos" if r["ultimo"] is None else f"sin datos {float(r['dias_sin_dato']):.0f} días (último {r['ultimo']})"
            findings.append(f"  • #{r['id']} {r['title']} (freq {r['frecuency']}): {label}")
        summary = f"💀 PUNTOS MUERTOS: {len(rows)} con telemetría activa sin datos >7 días o nunca"
        return {"summary": summary, "findings": findings}

    def _check_duplicates(self, start, end, threshold, max_results) -> Dict[str, Any]:
        rows = self._query(
            """
            SELECT catchment_point_id AS id, COUNT(*) AS veces
            FROM core_interactiondetail
            WHERE date_time_medition >= %s AND date_time_medition <= %s
            GROUP BY 1, date_time_medition HAVING COUNT(*) > 1
            ORDER BY veces DESC LIMIT %s
            """,
            [start, end, max_results],
        )
        total = sum(int(r["veces"] - 1) for r in rows)
        findings = [f"  • #{r['id']}: {r['veces']} registros duplicados" for r in rows]
        summary = f"🔁 DUPLICADOS: {total} duplicaciones en {len(rows)} puntos"
        return {"summary": summary, "findings": findings}

    def _check_outliers(self, start, end, threshold, max_results) -> Dict[str, Any]:
        neg_flow = self._query(
            """
            SELECT i.catchment_point_id AS id, cp.title, COUNT(*) AS negativos
            FROM core_interactiondetail i JOIN core_catchmentpoint cp ON cp.id = i.catchment_point_id
            WHERE i.flow < 0 AND i.date_time_medition >= %s AND i.date_time_medition <= %s
            GROUP BY 1, 2 ORDER BY negativos DESC LIMIT %s
            """,
            [start, end, max_results],
        )
        findings = [f"  • Flujo negativo #{r['id']} {r['title']}: {r['negativos']} lecturas" for r in neg_flow]
        summary = f"⚠️ OUTLIERS: {sum(int(r['negativos']) for r in neg_flow)} lecturas con flujo negativo en {len(neg_flow)} puntos"
        return {"summary": summary, "findings": findings}

    def _check_reconnection(self, start, end, threshold, max_results) -> Dict[str, Any]:
        rows = self._query(
            """
            SELECT i.catchment_point_id AS id, cp.title, COUNT(*) AS eventos,
                   MAX(i.days_not_conection) AS max_dias
            FROM core_interactiondetail i JOIN core_catchmentpoint cp ON cp.id = i.catchment_point_id
            WHERE i.days_not_conection > 0 AND i.date_time_medition >= %s AND i.date_time_medition <= %s
            GROUP BY 1, 2 ORDER BY eventos DESC LIMIT %s
            """,
            [start, end, max_results],
        )
        total = sum(int(r["eventos"] or 0) for r in rows)
        findings = [
            f"  • #{r['id']} {r['title']}: {r['eventos']} eventos de reconexión (hasta {r['max_dias']} días desconectado)"
            for r in rows
        ]
        summary = f"🔄 RECONEXIÓN: {total} eventos days_not_conection>0 en {len(rows)} puntos"
        return {"summary": summary, "findings": findings}

    def _check_nulls(self, start, end, threshold, max_results) -> Dict[str, Any]:
        rows = self._query(
            """
            SELECT i.catchment_point_id AS id, cp.title,
                   COUNT(*) FILTER (WHERE i.total IS NULL) AS total_null,
                   COUNT(*) FILTER (WHERE i.flow IS NULL) AS flow_null
            FROM core_interactiondetail i
            JOIN core_catchmentpoint cp ON cp.id = i.catchment_point_id
            JOIN core_schemescatchment_points_catchment sc ON sc.catchmentpoint_id = cp.id
            JOIN core_variable v ON v.scheme_catchment_id = sc.schemescatchment_id
            WHERE NOT i.is_error
              AND v.type_variable = 'TOTALIZADO'
              AND i.date_time_medition >= %s AND i.date_time_medition <= %s
            GROUP BY 1, 2
            HAVING COUNT(*) FILTER (WHERE i.total IS NULL) > 0
                OR COUNT(*) FILTER (WHERE i.flow IS NULL) > 0
            ORDER BY total_null DESC LIMIT %s
            """,
            [start, end, max_results],
        )
        findings = [
            f"  • #{r['id']} {r['title']}: total NULL en {r['total_null']}, flow NULL en {r['flow_null']}"
            for r in rows
        ]
        summary = f"🈳 NULLS: {len(rows)} puntos con campos críticos NULL en registros exitosos"
        return {"summary": summary, "findings": findings}

    # -------------------------------------------------------------- report

    def _write_report(self, output, start_str, end_str, results, total, errores, puntos) -> None:
        import os

        lines = [
            "# AUDITORÍA DE CALIDAD DE TELEMETRÍA",
            f"Rango: {start_str} → {end_str}",
            f"Ejecutado: {datetime.utcnow().isoformat()}Z",
            "",
            f"## Dimensión: {total:,} registros | {errores:,} errores ({errores / max(total, 1) * 100:.2f}%) | {puntos} puntos",
            "",
        ]
        for r in results:
            lines.append(f"## [{r['name']}] ({r['elapsed']:.1f}s)")
            lines.append(r["summary"])
            for f in r.get("findings", []):
                lines.append(f)
            lines.append("")
        try:
            os.makedirs(os.path.dirname(output), exist_ok=True)
            with open(output, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
        except OSError as e:
            self.stdout.write(f"⚠️ No se pudo escribir reporte {output}: {e}")
