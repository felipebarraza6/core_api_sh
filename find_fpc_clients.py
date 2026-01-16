
import os
import django
import sys

sys.path.append('/root/core_api_sh')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import Client, CatchmentPoint, DgaDataConfigCatchment

def find_clients():
    print("Searching for Clients 'FPC' or 'Tissue'...")
    clients = Client.objects.filter(name__icontains="Tissue") | Client.objects.filter(name__icontains="FPC")
    
    for client in clients:
        print(f"Client: {client.name} (ID: {client.id})")
        points = CatchmentPoint.objects.filter(project__client=client)
        for p in points:
            print(f"  Point: {p.title} (ID: {p.id})")
            config = DgaDataConfigCatchment.objects.filter(point_catchment=p).first()
            if config:
                print(f"    DGA Code: {config.code_dga}")
                print(f"    RUT: {config.rut_report_dga}")
                print(f"    Password: {'***' if config.password_dga_software else 'None'}")
            else:
                print("    No DGA Config")

if __name__ == "__main__":
    find_clients()
