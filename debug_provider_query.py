
import os
import django
from django.db.models import Count, Q

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint, DgaDataConfigCatchment, ProfileDataConfigCatchment

def debug_provider_counts():
    print("Debugging Provider Counts Logic...")

    # 1. Replicate 'num_obras' logic
    dga_points_qs = DgaDataConfigCatchment.objects.filter(
        code_dga__isnull=False
    ).exclude(code_dga__exact='')
    obras_points_ids = list(dga_points_qs.values_list('point_catchment_id', flat=True).distinct())
    print(f"Total Obras Points IDs: {len(obras_points_ids)}")

    # 2. Replicate 'obras_with_telemetry' logic (Known to be ~101)
    telemetry_profiles = ProfileDataConfigCatchment.objects.filter(
        point_catchment__in=obras_points_ids,
        is_telemetry=True
    )
    count_telemetry = telemetry_profiles.values('point_catchment').distinct().count()
    print(f"Reference Telemetry Count from Profile model: {count_telemetry}")

    # 3. Test the failing query mechanism
    # CatchmentPoint filtering
    points_with_telemetry_qs = CatchmentPoint.objects.filter(
        id__in=obras_points_ids,
        data_config_profiles__is_telemetry=True
    ).distinct()
    
    print(f"CatchmentPoint Filter Count: {points_with_telemetry_qs.count()}")
    
    # 4. Test Aggregation
    agg_result = points_with_telemetry_qs.aggregate(
        thethings=Count('id', filter=Q(is_thethings=True)),
        novus=Count('id', filter=Q(is_novus=True)),
        tdata=Count('id', filter=Q(is_tdata=True))
    )
    print("Aggregation Result:", agg_result)

    # 5. Check actual flags
    print("\nSample Check of flags for first 5 points in queryset:")
    for p in points_with_telemetry_qs[:5]:
        print(f"ID: {p.id} - Nettra: {p.is_thethings}, Novus: {p.is_novus}, Twin: {p.is_tdata}")

    # 6. Check if any point has any flag True globally within obras
    global_trues = CatchmentPoint.objects.filter(id__in=obras_points_ids).filter(
        Q(is_thethings=True) | Q(is_novus=True) | Q(is_tdata=True)
    ).count()
    print(f"\nPoints in Obras with AT LEAST ONE provider flag = True: {global_trues}")

if __name__ == '__main__':
    debug_provider_counts()
