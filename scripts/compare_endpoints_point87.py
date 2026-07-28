#!/usr/bin/env python3
"""
COMPARACIÓN DE ENDPOINTS — PUNTO 87
===================================
Consume los endpoints legacy e Ikolu para enero 2026 y compara consumos.
Solo lectura.

Uso dentro del contenedor django_api_secure:
    docker exec django_api_secure python /app/scripts/compare_endpoints_point87.py
"""

import os
import sys
import json

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

from rest_framework.test import APIRequestFactory, force_authenticate
from django.contrib.auth import get_user_model

from api.core.views.interaction_detail import InteractionDetailOverrideMonthViewSet, InteractionDetailViewSet
from api.core.views import reports as reports_module
from django.utils import timezone
reports_module.timezone = timezone  # monkey patch: json_by_point usa timezone sin importar
from api.core.views.reports import ReportsGenerationViewSet
from api.api_ik.views import DashboardStatsView
from api.api_ik.views_control_center import ControlCenterDailySummaryView

POINT_ID = 87
YEAR = 2026
MONTH = 1


def make_request(view_cls, url, query_params, user, action=None):
    factory = APIRequestFactory()
    request = factory.get(url, query_params)
    force_authenticate(request, user=user)

    if action:
        view = view_cls.as_view({request.method.lower(): action})
    elif hasattr(view_cls, 'as_view'):
        # ViewSet sin action específico -> usar list por defecto
        view = view_cls.as_view({'get': 'list'})
    else:
        view = view_cls.as_view()
    response = view(request)
    return response.status_code, response.data


def run():
    User = get_user_model()
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        print("No hay superusuario")
        return

    print(f"Usuario usado para requests: {user.username}")
    print()

    # 1. InteractionDetailOverrideMonthViewSet
    print("=" * 80)
    print("1. /api/interaction_detail_override_month/?catchment_point=87&date_time_medition__month=01&date_time_medition__year=2026")
    print("=" * 80)
    status, data = make_request(
        InteractionDetailOverrideMonthViewSet,
        '/api/interaction_detail_override_month/',
        {'catchment_point': POINT_ID, 'date_time_medition__month': MONTH, 'date_time_medition__year': YEAR},
        user,
        action='list'
    )
    print(f"Status: {status}")
    if status == 200:
        results = data if isinstance(data, list) else data.get('results', [])
        # Son últimos registros por día
        total_diff_sum = sum(float(r.get('total_diff') or 0) for r in results)
        total_today_sum = sum(float(r.get('total_today_diff') or 0) for r in results)
        first_total = float(results[-1]['total']) if results else 0
        last_total = float(results[0]['total']) if results else 0
        print(f"Registros devueltos: {len(results)}")
        print(f"Suma total_diff expuesto: {total_diff_sum:.2f}")
        print(f"Suma total_today_diff expuesto: {total_today_sum:.2f}")
        print(f"Primer total (más antiguo): {first_total:.0f}")
        print(f"Último total (más reciente): {last_total:.0f}")
        print(f"Último - primero: {last_total - first_total:.2f}")
        print("Primeros 3 y últimos 3 registros:")
        for r in results[:3] + results[-3:]:
            print(f"  {r.get('date_time_medition')} | total={r.get('total')} | total_diff={r.get('total_diff')} | total_today_diff={r.get('total_today_diff')} | pulses={r.get('pulses')} | is_error={r.get('is_error')}")
    else:
        print(data)
    print()

    # 2. ReportsGenerationViewSet json_by_point
    print("=" * 80)
    print("2. /api/reports/json/by-point/?point_id=87&year=2026&month=1")
    print("=" * 80)
    status, data = make_request(
        ReportsGenerationViewSet,
        '/api/reports/json/by-point/',
        {'point_id': POINT_ID, 'year': YEAR, 'month': MONTH},
        user,
        action='json_by_point'
    )
    print(f"Status: {status}")
    if status == 200:
        daily = data.get('daily_data', [])
        total_consumo = sum(float(d.get('consumo') or 0) for d in daily)
        print(f"Días devueltos: {len(daily)}")
        print(f"Suma consumo diario: {total_consumo:.2f}")
        print("Primeros 3 y últimos 3 días:")
        for d in daily[:3] + daily[-3:]:
            print(f"  {d.get('dia')} | consumo={d.get('consumo')} | total={d.get('total')} | registros={d.get('registros')}")
    else:
        print(data)
    print()

    # 3. ReportsGenerationViewSet json_annual_compressed
    print("=" * 80)
    print("3. /api/reports/json/annual-compressed/ (año 2026)")
    print("=" * 80)
    project_id = None
    try:
        from api.core.models import CatchmentPoint
        cp = CatchmentPoint.objects.get(id=POINT_ID)
        project_id = cp.project_id
    except Exception as e:
        print(f"No se pudo obtener project_id: {e}")

    if project_id:
        status, data = make_request(
            ReportsGenerationViewSet,
            '/api/reports/json/annual-compressed/',
            {'project_id': project_id},
            user,
            action='json_annual_compressed'
        )
        print(f"Status: {status}")
        if status == 200:
            for item in data:
                if item.get('catchment_point_id') == POINT_ID:
                    print(json.dumps(item, indent=2, default=str))
                    break
        else:
            print(data)
    print()

    # 4. DashboardStatsView (últimos 7 días, no filtra por punto individual fácil)
    print("=" * 80)
    print("4. /api/ik/dashboard_stats/ (últimos 7 días, busca punto 87 en last_7)")
    print("=" * 80)
    status, data = make_request(
        DashboardStatsView,
        '/api/ik/dashboard_stats/',
        {},
        user
    )
    print(f"Status: {status}")
    if status == 200:
        last_7 = data.get('last_7', [])
        for entry in last_7:
            if entry.get('point_id') == POINT_ID:
                print(json.dumps(entry, indent=2, default=str))
                break
        else:
            print(f"Punto {POINT_ID} no está en la página actual de dashboard_stats")
    else:
        print(data)
    print()

    # 5. ControlCenterDailySummaryView
    print("=" * 80)
    print("5. /api/ik/control_center/daily_summary/ (rango enero 2026)")
    print("=" * 80)
    status, data = make_request(
        ControlCenterDailySummaryView,
        '/api/ik/control_center/daily_summary/',
        {'start_date': f'{YEAR}-01-01', 'end_date': f'{YEAR}-01-31', 'point_id': POINT_ID},
        user
    )
    print(f"Status: {status}")
    if status == 200:
        days = data.get('days', {})
        total = sum(float(v.get('total_consumption') or 0) for v in days.values())
        print(f"Suma total_consumption diaria: {total:.2f}")
        print(f"Días con datos: {sum(1 for v in days.values() if v.get('total_consumption', 0) > 0)}")
    else:
        print(data)
    print()

    # 6. InteractionDetailViewSet (detalle crudo) para comparar serializer vs BD
    print("=" * 80)
    print("6. /api/interaction_detail/?catchment_point=87&date_time_medition__year=2026&date_time_medition__month=01")
    print("=" * 80)
    status, data = make_request(
        InteractionDetailViewSet,
        '/api/interaction_detail/',
        {'catchment_point': POINT_ID, 'date_time_medition__year': YEAR, 'date_time_medition__month': MONTH},
        user,
        action='list'
    )
    print(f"Status: {status}")
    if status == 200:
        results = data.get('results', [])
        total_diff_sum = sum(float(r.get('total_diff') or 0) for r in results)
        print(f"Registros devueltos (paginado): {len(results)}")
        print(f"Suma total_diff expuesto: {total_diff_sum:.2f}")
        print("Primeros 3 registros (más recientes):")
        for r in results[:3]:
            print(f"  {r.get('date_time_medition')} | total={r.get('total')} | total_diff={r.get('total_diff')} | pulses={r.get('pulses')} | is_error={r.get('is_error')}")
    else:
        print(data)
    print()


if __name__ == "__main__":
    run()
