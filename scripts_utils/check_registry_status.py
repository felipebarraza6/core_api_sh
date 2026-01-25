
import sys
sys.path.append('/app')
import os
import django
import json

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.dynamic_registry.models import SystemModule, ModuleView

def verify_dynamic_registry():
    print("--- Verifying Dynamic Registry ---")
    
    # 1. Check Modules
    modules = SystemModule.objects.all()
    print(f"📦 Modules found: {modules.count()}")
    for m in modules:
        print(f"   - {m.name} ({m.slug})")
        
    # 2. Check Views
    views = ModuleView.objects.all()
    print(f"👁️  Views found: {views.count()}")
    for v in views:
        print(f"   - {v.module.slug} -> {v.key} ({v.view_type})")
        if v.key == 'points-list':
             print(f"     Layout Config Keys: {list(v.layout_config.keys())}")

    if modules.count() > 0 and views.count() > 0:
        print("✅ Dynamic Registry Data Verification: PASSED")
    else:
        print("❌ Dynamic Registry Data Verification: FAILED (No data found)")

if __name__ == "__main__":
    verify_dynamic_registry()
