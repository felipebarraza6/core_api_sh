
import sys
sys.path.append('/app')
import os
import json
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

def check_menu():
    print("--- Checking API Menu Response ---")
    User = get_user_model()
    # Use existing user (from previous tests)
    try:
        user = User.objects.get(username='audit_tester') # Created in crud test
    except:
        user = User.objects.create_superuser('admin_check', 'admin@check.com', 'pass')

    # Ensure user has perm to see the module
    from django.contrib.auth.models import Permission
    perm = Permission.objects.get(codename='view_auditlog')
    user.user_permissions.add(perm)

    client = APIClient()
    client.force_authenticate(user=user)
    
    resp = client.get('/api/registry/modules/menu/')
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ Menu Items: {len(data)}")
        
        found = False
        for item in data:
            print(f" - {item['name']} ({item['slug']})")
            if item['slug'] == 'security-audit':
                found = True
        
        if found:
            print("✅ SUCCESS: 'security-audit' module is served in the menu.")
        else:
            print("❌ FAILURE: 'security-audit' missing from menu.")
    else:
        print(f"❌ Failed to get menu: {resp.status_code}")

if __name__ == "__main__":
    check_menu()
