#!/usr/bin/env python3
"""
Test del cronjob dinámico Novus
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

# Importar y ejecutar
from api.cronjobs.telemetry.novus_dynamic import run
from api.core.models import CatchmentPoint

if __name__ == "__main__":
    print("🧪 TESTEANDO CRONJOB DINÁMICO NOVUS")
    print("=" * 50)

    # Verificar puntos antes
    novus_points = CatchmentPoint.objects.filter(is_novus=True)
    print(f"📊 Puntos con is_novus=True: {novus_points.count()}")

    for point in novus_points:
        print(f"  - Punto {point.id}: {point.title}")

        # Verificar configuraciones dinámicas
        from api.core.providers.models import CatchmentPointProvider
        configs = CatchmentPointProvider.objects.filter(point=point)
        print(f"    Configs dinámicas: {configs.count()}")
        for config in configs:
            print(f"      {config.provider.name} -> {config.point_code}")

    print("\n🔄 Ejecutando cronjob...")
    run()
    print("\n✅ Test completado")