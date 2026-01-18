#!/usr/bin/env python
"""Script para crear esquema TWIN y asignarlo al punto"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
sys.path.insert(0, '/app')
django.setup()

from api.core.models import TelemetryScheme, SchemeVariable, CatchmentPoint, CoreVariable

# 1. Crear esquema
scheme, created = TelemetryScheme.objects.get_or_create(
    name='TWIN - Totalizado + Caudal',
    defaults={'description': 'Esquema estándar TWIN con totalizado (5000) y caudal (5001)'}
)
status = 'Creado' if created else 'Existente'
print(f'✨ Esquema: {scheme.name} (ID: {scheme.id}) - {status}')

# 2. Variables del esquema - Totalizado
var_total, created = SchemeVariable.objects.get_or_create(
    scheme=scheme,
    internal_code='total',
    defaults={
        'name': 'Totalizado (m³)',
        'unit': 'm³',
        'type_variable': 'TOTALIZADO',
        'provider_key': '5000',
        'operation': 'PHYSICAL',
        'priority': 10,
        'configuration': {'pulses_factor': 1000.0, 'calculate_nivel': False}
    }
)
status = 'Creada' if created else 'Existente'
print(f'  📊 Variable total: {status}')

# Variables del esquema - Caudal
var_flow, created = SchemeVariable.objects.get_or_create(
    scheme=scheme,
    internal_code='flow',
    defaults={
        'name': 'Caudal (L/s)',
        'unit': 'L/s',
        'type_variable': 'CAUDAL',
        'provider_key': '5001',
        'operation': 'PHYSICAL',
        'priority': 20,
        'configuration': {}
    }
)
status = 'Creada' if created else 'Existente'
print(f'  📊 Variable flow: {status}')

# 3. Asignar esquema al punto 137
point = CatchmentPoint.objects.get(id=137)
old_scheme = point.processing_scheme.name if point.processing_scheme else 'Ninguno'
point.processing_scheme = scheme
point.save()
print(f'\n🔗 Punto: {point.title} (ID: {point.id})')
print(f'   Esquema anterior: {old_scheme}')
print(f'   Esquema nuevo: {scheme.name}')

# 4. Eliminar variables directas del punto
vars_directas = CoreVariable.objects.filter(point=point)
count = vars_directas.count()
if count > 0:
    vars_directas.delete()
    print(f'\n🗑️  Eliminadas {count} variables directas del punto')
    print(f'   Ahora usa SOLO las variables del esquema')
else:
    print(f'\n✅ El punto ya no tenía variables directas')

print(f'\n✅ Configuración completada')
print(f'   El punto {point.title} ahora hereda las variables del esquema:')
print(f'   - total (5000) - TOTALIZADO')
print(f'   - flow (5001) - CAUDAL')
