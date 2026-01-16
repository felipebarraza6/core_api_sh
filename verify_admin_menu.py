
import os
import django
from django.conf import settings
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from django.contrib import admin

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

User = get_user_model()
# Create a superuser or use existing
# For this test we just need a user object that is a superuser
try:
    user = User.objects.filter(is_superuser=True).first()
except:
    user = None

if not user:
    print("No superuser found. Creating ephemeral one for test.")
    user = User(username='test_admin', is_superuser=True, is_staff=True)

factory = RequestFactory()
request = factory.get('/admin/')
request.user = user

app_list = admin.site.get_app_list(request)

found = False
for app in app_list:
    print(f"App: {app['name']} ({app['app_label']})")
    for model in app['models']:
        print(f"  - Model: {model['name']} (object_name: {model['object_name']}) url: {model.get('admin_url')}")
        if model['object_name'] == 'Variable':
            found = True

if found:
    print("\nSUCCESS: Variable model FOUND in admin menu.")
else:
    print("\nFAILURE: Variable model NOT FOUND in admin menu.")
