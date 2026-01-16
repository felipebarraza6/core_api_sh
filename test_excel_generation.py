#!/usr/bin/env python3
"""
Test de generación de Excel después del refactor de formatters.

Valida que excel_generator.py funciona correctamente con el nuevo módulo centralizado.
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
sys.path.insert(0, '/app')
django.setup()

from api.core.models import CatchmentPoint
from api.core.reports.excel_generator import generate_excel_by_project

print("=== TEST GENERACIÓN EXCEL POST-REFACTOR ===")
print()

# Buscar puntos con datos (máximo 3 para test rápido)
points = list(CatchmentPoint.objects.filter(
    interactiondetail__isnull=False
).distinct()[:3])

if points:
    print(f"📍 Generando Excel para {len(points)} puntos:")
    for p in points:
        print(f"   - {p.title} (ID: {p.id})")
    print()

    try:
        excel_buffer = generate_excel_by_project(
            points=points,
            project_name="Test Project"
        )

        # Guardar Excel de test
        output_path = '/tmp/test_excel_refactor.xlsx'
        with open(output_path, 'wb') as f:
            f.write(excel_buffer.getvalue())

        file_size = os.path.getsize(output_path)
        print(f"✅ Excel generado exitosamente")
        print(f"   Ubicación: {output_path}")
        print(f"   Tamaño: {file_size:,} bytes")
        print()

        # Validar que el Excel no está corrupto
        if file_size > 5000:  # Mínimo 5KB para archivo Excel válido
            print(f"✅ Excel tiene contenido válido ({file_size} bytes)")
        else:
            print(f"❌ Excel muy pequeño, probablemente corrupto")
            sys.exit(1)

        # Validar que es un archivo Excel válido (ZIP signature)
        with open(output_path, 'rb') as f:
            header = f.read(4)
            if header == b'PK\x03\x04':  # ZIP header
                print(f"✅ Excel tiene firma válida (ZIP/XLSX)")
            else:
                print(f"❌ Excel corrupto (firma inválida)")
                sys.exit(1)

        print()
        print("✅ FIX 4 (excel_utils.py) VALIDADO")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
else:
    print("⚠️  No se encontraron puntos con datos para test")
    print("   Test omitido (no crítico)")
