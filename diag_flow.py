import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import InteractionDetail, CatchmentPoint
from api.core.utils.flow_display import get_interaction_flow_display_data
from datetime import datetime
import pytz

def test_point(cp_id):
    point = CatchmentPoint.objects.get(id=cp_id)
    records = InteractionDetail.objects.filter(catchment_point=point).order_by('-date_time_medition')[:10]
    
    print(f"--- Diagnóstico Punto {cp_id}: {point.title} ---")
    for r in records:
        flow_data = get_interaction_flow_display_data(r)
        print(f"ID: {r.id} | Fecha: {r.date_time_medition} | Total(DB): {r.total} | Consumo(DB): {r.total_diff} | Flow: {flow_data['value']} (Calculated: {flow_data['is_calculated']}, Type: {flow_data['type']})")

if __name__ == "__main__":
    test_point(14)
