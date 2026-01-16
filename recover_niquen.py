import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

import requests
import json
import datetime
from django.utils import timezone
from api.core.models import InteractionDetail

# --- CONFIG ---
DEVICE_TOKEN = "286c91f0-9d4a-11f0-8fb8-2ba44d87275b"
KEY = "ai1ActualValue"
CP_ID = 189
# Need to confirm D3 for Niquen. San Carlos was 13.00.
# Assuming I should just calc Nivel (val/100) and ensure timestamps are perfect.
# Water table calculation depends on D3. Let's fetch it from DB or verify.
# If unavailable, safer to use a placeholder or previous logic?
# Actually, let's fetch D3 from DB inside the script.
CALC_DIVISOR = 100.0

def get_d3_from_db():
    from api.core.models import CatchmentPoint
    try:
        cp = CatchmentPoint.objects.get(id=CP_ID)
        profile = cp.data_config_profiles.filter(is_telemetry=True).first()
        if profile and hasattr(profile, 'd3'):
            return float(profile.d3)
        # Fallback if d3 is in a dict or different field
        if profile:
             # Try accessing as dict if it's not a direct field
             # data = profile.__dict__ ...
             pass
    except Exception as e:
        print(f"Error fetching D3: {e}")
    return 13.00 # Default fallback? Or maybe 0?

# --- AUTH ---
def get_auth_token():
    url = "https://api.twindimension.com/tdata/v1/login"
    payload = json.dumps({
        "username": "sadmin.smarthydro@twindimension.io",
        "password": "Smart.1238"
    })
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.post(url, headers=headers, data=payload, timeout=10)
        return response.json()["token"]
    except Exception as e:
        print(f"Auth Error: {e}")
        return None

# --- MAIN ---
def main():
    d3_val = get_d3_from_db()
    print(f"Using D3: {d3_val}")

    token_auth = get_auth_token()
    if not token_auth:
        return

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    ts_from = int(today_start.timestamp() * 1000)
    ts_to = int(now.timestamp() * 1000)

    url = f"https://api.twindimension.com/tdata/v1/telemetry/DEVICE/{DEVICE_TOKEN}/values/timeseries?keys={KEY}&startTs={ts_from}&endTs={ts_to}&limit=5000"
    headers = {'Authorization': f"Bearer {token_auth}"}

    print(f"Fetching data from {today_start} to {now}...")
    resp = requests.get(url, headers=headers, timeout=20)
    data = resp.json()

    if KEY not in data:
        print("No data found.")
        return

    items = data[KEY]
    items.sort(key=lambda x: x['ts'])
    
    print(f"Found {len(items)} raw data points.")

    current_slot = today_start
    slots_processed = 0
    
    while current_slot < now:
        target_ts = current_slot.timestamp() * 1000
        closest_item = None
        min_diff = float('inf')
        
        for item in items:
            diff = abs(item['ts'] - target_ts)
            if diff < min_diff:
                min_diff = diff
                closest_item = item
        
        if closest_item and min_diff < 300000:
            raw_val = float(closest_item['value'])
            nivel = raw_val / CALC_DIVISOR
            freatico = d3_val - nivel
            
            InteractionDetail.objects.update_or_create(
                catchment_point_id=CP_ID,
                date_time_medition=current_slot,
                defaults={
                    'nivel': "{:.2f}".format(nivel),
                    'total': None,
                    'flow': "0.00",
                    'water_table': "{:.2f}".format(freatico),
                    'date_time_last_logger': datetime.datetime.fromtimestamp(closest_item['ts']/1000, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                }
            )
            slots_processed += 1
        else:
            print(f"No data for slot {current_slot} (Diff: {min_diff})")
        
        current_slot += datetime.timedelta(minutes=10)

    print(f"Done. Processed {slots_processed} slots.")

if __name__ == "__main__":
    main()
