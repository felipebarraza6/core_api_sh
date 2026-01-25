
import sys
sys.path.append('/app')
import os
import django
from django.test import RequestFactory, Client

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.presentation.views import PresentationView

def verify_presentation_page():
    print("--- Verifying Presentation Landing Page ---")
    factory = RequestFactory()
    request = factory.get('/presentation/')
    
    view = PresentationView.as_view()
    response = view(request)
    response.render()
    
    content = response.content.decode('utf-8')
    
    # Check for key elements from AGENTS.md
    checks = [
        "Sistema de Agentes & Responsabilidades",
        "Unified API",
        "Gateway (V0)",
        "Dynamic Registry",
        "api/registry/modules",
        "Mapa de Arquitectura API",
        '<div class="mermaid">'
    ]
    
    all_passed = True
    for check in checks:
        if check in content:
            print(f"✅ Found: '{check}'")
        else:
            print(f"❌ Missing: '{check}'")
            all_passed = False
            
    if all_passed:
        print("✅ Presentation Page Verification: PASSED")
    else:
        print("❌ Presentation Page Verification: FAILED")

if __name__ == "__main__":
    verify_presentation_page()
