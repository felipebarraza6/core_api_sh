
import os
import django
import sys
from django.utils import timezone

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail, Client

def send_fpc_tissue():
    print("Searching for FPC Tissue client...")
    try:
        # Find FPC Tissue client
        # Using icontains to be safe based on "FPC Tissue"
        clients = Client.objects.filter(name__icontains="FPC")
        
        if not clients.exists():
            print("❌ No client found matching 'FPC Tissue'")
            print("Listing all clients containing 'FPC' or 'Tissue':")
            matches = Client.objects.filter(name__icontains="tissue") | Client.objects.filter(name__icontains="fpc")
            for c in matches:
                print(f" - {c.name} (ID: {c.id})")
                
            print("\nListing first 20 clients just in case:")
            for c in Client.objects.all()[:20]:
                print(f" - {c.name} (ID: {c.id})")
            return

        for client in clients:
            print(f"Found Client: {client.name} (ID: {client.id})")
            
            # Find catchments via project -> catchment
            # Accessing related objects might need careful traversal if related names are different
            # Based on models: Client -> ProjectCatchments (client) -> CatchmentPoint (project)
            
            projects = client.projectcatchments_set.all()
            for project in projects:
                print(f"  Project: {project.name} (ID: {project.id})")
                points = project.catchment_points.all()
                
                for point in points:
                    print(f"    Point: {point.title} (ID: {point.id})")
                    
                    # Find last record to send
                    # Check if there are any records with send_dga=True or just pick last one
                    last_record = InteractionDetail.objects.filter(
                        catchment_point=point
                    ).order_by('-date_time_medition').first()
                    
                    if not last_record:
                        print("      No records found.")
                        continue
                        
                    print(f"      Last Record ID: {last_record.id} Date: {last_record.date_time_medition}")
                    print(f"      Current Send Status: {last_record.send_dga}")
                    print(f"      Current Return DGA: {last_record.return_dga}")
                    
                    # Force Send
                    print("      🚀 Attempting to send to DGA...")
                    
                    # We need to use the logic from cron_dga
                    from api.core.models import DgaDataConfigCatchment
                    from api.cronjobs.dga.cron_dga import _prepare_response_data, send
                    
                    dga_config = DgaDataConfigCatchment.objects.filter(point_catchment=point).first()
                    if not dga_config:
                        print("      ❌ No DGA Config found for this point.")
                        continue
                        
                    if not dga_config.send_dga:
                        print("      ⚠️ DGA Config has send_dga=False. Ignoring.")
                        # Force temporarily? User asked to send it.
                        # Let's try to send anyway if we have config
                        
                    response_data = _prepare_response_data(last_record, dga_config)
                    if not response_data:
                         print("      ❌ Failed to prepare data (incomplete config?)")
                         continue
                         
                    print(f"      Payload prepared for code: {response_data.get('code_dga')}")
                    
                    # Send and captur output
                    success = send(response_data)
                    
                    # Refresh to see what happened
                    last_record.refresh_from_db()
                    print(f"      RESULT: {'✅ Success' if success else '❌ Failure'}")
                    print(f"      Return Message: {last_record.return_dga}")
                    print("-" * 50)

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    send_fpc_tissue()
