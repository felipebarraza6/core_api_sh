
from api.core.models import CatchmentPoint, DgaDataConfigCatchment, ProfileDataConfigCatchment

def debug_flags():
    print("--- Debugging Provider Flags ---")
    
    # Replicate the view logic to get the pool of points
    dga_points_qs = DgaDataConfigCatchment.objects.filter(
        code_dga__isnull=False
    ).exclude(code_dga__exact='')
    obras_points_ids = list(dga_points_qs.values_list('point_catchment_id', flat=True).distinct())
    
    print(f"Total Obras Points: {len(obras_points_ids)}")
    
    # Get profiles
    profiles_map = {
        p.point_catchment_id: p 
        for p in ProfileDataConfigCatchment.objects.filter(point_catchment__in=obras_points_ids)
    }
    
    connected_count = 0
    nettra_count = 0
    novus_count = 0
    twin_count = 0
    
    # Iterate and check flags
    points = CatchmentPoint.objects.filter(id__in=obras_points_ids)
    
    print("\n--- Sampling Points ---")
    for i, point in enumerate(points):
        profile = profiles_map.get(point.id)
        is_connected = False
        if profile and profile.is_telemetry:
            is_connected = True
            connected_count += 1
            
            if point.is_thethings:
                nettra_count += 1
            if point.is_novus:
                novus_count += 1
            if point.is_tdata:
                twin_count += 1
        
        # Print sample of 10 connected points
        if is_connected and i < 20: 
            print(f"ID: {point.id} | Connected: YES | Nettra: {point.is_thethings} ({type(point.is_thethings)}) | Novus: {point.is_novus} | Twin: {point.is_tdata}")

    print("\n--- Summary ---")
    print(f"Total Connected: {connected_count}")
    print(f"Nettra Count: {nettra_count}")
    print(f"Novus Count: {novus_count}")
    print(f"Twin Count: {twin_count}")

debug_flags()
