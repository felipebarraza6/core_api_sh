import sys
sys.path.append('/app')
import os
import django
from django.utils import timezone

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models.users import User
from api.telemetry.models import CatchmentPoint, CoreVariable, TelemetryMeasurement, TelemetryRecord
from api.telemetry.ingestion.controllers.unified_processing import save_telemetry_data

def test_ingestion_storage():
    print("--- Starting Ingestion Storage Verification ---")
    
    # 1. Mock Data
    user, _ = User.objects.get_or_create(email='test_ingest@example.com', defaults={'username': 'testingest'})
    point, _ = CatchmentPoint.objects.get_or_create(id=9998, defaults={'title': 'Ingest Point', 'owner_user': user})
    
    var_flow, _ = CoreVariable.objects.get_or_create(
        point=point,
        internal_code='flow',
        defaults={'name': 'Flow Variable'}
    )
    
    var_level, _ = CoreVariable.objects.get_or_create(
        point=point,
        internal_code='nivel',
        defaults={'name': 'Level Variable'}
    )
    
    # 2. Simulate Processed Register
    timestamp = timezone.now()
    created_register = {
        'date_time_medition': timestamp.isoformat(),
        'flow': 123.45,
        'nivel': 5.67,
        'ignored_var': 999.99 # Should not be saved as measurement because it has no CoreVariable
    }
    
    # 3. Call Controller
    print("Calling save_telemetry_data...")
    try:
        record = save_telemetry_data(point.id, created_register)
    except Exception as e:
        print(f"❌ FAILED: Exception in save_telemetry_data: {e}")
        return
    
    if not record:
        print("❌ FAILED: Record was not returned (returned None)")
        return

    print(f"✅ Record created: {record.id}")
    
    # 4. Verify Measurements
    measurements = TelemetryMeasurement.objects.filter(record=record)
    print(f"Found {measurements.count()} measurements associated with record.")
    
    if measurements.count() != 2:
         print(f"❌ FAILED: Expected 2 measurements (flow, nivel), got {measurements.count()}")
         for m in measurements:
             print(f"  - Found: {m.variable.internal_code} = {m.final_value}")
    else:
        print("✅ Correct number of measurements found.")
        
    # Check values
    m_flow = measurements.filter(variable=var_flow).first()
    if m_flow and abs(m_flow.final_value - 123.45) < 0.001:
        print(f"✅ Flow measurement correct: {m_flow.final_value}")
    else:
        print(f"❌ FAILED: Flow measurement incorrect or missing. Got: {m_flow.final_value if m_flow else 'None'}")
        
    m_level = measurements.filter(variable=var_level).first()
    if m_level and abs(m_level.final_value - 5.67) < 0.001:
        print(f"✅ Level measurement correct: {m_level.final_value}")
    else:
        print(f"❌ FAILED: Level measurement incorrect or missing. Got: {m_level.final_value if m_level else 'None'}")

    print("--- Verification Complete ---")

if __name__ == "__main__":
    test_ingestion_storage()
