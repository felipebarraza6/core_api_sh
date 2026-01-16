import os
import django
import redis
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

def test_redis():
    print(f"Testing Redis connection...")
    try:
        # METHOD 1: Direct Redis
        r = redis.Redis(host='redis', port=6379, db=1)
        r.ping()
        print("Direct Redis: SUCCESS")
    except Exception as e:
        print(f"Direct Redis: FAILED - {e}")

    try:
        # METHOD 2: Django Cache
        from django_redis import get_redis_connection
        con = get_redis_connection("default")
        con.set("test_key", "hello")
        val = con.get("test_key")
        print(f"Django Cache: SUCCESS (Val: {val})")
        
        # Check specific lock
        print(f"Checking keys: {con.keys('disconnection:188:*')}")
        
    except Exception as e:
        print(f"Django Cache: FAILED - {e}")

if __name__ == "__main__":
    test_redis()
