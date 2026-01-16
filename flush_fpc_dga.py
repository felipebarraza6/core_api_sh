
import os
import django
import sys
import time

sys.path.append('/root/core_api_sh')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail, Client, DgaDataConfigCatchment
from api.cronjobs.dga.cron_dga import _prepare_response_data
from api.cronjobs.dga.send_data_dga import send

def flush_fpc():
    print("Flushing DGA queue for FPC clients...")
    
    # Get FPC Client
    clients = Client.objects.filter(name__icontains="Tissue") | Client.objects.filter(name__icontains="FPC")
    client_ids = [c.id for c in clients]
    print(f"Targeting Clients: {client_ids}")

    # Get pending records
    pending = InteractionDetail.objects.filter(
        catchment_point__project__client__id__in=client_ids,
        send_dga=True
    ).order_by('created')
    
    total = pending.count()
    print(f"Found {total} pending records for FPC.")
    
    # Store IDs to avoid re-querying if status doesn't change
    pending_ids = list(pending.values_list('id', flat=True))
    
    count = 0
    for pid in pending_ids:
        count += 1
        print(f"Processing {count}/{total} - ID: {pid}")
        
        try:
            register = InteractionDetail.objects.get(id=pid)
            if not register.send_dga:
                print("  Skipping, already processed.")
                continue

            dga_config = DgaDataConfigCatchment.objects.filter(point_catchment=register.catchment_point).first()
            if not dga_config:
                print("  No DGA Config, skipping.")
                continue

            response_data = _prepare_response_data(register, dga_config)
            if response_data:
                # Call send
                # result is True (success) or False (fail)
                # But we care about DB update.
                result = send(response_data)
                
                # Check status
                register.refresh_from_db()
                if not register.send_dga:
                     print(f"  Result: REMOVED from queue (Return: {register.return_dga})")
                else:
                     print(f"  Result: RETRIED (kept in queue) - {register.return_dga}")
            else:
                print("  Failed to prepare data.")

        except Exception as e:
            print(f"  Error processing {pid}: {e}")

if __name__ == "__main__":
    flush_fpc()
