import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import Variable

def reset_additions():
    print("--- Resetting 'addition' values to 0 ---")
    vars_to_reset = Variable.objects.filter(addition__isnull=False).exclude(addition=0)
    
    count = vars_to_reset.count()
    print(f"Found {count} variables to reset.")
    
    if count == 0:
        print("No variables to reset.")
        return

    # Bulk update for efficiency
    updated = vars_to_reset.update(addition=0)
    print(f"Successfully reset {updated} variables to 0.")

if __name__ == "__main__":
    reset_additions()
