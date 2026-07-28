"""Helpers para calcular consumo a partir del totalizador acumulado."""

from django.db.models import F


def calculate_consumption_for_points(point_ids, start_dt, end_dt):
    """
    Calcula el consumo real en un rango de fechas como la diferencia entre
    el último total acumulado válido y el primero del rango.

    Esto evita acumular saltos anómalos provenientes de datos corruptos o
    reseteos mal compensados que afectan a Sum('total_diff').

    Args:
        point_ids: iterable de IDs de CatchmentPoint.
        start_dt: datetime aware de inicio del rango (inclusive).
        end_dt: datetime aware de término del rango (inclusive).

    Returns:
        dict: {catchment_point_id: consumo_en_m3 (float)}
    """
    from api.core.models import InteractionDetail

    if not point_ids:
        return {}

    first_total_map = {
        item['catchment_point_id']: float(item['total'] or 0)
        for item in InteractionDetail.objects.filter(
            catchment_point_id__in=point_ids,
            date_time_medition__gte=start_dt,
            date_time_medition__lte=end_dt,
            is_error=False,
        ).exclude(total__isnull=True).exclude(total='').order_by(
            'catchment_point_id', 'date_time_medition'
        ).distinct('catchment_point_id').values('catchment_point_id', 'total')
    }

    last_total_map = {
        item['catchment_point_id']: float(item['total'] or 0)
        for item in InteractionDetail.objects.filter(
            catchment_point_id__in=point_ids,
            date_time_medition__gte=start_dt,
            date_time_medition__lte=end_dt,
            is_error=False,
        ).exclude(total__isnull=True).exclude(total='').order_by(
            'catchment_point_id', '-date_time_medition'
        ).distinct('catchment_point_id').values('catchment_point_id', 'total')
    }

    result = {}
    for cp_id in point_ids:
        first_total = first_total_map.get(cp_id, 0.0)
        last_total = last_total_map.get(cp_id, 0.0)
        result[cp_id] = max(0.0, last_total - first_total)

    return result


def calculate_consumption_for_point(point_id, start_dt, end_dt):
    """
    Versión para un único punto.
    """
    result = calculate_consumption_for_points([point_id], start_dt, end_dt)
    return result.get(point_id, 0.0)


def get_filtered_total_consumption_year(cp_id, year):
    from django.db import connection
    from django.db.models import Sum, Value
    from django.db.models.functions import Coalesce
    from api.core.models import InteractionDetail

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COALESCE(
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_diff),
                0.0
            )
            FROM core_interactiondetail
            WHERE catchment_point_id = %s
              AND EXTRACT(YEAR FROM date_time_medition) = %s
              AND total_diff > 0
              AND is_error = false
        """, [cp_id, year])
        row = cursor.fetchone()
        median = float(row[0]) if row and row[0] is not None else 0.0

    threshold = max(median * 5, 10)

    result = InteractionDetail.objects.filter(
        catchment_point_id=cp_id,
        date_time_medition__year=year,
        total_diff__lte=threshold,
        is_error=False,
    ).aggregate(
        total=Coalesce(Sum('total_diff'), Value(0))
    )
    return float(result['total']) or 0
