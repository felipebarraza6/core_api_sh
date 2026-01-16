
import os
import django
import sys
from io import BytesIO

# Setup Django configuration
sys.path.append('/root/core_api_sh')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
django.setup()

from api.core.models import CatchmentPoint
from api.core.reports.pdf_generator import generate_telemetry_analysis_pdf
from api.core.validators.telemetry_validator import analyze_data_coherence

def verify_osorno_fix():
    print("Verifying PDF Generation Fix for Osorno...")
    
    # Try to find 'Ejercito D9' or similar
    points = CatchmentPoint.objects.filter(title__icontains="Ejercito D9")
    if not points.exists():
        print("Warning: 'Ejercito D9' not found, searching for 'Ejercito'...")
        points = CatchmentPoint.objects.filter(title__icontains="Ejercito")
        
    if not points.exists():
        print("Warning: No 'Ejercito' points found, using first available point.")
        point = CatchmentPoint.objects.first()
    else:
        point = points.first()
        
    if not point:
        print("Error: No catchment points found in database.")
        return
    
    print(f"Testing with point: {point.title} (ID: {point.id})")
    
    # 1. Verify validator output
    print("\n1. Verifying analyze_data_coherence output...")
    try:
        analisis = analyze_data_coherence(point.id, days_back=30)
        
        keys_to_check = ['incidencias_criticas', 'incidencias_advertencia', 'incidencias_info']
        all_present = True
        for key in keys_to_check:
            if key in analisis:
                print(f"SUCCESS: '{key}' is present. Value: {analisis[key]}")
            else:
                print(f"FAILURE: '{key}' is MISSING.")
                all_present = False
        
    except Exception as e:
        print(f"Error calling validator: {e}")
        import traceback
        traceback.print_exc()

    # 2. Verify PDF generation
    print("\n2. Verifying generate_telemetry_analysis_pdf...")
    try:
        pdf_buffer = generate_telemetry_analysis_pdf([point], user_info="Test Osorno Fix")
        
        if isinstance(pdf_buffer, BytesIO) and pdf_buffer.getbuffer().nbytes > 0:
            print(f"SUCCESS: PDF generated successfully. Size: {pdf_buffer.getbuffer().nbytes} bytes.")
        else:
            print("FAILURE: PDF generation returned empty buffer or invalid type.")
            
    except Exception as e:
        print(f"FAILURE: PDF generation raised an exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_osorno_fix()
