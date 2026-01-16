#!/usr/bin/env python3
"""
Test de generación de PDF después del refactor de formatters.

Valida que pdf_generator.py funciona correctamente con el nuevo módulo centralizado.
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
sys.path.insert(0, '/app')
django.setup()

from api.core.models import CatchmentPoint
from api.core.reports.pdf_generator import generate_telemetry_analysis_pdf

print("=== TEST GENERACIÓN PDF POST-REFACTOR ===")
print()

# Buscar un punto con datos
point = CatchmentPoint.objects.filter(
    interactiondetail__isnull=False
).first()

if point:
    print(f"📍 Generando PDF para punto: {point.title} (ID: {point.id})")
    print(f"   Proyecto: {point.project.name if point.project else 'N/A'}")
    print()

    try:
        pdf_buffer = generate_telemetry_analysis_pdf(
            points=[point],
            project_name=point.project.name if point.project else "Test Project",
            user_info={"name": "Test User", "email": "test@test.com"}
        )

        # Obtener bytes del buffer
        pdf_content = pdf_buffer.getvalue() if hasattr(pdf_buffer, 'getvalue') else pdf_buffer

        # Guardar PDF de test
        output_path = '/tmp/test_pdf_refactor.pdf'
        with open(output_path, 'wb') as f:
            f.write(pdf_content)

        print(f"✅ PDF generado exitosamente")
        print(f"   Ubicación: {output_path}")
        print(f"   Tamaño: {len(pdf_content):,} bytes")
        print()

        # Validar que el PDF no está corrupto (debe empezar con %PDF)
        if pdf_content[:4] == b'%PDF':
            print("✅ PDF válido (header correcto)")
        else:
            print("❌ PDF corrupto (header inválido)")
            sys.exit(1)

        # Validar que tiene contenido mínimo
        if len(pdf_content) > 1000:
            print(f"✅ PDF tiene contenido ({len(pdf_content)} bytes)")
        else:
            print(f"❌ PDF muy pequeño, probablemente vacío")
            sys.exit(1)

        print()
        print("✅ FIX 3 (pdf_generator.py) VALIDADO")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
else:
    print("⚠️  No se encontró punto con datos para test")
    print("   Test omitido (no crítico)")
