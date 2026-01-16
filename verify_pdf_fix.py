
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

def verify_fix():
    print("Verifying PDF Generation Fix...")
    
    # Try to find 'Ejercito P1' or any point
    points = CatchmentPoint.objects.filter(title__icontains="Ejercito P1")
    if not points.exists():
        print("Warning: 'Ejercito P1' not found, using first available point.")
        point = CatchmentPoint.objects.first()
        if not point:
            print("Error: No catchment points found in database.")
            return
    else:
        point = points.first()
    
    print(f"Testing with point: {point.title} (ID: {point.id})")
    
    # 1. Verify validator output directly
    print("\n1. Verifying analyze_data_coherence output...")
    try:
        analisis = analyze_data_coherence(point.id, days_back=30)
        
        # Check if fechas_pulsos_cero exists
        fpc_list = analisis.get('fechas_pulsos_cero', [])
        print(f"Found {len(fpc_list)} entries in fechas_pulsos_cero.")
        
        if fpc_list:
            first_entry = fpc_list[0]
            print(f"First entry keys: {list(first_entry.keys())}")
            if 'fecha_logger' in first_entry:
                print("SUCCESS: 'fecha_logger' key is present in validator output.")
                print(f"Value: {first_entry['fecha_logger']}")
            else:
                print("FAILURE: 'fecha_logger' key is MISSING in validator output.")
        else:
            print("No 'pulsos=0' records found for this point. Verification of that part skipped, but proceeding to PDF gen.")
            
    except Exception as e:
        print(f"Error calling validator: {e}")
        import traceback
        traceback.print_exc()

    # 2. Verify PDF generation
    print("\n2. Verifying generate_telemetry_analysis_pdf...")
    try:
        pdf_buffer = generate_telemetry_analysis_pdf([point], user_info="Test Use")
        
        if isinstance(pdf_buffer, BytesIO) and pdf_buffer.getbuffer().nbytes > 0:
            print(f"SUCCESS: PDF generated successfully. Size: {pdf_buffer.getbuffer().nbytes} bytes.")
        else:
            print("FAILURE: PDF generation returned empty buffer or invalid type.")
            
    except Exception as e:
        print(f"FAILURE: PDF generation raised an exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_fix()
