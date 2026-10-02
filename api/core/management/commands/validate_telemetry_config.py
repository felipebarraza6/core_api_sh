"""
Validación de configuración de telemetría (solo lectura).

Detecta problemas de configuración que la auditoría 2026-10-02 encontró
como causa de lecturas falsas / envíos incorrectos a DGA:

1. Tokens de proveedor compartidos entre puntos distintos
   (ej. #14/#27 P100+Arauco, #3/#44 San Vicente+Sondaje 830).
2. Variables de NIVEL cuyo nombre sugiere mapeo incorrecto
   (ej. Monte Águila #26: str_variable="Nivel Freático" en vez de "nivel").
3. Tokens vacíos en puntos con telemetría activa.
4. Varias variables TOTALIZADO en el mismo punto.

Uso:
    python manage.py validate_telemetry_config
    python manage.py validate_telemetry_config --json
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

from django.core.management.base import BaseCommand

from api.core.models import (
    ProfileDataConfigCatchment,
    Variable,
)


# Nombres de variable de nivel que suelen ser un mapeo erróneo
# (auditoría: Monte Águila #26 pedía "Nivel Freático", que no existe en TheThings;
#  la variable real era "nivel").
_SUSPICIOUS_NIVEL_NAMES = re.compile(
    r"fre[aá]tic|water[\s_]?table|nivel[\s_]?fre",
    re.IGNORECASE,
)


def collect_config_issues():
    """
    Recorre perfiles y variables y devuelve un dict de hallazgos (solo lectura).

    Returns:
        {
          "shared_tokens": [...],
          "suspicious_nivel_variables": [...],
          "empty_tokens": [...],
          "multiple_totalizado": [...],
          "summary": {...},
        }
    """
    shared_tokens = []
    suspicious_nivel = []
    empty_tokens = []
    multiple_totalizado = []

    # --- Tokens por punto (profile + variables) ---
    # Un "token efectivo" de un punto es el conjunto de tokens no vacíos
    # que usa para consultar al proveedor.
    token_to_points = defaultdict(set)  # token -> set[(point_id, title, source)]
    point_tokens = defaultdict(set)  # point_id -> set[token]

    profiles = ProfileDataConfigCatchment.objects.select_related(
        "point_catchment"
    ).filter(is_telemetry=True)

    for profile in profiles:
        point = profile.point_catchment
        if not point:
            continue
        token = (profile.token_service or "").strip()
        if not token:
            empty_tokens.append({
                "point_id": point.id,
                "title": point.title,
                "source": "profile.token_service",
            })
            continue
        token_to_points[token].add((point.id, point.title, "profile"))
        point_tokens[point.id].add(token)

    # Variables con token propio
    variables = (
        Variable.objects.select_related("scheme_catchment")
        .prefetch_related("scheme_catchment__points_catchment")
        .all()
    )

    totalizado_by_point = defaultdict(list)

    for var in variables:
        scheme = var.scheme_catchment
        if not scheme:
            continue
        points = list(scheme.points_catchment.all())
        token = (var.token_service or "").strip()

        for point in points:
            if token:
                token_to_points[token].add((point.id, point.title, f"variable:{var.id}"))
                point_tokens[point.id].add(token)

            if (var.type_variable or "").upper() == "TOTALIZADO":
                totalizado_by_point[point.id].append({
                    "variable_id": var.id,
                    "str_variable": var.str_variable,
                    "title": point.title,
                })

            # NIVEL con nombre sospechoso (posible confusión con freático)
            if (var.type_variable or "").upper() == "NIVEL":
                name = var.str_variable or ""
                if _SUSPICIOUS_NIVEL_NAMES.search(name):
                    suspicious_nivel.append({
                        "point_id": point.id,
                        "title": point.title,
                        "variable_id": var.id,
                        "str_variable": name,
                        "type_variable": var.type_variable,
                        "hint": (
                            "El nombre sugiere 'nivel freático' pero el tipo es NIVEL. "
                            "Verificar que la variable exista en el proveedor "
                            "(caso Monte Águila #26: 'Nivel Freático' no existía; "
                            "la correcta era 'nivel')."
                        ),
                    })

    # Tokens compartidos entre ≥2 puntos distintos
    for token, owners in token_to_points.items():
        point_ids = {o[0] for o in owners}
        if len(point_ids) < 2:
            continue
        shared_tokens.append({
            "token_preview": f"{token[:8]}…{token[-4:]}" if len(token) > 14 else token,
            "token_length": len(token),
            "points": sorted(
                [{"point_id": pid, "title": title, "source": src} for pid, title, src in owners],
                key=lambda x: x["point_id"],
            ),
            "hint": (
                "Varios puntos leen el mismo dispositivo. "
                "Ejemplos auditados: #14/#27 y #3/#44."
            ),
        })

    for point_id, vars_list in totalizado_by_point.items():
        if len(vars_list) > 1:
            title = vars_list[0].get("title", "")
            multiple_totalizado.append({
                "point_id": point_id,
                "title": title,
                "variables": [
                    {"variable_id": v["variable_id"], "str_variable": v["str_variable"]}
                    for v in vars_list
                ],
            })

    # Deduplicar empty_tokens por point_id
    seen_empty = set()
    empty_deduped = []
    for item in empty_tokens:
        if item["point_id"] in seen_empty:
            continue
        seen_empty.add(item["point_id"])
        empty_deduped.append(item)

    # Deduplicar suspicious por (point_id, variable_id)
    seen_susp = set()
    susp_deduped = []
    for item in suspicious_nivel:
        key = (item["point_id"], item["variable_id"])
        if key in seen_susp:
            continue
        seen_susp.add(key)
        susp_deduped.append(item)

    return {
        "shared_tokens": shared_tokens,
        "suspicious_nivel_variables": susp_deduped,
        "empty_tokens": empty_deduped,
        "multiple_totalizado": multiple_totalizado,
        "summary": {
            "shared_token_groups": len(shared_tokens),
            "suspicious_nivel_count": len(susp_deduped),
            "empty_token_points": len(empty_deduped),
            "multiple_totalizado_points": len(multiple_totalizado),
            "has_issues": bool(
                shared_tokens or susp_deduped or empty_deduped or multiple_totalizado
            ),
        },
    }


class Command(BaseCommand):
    help = (
        "Valida configuración de telemetría (tokens duplicados, variables "
        "sospechosas). Solo lectura — no modifica datos."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Salida en JSON (para automatización).",
        )

    def handle(self, *args, **options):
        report = collect_config_issues()

        if options["json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return

        self.stdout.write("=" * 72)
        self.stdout.write("VALIDACIÓN DE CONFIG TELEMETRÍA (solo lectura)")
        self.stdout.write("=" * 72)

        summary = report["summary"]
        self.stdout.write(
            f"\nResumen: shared_tokens={summary['shared_token_groups']} | "
            f"nivel_sospechoso={summary['suspicious_nivel_count']} | "
            f"token_vacío={summary['empty_token_points']} | "
            f"multi_totalizado={summary['multiple_totalizado_points']}"
        )

        if report["shared_tokens"]:
            self.stdout.write(self.style.WARNING("\n--- Tokens compartidos entre puntos ---"))
            for group in report["shared_tokens"]:
                pts = ", ".join(
                    f"#{p['point_id']} ({p['title']})" for p in group["points"]
                )
                self.stdout.write(f"  token {group['token_preview']}: {pts}")
                self.stdout.write(f"    → {group['hint']}")

        if report["suspicious_nivel_variables"]:
            self.stdout.write(self.style.WARNING("\n--- Variables NIVEL con nombre sospechoso ---"))
            for item in report["suspicious_nivel_variables"]:
                self.stdout.write(
                    f"  #{item['point_id']} ({item['title']}): "
                    f"variable_id={item['variable_id']} "
                    f"str_variable='{item['str_variable']}'"
                )
                self.stdout.write(f"    → {item['hint']}")

        if report["empty_tokens"]:
            self.stdout.write(self.style.WARNING("\n--- Perfiles telemetría sin token ---"))
            for item in report["empty_tokens"]:
                self.stdout.write(f"  #{item['point_id']} ({item['title']})")

        if report["multiple_totalizado"]:
            self.stdout.write(self.style.WARNING("\n--- Puntos con varios TOTALIZADO ---"))
            for item in report["multiple_totalizado"]:
                names = ", ".join(v["str_variable"] for v in item["variables"])
                self.stdout.write(f"  #{item['point_id']} ({item['title']}): {names}")

        if not summary["has_issues"]:
            self.stdout.write(self.style.SUCCESS("\nSin problemas de configuración detectados."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    "\nHay hallazgos. Revisar con operaciones/cumplimiento. "
                    "Este comando no modifica datos."
                )
            )
