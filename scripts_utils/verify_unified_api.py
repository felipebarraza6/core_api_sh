
import sys
sys.path.append('/app')
import os
import django
# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from django.test import RequestFactory
from api.unified.views.catchment_points import CatchmentPointViewSet
from api.unified.views.devices import DeviceViewSet
from api.unified.views.dashboard import DashboardViewSet

from rest_framework.test import APIRequestFactory, force_authenticate

def verify_endpoints():
    print("--- Verifying Unified API Endpoints ---")
    factory = APIRequestFactory()
    
    # Mock user auth
    from api.core.models.users import User
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        print("⚠️  No superuser found for test, skipping auth check might fail")
        return

    # 1. Test Points List
    print("1. Testing /api/points/ ...")
    view_points = CatchmentPointViewSet.as_view({'get': 'list'})
    request = factory.get('/api/points/')
    force_authenticate(request, user=user)
    response = view_points(request)
    print(f"   Status Code: {response.status_code}")
    if response.status_code == 200:
        print("   ✅ /api/points/ OK")
    else:
        response.render()
        print(f"   ❌ /api/points/ FAILED: {response.content}")

    # 2. Test Devices List
    print("2. Testing /api/devices/ ...")
    view_devices = DeviceViewSet.as_view({'get': 'list'})
    request = factory.get('/api/devices/')
    force_authenticate(request, user=user)
    response = view_devices(request)
    print(f"   Status Code: {response.status_code}")
    if response.status_code == 200:
        print("   ✅ /api/devices/ OK")
    else:
        response.render()
        print(f"   ❌ /api/devices/ FAILED: {response.content}")

    # 3. Test Dashboard Summary
    print("3. Testing /api/dashboard/summary/ ...")
    view_dash = DashboardViewSet.as_view({'get': 'summary'})
    request = factory.get('/api/dashboard/summary/')
    force_authenticate(request, user=user)
    response = view_dash(request)
    print(f"   Status Code: {response.status_code}")
    if response.status_code == 200:
        print("   ✅ /api/dashboard/summary/ OK")
        response.render()
        # Truncate content for display
        print(f"   Data: {str(response.data)[:200]}...")
    else:
        response.render()
        print(f"   ❌ /api/dashboard/summary/ FAILED: {response.content}")

if __name__ == "__main__":
    verify_endpoints()
