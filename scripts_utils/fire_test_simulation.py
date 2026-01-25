
import sys
sys.path.append('/app')
import os
import django
from django.utils import timezone
import json

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from api.telemetry.models import CatchmentPoint, TelemetryRecord, CoreVariable
from api.dynamic_registry.models import AuditLog
from api.compliance.models import ComplianceVoucher, ComplianceProvider

def fire_test():
    print("🔥 INICIANDO PRUEBA DE FUEGO DEL SISTEMA 🔥")
    print("==========================================")

    User = get_user_model()
    # 1. Setup User (Operator)
    user, _ = User.objects.get_or_create(username='operator_fire', email='op@fire.com')
    # Grant permissions needed
    from django.contrib.auth.models import Permission
    perms = Permission.objects.filter(codename__in=['change_telemetryrecord', 'view_auditlog', 'view_catchmentpoint', 'add_telemetryrecord'])
    user.user_permissions.add(*perms)
    
    client = APIClient()
    client.force_authenticate(user=user)

    # 2. Setup Infrastructure (Point)
    print("\n[PASO 1] Creando Infraestructura Virtual...")
    point, created = CatchmentPoint.objects.get_or_create(
        point_code='FIRE-TEST-001',
        defaults={'title': 'Pozo de Prueba Fire', 'is_active': True}
    )
    print(f"✅ Punto de Captación: {point} (ID: {point.id})")

    # 3. Simulate Ingestion (Raw Telemetry)
    # We will use the Proxy to simulate a "Manual Entry" or direct API ingestion if exposed.
    # For now, let's create the record directly to simulate the "Hardware" part.
    print("\n[PASO 2] Simulando Ingestión de Hardware (MQTT)...")
    variable, _ = CoreVariable.objects.get_or_create(code='flow', defaults={'name': 'Caudal', 'unit': 'l/s'})
    
    record = TelemetryRecord.objects.create(
        point=point,
        variable=variable,
        value=50.5,
        timestamp=timezone.now(),
        metadata={'source': 'fire_test_script'}
    )
    print(f"✅ Telemetría Ingestada: {record.value} l/s a las {record.timestamp}")

    # 4. User Interaction: Correction via Data Proxy
    # The operator realizes 50.5 is wrong, it should be 55.0
    print("\n[PASO 3] Operador corrige dato vía Data Proxy (Audit)...")
    
    url = f'/api/registry/proxy/telemetry/telemetryrecord/{record.id}/'
    payload = {'value': 55.0} # PATCH
    
    resp = client.patch(url, payload, format='json')
    
    if resp.status_code == 200:
        print(f"✅ Corrección Exitosa: Valor actualizado a {resp.data['value']}")
    else:
        print(f"❌ Error en Proxy: {resp.status_code} {resp.content}")
        return

    # 5. Verify Audit Log
    print("\n[PASO 4] Verificando Auditoría (Traceability)...")
    log = AuditLog.objects.filter(resource_id=str(record.id), action='UPDATE').last()
    if log:
        print(f"✅ Auditoría Encontrada: {log}")
        print(f"   Payload: {log.payload}")
        print(f"   User: {log.user.email}")
    else:
        print("❌ FALLO: No se encontró registro de auditoría.")

    # 6. Compliance Snapshot
    print("\n[PASO 5] Verificando Salud Normativa...")
    # Simulate a voucher separately to see if dashboard picks it up
    provider, _ = ComplianceProvider.objects.get_or_create(name='test_dga', defaults={'display_name': 'Test DGA', 'data_endpoint_template': '/api'})
    ComplianceVoucher.objects.create(
        point=point,
        provider=provider,
        data_timestamp=timezone.now(),
        voucher_status='SENT', # Success!
        voucher_code='XYZ-123'
    )
    
    resp_dash = client.get('/api/compliance/dashboard/status_summary/')
    if resp_dash.status_code == 200:
        data = resp_dash.json()
        print(f"✅ Dashboard de Compliance: Health Score = {data['health_score']}%")
        print(f"   Stats: {data['stats']}")
    else:
        print(f"❌ Error Dashboard: {resp_dash.status_code}")

    print("\n🔥 PRUEBA DE FUEGO COMPLETADA 🔥")

if __name__ == "__main__":
    fire_test()
