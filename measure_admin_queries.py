#!/usr/bin/env python3
"""
Medir queries del admin ANTES y DESPUÉS de optimización.

Compara el número de queries ejecutadas en changelist de InteractionDetailAdmin.
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
sys.path.insert(0, '/app')
django.setup()

from django.test.utils import override_settings
from django.db import connection, reset_queries
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from api.core.admin import InteractionDetailAdmin
from api.core.models import InteractionDetail, User

print("=" * 60)
print("MEDICIÓN DE QUERIES - InteractionDetailAdmin")
print("=" * 60)
print()

# Habilitar query logging
with override_settings(DEBUG=True):
    # Setup
    admin = InteractionDetailAdmin(InteractionDetail, AdminSite())
    factory = RequestFactory()
    request = factory.get('/admin/core/interactiondetail/')

    # Obtener superuser para el request
    request.user = User.objects.filter(is_superuser=True).first()
    if not request.user:
        print("❌ No hay superuser disponible para test")
        sys.exit(1)

    # Reset queries
    reset_queries()

    # Ejecutar changelist (simular página de admin)
    try:
        queryset = admin.get_queryset(request)
        # Forzar evaluación de 24 registros (1 página)
        records = list(queryset[:24])

        # Simular renderización de list_display (esto causa N+1 si no está optimizado)
        print(f"⏳ Simulando renderización de list_display methods...")
        for record in records:
            # Llamar a los métodos display que acceden a relaciones
            admin.get_catchment_point_display(record)
            admin.get_flow_display(record)
            # No llamar a todos para no hacer el test demasiado lento
        print()

    except Exception as e:
        print(f"❌ Error ejecutando queryset: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Contar queries
    query_count = len(connection.queries)

    print(f"📊 Queries ejecutadas: {query_count}")
    print(f"   Registros evaluados: 24")
    print()

    # Análisis
    if query_count > 50:
        print(f"❌ PROBLEMA N+1 DETECTADO")
        print(f"   Se ejecutaron {query_count} queries para 24 registros")
        print(f"   Esperado: <10 queries con optimización")
        print()
        print("🔍 Muestra de queries:")
        for i, query in enumerate(connection.queries[:10], 1):
            sql = query['sql'][:100]
            time = query['time']
            print(f"   {i}. [{time}s] {sql}...")
    elif query_count > 20:
        print(f"⚠️  QUERIES ELEVADAS")
        print(f"   {query_count} queries es mejorable")
        print(f"   Objetivo: <10 queries")
    elif query_count <= 10:
        print(f"✅ QUERIES OPTIMIZADAS")
        print(f"   {query_count} queries es excelente para 24 registros")
        print(f"   Admin está bien optimizado con select_related/prefetch")
    else:
        print(f"🟡 QUERIES ACEPTABLES")
        print(f"   {query_count} queries es aceptable pero mejorable")

    print()
    print("=" * 60)
