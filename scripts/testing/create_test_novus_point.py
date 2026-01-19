#!/usr/bin/env python3
"""
Crear punto de prueba para Novus

Crea un punto de captación de ejemplo con configuración Novus
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


def create_test_novus_point():
    """Crear punto de prueba con configuración Novus"""

    print("🔧 CREANDO PUNTO DE PRUEBA NOVUS")
    print("=" * 40)

    # Crear cliente
    client, created = Client.objects.get_or_create(
        name="Cliente Prueba Novus",
        defaults={
            'rut': '99.999.999-9',
            'address': 'Dirección de Prueba',
            'phone': '+56987654321',
            'email': 'prueba@novus.cl'
        }
    )
    print(f"{'✅ Creado' if created else 'ℹ️ Ya existe'} cliente: {client.name}")

    # Crear proyecto
    project, created = ProjectCatchments.objects.get_or_create(
        name="Proyecto Novus Dinámico",
        client=client,
        defaults={'code_internal': 'NOVUS-TEST'}
    )
    print(f"{'✅ Creado' if created else 'ℹ️ Ya existe'} proyecto: {project.name}")

    # Crear punto de captación
    point, created = CatchmentPoint.objects.get_or_create(
        title="Pozo Novus Dinámico",
        project=project,
        defaults={
            'owner_user_id': 1,  # Asumiendo que existe el admin
            'is_novus': True,     # ✅ IMPORTANTE: Marca como Novus
            'frecuency': '60',    # Cada hora
            'lat': '-33.500000',
            'lon': '-70.600000'
        }
    )
    print(f"{'✅ Creado' if created else 'ℹ️ Ya existe'} punto: {point.title} (ID: {point.id})")

    # Crear configuración de datos
    profile_config, created = ProfileDataConfigCatchment.objects.get_or_create(
        point_catchment=point,
        defaults={
            'token_service': 'demo_token_novus',
            'd1': 15.5,  # Profundidad
            'd2': 12.0,  # Posición bomba
            'd3': 8.5,   # Posición nivel
            'd4': 3.0,   # Diámetro ducto
            'd5': 2.0,   # Diámetro flujómetro
            'd6': 1500,  # Total inicial
            'is_telemetry': True
        }
    )
    print(f"{'✅ Creada' if created else 'ℹ️ Ya existe'} configuración física")

    # Crear esquema con variables
    scheme, created = SchemesCatchment.objects.get_or_create(
        name='Esquema Novus Dinámico',
        defaults={
            'description': 'Esquema de prueba para sistema dinámico'
        }
    )
    # Agregar el punto al esquema (ManyToMany)
    if point not in scheme.points_catchment.all():
        scheme.points_catchment.add(point)
        print("✅ Punto agregado al esquema")
    print(f"{'✅ Creado' if created else 'ℹ️ Ya existe'} esquema")

    # Variables de ejemplo
    variables_data = [
        {
            'str_variable': 'caudal',
            'type_variable': 'CAUDAL',
            'service': 'TWIN',           # ← Usa Twin para caudal
            'token_service': 'device_twin_001'
        },
        {
            'str_variable': 'nivel',
            'type_variable': 'NIVEL',
            'service': 'NETTRA',         # ← Usa Nettra para nivel
            'token_service': 'sensor_nettra_001'
        },
        {
            'str_variable': 'total',
            'type_variable': 'TOTALIZADO',
            'service': 'NOVUS',          # ← Usa Novus (que usa Nettra)
            'token_service': 'meter_novus_001'
        }
    ]

    for var_data in variables_data:
        var, created = Variable.objects.get_or_create(
            scheme_catchment=scheme,
            str_variable=var_data['str_variable'],
            defaults=var_data
        )
        print(f"{'✅ Creada' if created else 'ℹ️ Ya existe'} variable: {var.str_variable} ({var.service})")

    print("\n🎯 PUNTO DE PRUEBA CREADO")
    print("=" * 40)
    print(f"ID del punto: {point.id}")
    print(f"Variables configuradas: {len(variables_data)}")
    print("  - Caudal → TWIN (provider 'twin')")
    print("  - Nivel → NETTRA (provider 'nettra')")
    print("  - Total → NOVUS (provider 'nettra')")

    print("\n🚀 PRUEBA EL SISTEMA DINÁMICO")
    print("Ahora puedes ejecutar:")
    print("python3 migrate_novus_points.py")
    print("python3 api/cronjobs/telemetry/novus_dynamic.py")

    return point.id


if __name__ == "__main__":
    point_id = create_test_novus_point()
    print(f"\n✅ Punto de prueba creado con ID: {point_id}")