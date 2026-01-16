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
DEVICE_TOKEN = "8175a570-9d54-11f0-8fb8-2ba44d87275b"
KEY = "ai1ActualValue"
CP_ID = 188
D3 = 13.00
CALC_DIVISOR = 100.0

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
    token_auth = get_auth_token()
    if not token_auth:
        return

    # Range: Today 00:00 to Now
    now = timezone.now()
    # Ensure usage of correct timezone if possible, but for simplicity
    # we work with UTC or local? The container uses UTC usually.
    # The timestamps from API are UTC (ts/1000).
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
    # items are sorted? Usually descending. Let's sort by TS for binary search or easy iteration.
    items.sort(key=lambda x: x['ts'])
    
    print(f"Found {len(items)} raw data points.")

    # Generate Target Slots (10 min)
    current_slot = today_start
    slots_processed = 0
    
    while current_slot < now:
        # Find closest item
        target_ts = current_slot.timestamp() * 1000
        
        # Simple linear search for closest (inefficient but fine for 2000 items)
        closest_item = None
        min_diff = float('inf')
        
        for item in items:
            diff = abs(item['ts'] - target_ts)
            if diff < min_diff:
                min_diff = diff
                closest_item = item
        
        # Check if reasonably close (e.g. within 5 mins)
        # 5 mins = 300,000 ms
        if closest_item and min_diff < 300000:
            # Prepare Values
            raw_val = float(closest_item['value'])
            nivel = raw_val / CALC_DIVISOR
            freatico = D3 - nivel
            
            # Create/Update Record
            # We explicitly set the time to the SLOT time (perfect 10 min)
            InteractionDetail.objects.update_or_create(
                catchment_point_id=CP_ID,
                date_time_medition=current_slot,
                defaults={
                    'nivel': "{:.2f}".format(nivel),
                    'total': None, # Assuming no total
                    'flow': "0.00",
                    'water_table': "{:.2f}".format(freatico),
                    # We can store date_time_last_logger as the ACTUAL time
                    'date_time_last_logger': datetime.datetime.fromtimestamp(closest_item['ts']/1000, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                }
            )
            # print(f"Recovered {current_slot}: Nivel {nivel}")
            slots_processed += 1
        else:
            print(f"No data for slot {current_slot} (Diff: {min_diff})")
        
        current_slot += datetime.timedelta(minutes=10)

    print(f"Done. Processed {slots_processed} slots.")

if __name__ == "__main__":
    main()
