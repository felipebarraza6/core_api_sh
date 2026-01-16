#!/usr/bin/env python
"""Test script for batch endpoints."""
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
from api.core.models import User, CatchmentPoint

# Get a test user
user = User.objects.filter(is_staff=True).first()
if not user:
    print('ERROR: No staff user found')
    sys.exit(1)

print(f"Testing with user: {user.email}")

# Get some real point IDs
point_ids = list(CatchmentPoint.objects.values_list('id', flat=True)[:5])
print(f"Using point_ids: {point_ids}")

# Test BatchTelemetryView
factory = RequestFactory()
request = factory.post(
    '/api/batch/telemetry/', 
    {'point_ids': point_ids, 'hours': 24}, 
    content_type='application/json'
)
force_authenticate(request, user=user)

view = BatchTelemetryView.as_view()
response = view(request)

print(f"\n=== BatchTelemetryView ===")
print(f"Status: {response.status_code}")
print(f"Meta: {response.data.get('meta', {})}")
print(f"Data keys (first 3): {list(response.data.get('data', {}).keys())[:3]}")

if response.data.get('data'):
    first_key = list(response.data['data'].keys())[0]
    first_item = response.data['data'][first_key]
    print(f"Sample point {first_key}: {list(first_item.keys())}")

# Test BatchStatsView  
request2 = factory.post(
    '/api/batch/stats/',
    {'point_ids': point_ids, 'days': 30},
    content_type='application/json'
)
force_authenticate(request2, user=user)

view2 = BatchStatsView.as_view()
response2 = view2(request2)

print(f"\n=== BatchStatsView ===")
print(f"Status: {response2.status_code}")
print(f"Data keys: {list(response2.data.get('data', {}).keys())[:3]}")

print("\n✅ Batch endpoints working correctly!")
