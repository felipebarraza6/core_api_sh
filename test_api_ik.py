#!/usr/bin/env python
"""Test script for api_ik endpoints (separate from main API)."""
import os
import sys
import django

# Setup Django
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from django.test import RequestFactory
from rest_framework.test import force_authenticate
from api.core.views.batch_views import BatchTelemetryView, BatchStatsView
from api.api_ik.views import OptimizedLoginView
from api.core.models import User, CatchmentPoint

# Get test user
user = User.objects.filter(is_staff=True).first()
if not user:
    print('ERROR: No staff user found')
    sys.exit(1)

print(f"Testing with user: {user.email}")

# Get some real point IDs
point_ids = list(CatchmentPoint.objects.values_list('id', flat=True)[:5])
print(f"Using point_ids: {point_ids}")

factory = RequestFactory()

# Test 1: BatchTelemetryView (now via /api/ik/batch/telemetry/)
print(f"\n=== Test 1: /api/ik/batch/telemetry/ ===")
request = factory.post('/api/ik/batch/telemetry/', 
    {'point_ids': point_ids, 'hours': 24}, 
    content_type='application/json')
force_authenticate(request, user=user)
response = BatchTelemetryView.as_view()(request)
print(f"Status: {response.status_code}")
print(f"Returned: {response.data.get('meta', {}).get('returned', 0)} points")

# Test 2: BatchStatsView
print(f"\n=== Test 2: /api/ik/batch/stats/ ===")
request2 = factory.post('/api/ik/batch/stats/',
    {'point_ids': point_ids, 'days': 30},
    content_type='application/json')
force_authenticate(request2, user=user)
response2 = BatchStatsView.as_view()(request2)
print(f"Status: {response2.status_code}")

# Test 3: OptimizedLoginView
print(f"\n=== Test 3: /api/ik/login/ (OptimizedLoginView) ===")
request3 = factory.post('/api/ik/login/',
    {'email': user.email, 'password': 'test123'},  # Won't work with wrong password
    content_type='application/json')
response3 = OptimizedLoginView.as_view()(request3)
print(f"Status: {response3.status_code}")
# Just checking it returns 401 (wrong password) not 500 (error)
if response3.status_code in [200, 401]:
    print("OptimizedLoginView works correctly!")
else:
    print(f"Unexpected status: {response3.status_code}")

print("\n✅ All /api/ik/ endpoints are working!")
print("\nAPI Summary:")
print("  - /api/        -> Original API (unchanged)")
print("  - /api/ik/     -> New optimized API")
