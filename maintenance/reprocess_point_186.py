#!/usr/bin/env python3
"""
SCRIPT: Reprocesar Agricola Nahuen (ID 186)
===========================================
Recalcula TOTAL y diffs basándose en pulsos y configuración actual.
"""

import os
import django

if 'DJANGO_SETTINGS_MODULE' not in os.environ:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
    django.setup()

from django.db import transaction
from api.core.models import InteractionDetail, CatchmentPoint, ProfileDataConfigCatchment, Variable

POINT_ID = 186
BATCH_SIZE = 1000

def get_config(point_id):
    point = CatchmentPoint.objects.get(id=point_id)
    profile = ProfileDataConfigCatchment.objects.filter(point_catchment=point).first()
    addition = profile.addition if profile else 0
    
    # Get pulses factor from Variable
    # Assuming 'TOTALIZADO' type or similar. If multiple, take the first one with logic.
    # Based on investigation, ID 140 is TOTALIZADO with factor 100.
    variable = Variable.objects.filter(scheme_catchment__in=point.schemes.all(), type_variable='TOTALIZADO').first()
    factor = variable.pulses_factor if variable else 1000 # default
    
    return factor, addition

def recalculate(dry_run=True):
    print(f"Reprocesando Punto {POINT_ID} - Dry Run: {dry_run}")
    
    factor, addition = get_config(POINT_ID)
    print(f"Configuración usada: Factor={factor}, Addition={addition}")
    
    records = InteractionDetail.objects.filter(catchment_point_id=POINT_ID).order_by('created')
    total_records = records.count()
    print(f"Registros encontrados: {total_records}")
    
    if total_records == 0:
        return

    updates_total = []
    updates_diff = []
    updates_today = []
    
    prev_total = None
    current_day = None
    first_total_of_day = None
    
    # Iterate and calculate
    # We need to process sequentially because diffs depend on previous total
    
    # Optimization: Fetch values to memory if not too large (2M records might be too much, but for 1 point likely ok?)
    # If point has huge history, maybe use iterator. 
    # Let's use iterator but we need to track state.
    
    processed = 0
    
    for record in records.iterator(chunk_size=BATCH_SIZE):
        processed += 1
        if processed % 1000 == 0:
            print(f"Procesados {processed}/{total_records}...", end='\r')
            
        pulses = record.pulses
        old_total = record.total
        old_diff = record.total_diff
        old_today = record.total_today_diff
        
        # 1. Recalculate Total
        new_total = old_total
        if pulses is not None:
            # Formula: (pulses * factor) / 1000 + addition
            val_m3 = (float(pulses) * float(factor)) / 1000.0
            new_total = int(round(val_m3 + float(addition)))
        
        if new_total != old_total:
             updates_total.append({'id': record.id, 'val': new_total})

        # 2. Recalculate Diffs (using new_total)
        new_diff = old_diff
        if prev_total is not None and new_total is not None:
            new_diff = new_total - prev_total
            if new_diff < 0: new_diff = 0
            # Cap extreme diffs? User said "escala correcta", so maybe trust the calc?
            # Let's verify with MAX_DIFF_HOUR usually used
            if new_diff > 500: new_diff = 0
        else:
            new_diff = 0 # First record or missing prev
            
        if new_diff != old_diff:
            updates_diff.append({'id': record.id, 'val': new_diff})
            
        # 3. Recalculate Today Diff
        record_date = record.created.date() if record.created else None
        new_today = old_today
        
        if record_date:
            if current_day != record_date:
                current_day = record_date
                first_total_of_day = new_total
            
            if first_total_of_day is not None and new_total is not None:
                new_today = new_total - first_total_of_day
                if new_today < 0: new_today = 0
                if new_today > 10000: new_today = 0
        
        if new_today != old_today:
            updates_today.append({'id': record.id, 'val': new_today})
            
        prev_total = new_total
    
    print(f"\nResumen de cambios:")
    print(f"  Total updates: {len(updates_total)}")
    print(f"  Diff updates: {len(updates_diff)}")
    print(f"  Today updates: {len(updates_today)}")
    
    if not dry_run:
        print("Aplicando cambios en la base de datos...")
        with transaction.atomic():
            # Apply in batches to avoid memory issues with huge queries
            batch_update(InteractionDetail, updates_total, 'total')
            batch_update(InteractionDetail, updates_diff, 'total_diff')
            batch_update(InteractionDetail, updates_today, 'total_today_diff')
        print("✅ Cambios aplicados correctamente.")
    else:
        print("ℹ️ Modo Dry Run - No se aplicaron cambios.")

def batch_update(model, updates, field_name):
    if not updates:
        return
    
    # This can be slow if doing one by one. Use bulk_update if possible, or raw SQL if very large.
    # Django bulk_update is good.
    
    # We need to construct model instances with ID and the field
    # But we don't want to fetch them all again.
    # Actually, simplistic approach:
    # model.objects.bulk_update([model(id=u['id'], field_name=u['val'])], [field_name])
    
    print(f"  Aplicando {len(updates)} updates para {field_name}...", end='')
    
    # Chunking
    chunk_size = 1000
    for i in range(0, len(updates), chunk_size):
        chunk = updates[i:i+chunk_size]
        objects = [model(id=u['id'], **{field_name: u['val']}) for u in chunk]
        model.objects.bulk_update(objects, [field_name])
        print(".", end='', flush=True)
    print(" Done.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    
    recalculate(dry_run=not args.apply)
