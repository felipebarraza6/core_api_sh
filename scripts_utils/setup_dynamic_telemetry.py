
import sys
sys.path.append('/app')
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.dynamic_registry.models import SystemModule, ModuleView, DynamicAction

def setup_telemetry_ui():
    print("--- Setting up Dynamic Telemetry UI ---")
    
    # 1. Module: Telemetría
    mod, created = SystemModule.objects.update_or_create(
        slug='telemetry',
        defaults={
            'name': 'Gestión de Telemetría',
            'description': 'Monitoreo de pozos y canales en tiempo real',
            'icon': 'water_drop',
            'order': 10,
            'is_active': True
        }
    )
    print(f"✅ Module: {mod}")

    # 2. View: Table of Catchment Points
    layout_table = {
        "title": "Puntos de Captación",
        "columns": [
            {"key": "point_code", "label": "Código", "type": "text", "sortable": True},
            {"key": "name", "label": "Nombre", "type": "text", "sortable": True},
            {"key": "status", "label": "Estado", "type": "status_badge"},
            {"key": "last_reading", "label": "Última Lectura", "type": "datetime"},
        ],
        "filters": [
            {"key": "status", "label": "Estado", "type": "select", "options": ["active", "alert", "offline"]},
            {"key": "search", "label": "Buscar...", "type": "search_bar"}
        ]
    }
    
    view_list, _ = ModuleView.objects.update_or_create(
        module=mod,
        key='points-list',
        defaults={
            'name': 'Puntos de Captación',
            'view_type': 'TABLE',
            'data_source': '/api/telemetry/points/',
            'layout_config': layout_table,
            'is_home': True,
            'order': 1
        }
    )
    
    # Actions for Table
    DynamicAction.objects.update_or_create(
        view=view_list,
        key='create_point',
        defaults={
            'name': 'Nuevo Punto',
            'icon': 'add',
            'action_type': 'NAVIGATE',
            'target': '/telemetry/points/new'
        }
    )
    print(f"✅ View: {view_list}")

    # 3. View: Dashboard
    view_dash, _ = ModuleView.objects.update_or_create(
        module=mod,
        key='global-dashboard',
        defaults={
            'name': 'Dashboard Global',
            'view_type': 'DASHBOARD',
            'data_source': '/api/telemetry/stats/global/',
            'layout_config': {
                "widgets": [
                    {"type": "kpi_card", "title": "Total Puntos", "data_key": "total_points"},
                    {"type": "chart_line", "title": "Caudal Promedio (24h)", "data_key": "flow_history"},
                    {"type": "map_view", "title": "Ubicación Geográfica"}
                ]
            },
            'order': 0
        }
    )
    print(f"✅ View: {view_dash}")
    print("--- Setup Complete ---")

if __name__ == "__main__":
    setup_telemetry_ui()
