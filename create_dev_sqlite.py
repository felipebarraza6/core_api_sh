#!/usr/bin/env python3
"""
SCRIPT: Crear SQLite de Desarrollo (Mínimo)
============================================
Solo los datos esenciales: Clientes, Puntos, Mediciones
"""

import os
import sqlite3

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
import django
django.setup()

from api.core.models import Client, CatchmentPoint, InteractionDetail

OUTPUT_PATH = '/tmp/dev_database.sqlite3'
RECORDS_PER_POINT = 100


def main():
    print("=" * 60)
    print("CREAR SQLite DE DESARROLLO")
    print("=" * 60)
    
    if os.path.exists(OUTPUT_PATH):
        os.remove(OUTPUT_PATH)
    
    conn = sqlite3.connect(OUTPUT_PATH)
    c = conn.cursor()
    
    # Tablas
    c.execute('CREATE TABLE core_client (id INTEGER PRIMARY KEY, name TEXT)')
    c.execute('CREATE TABLE core_catchmentpoint (id INTEGER PRIMARY KEY, title TEXT, frecuency INTEGER)')
    c.execute('''CREATE TABLE core_interactiondetail (
        id INTEGER PRIMARY KEY, catchment_point_id INTEGER, 
        pulses INTEGER, total INTEGER, total_diff INTEGER, total_today_diff INTEGER,
        flow REAL, nivel REAL, created TEXT
    )''')
    
    # Clientes
    print("Exportando clientes...")
    for obj in Client.objects.all():
        c.execute('INSERT INTO core_client VALUES (?, ?)', (obj.id, obj.name))
    print(f"  {Client.objects.count()} clientes")
    
    # Puntos
    print("Exportando puntos...")
    for obj in CatchmentPoint.objects.all():
        c.execute('INSERT INTO core_catchmentpoint VALUES (?, ?, ?)',
                  (obj.id, obj.title, obj.frecuency))
    print(f"  {CatchmentPoint.objects.count()} puntos")
    
    # Mediciones
    print(f"Exportando mediciones ({RECORDS_PER_POINT}/punto)...")
    total = 0
    for point in CatchmentPoint.objects.all():
        records = InteractionDetail.objects.filter(catchment_point_id=point.id).order_by('-created')[:RECORDS_PER_POINT]
        for r in records:
            c.execute('INSERT INTO core_interactiondetail VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                      (r.id, r.catchment_point_id, r.pulses, r.total, r.total_diff, r.total_today_diff,
                       float(r.flow) if r.flow else 0, float(r.nivel) if r.nivel else 0, str(r.created)))
            total += 1
    print(f"  {total} mediciones")
    
    conn.commit()
    conn.close()
    
    size_mb = os.path.getsize(OUTPUT_PATH) / (1024 * 1024)
    print(f"\n✅ {OUTPUT_PATH} ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
