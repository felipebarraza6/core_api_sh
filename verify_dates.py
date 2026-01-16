
import os
import sys
from datetime import datetime
import pytz

# sys.path.append('/root/core_api_sh')
# os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
# django.setup()

from api.core.serializers.catchment_points import CatchmentPointIkoluSerializer, InteractionDetailModuleSerializer
from api.core.models import InteractionDetail

# Mock objects to test serialization without DB if possible, or use real objects
# However, creating mock objects for Django models can be tricky.
# Let's try to verify the _serialize_light method directly or via a dummy object wrapper if possible.
# Actually, we can just test the method logic in isolation or create a real InteractionDetail in memory.

class MockInteractionDetail:
    def __init__(self, date_time_medition, date_time_last_logger, flow, total, total_diff, total_today_diff, nivel, water_table, send_dga, return_dga, n_voucher):
        self.date_time_medition = date_time_medition
        self.date_time_last_logger = date_time_last_logger
        self.flow = flow
        self.total = total
        self.total_diff = total_diff
        self.total_today_diff = total_today_diff
        self.nivel = nivel
        self.water_table = water_table
        self.send_dga = send_dga
        self.return_dga = return_dga
        self.n_voucher = n_voucher

# Test Data
tz = pytz.timezone("America/Santiago")
dt = datetime(2023, 10, 27, 14, 30, 0, tzinfo=tz)

mock_obj = MockInteractionDetail(
    date_time_medition=dt,
    date_time_last_logger=dt,
    flow=10.5,
    total=1000,
    total_diff=5,
    total_today_diff=50,
    nivel=1.2,
    water_table=2.5,
    send_dga=True,
    return_dga=True,
    n_voucher='123'
)

# Test _serialize_light via the serializer class (instantiating it)
# We can access the method if we instantiate the serializer
serializer = CatchmentPointIkoluSerializer()
serialized_data = serializer._serialize_light([mock_obj])

print("Serialized Data (Light):")
print(serialized_data[0]['date_time_medition'])

# Verify format
expected_format = "2023-10-27 14:30:00"
if serialized_data[0]['date_time_medition'] == expected_format:
    print("SUCCESS: Date format is correct (ISO-like)")
else:
    print(f"FAILURE: Date format is incorrect. Got: {serialized_data[0]['date_time_medition']}")

# Test InteractionDetailModuleSerializer
# We need to use a real model instance or a mock that behaves like one for DRF ModelSerializer
# But ModelSerializer usually requires a model instance.
# Let's just create an InteractionDetail object in memory (not saved)
detail = InteractionDetail(
    date_time_medition=dt,
    date_time_last_logger=dt,
    flow=10.5,
    total=1000,
    total_diff=5,
    total_today_diff=50,
    nivel=1.2,
    water_table=2.5,
    send_dga=True,
    return_dga=True,
    n_voucher='123'
)
# Mock the cached property or method if needed, but here we just need to test date field
# The serializer field format handles it.

serializer_detail = InteractionDetailModuleSerializer(detail)
print("\nSerialized Data (Standard DRF):")
print(serializer_detail.data['date_time_medition'])

if serializer_detail.data['date_time_medition'] == expected_format:
    print("SUCCESS: Standard serializer date format is correct")
else:
    print(f"FAILURE: Standard serializer date format is incorrect. Got: {serializer_detail.data['date_time_medition']}")
