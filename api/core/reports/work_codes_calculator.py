"""
Calculadora del reporte de códigos de obra.

Helper reutilizable por:
- scripts/reporte_codigos_obra.py
- scripts/enviar_reporte_codigos_obra.py
- api/core/views/reports.py (endpoint)
- api/cronjobs/reports/work_codes_monthly.py (cronjob)
"""

from decimal import Decimal
from django.db.models import Count, Avg, Sum, Q, Max
from api.core.models import DgaDataConfigCatchment, InteractionDetail


def safe_float(value, default=0.0):
    """Convierte un valor a float de forma segura."""
    if value is None:
        return default
    if isinstance(value, (int, float, Decimal)):
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    try:
        return float(str(value).replace(",", "."))
    except (ValueError, TypeError):
        return default


def safe_int(value, default=0):
    """Convierte un valor a int de forma segura."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def build_work_codes_report(year, project_id=None):
    """
    Construye el reporte de códigos de obra.

    Args:
        year: Año a consultar (int).
        project_id: Opcional, filtrar por proyecto (int).

    Returns:
        list[dict]: Filas del reporte.
    """
    qs = DgaDataConfigCatchment.objects.select_related(
        "point_catchment", "point_catchment__project", "point_catchment__project__client"
    ).filter(
        code_dga__isnull=False
    ).exclude(
        code_dga=""
    ).order_by(
        "point_catchment__project__client__name",
        "point_catchment__project__name",
        "point_catchment__title",
    )

    if project_id:
        qs = qs.filter(point_catchment__project_id=project_id)

    results = []
    for cfg in qs:
        point = cfg.point_catchment
        if not point:
            continue

        project = point.project
        client = project.client if project else None

        flow_granted = safe_float(cfg.flow_granted_dga)
        total_granted = safe_int(cfg.total_granted_dga)

        tiene_caudal_configurado = flow_granted > 0
        tiene_total_configurado = total_granted > 0

        # Agregados del año para el punto
        agg = InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__year=year
        ).aggregate(
            veces_supero=Count(
                "id",
                filter=Q(flow__gt=cfg.flow_granted_dga) if tiene_caudal_configurado else Q(pk__isnull=True)
            ),
            caudal_promedio=Avg("flow"),
            consumo=Sum("total_diff"),
            ultima_medicion_anio=Max("date_time_medition"),
        )

        veces_supero = safe_int(agg["veces_supero"])
        caudal_promedio = safe_float(agg["caudal_promedio"])
        consumo = safe_int(agg["consumo"])
        ultima_medicion_anio = agg["ultima_medicion_anio"]

        # Última medición del punto (independiente del año)
        last_interaction = InteractionDetail.objects.filter(
            catchment_point=point
        ).order_by("-date_time_medition").first()
        ultima_medicion_punto = last_interaction.date_time_medition if last_interaction else None

        pct_gastado = None
        pct_disponible = None
        m3_disponibles = None
        estado_total = "OK"
        if tiene_total_configurado:
            pct_gastado = (consumo / total_granted) * 100
            pct_disponible = 100 - pct_gastado
            m3_disponibles = total_granted - consumo
            if pct_gastado >= 100:
                estado_total = "SUPERADO"
            elif pct_gastado >= 80:
                estado_total = "PROXIMO"
        else:
            estado_total = "SIN_TOTAL"

        estado_caudal = "OK"
        if not tiene_caudal_configurado:
            estado_caudal = "SIN_CAUDAL"
        elif veces_supero > 0:
            estado_caudal = "SUPERADO"

        results.append({
            "cliente": client.name if client else "Sin cliente",
            "proyecto": project.name if project else "Sin proyecto",
            "punto_id": point.id,
            "punto": point.title or "Sin título",
            "codigo_obra": cfg.code_dga,
            "estandar": cfg.get_standard_display() if cfg.standard else cfg.standard,
            "caudal_autorizado_lt_s": flow_granted if tiene_caudal_configurado else None,
            "tiene_caudal_configurado": tiene_caudal_configurado,
            "veces_supero_caudal": veces_supero,
            "caudal_promedio_lt_s": round(caudal_promedio, 2),
            "total_autorizado_m3": total_granted if tiene_total_configurado else None,
            "tiene_total_configurado": tiene_total_configurado,
            "consumo_acumulado_m3": consumo,
            "pct_gastado": round(pct_gastado, 2) if pct_gastado is not None else None,
            "pct_disponible": round(pct_disponible, 2) if pct_disponible is not None else None,
            "m3_disponibles": m3_disponibles,
            "estado_total": estado_total,
            "estado_caudal": estado_caudal,
            "ultima_medicion_anio": ultima_medicion_anio.strftime("%Y-%m-%d %H:%M") if ultima_medicion_anio else None,
            "ultima_medicion_punto": ultima_medicion_punto.strftime("%Y-%m-%d %H:%M") if ultima_medicion_punto else None,
        })

    return results
