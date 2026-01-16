import requests
import json
import datetime

# Login
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

token_auth = get_auth_token()
if not token_auth:
    print("Failed to get auth token")
    exit(1)

# Fetch Data
device_token = "8175a570-9d54-11f0-8fb8-2ba44d87275b"
key = "ai1ActualValue"

# Try fetching with a generic large range if supported, or default
# TData API usually supports ?from= timestampMillis & to= timestampMillis
# Let's try fetching the last 24 hours.
now = datetime.datetime.now()
yesterday = now - datetime.timedelta(days=1)
ts_from = int(yesterday.timestamp() * 1000)
ts_to = int(now.timestamp() * 1000)

# Try startTs / endTs (ThingsBoard style)
url = f"https://api.twindimension.com/tdata/v1/telemetry/DEVICE/{device_token}/values/timeseries?keys={key}&startTs={ts_from}&endTs={ts_to}&limit=5000"
headers = {'Authorization': f"Bearer {token_auth}"}

print(f"Fetching from {ts_from} to {ts_to}")
try:
    response = requests.get(url, headers=headers, timeout=20)
    data = response.json()
    
    if key in data:
        items = data[key]
        print(f"Got {len(items)} items.")
        if items:
            first = items[0]
            last = items[-1]
            print(f"First: {datetime.datetime.fromtimestamp(first['ts']/1000)} Value: {first['value']}")
            print(f"Last: {datetime.datetime.fromtimestamp(last['ts']/1000)} Value: {last['value']}")
            
            # Print a sample of timestamps to see frequency
            for i in items[:10]:
                 print(f" - {datetime.datetime.fromtimestamp(i['ts']/1000)}")
    else:
        print("Key not in response or no data", data.keys())
        print(data)

except Exception as e:
    print(f"Fetch Error: {e}")
