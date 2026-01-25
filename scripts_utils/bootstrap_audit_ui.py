
import sys
sys.path.append('/app')
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.dynamic_registry.models import SystemModule, ModuleView, DashboardWidget

def bootstrap_audit_ui():
    print("--- Bootstrapping Audit Log UI ---")
    
    # 1. Create/Get "Security & Audit" Module
    module, created = SystemModule.objects.get_or_create(
        slug='security-audit',
        defaults={
            'name': 'Seguridad y Auditoría',
            'description': 'Trazabilidad y control de acceso',
            'icon': 'security', # Material Icon
            'order': 99,
            'is_active': True,
            'required_permissions': ['dynamic_registry.view_auditlog']
        }
    )
    if created:
        print("✅ Created Module: Seguridad y Auditoría")
    else:
        print("ℹ️ Module already exists")

    # 2. Create "Audit Logs" Table View
    # Defines the Layout to show the AuditLog model
    view_logs, created = ModuleView.objects.get_or_create(
        module=module,
        key='audit-logs',
        defaults={
            'name': 'Registros de Auditoría',
            'view_type': 'TABLE',
            'data_source': '/api/registry/proxy/dynamic_registry/auditlog/',
            'is_home': True,
            'layout_config': {
                'columns': [
                    {'field': 'timestamp', 'label': 'Fecha/Hora', 'type': 'datetime', 'sortable': True},
                    {'field': 'user', 'label': 'Usuario', 'type': 'text'},
                    {'field': 'action', 'label': 'Acción', 'type': 'badge', 'colors': {'CREATE': 'green', 'UPDATE': 'blue', 'DELETE': 'red'}},
                    {'field': 'resource', 'label': 'Recurso', 'type': 'text'},
                    {'field': 'ip_address', 'label': 'IP Origen', 'type': 'text'}
                ],
                'actions': [
                    {'label': 'Ver Payload', 'action': 'OPEN_MODAL', 'target': 'audit-detail'}
                ]
            }
        }
    )
    if created:
        print("✅ Created View: Audit Logs Table")
    else:
        print("ℹ️ View 'Audit Logs' already exists")
        
    # 3. Create "Security Dashboard" (New Capability!)
    # Uses the DashboardWidget system
    view_dash, created = ModuleView.objects.get_or_create(
        module=module,
        key='security-dashboard',
        defaults={
            'name': 'Panel de Seguridad',
            'view_type': 'DASHBOARD',
            'order': 1
        }
    )
    if created:
        print("✅ Created View: Security Dashboard")
        
        # Add Widgets
        # Widget 1: Total Actions Today (Count)
        DashboardWidget.objects.create(
            dashboard=view_dash,
            widget_type='KPI_CARD',
            title='Movimientos Hoy',
            data_source='/api/registry/proxy/dynamic_registry/auditlog/?aggregate=count',
            order=1,
            visual_config={'color': 'blue', 'icon': 'history'}
        )
        print("   + Added Widget: KPI Movimientos")

    print("\n🎉 Bootstrap Complete. The 'Security' menu should now appear for admins.")

if __name__ == "__main__":
    bootstrap_audit_ui()
