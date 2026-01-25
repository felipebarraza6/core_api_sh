
import sys
sys.path.append('/app')
import os
import django
from django.test import RequestFactory
from django.contrib.auth import get_user_model

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.dynamic_registry.views import DataProxyViewSet
from api.telemetry.models import CatchmentPoint

def verify_dynamic_proxy():
    print("--- Verifying Dynamic Data Proxy ---")

    # 1. Setup User & Request
    User = get_user_model()
    # Create superuser to bypass permissions (or standard user with perms)
    username = 'proxy_tester'
    email = 'test@example.com'
    password = 'pass'
    
    try:
        user = User.objects.get(email=email)
        print(f"User with email {email} already exists. Using it.")
    except User.DoesNotExist:
        try:
            user = User.objects.create_superuser(username, email, password)
            print("Created new superuser.")
        except Exception as e:
            # Fallback if username exists but email is different or other error
            try:
                user = User.objects.get(username=username)
                print(f"User {username} exists. Using it.")
            except:
                raise e

    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType
    
    # Grant permission
    try:
        content_type = ContentType.objects.get(app_label='dynamic_registry', model='systemmodule')
        permission = Permission.objects.get(content_type=content_type, codename='view_systemmodule')
        user.user_permissions.add(permission)
        print("Granted view_systemmodule permission.")
    except Exception as e:
        print(f"Warning: Could not grant permission: {e}")

    from rest_framework.test import APIClient
    
    client = APIClient()
    client.force_authenticate(user=user)
    
    # 2. Test List: /api/registry/proxy/dynamic_registry/systemmodule/
    print("\n[TEST 1] List SystemModules (via Proxy)")
    response = client.get('/api/registry/proxy/dynamic_registry/systemmodule/')
    
    if response.status_code == 200:
        count = response.data.get('count', 0)
        print(f"✅ Success (200 OK). Found {count} items.")
    else:
        print(f"❌ Failed. Status: {response.status_code}")
        print(response.data)

    # 3. Test Invalid Model
    print("\n[TEST 2] Access Invalid Model")
    response = client.get('/api/registry/proxy/bad/model/')
    
    if response.status_code == 404:
         print("✅ Success (404 Not Found as expected).")
    else:
         print(f"❌ Unexpected status: {response.status_code}")

if __name__ == "__main__":
    verify_dynamic_proxy()
