
import os
import django
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
django.setup()

from api.core.models import User, CatchmentPoint
from api.core.serializers.users import UserProfile

try:
    # Try to find a user linked to point 179
    point = CatchmentPoint.objects.filter(id=179).first()
    if point:
        print(f"Found point: {point.title}")
        user = point.owner_user
        if not user and point.users_viewers.exists():
            user = point.users_viewers.first()
        
        if user:
            print(f"Testing serialization for user: {user.username}")
            serializer = UserProfile(user, context={'user': user})
            data = serializer.data
            print("Serialization successful!")
            # print(data) 
        else:
            print("No user found for point 179")
    else:
        print("Point 179 not found")

except Exception as e:
    import traceback
    traceback.print_exc()
