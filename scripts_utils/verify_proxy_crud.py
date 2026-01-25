
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
from api.dynamic_registry.models import SystemModule, AuditLog

def verify_proxy_crud_audit():
    print("--- Verifying Proxy CRUD & Audit ---")
    
    User = get_user_model()
    # 1. Setup User
    try:
        user = User.objects.get(username='audit_tester')
    except User.DoesNotExist:
        user = User.objects.create_user('audit_tester', 'audit@test.com', 'pass')

    # Grant permissions: view, add, change, delete SystemModule
    ct = ContentType.objects.get_for_model(SystemModule)
    perms = Permission.objects.filter(content_type=ct, codename__in=['view_systemmodule', 'add_systemmodule', 'change_systemmodule', 'delete_systemmodule'])
    user.user_permissions.set(perms)
    print(f"Granted {perms.count()} permissions to audit_tester.")

    client = APIClient()
    client.force_authenticate(user=user)

    import uuid
    random_slug = f"audit-test-{uuid.uuid4().hex[:6]}"
    
    # 2. CREATE SystemModule via Proxy
    print("\n[TEST 1] Create SystemModule (POST)")
    payload = {
        "name": "Audit Test Module",
        "slug": random_slug,
        "icon": "shield",
        "is_active": True
    }
    resp = client.post('/api/registry/proxy/dynamic_registry/systemmodule/', payload, format='json')
    if resp.status_code == 201:
        new_id = resp.data['id']
        print(f"✅ Created (201). ID: {new_id}")
    else:
        print(f"❌ Failed Create: {resp.status_code} {resp.data}")
        return

    # 3. VERIFY AUDIT LOG (CREATE)
    log = AuditLog.objects.filter(resource_id=str(new_id), action='CREATE').last()
    if log and log.user == user:
        print(f"✅ Audit Log found: {log}")
    else:
        print(f"❌ Audit Log MISSING for Create!")

    # 4. UPDATE SystemModule via Proxy
    print("\n[TEST 2] Update SystemModule (PATCH)")
    patch_data = {"name": "Audit Test UPDATED"}
    resp = client.patch(f'/api/registry/proxy/dynamic_registry/systemmodule/{new_id}/', patch_data, format='json')
    if resp.status_code == 200:
        print(f"✅ Updated (200). Name: {resp.data['name']}")
    else:
        print(f"❌ Failed Update: {resp.status_code} {resp.data}")

    # 5. VERIFY AUDIT LOG (UPDATE)
    log = AuditLog.objects.filter(resource_id=str(new_id), action='UPDATE').last()
    if log and log.payload.get('name') == "Audit Test UPDATED":
        print(f"✅ Audit Log found for UPDATE: {log}")
    else:
        print(f"❌ Audit Log MISSING or Incorrect for Update!")

    # 6. DELETE SystemModule via Proxy
    print("\n[TEST 3] Delete SystemModule (DELETE)")
    resp = client.delete(f'/api/registry/proxy/dynamic_registry/systemmodule/{new_id}/')
    if resp.status_code == 204:
        print(f"✅ Deleted (204).")
    else:
        print(f"❌ Failed Delete: {resp.status_code}")

    # 7. VERIFY AUDIT LOG (DELETE)
    log = AuditLog.objects.filter(resource_id=str(new_id), action='DELETE').last()
    if log:
        print(f"✅ Audit Log found for DELETE: {log}")
    else:
        print(f"❌ Audit Log MISSING for Delete!")

if __name__ == "__main__":
    verify_proxy_crud_audit()
