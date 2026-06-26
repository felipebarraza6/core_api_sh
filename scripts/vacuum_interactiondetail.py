#!/usr/bin/env python3
"""
VACUUM + ANALYZE para core_interactiondetail
=============================================

Ejecuta VACUUM FULL ANALYZE en la tabla interactiondetail para:
- Eliminar filas muertas (dead tuples)
- Recuperar espacio en disco
- Actualizar estadísticas del query planner

USO:
    # Dry-run (solo muestra estadísticas actuales)
    docker exec -u root -w /app django_api_secure python scripts/vacuum_interactiondetail.py --dry-run

    # Ejecutar (REQUIERE ventana de mantenimiento - bloquea la tabla)
    docker exec -u root -w /app django_api_secure python scripts/vacuum_interactiondetail.py --force

NOTA: VACUUM FULL bloquea la tabla completamente durante la operación.
      No ejecutar durante horas de pico.
"""

import os
import sys
import argparse

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
import django
django.setup()

from django.db import connection


def log(msg):
    print(msg, flush=True)


def get_stats():
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                schemaname || '.' || relname as tabla,
                n_live_tup as filas_vivas,
                n_dead_tup as filas_muertas,
                pg_size_pretty(pg_total_relation_size(relid)) as tamano_total,
                pg_size_pretty(pg_relation_size(relid)) as tamano_datos,
                pg_size_pretty(pg_indexes_size(relid)) as tamano_indices,
                ROUND(n_dead_tup * 100.0 / NULLIF(n_live_tup + n_dead_tup, 0), 2) as pct_muertas
            FROM pg_stat_user_tables
            WHERE relname = 'core_interactiondetail'
        """)
        return cursor.fetchone()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Ejecutar VACUUM FULL")
    parser.add_argument("--reindex", action="store_true", help="También ejecutar REINDEX")
    args = parser.parse_args()

    log("=== Estadísticas actuales de core_interactiondetail ===")
    stats = get_stats()
    if stats:
        log(f"Tabla:           {stats[0]}")
        log(f"Filas vivas:     {stats[1]:,}")
        log(f"Filas muertas:   {stats[2]:,}")
        log(f"Tamaño total:    {stats[3]}")
        log(f"Tamaño datos:    {stats[4]}")
        log(f"Tamaño índices:  {stats[5]}")
        log(f"% muertas:       {stats[6]}%")
    else:
        log("No se encontraron estadísticas.")
        return

    if not args.force:
        log("")
        log("[DRY-RUN] No se ejecutó VACUUM. Usa --force para ejecutar.")
        log("[DRY-RUN] Usa --reindex para también reconstruir índices.")
        return

    log("")
    log("⚠️  Ejecutando VACUUM FULL ANALYZE...")
    log("⚠️  Esta operación BLOQUEA la tabla.")
    log("")

    with connection.cursor() as cursor:
        log("Paso 1/3: VACUUM FULL ANALYZE core_interactiondetail")
        cursor.execute("VACUUM FULL ANALYZE core_interactiondetail")
        log("✅ VACUUM completado")

        if args.reindex:
            log("")
            log("Paso 2/3: REINDEX TABLE CONCURRENTLY core_interactiondetail")
            cursor.execute("REINDEX TABLE CONCURRENTLY core_interactiondetail")
            log("✅ REINDEX completado")

        log("")
        log("Paso 3/3: Actualizando estadísticas")
        cursor.execute("ANALYZE core_interactiondetail")
        log("✅ ANALYZE completado")

    log("")
    log("=== Estadísticas post-VACUUM ===")
    stats = get_stats()
    if stats:
        log(f"Tabla:           {stats[0]}")
        log(f"Filas vivas:     {stats[1]:,}")
        log(f"Filas muertas:   {stats[2]:,}")
        log(f"Tamaño total:    {stats[3]}")
        log(f"Tamaño datos:    {stats[4]}")
        log(f"Tamaño índices:  {stats[5]}")
        log(f"% muertas:       {stats[6]}%")


if __name__ == "__main__":
    main()
