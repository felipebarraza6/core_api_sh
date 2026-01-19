#!/usr/bin/env python3
"""
Crear punto de prueba para Twin

Crea un punto de captación de ejemplo con configuración Twin
para probar el sistema dinámico.
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import (
    Client, ProjectCatchments, CatchmentPoint,
    ProfileDataConfigCatchment, SchemesCatchment, Variable
)


def create_test_twin_point():
    """Crear punto de prueba con configuración Twin"""

    print("🔧 CREANDO PUNTO DE PRUEBA TWIN")
    print("=" * 40)

    # Crear cliente
    client, created = Client.objects.get_or_create(
        name="Cliente Prueba Twin",
        defaults={
            'rut': '77.777.777-7',
            'address': 'Dirección de Prueba Twin',
            'phone': '+56977777777',
            'email': 'prueba@twin.cl'
        }
    )
    print(f"{'✅ Creado' if created else 'ℹ️ Ya existe'} cliente: {client.name}")

    # Crear proyecto
    project, created = ProjectCatchments.objects.get_or_create(
        name="Proyecto Twin Dinámico",
        client=client,
        defaults={'code_internal': 'TWIN-TEST'}
    )
    print(f"{'✅ Creado' if created else 'ℹ️ Ya existe'} proyecto: {project.name}")

    # Crear punto de captación - TWIN usa is_tdata=True
    point, created = CatchmentPoint.objects.get_or_create(
        title="Pozo Twin Dinámico",
        project=project,
        defaults={
            'owner_user_id': 1,  # Asumiendo que existe el admin
            'is_tdata': True,     # ✅ IMPORTANTE: Marca como Twin (tdata)
            'frecuency': '60',    # Cada hora
            'lat': '-33.400000',
            'lon': '-70.500000'
        }
    )
    print(f"{'✅ Creado' if created else 'ℹ️ Ya existe'} punto: {point.title} (ID: {point.id})")

    # Crear configuración de datos
    profile_config, created = ProfileDataConfigCatchment.objects.get_or_create(
        point_catchment=point,
        defaults={
            'token_service': 'demo_token_twin',
            'd1': 20.5,  # Profundidad
            'd2': 15.0,  # Posición bomba
            'd3': 10.5,  # Posición nivel
            'd4': 4.0,   # Diámetro ducto
            'd5': 3.0,   # Diámetro flujómetro
            'd6': 2000,  # Total inicial
            'is_telemetry': True
        }
    )
    print(f"{'✅ Creada' if created else 'ℹ️ Ya existe'} configuración física")

    # Crear esquema con variables
    scheme, created = SchemesCatchment.objects.get_or_create(
        name='Esquema Twin Dinámico',
        defaults={
            'description': 'Esquema de prueba para sistema dinámico Twin'
        }
    )
    # Agregar el punto al esquema (ManyToMany)
    if point not in scheme.points_catchment.all():
        scheme.points_catchment.add(point)
        print("✅ Punto agregado al esquema")
    print(f"{'✅ Creado' if created else 'ℹ️ Ya existe'} esquema")

    # Variables de ejemplo para Twin
    variables_data = [
        {
            'str_variable': 'caudal',
            'type_variable': 'CAUDAL',
            'service': 'TWIN',           # ← Twin es el servicio principal
            'token_service': 'device_twin_002'
        },
        {
            'str_variable': 'nivel',
            'type_variable': 'NIVEL',
            'service': 'TWIN',           # ← También usa Twin
            'token_service': 'sensor_twin_002'
        },
        {
            'str_variable': 'total',
            'type_variable': 'TOTALIZADO',
            'service': 'TWIN',           # ← Twin para totales
            'token_service': 'meter_twin_002'
        }
    ]

    for var_data in variables_data:
        var, created = Variable.objects.get_or_create(
            scheme_catchment=scheme,
            str_variable=var_data['str_variable'],
            defaults=var_data
        )
        print(f"{'✅ Creada' if created else 'ℹ️ Ya existe'} variable: {var.str_variable} ({var.service})")

    print("\n🎯 PUNTO DE PRUEBA TWIN CREADO")
    print("=" * 40)
    print(f"ID del punto: {point.id}")
    print(f"Variables configuradas: {len(variables_data)}")
    print("  - Caudal → TWIN (provider 'twin')")
    print("  - Nivel → TWIN (provider 'twin')")
    print("  - Total → TWIN (provider 'twin')")

    print("\n🚀 PRUEBA EL SISTEMA DINÁMICO TWIN")
    print("Ahora puedes ejecutar:")
    print("python3 migrate_twin_points.py")
    print("python3 api/cronjobs/telemetry/twin_dynamic.py")

    return point.id


if __name__ == "__main__":
    point_id = create_test_twin_point()
    print(f"\n✅ Punto de prueba Twin creado con ID: {point_id}")