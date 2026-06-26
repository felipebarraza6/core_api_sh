#!/usr/bin/env python
"""
Script de Limpieza de Datos - Enero 2026
Detecta y corrige incoherencias en telemetría:
- Total=0 con pulsos>0 (incoherencia crítica)
- Saltos masivos irreales
- Caídas sospechosas
"""
import os
import sys
import django
from datetime import datetime, timedelta

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
sys.path.insert(0, '/app')
django.setup()

from django.db.models import Q, Count, Sum, Avg
from api.core.models import CatchmentPoint, InteractionDetail
from django.utils import timezone
import pytz

chile_tz = pytz.timezone("America/Santiago")

# Rango de análisis: Todo enero 2026
START_DATE = datetime(2026, 1, 1, 0, 0, 0, tzinfo=chile_tz)
END_DATE = datetime(2026, 2, 1, 0, 0, 0, tzinfo=chile_tz)

def analyze_january_data():
    """Analiza datos de enero y reporta problemas."""
    print("=" * 80)
    print("ANÁLISIS DE COHERENCIA - ENERO 2026")
    print("=" * 80)
    print(f"Período: {START_DATE.strftime('%Y-%m-%d')} a {END_DATE.strftime('%Y-%m-%d')}")
    print()

    # Obtener puntos con telemetría activa
    active_points = CatchmentPoint.objects.filter(
        Q(is_tdata=True) | Q(is_thethings=True) | Q(is_novus=True)
    )
    total_points = active_points.count()
    print(f"📊 Puntos con telemetría activa: {total_points}")
    print()

    # Estadísticas generales
    total_records = InteractionDetail.objects.filter(
        date_time_medition__gte=START_DATE,
        date_time_medition__lt=END_DATE
    ).count()
    print(f"📈 Total de registros en enero: {total_records:,}")
    print()

    # PROBLEMA 1: Total=0 con Pulsos>0 (Incoherencia crítica)
    incoherencias = InteractionDetail.objects.filter(
        date_time_medition__gte=START_DATE,
        date_time_medition__lt=END_DATE,
        total_diff=0,
        pulses__gt=0
    )

    incoherencias_count = incoherencias.count()
    print(f"❌ PROBLEMA 1: Total=0 con Pulsos>0")
    print(f"   Registros afectados: {incoherencias_count:,}")

    if incoherencias_count > 0:
        # Agrupar por punto
        points_with_issue = {}
        for record in incoherencias.select_related('catchment_point'):
            point_title = record.catchment_point.title
            if point_title not in points_with_issue:
                points_with_issue[point_title] = {
                    'count': 0,
                    'total_pulses': 0,
                    'point_id': record.catchment_point_id
                }
            points_with_issue[point_title]['count'] += 1
            points_with_issue[point_title]['total_pulses'] += record.pulses or 0

        print(f"   Puntos afectados: {len(points_with_issue)}")
        print(f"   Top 10 puntos:")
        sorted_points = sorted(points_with_issue.items(), key=lambda x: x[1]['count'], reverse=True)[:10]
        for point_name, data in sorted_points:
            print(f"      • {point_name}: {data['count']} registros, {data['total_pulses']:,} pulsos perdidos")
    print()

    # PROBLEMA 2: Saltos masivos (recuperaciones > 1000 m³)
    saltos = []
    for point in active_points:
        records = InteractionDetail.objects.filter(
            catchment_point_id=point.id,
            date_time_medition__gte=START_DATE,
            date_time_medition__lt=END_DATE
        ).order_by('date_time_medition')

        prev_total = None
        for record in records:
            total_diff = float(record.total_diff or 0)
            if prev_total is not None and prev_total == 0 and total_diff > 1000:
                saltos.append({
                    'point': point.title,
                    'point_id': point.id,
                    'record_id': record.id,
                    'value': total_diff,
                    'date': record.date_time_medition
                })
            prev_total = total_diff

    print(f"⚠️  PROBLEMA 2: Saltos masivos (0 → >1000 m³)")
    print(f"   Registros afectados: {len(saltos)}")
    if len(saltos) > 0:
        print(f"   Top 10 saltos:")
        sorted_saltos = sorted(saltos, key=lambda x: x['value'], reverse=True)[:10]
        for salto in sorted_saltos:
            print(f"      • {salto['point']}: {salto['value']:.1f} m³ el {salto['date'].strftime('%Y-%m-%d %H:%M')}")
    print()

    # PROBLEMA 3: Caídas sospechosas (drop de >500 m³ a 0)
    caidas = []
    for point in active_points:
        records = InteractionDetail.objects.filter(
            catchment_point_id=point.id,
            date_time_medition__gte=START_DATE,
            date_time_medition__lt=END_DATE
        ).order_by('date_time_medition')

        prev_total = None
        for record in records:
            total_diff = float(record.total_diff or 0)
            if prev_total is not None and prev_total > 500 and total_diff == 0:
                caidas.append({
                    'point': point.title,
                    'point_id': point.id,
                    'record_id': record.id,
                    'prev_value': prev_total,
                    'date': record.date_time_medition
                })
            prev_total = total_diff

    print(f"🔻 PROBLEMA 3: Caídas sospechosas (>500 m³ → 0)")
    print(f"   Registros afectados: {len(caidas)}")
    if len(caidas) > 0:
        print(f"   Top 10 caídas:")
        sorted_caidas = sorted(caidas, key=lambda x: x['prev_value'], reverse=True)[:10]
        for caida in sorted_caidas:
            print(f"      • {caida['point']}: {caida['prev_value']:.1f} m³ → 0 el {caida['date'].strftime('%Y-%m-%d %H:%M')}")
    print()

    print("=" * 80)
    print("RESUMEN")
    print("=" * 80)
    print(f"Total registros problemáticos: {incoherencias_count + len(saltos) + len(caidas):,}")
    print(f"  - Incoherencias (Total=0, Pulsos>0): {incoherencias_count:,}")
    print(f"  - Saltos masivos: {len(saltos)}")
    print(f"  - Caídas sospechosas: {len(caidas)}")
    print()

    return {
        'incoherencias': incoherencias,
        'incoherencias_count': incoherencias_count,
        'saltos': saltos,
        'caidas': caidas,
        'points_with_issue': points_with_issue if incoherencias_count > 0 else {}
    }


def fix_incoherencias(incoherencias, dry_run=True):
    """Corrige registros con Total=0 pero Pulsos>0."""
    print()
    print("=" * 80)
    print("CORRECCIÓN: Incoherencias Total=0 con Pulsos>0")
    print("=" * 80)

    if dry_run:
        print("🔍 MODO DRY-RUN (no se guardan cambios)")
    else:
        print("✏️  MODO ESCRITURA (guardando cambios en BD)")
    print()

    corrected = 0
    for record in incoherencias:
        pulses = record.pulses or 0
        if pulses > 0:
            # Recalcular total_diff basado en pulsos y escala del punto
            point = record.catchment_point

            # Obtener configuración de escala
            from api.core.models import ProfileDataConfigCatchment
            config = ProfileDataConfigCatchment.objects.filter(
                point_catchment=point
            ).first()

            if config and config.scale_total:
                # Calcular total correcto: pulsos * escala
                new_total = pulses * float(config.scale_total)

                if not dry_run:
                    record.total_diff = new_total
                    record.save(update_fields=['total_diff'])

                corrected += 1
                if corrected <= 10:  # Mostrar solo primeros 10
                    print(f"   ✅ {point.title}: {pulses} pulsos × {config.scale_total} = {new_total:.3f} m³")

    print()
    print(f"Total corregido: {corrected:,} registros")
    return corrected


def mark_suspicious_records(saltos, caidas, dry_run=True):
    """Marca registros sospechosos agregando un flag."""
    print()
    print("=" * 80)
    print("MARCADO: Registros sospechosos (saltos/caídas)")
    print("=" * 80)

    if dry_run:
        print("🔍 MODO DRY-RUN (no se guardan cambios)")
    else:
        print("✏️  MODO ESCRITURA (guardando cambios en BD)")
    print()

    # Para marcar necesitaríamos un campo 'is_suspicious' en el modelo
    # Por ahora solo reportamos
    print(f"Saltos a revisar manualmente: {len(saltos)}")
    print(f"Caídas a revisar manualmente: {len(caidas)}")
    print()
    print("💡 Estos registros requieren revisión manual caso por caso.")
    print("   Pueden ser válidos (mantenimiento, cierre de válvula, etc.)")

    return len(saltos) + len(caidas)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Limpieza de datos enero 2026')
    parser.add_argument('--dry-run', action='store_true', default=True,
                        help='Modo dry-run (no guarda cambios)')
    parser.add_argument('--fix', action='store_true',
                        help='Aplicar correcciones (desactiva dry-run)')
    args = parser.parse_args()

    dry_run = not args.fix

    # Análisis
    results = analyze_january_data()

    # Corrección
    if results['incoherencias_count'] > 0:
        print()
        if dry_run:
            print("⚠️  Para aplicar correcciones, ejecuta con: --fix")
            print()
            fix_incoherencias(results['incoherencias'], dry_run=True)
        else:
            response = input("\n¿Deseas aplicar las correcciones? (escribe 'SI' para confirmar): ")
            if response.strip().upper() == 'SI':
                fix_incoherencias(results['incoherencias'], dry_run=False)
                print("\n✅ Correcciones aplicadas exitosamente")
            else:
                print("\n❌ Correcciones canceladas")

    # Marcar sospechosos
    if len(results['saltos']) > 0 or len(results['caidas']) > 0:
        mark_suspicious_records(results['saltos'], results['caidas'], dry_run=True)

    print()
    print("=" * 80)
    print("ANÁLISIS COMPLETADO")
    print("=" * 80)
