import os
import django
from datetime import datetime
import pytz

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from django.conf import settings
from django.utils import timezone
from api.core.serializers.catchment_points import CatchmentPointIkoluSerializer

# Mock class to simulate InteractionDetail
class MockInteractionDetail:
    def __init__(self, dt, dt_last):
        self.date_time_medition = dt
        self.date_time_last_logger = dt_last
        self.flow = 10.5
        self.total = 1000
        self.total_diff = 10
        self.total_today_diff = 20
        self.nivel = 5.0
        self.water_table = 2.0
        self.send_dga = False
        self.return_dga = "OK"
        self.n_voucher = "ABC"

def test_timezone_serialization():
    print(f"Time Zone: {settings.TIME_ZONE}")
    
    # Create a specific UTC time: 2025-12-19 12:00:00 UTC
    # In America/Santiago (UTC-3), this should be 09:00:00
    utc_dt = datetime(2025, 12, 19, 12, 0, 0, tzinfo=pytz.UTC)
    
    # Mock serializer instance
    serializer = CatchmentPointIkoluSerializer()
    
    # Manually call _serialize_light
    records = [MockInteractionDetail(utc_dt, utc_dt)]
    serialized_data = serializer._serialize_light(records)
    
    result = serialized_data[0]
    print(f"Input UTC: {utc_dt}")
    print(f"Serialized date_time_medition: {result['date_time_medition']}")
    
    # Check expected format: %Y-%d-%m %H:%M
    # Expected Incorrect (Current): "2025-19-12 12:00" (UTC time)
    # Expected Correct (Goal): "2025-19-12 09:00" (Santiago time)
    
    expected_hour_str = "09:00" 
    if expected_hour_str in result['date_time_medition']:
         print("SUCCESS: Timezone converted correctly.")
    else:
         print("FAILURE: Timezone NOT converted correctly (likely showing UTC).")

if __name__ == "__main__":
    test_timezone_serialization()
