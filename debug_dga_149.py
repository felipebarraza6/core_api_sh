
import os
import django
import sys
import logging

sys.path.append('/root/core_api_sh')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

# Configure logging to stdout
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

from api.core.models import DgaDataConfigCatchment, InteractionDetail, CatchmentPoint
from api.cronjobs.dga.cron_dga import _prepare_response_data
from api.cronjobs.dga.send_data_dga import send

POINT_ID = 149

def debug_send():
    print(f"Checking pending records for point {POINT_ID}...")
    pending = InteractionDetail.objects.filter(
        catchment_point_id=POINT_ID, 
        send_dga=True
    ).order_by('created').first()

    if not pending:
        print("No pending records found.")
        return

    print(f"Found pending record: {pending.id} from {pending.date_time_medition}")

    dga_config = DgaDataConfigCatchment.objects.filter(point_catchment_id=POINT_ID).first()
    if not dga_config:
        print("No DGA Config found!")
        return

    print("Preparing data...")
    response_data = _prepare_response_data(pending, dga_config)
    
    if not response_data:
        print("Failed to prepare data.")
        return

    print("Data prepared:", response_data)
    
    print("Attempting to send...")
    result = send(response_data)
    print(f"Send result: {result}")

    # Reload record to see changes
    pending.refresh_from_db()
    print(f"Record state after send:")
    print(f"  Send DGA: {pending.send_dga}")
    print(f"  Return DGA: {pending.return_dga}")
    print(f"  Voucher: {pending.n_voucher}")
    print(f"  Is Error: {pending.is_error}")

def check_queue_size():
    count = InteractionDetail.objects.filter(send_dga=True).exclude(catchment_point=1).count()
    print(f"Total pending DGA records in system: {count}")

if __name__ == "__main__":
    check_queue_size()
    debug_send()
