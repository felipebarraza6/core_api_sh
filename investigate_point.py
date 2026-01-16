import os
import sys
import django

# Setup Django
sys.path.insert(0, '/root/core_api_sh')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint, DgaDataConfigCatchment, InteractionDetail
from api.cronjobs.dga.caudal_calculations import calculate_daily_average_flow

def investigate():
    point_title = "P1 - agricolanahuen@smarthydro.cl"
    point = CatchmentPoint.objects.filter(title__icontains="agricolanahuen").first()
    
    if not point:
        print(f"Punto no encontrado: {point_title}")
        return

    print(f"Investigando Punto: {point.title} (ID: {point.id})")
    
    dga_config = DgaDataConfigCatchment.objects.filter(point_catchment=point).first()
    if not dga_config:
        print("No tiene configuración DGA")
    else:
        print(f"Estándar DGA: {dga_config.standard}")
        print(f"Habilitado enviar DGA: {dga_config.send_dga}")

    # Ver últimos registros
    print("\nÚltimos 5 registros:")
    records = InteractionDetail.objects.filter(catchment_point=point).order_by('-date_time_medition')[:5]
    for r in records:
        print(f"ID: {r.id} | Fecha: {r.date_time_medition} | Total: {r.total} | Diff: {r.total_diff} | Flow: {r.flow}")

    if dga_config and dga_config.standard == "MEDIO":
        print("\nProbando calculate_daily_average_flow para el registro más reciente...")
        last_record = records[0]
        flow = calculate_daily_average_flow(last_record, dga_config)
        print(f"Resultado del cálculo: {flow}")

if __name__ == "__main__":
    investigate()
