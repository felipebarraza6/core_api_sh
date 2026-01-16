import os
import django
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from django.contrib.admin.models import LogEntry, DELETION
from django.contrib.contenttypes.models import ContentType
from api.core.models import CatchmentPoint

def search_logs():
    print("SEARCHING DJANGO ADMIN LOGS...")
    
    # 1. Search by text in object_repr
    print("\n--- Searching 'Huerto' or 'Higuera' in object_repr ---")
    logs = LogEntry.objects.filter(object_repr__icontains='Higuera') | \
           LogEntry.objects.filter(object_repr__icontains='Huerto')
    
    found = False
    for log in logs:
        found = True
        print(f"[{log.action_time}] User: {log.user} | Action: {log.action_flag} | ID: {log.object_id} | Repr: {log.object_repr}")
        
    if not found:
        print("No matches found for names.")

    # 2. Search for recent deletions of CatchmentPoints
    print("\n--- Searching Deletions of CatchmentPoints (Last 50) ---")
    try:
        ct = ContentType.objects.get_for_model(CatchmentPoint)
        # Action 3 is DELETION
        del_logs = LogEntry.objects.filter(content_type=ct, action_flag=3).order_by('-action_time')[:50]
        
        if not del_logs:
            print("No point deletions found in logs.")
        
        for log in del_logs:
            print(f"[{log.action_time}] DELETED ID: {log.object_id} | Name was: {log.object_repr} | User: {log.user}")
            
    except Exception as e:
        print(f"Error checking point deletions: {e}")

if __name__ == '__main__':
    search_logs()
