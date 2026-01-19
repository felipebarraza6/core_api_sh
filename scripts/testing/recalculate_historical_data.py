#!/usr/bin/env python3
"""
SCRIPT: Recalcular Datos Históricos (V3)
====================================
Recalcula total_diff y total_today_diff para todos los registros V3
basándose en los pulsos almacenados y las nuevas reglas.

Uso:
    python manage.py shell < recalculate_historical_data.py

O dentro del contenedor:
    docker exec -it django_api_secure python manage.py shell < recalculate_historical_data.py
"""

import os
import sys
import django

# Setup Django si se ejecuta como script standalone
if 'DJANGO_SETTINGS_MODULE' not in os.environ:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
    django.setup()

from django.db import transaction
from django.db.models import F
from api.core.models import TelemetryRecord, CatchmentPoint, ProfileDataConfigCatchment
from datetime import datetime, timedelta
from django.utils import timezone

# Constantes
MAX_DIFF_HOUR = 500  # Máximo diff horario razonable
MAX_DIFF_DAY = 10000  # Máximo diff diario razonable
BATCH_SIZE = 1000


def get_point_config(point_id):
    """Obtener factor de pulsos y offset del perfil"""
    try:
        profile = ProfileDataConfigCatchment.objects.filter(point_catchment_id=point_id).first()
        if profile:
            return {
                'pulses_factor': profile.pulses_factor or 1000,
                'addition': profile.addition or 0
            }
    except:
        pass
    return {'pulses_factor': 1000, 'addition': 0}


def recalculate_total_from_pulses(pulses, pulses_factor, addition):
    """Recalcular total usando fórmula: (pulsos * factor / 1000) + offset"""
    if pulses is None:
        return None
    try:
        raw_m3 = (float(pulses) * float(pulses_factor)) / 1000.0
        return int(round(raw_m3 + float(addition)))
    except:
        return None


def recalculate_point_history(point_id, dry_run=True):
    """
    Recalcular toda la historia de un punto V3.
    """
    stats = {
        'total_records': 0,
        'total_diff_fixed': 0,
        'total_today_diff_fixed': 0,
        'errors': 0
    }
    
    config = get_point_config(point_id)
    
    # Obtener todos los registros ordenados por fecha
    registros = TelemetryRecord.objects.filter(
        point_id=point_id
    ).order_by('timestamp', 'id')
    
    stats['total_records'] = registros.count()
    
    if stats['total_records'] == 0:
        return stats
    
    prev_total = None
    current_day = None
    first_total_of_day = None
    
    updates = [] # List of records to update
    
    # Iterar sobre los objetos para acceder al JSON data
    for r in registros.iterator(chunk_size=1000):
        data = r.data
        record_id = r.id
        
        pulses = data.get('pulses')
        total = float(data.get('total', 0)) if data.get('total') is not None else None
        current_diff = float(data.get('total_diff', 0))
        current_today = float(data.get('total_today_diff', 0))
        
        record_date = r.timestamp.date() if r.timestamp else None
        
        modified = False
        
        # Recalcular total si tenemos pulsos
        if pulses is not None:
            recalc_total = recalculate_total_from_pulses(
                pulses, config['pulses_factor'], config['addition']
            )
            if recalc_total and total is not None and abs(recalc_total - total) > 1000:
                pass # Usar total almacenado
        
        # Calcular diff horario correcto
        correct_diff = current_diff
        if prev_total is not None and total is not None:
            correct_diff = total - prev_total
            if correct_diff < 0: correct_diff = 0
            elif correct_diff > MAX_DIFF_HOUR: correct_diff = 0
            
            if abs(current_diff - correct_diff) > 0.01:
                data['total_diff'] = correct_diff
                modified = True
                stats['total_diff_fixed'] += 1
        
        # Calcular diff diario correcto
        correct_today = current_today
        if record_date:
            if current_day != record_date:
                current_day = record_date
                first_total_of_day = total
            
            if first_total_of_day is not None and total is not None:
                correct_today = total - first_total_of_day
                if correct_today < 0: correct_today = 0
                elif correct_today > MAX_DIFF_DAY: correct_today = 0
                
                if abs(current_today - correct_today) > 0.01:
                    data['total_today_diff'] = correct_today
                    modified = True
                    stats['total_today_diff_fixed'] += 1
        
        prev_total = total
        
        if modified and not dry_run:
            r.data = data # Asignar data modificado
            updates.append(r)
            if len(updates) >= BATCH_SIZE:
                TelemetryRecord.objects.bulk_update(updates, ['data'])
                updates = []

    if not dry_run and updates:
        TelemetryRecord.objects.bulk_update(updates, ['data'])
    
    return stats


def run_full_audit(dry_run=True, limit_points=None):
    """
    Ejecutar auditoría completa de todos los puntos V3.
    """
    print("=" * 60)
    print("AUDITORÍA Y CORRECCIÓN DE DATOS HISTÓRICOS (V3)")
    print("=" * 60)
    print(f"Modo: {'DRY RUN (sin cambios)' if dry_run else '🔴 APLICANDO CAMBIOS'}")
    print()
    
    puntos = CatchmentPoint.objects.all().order_by('id')
    if limit_points:
        puntos = puntos[:limit_points]
    
    total_stats = {
        'points_processed': 0,
        'total_records': 0,
        'total_diff_fixed': 0,
        'total_today_diff_fixed': 0,
        'errors': 0
    }
    
    for punto in puntos:
        try:
            stats = recalculate_point_history(punto.id, dry_run=dry_run)
            
            total_stats['points_processed'] += 1
            total_stats['total_records'] += stats['total_records']
            total_stats['total_diff_fixed'] += stats['total_diff_fixed']
            total_stats['total_today_diff_fixed'] += stats['total_today_diff_fixed']
            
            if stats['total_diff_fixed'] > 0 or stats['total_today_diff_fixed'] > 0:
                print(f"  Punto {punto.id}: {stats['total_records']:,} registros | "
                      f"Diff fixes: {stats['total_diff_fixed']} | "
                      f"Today fixes: {stats['total_today_diff_fixed']}")
                      
        except Exception as e:
            print(f"  ❌ Punto {punto.id}: Error - {e}")
            total_stats['errors'] += 1
    
    print()
    print("=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"Puntos procesados: {total_stats['points_processed']}")
    print(f"Registros analizados: {total_stats['total_records']:,}")
    print(f"total_diff corregidos: {total_stats['total_diff_fixed']:,}")
    print(f"total_today_diff corregidos: {total_stats['total_today_diff_fixed']:,}")
    print(f"Errores: {total_stats['errors']}")
    print()
    
    if dry_run:
        print("ℹ️ Ejecutar con dry_run=False para aplicar cambios")
    else:
        print("✅ Cambios aplicados")
    
    return total_stats


def quick_fix_extreme_values():
    """
    Corrección rápida: Solo arregla valores extremos sin recalcular todo.
    (Adaptado para V3 iterando y filtrando en Python)
    """
    print("=" * 60)
    print("CORRECCIÓN RÁPIDA DE VALORES EXTREMOS (V3)")
    print("=" * 60)
    
    # Nota: No podemos usar update() directo en JSONField conditions fácilmente
    # sin DB-specific funcs. Haremos un scan.
    
    records = TelemetryRecord.objects.filter(data__isnull=False)
    count_high = 0
    count_neg = 0
    count_today_neg = 0
    count_today_high = 0
    updates = []
    
    for r in records.iterator(chunk_size=2000):
        data = r.data
        modified = False
        
        diff = float(data.get('total_diff', 0))
        today = float(data.get('total_today_diff', 0))
        
        if diff > 500:
            data['total_diff'] = 0
            modified = True
            count_high += 1
        elif diff < 0:
            data['total_diff'] = 0
            modified = True
            count_neg += 1
            
        if today < 0:
            data['total_today_diff'] = 0
            modified = True
            count_today_neg += 1
        elif today > 10000:
            data['total_today_diff'] = 0
            modified = True
            count_today_high += 1
            
        if modified:
            r.data = data
            updates.append(r)
            if len(updates) >= 1000:
                TelemetryRecord.objects.bulk_update(updates, ['data'])
                updates = []
                
    if updates:
        TelemetryRecord.objects.bulk_update(updates, ['data'])
        
    print(f"✅ total_diff > 500 corregidos: {count_high}")
    print(f"✅ total_diff negativos corregidos: {count_neg}")
    print(f"✅ total_today_diff negativos corregidos: {count_today_neg}")
    print(f"✅ total_today_diff > 10,000 corregidos: {count_today_high}")
    
    print()
    print(f"Total correcciones: {count_high + count_neg + count_today_neg + count_today_high}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Recalcular datos históricos')
    parser.add_argument('--apply', action='store_true', help='Aplicar cambios (sin esto es dry run)')
    parser.add_argument('--quick', action='store_true', help='Solo corregir valores extremos')
    parser.add_argument('--limit', type=int, help='Limitar a N puntos')
    
    args = parser.parse_args()
    
    if args.quick:
        quick_fix_extreme_values()
    else:
        run_full_audit(dry_run=not args.apply, limit_points=args.limit)
