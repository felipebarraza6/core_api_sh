import os
import django
from django.conf import settings
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import User, InteractionDetail
from api.core.serializers.catchment_points import CatchmentPointIkoluSerializer
from api.core.serializers.users import UserProfile

def inspect_comasa():
    try:
        user = User.objects.get(username='comasa')
        print(f"User: {user.username} (ID: {user.id})")
    except User.DoesNotExist:
        print("User 'comasa' not found")
        return

    # Mock request context
    class MockRequest:
        def __init__(self, user):
            self.user = user
            self.query_params = {}
            self.method = 'GET'

    request = MockRequest(user)
    context = {'user': user, 'request': request}
    
    # Run UserProfile serializer logic to get catchment points
    # We can instantiate UserProfile to see what it does
    user_profile = UserProfile(user, context=context)
    data = user_profile.data
    
    catchment_points = data.get('catchment_points', [])
    if not catchment_points:
        print("No catchment points found for user.")
        return

    print(f"Found {len(catchment_points)} catchment points.")
    
    for cp in catchment_points:
        print(f"\n--- Point: {cp.get('title')} ---")
        modules = cp.get('modules', {})
        today_records = modules.get('today', [])
        
        if not today_records:
            print("  No records for today.")
            continue
            
        print(f"  Today Records ({len(today_records)}):")
        # Print first 3
        for i, rec in enumerate(today_records[:3]):
            print(f"    [{i}] Time: {rec.get('date_time_medition')} | Flow: {rec.get('flow')}")
            
            # Try to match with DB to see raw value
            # We have to reverse-engineer the string to find the DB record? 
            # Or just fetch latest from DB directly to compare
            
    # Also fetch raw DB records for the first point to compare
    if catchment_points:
        import datetime
        cp_id = catchment_points[0]['id']
        print(f"\n--- Raw DB Check for Point ID {cp_id} ---")
        today = timezone.localtime(timezone.now()).date()
        today_recs = InteractionDetail.objects.filter(
            catchment_point_id=cp_id,
            date_time_medition__date=today
        ).order_by('-date_time_medition')[:3]
        
        for r in today_recs:
             print(f"  DB Raw: {r.date_time_medition} | TZ: {r.date_time_medition.tzinfo}")
             print(f"  Local:  {timezone.localtime(r.date_time_medition)}")

if __name__ == "__main__":
    inspect_comasa()
