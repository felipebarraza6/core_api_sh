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
DEVICE_TOKEN = "e9b13050-a2d6-11f0-8fb8-2ba44d87275b"
KEY = "ai1ActualValue"
CP_ID = 187
D3 = 8.00 # Matching DB value
CALC_DIVISOR = 100.0 # Corrected divisor

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
    print(f"Using D3: {D3} | Divisor: {CALC_DIVISOR}")

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
    if items:
        first_ts = datetime.datetime.fromtimestamp(items[0]['ts']/1000, tz=datetime.timezone.utc)
        last_ts = datetime.datetime.fromtimestamp(items[-1]['ts']/1000, tz=datetime.timezone.utc)
        print(f"Data Range: {first_ts} to {last_ts}")

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
            freatico = D3 - nivel
            
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
