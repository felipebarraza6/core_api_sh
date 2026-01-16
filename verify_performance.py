
import os
import django
import time
import cProfile
import pstats

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
django.setup()

from api.core.models import User
from api.core.serializers.users import UserProfile

def benchmark_user(username):
    print(f"Searching for user: {username}")
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        print(f"User {username} not found. Listing first 5 users:")
        for u in User.objects.all()[:5]:
            print(f"- {u.username}")
        return

    print(f"Found user: {user.username} (ID: {user.id})")
    
    # Mock context with user
    context = {'user': user}
    
    print("Starting serialization...")
    start_time = time.time()
    
    # Execute serializer
    serializer = UserProfile(user, context=context)
    data = serializer.data
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"Serialization finished in: {duration:.4f} seconds")
    
    # Analyze result size
    points_count = len(data.get('catchment_points', []))
    print(f"Serialized {points_count} catchment points.")
    
    if points_count > 0:
        first_point = data['catchment_points'][0]
        # Inspect structure of first point
        print("Structure check (First Point keys):")
        print(first_point.keys())
        if 'modules' in first_point:
            print("Modules keys:", first_point['modules'].keys())
            if 'today' in first_point['modules']:
                 print(f"Today records count: {len(first_point['modules']['today'])}")

if __name__ == "__main__":
    benchmark_user('productosfernandez')
