import os
import django
import redis
from django.conf import settings
from django_redis import get_redis_connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

def test_nx():
    print(f"Testing Redis NX support...")
    con = get_redis_connection("default")
    key = "test_nx_key_123"
    con.delete(key)
    
    # First set
    res1 = con.set(key, "1", nx=True, ex=60)
    print(f"First Set (nx=True): {res1} (Expected True/OK)")
    
    # Second set
    res2 = con.set(key, "2", nx=True, ex=60)
    print(f"Second Set (nx=True): {res2} (Expected None/False)")
    
    val = con.get(key)
    print(f"Value: {val} (Expected b'1')")
    
    con.delete(key)

if __name__ == "__main__":
    test_nx()
