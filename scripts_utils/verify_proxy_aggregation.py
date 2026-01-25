
import sys
sys.path.append('/app')
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIClient
from api.dynamic_registry.models import SystemModule

def verify_aggregation():
    print("--- Verifying Data Proxy Aggregation ---")
    
    User = get_user_model()
    # 1. Setup User
    try:
        user = User.objects.get(username='agg_tester')
    except User.DoesNotExist:
        user = User.objects.create_user('agg_tester', 'agg@test.com', 'pass')

    # Grant permissions
    ct = ContentType.objects.get_for_model(SystemModule)
    perm = Permission.objects.get(content_type=ct, codename='view_systemmodule')
    user.user_permissions.add(perm)

    client = APIClient()
    client.force_authenticate(user=user)
    
    # 2. Add Dummy Data (to have something to sum/average)
    # SystemModule doesn't have numeric fields easy to sum, but we can COUNT.
    count_initial = SystemModule.objects.count()
    
    # 3. Test COUNT
    print(f"\n[TEST 1] Count SystemModules (Expected: {count_initial})")
    url = '/api/registry/proxy/dynamic_registry/systemmodule/?aggregate=count'
    resp = client.get(url)
    
    if resp.status_code == 200:
        val = resp.data.get('value')
        print(f"✅ Success. Count: {val}")
        if val == count_initial:
            print("✅ Count matches DB.")
        else:
            print(f"❌ Count Mismatch! DB: {count_initial}, API: {val}")
    else:
        print(f"❌ Failed: {resp.status_code} {resp.data}")

    # 4. Test INVALID Aggregation
    print("\n[TEST 2] Invalid Aggregation Function")
    url = '/api/registry/proxy/dynamic_registry/systemmodule/?aggregate=magic'
    resp = client.get(url)
    if resp.status_code == 400:
        print("✅ Correctly rejected invalid aggregation (400).")
    else:
        print(f"❌ Unexpected status: {resp.status_code}")

    # 5. Test Missing Field
    print("\n[TEST 3] Missing Field for Sum")
    url = '/api/registry/proxy/dynamic_registry/systemmodule/?aggregate=sum'
    resp = client.get(url)
    if resp.status_code == 400:
        print("✅ Correctly rejected missing field (400).")
    else:
        print(f"❌ Unexpected status: {resp.status_code}")

if __name__ == "__main__":
    verify_aggregation()
