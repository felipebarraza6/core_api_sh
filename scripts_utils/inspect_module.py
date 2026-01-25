
import sys
sys.path.append('/app')
import os
import json
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from api.dynamic_registry.models import SystemModule

def inspect_module(module_slug):
    print(f"--- Inspecting Module: {module_slug} ---")
    User = get_user_model()
    try:
        user = User.objects.get(username='audit_tester')
    except:
        user = User.objects.create_superuser('inspector', 'inspector@test.com', 'pass')

    # Ensure perm
    from django.contrib.auth.models import Permission
    try:
        perm = Permission.objects.get(codename='view_auditlog')
        user.user_permissions.add(perm)
    except:
        pass

    client = APIClient()
    client.force_authenticate(user=user)
    
    # 1. Get Module Detail (Views)
    # We need to find the ID or assume standard route behavior if using ViewSet
    # But RegistryViewSet lookup_field is slug.
    resp = client.get(f'/api/registry/modules/{module_slug}/')
    
    if resp.status_code == 200:
        data = resp.json()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"❌ Error {resp.status_code}: {resp.content}")

if __name__ == "__main__":
    inspect_module('security-audit')
