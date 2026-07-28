#!/usr/bin/env python3
"""
AUDITORÍA PUNTO 87 — SAN FERNANDO DOLE
======================================
Diagnóstico de discrepancias en totales anuales/mensuales.
Solo lectura. No modifica datos.

Uso dentro del contenedor django_api_secure:
    docker exec django_api_secure python /app/scripts/audit_point_87_san_fernando.py
"""

import os
import sys
from datetime import datetime, date
from collections import defaultdict

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

from django.db import connection
from django.db.models import Sum, Min, Max, Count, Avg, Q
from django.utils import timezone
import pytz

from api.core.models import InteractionDetail, CatchmentPoint, CounterResetLog, ProfileDataConfigCatchment

POINT_ID = 87
YEAR = 2026


def safe_float(val):
    try:
        return float(val) if val is not None and val != '' else 0.0
    except (ValueError, TypeError):
        return 0.0


def run():
    chile_tz = pytz.timezone("America/Santiago")
    point = CatchmentPoint.objects.filter(id=POINT_ID).first()
    if not point:
        print(f"Punto {POINT_ID} no encontrado")
        return

    print(f"Punto: #{point.id} — {point.title}")
    print(f"Proveedor: TWIN={point.is_tdata} NOVUS={point.is_novus} NETTRA={point.is_thethings}")
    print(f"Frecuencia: {point.frecuency}")
    print()

    # Perfil y addition
    profile = ProfileDataConfigCatchment.objects.filter(point_catchment=point).first()
    if profile:
        print(f"ProfileDataConfigCatchment.addition actual: {profile.addition}")
        print(f"  d6={profile.d6}, max_diff_m3_per_hour={profile.max_diff_m3_per_hour}, reconnection_threshold_hours={profile.reconnection_threshold_hours}")
    else:
        print("Sin ProfileDataConfigCatchment")
    print()

    # Variables
    from api.core.models import Variable
    variables = Variable.objects.filter(scheme_catchment__points_catchment=point)
    var_types = list(variables.values_list('type_variable', flat=True).distinct())
    print(f"Variables asociadas: {var_types}")
    totalizado_var = variables.filter(type_variable='TOTALIZADO').first()
    if totalizado_var:
        print(f"TOTALIZADO pulses_factor: {totalizado_var.pulses_factor}")
    print()

    # Datos por mes
    print("=" * 80)
    print("DIAGNÓSTICO POR MES — AÑO 2026")
    print("=" * 80)

    results = []
    for month in range(1, 13):
        month_start = datetime(YEAR, month, 1, 0, 0, 0, tzinfo=chile_tz)
        if month == 12:
            month_end = datetime(YEAR + 1, 1, 1, 0, 0, 0, tzinfo=chile_tz)
        else:
            month_end = datetime(YEAR, month + 1, 1, 0, 0, 0, tzinfo=chile_tz)

        qs = InteractionDetail.objects.filter(
            catchment_point=point,
            date_time_medition__gte=month_start,
            date_time_medition__lt=month_end,
        )

        if not qs.exists():
            continue

        # Agregaciones
        agg_all = qs.aggregate(
            count=Count('id'),
            sum_total_diff=Sum('total_diff'),
            min_total=Min('total'),
            max_total=Max('total'),
            avg_flow=Avg('flow'),
            error_count=Count('id', filter=Q(is_error=True)),
            zero_diff_count=Count('id', filter=Q(total_diff=0)),
        )

        agg_no_error = qs.exclude(is_error=True).aggregate(
            sum_total_diff=Sum('total_diff'),
            min_total=Min('total'),
            max_total=Max('total'),
        )

        # Primer y último registro
        first = qs.order_by('date_time_medition').first()
        last = qs.order_by('-date_time_medition').first()

        # last - first (todos)
        first_total = safe_float(first.total) if first else 0
        last_total = safe_float(last.total) if last else 0
        last_minus_first_all = last_total - first_total if last_total >= first_total else last_total

        # last - first (sin errores)
        first_ne = qs.exclude(is_error=True).order_by('date_time_medition').first()
        last_ne = qs.exclude(is_error=True).order_by('-date_time_medition').first()
        first_total_ne = safe_float(first_ne.total) if first_ne else 0
        last_total_ne = safe_float(last_ne.total) if last_ne else 0
        last_minus_first_ne = last_total_ne - first_total_ne if last_total_ne >= first_total_ne else last_total_ne

        results.append({
            'month': month,
            'count': agg_all['count'] or 0,
            'sum_total_diff_all': agg_all['sum_total_diff'] or 0,
            'sum_total_diff_no_error': agg_no_error['sum_total_diff'] or 0,
            'last_minus_first_all': last_minus_first_all,
            'last_minus_first_no_error': last_minus_first_ne,
            'min_total': safe_float(agg_all['min_total']),
            'max_total': safe_float(agg_all['max_total']),
            'first_total': first_total,
            'last_total': last_total,
            'first_dt': first.date_time_medition.astimezone(chile_tz).strftime('%Y-%m-%d %H:%M:%S') if first and first.date_time_medition else None,
            'last_dt': last.date_time_medition.astimezone(chile_tz).strftime('%Y-%m-%d %H:%M:%S') if last and last.date_time_medition else None,
            'error_count': agg_all['error_count'] or 0,
            'zero_diff_count': agg_all['zero_diff_count'] or 0,
        })

    # Imprimir tabla
    header = f"{'Mes':>4} {'Regs':>8} {'Σdiff(todos)':>14} {'Σdiff(ok)':>14} {'Last-First(todos)':>18} {'Last-First(ok)':>16} {'Errores':>8} {'ZeroDiff':>9} {'Primer total':>14} {'Último total':>14}"
    print(header)
    print("-" * len(header))

    annual_sum_diff_all = 0
    annual_sum_diff_ne = 0
    annual_last_minus_first = 0
    for r in results:
        annual_sum_diff_all += r['sum_total_diff_all']
        annual_sum_diff_ne += r['sum_total_diff_no_error']
        annual_last_minus_first += r['last_minus_first_all']
        print(f"{r['month']:>4} {r['count']:>8} {r['sum_total_diff_all']:>14.2f} {r['sum_total_diff_no_error']:>14.2f} {r['last_minus_first_all']:>18.2f} {r['last_minus_first_no_error']:>16.2f} {r['error_count']:>8} {r['zero_diff_count']:>9} {r['first_total']:>14.0f} {r['last_total']:>14.0f}")

    print("-" * len(header))
    print(f"{'ANUAL':>4} {sum(r['count'] for r in results):>8} {annual_sum_diff_all:>14.2f} {annual_sum_diff_ne:>14.2f} {annual_last_minus_first:>18.2f} {'-':>16} {'-':>8} {'-':>9} {'-':>14} {'-':>14}")
    print()

    # Detalle de discrepancias mes a mes
    print("=" * 80)
    print("DISCREPANCIAS MES A MES (Σdiff(todos) vs Last-First)")
    print("=" * 80)
    for r in results:
        diff = r['sum_total_diff_all'] - r['last_minus_first_all']
        if abs(diff) > 1:
            print(f"Mes {r['month']:02d}: Δ = {diff:+.2f} m³ | Σdiff={r['sum_total_diff_all']:.2f} | Last-First={r['last_minus_first_all']:.2f}")
    print()

    # Resets
    print("=" * 80)
    print("COUNTER RESET LOGS — 2026")
    print("=" * 80)
    year_start = datetime(YEAR, 1, 1, 0, 0, 0, tzinfo=chile_tz)
    year_end = datetime(YEAR + 1, 1, 1, 0, 0, 0, tzinfo=chile_tz)
    resets = CounterResetLog.objects.filter(
        point_catchment=point,
        date_time_medition__gte=year_start,
        date_time_medition__lt=year_end,
    ).order_by('date_time_medition')

    if resets.exists():
        print(f"{'Fecha':>20} {'Tipo':>20} {'Last pulses':>12} {'Curr pulses':>12} {'Amount add':>12} {'Add before':>12} {'Add after':>12} {'Total before':>14} {'Total after':>14}")
        for r in resets:
            dt = r.date_time_medition.astimezone(chile_tz).strftime('%Y-%m-%d %H:%M:%S') if r.date_time_medition else '-'
            print(f"{dt:>20} {r.reset_type:>20} {r.last_pulses or '-':>12} {r.current_pulses or '-':>12} {r.amount_to_add or '-':>12} {r.addition_before or '-':>12} {r.addition_after or '-':>12} {r.total_before or '-':>14} {r.total_after or '-':>14}")
    else:
        print("No hay CounterResetLog en 2026")
    print()

    # Registros con total_diff=0 pero total cambiando
    print("=" * 80)
    print("REGISTROS CON total_diff=0 PERO total CAMBIANDO (>1 m³)")
    print("=" * 80)
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                id,
                date_time_medition,
                total,
                total_diff,
                pulses,
                is_error,
                LAG(total::numeric) OVER (ORDER BY date_time_medition) as prev_total
            FROM core_interactiondetail
            WHERE catchment_point_id = %s
              AND date_time_medition >= %s
              AND date_time_medition < %s
            ORDER BY date_time_medition
        """, [POINT_ID, year_start, year_end])

        suspicious = []
        for row in cursor.fetchall():
            pk, dt, total, total_diff, pulses, is_error, prev_total = row
            total_num = safe_float(total)
            prev_num = safe_float(prev_total)
            if total_diff == 0 and abs(total_num - prev_num) > 1:
                suspicious.append({
                    'id': pk,
                    'dt': dt.astimezone(chile_tz).strftime('%Y-%m-%d %H:%M:%S') if dt else '-',
                    'total': total_num,
                    'prev_total': prev_num,
                    'diff': total_num - prev_num,
                    'pulses': pulses,
                    'is_error': is_error,
                })

        if suspicious:
            print(f"Encontrados {len(suspicious)} registros sospechosos (primeros 50):")
            print(f"{'ID':>8} {'Fecha':>20} {'Total':>12} {'Prev total':>12} {'Δ total':>10} {'Pulses':>10} {'is_error':>8}")
            for s in suspicious[:50]:
                print(f"{s['id']:>8} {s['dt']:>20} {s['total']:>12.0f} {s['prev_total']:>12.0f} {s['diff']:>10.0f} {s['pulses'] or 0:>10} {str(s['is_error']):>8}")
        else:
            print("No se encontraron registros con total_diff=0 y total cambiando")
    print()

    # Detalle de caídas inexplicadas
    print("=" * 80)
    print("CAÍDAS INEXPLICADAS DE TOTAL (total < prev_total - 1)")
    print("=" * 80)
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                id,
                date_time_medition,
                total::numeric as total_num,
                LAG(total::numeric) OVER (ORDER BY date_time_medition) as prev_total,
                pulses,
                is_error
            FROM core_interactiondetail
            WHERE catchment_point_id = %s
              AND date_time_medition >= %s
              AND date_time_medition < %s
            ORDER BY date_time_medition
        """, [POINT_ID, year_start, year_end])

        drops = []
        for row in cursor.fetchall():
            pk, dt, total_num, prev_total, pulses, is_error = row
            total_num = safe_float(total_num)
            prev_num = safe_float(prev_total)
            if total_num < prev_num - 1:
                drops.append({
                    'id': pk,
                    'dt': dt.astimezone(chile_tz).strftime('%Y-%m-%d %H:%M:%S') if dt else '-',
                    'total': total_num,
                    'prev_total': prev_num,
                    'drop': prev_num - total_num,
                    'pulses': pulses,
                    'is_error': is_error,
                })

        if drops:
            print(f"Encontradas {len(drops)} caídas (primeras 50):")
            print(f"{'ID':>8} {'Fecha':>20} {'Total':>12} {'Prev total':>12} {'Caída':>10} {'Pulses':>10} {'is_error':>8}")
            for d in drops[:50]:
                print(f"{d['id']:>8} {d['dt']:>20} {d['total']:>12.0f} {d['prev_total']:>12.0f} {d['drop']:>10.0f} {d['pulses'] or 0:>10} {str(d['is_error']):>8}")
        else:
            print("No se encontraron caídas inexplicadas")
    print()

    print("=" * 80)
    print("FIN DEL DIAGNÓSTICO")
    print("=" * 80)


if __name__ == "__main__":
    run()
