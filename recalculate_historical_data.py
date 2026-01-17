#!/usr/bin/env python3
"""
SCRIPT: Recalcular Datos Históricos
====================================
Recalcula total_diff y total_today_diff para todos los registros
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
from api.core.models import InteractionDetail, CatchmentPoint, ProfileDataConfigCatchment
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
    Recalcular toda la historia de un punto.
    
    Args:
        point_id: ID del punto
        dry_run: Si True, solo muestra lo que haría sin modificar
    
    Returns:
        Dict con estadísticas
    """
    stats = {
        'total_records': 0,
        'total_diff_fixed': 0,
        'total_today_diff_fixed': 0,
        'errors': 0
    }
    
    config = get_point_config(point_id)
    
    # Obtener todos los registros ordenados por fecha
    registros = InteractionDetail.objects.filter(
        catchment_point_id=point_id
    ).order_by('created', 'id')
    
    stats['total_records'] = registros.count()
    
    if stats['total_records'] == 0:
        return stats
    
    # Procesar por día
    registros_list = list(registros.values('id', 'pulses', 'total', 'total_diff', 'total_today_diff', 'created'))
    
    prev_total = None
    current_day = None
    first_total_of_day = None
    
    updates_diff = []
    updates_today = []
    
    for r in registros_list:
        record_id = r['id']
        pulses = r['pulses']
        total = r['total']
        current_diff = r['total_diff']
        current_today = r['total_today_diff']
        record_date = r['created'].date() if r['created'] else None
        
        # Recalcular total si tenemos pulsos
        if pulses is not None:
            recalc_total = recalculate_total_from_pulses(
                pulses, config['pulses_factor'], config['addition']
            )
            # Si el total recalculado difiere mucho, usar el almacenado
            # (puede haber tenido ajustes manuales válidos)
            if recalc_total and abs(recalc_total - (total or 0)) > 1000:
                # Usar total almacenado, no recalcular
                pass
        
        # Calcular diff horario correcto
        if prev_total is not None and total is not None:
            correct_diff = total - prev_total
            
            # Aplicar reglas de validación
            if correct_diff < 0:
                correct_diff = 0
            elif correct_diff > MAX_DIFF_HOUR:
                correct_diff = 0  # Salto masivo, clampar
            
            # Verificar si necesita corrección
            if current_diff != correct_diff:
                updates_diff.append({
                    'id': record_id,
                    'old': current_diff,
                    'new': correct_diff
                })
                stats['total_diff_fixed'] += 1
        
        # Calcular diff diario correcto
        if record_date:
            if current_day != record_date:
                # Nuevo día, resetear
                current_day = record_date
                first_total_of_day = total
            
            if first_total_of_day is not None and total is not None:
                correct_today = total - first_total_of_day
                
                # Validación
                if correct_today < 0:
                    correct_today = 0
                elif correct_today > MAX_DIFF_DAY:
                    correct_today = 0
                
                if current_today != correct_today:
                    updates_today.append({
                        'id': record_id,
                        'old': current_today,
                        'new': correct_today
                    })
                    stats['total_today_diff_fixed'] += 1
        
        prev_total = total
    
    # Aplicar correcciones si no es dry_run
    if not dry_run:
        with transaction.atomic():
            # Batch update para total_diff
            for upd in updates_diff:
                InteractionDetail.objects.filter(id=upd['id']).update(total_diff=upd['new'])
            
            # Batch update para total_today_diff
            for upd in updates_today:
                InteractionDetail.objects.filter(id=upd['id']).update(total_today_diff=upd['new'])
    
    return stats


def run_full_audit(dry_run=True, limit_points=None):
    """
    Ejecutar auditoría completa de todos los puntos.
    
    Args:
        dry_run: Si True, solo muestra lo que haría
        limit_points: Limitar a N puntos (para pruebas)
    """
    print("=" * 60)
    print("AUDITORÍA Y CORRECCIÓN DE DATOS HISTÓRICOS")
    print("=" * 60)
    print(f"Modo: {'DRY RUN (sin cambios)' if dry_run else '🔴 APLICANDO CAMBIOS'}")
    print()
    
    # Obtener todos los puntos
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
    Más rápido para limpiar los casos más evidentes.
    """
    print("=" * 60)
    print("CORRECCIÓN RÁPIDA DE VALORES EXTREMOS")
    print("=" * 60)
    
    # 1. Diffs > 500 → 0
    count_high = InteractionDetail.objects.filter(total_diff__gt=500).update(total_diff=0)
    print(f"✅ total_diff > 500 corregidos: {count_high}")
    
    # 2. Diffs negativos → 0
    count_neg = InteractionDetail.objects.filter(total_diff__lt=0).update(total_diff=0)
    print(f"✅ total_diff negativos corregidos: {count_neg}")
    
    # 3. total_today_diff negativos → 0
    count_today_neg = InteractionDetail.objects.filter(total_today_diff__lt=0).update(total_today_diff=0)
    print(f"✅ total_today_diff negativos corregidos: {count_today_neg}")
    
    # 4. total_today_diff > 10000 → 0
    count_today_high = InteractionDetail.objects.filter(total_today_diff__gt=10000).update(total_today_diff=0)
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
