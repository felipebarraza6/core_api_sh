import os
import sqlite3
import sys

import django

# Configurar entorno Django
sys.path.append(os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
os.environ["LOCAL_DB_NAME"] = "smarthydro_dev"
os.environ["POSTGRES_USER"] = "smarthydro_dev_user"
os.environ["POSTGRES_PASSWORD"] = "dev_password_123"

django.setup()

from django.db import transaction

from api.core.models import (
    CatchmentPoint,
    Client,
    ProfileDataConfigCatchment,
    ProjectCatchments,
    User,
)

# Ruta a la base de datos legacy
SQLITE_DB_PATH = "dev_database.sqlite3"


def migrate_legacy_data():
    if not os.path.exists(SQLITE_DB_PATH):
        print(f"❌ Error: No se encuentra {SQLITE_DB_PATH}")
        return

    print(f"🔄 Iniciando migración desde {SQLITE_DB_PATH}...")

    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        with transaction.atomic():
            # 1. Migrar Clientes
            print("\n📦 Migrando Clientes...")
            cursor.execute("SELECT * FROM core_client")
            clients = cursor.fetchall()

            client_map = {}  # Map legacy_id -> new_instance

            for row in clients:
                # La tabla legacy solo tiene 'id' y 'name'
                # Generamos RUT dummy si no existe
                rut_val = f"LEGACY-{row['id']}"

                client, created = Client.objects.update_or_create(
                    rut=rut_val,
                    defaults={
                        "name": row["name"],
                        "address": "Dirección Migrada",
                        "phone": "",
                        "email": "",
                    },
                )
                client_map[row["id"]] = client
                status = "✅ Creado" if created else "♻️ Actualizado"
                print(f"   - {status}: {client.name} (ID Original: {row['id']})")

            # 2. Migrar Puntos de Captación
            print("\n📦 Migrando Puntos de Captación...")
            cursor.execute("SELECT * FROM core_catchmentpoint")
            points = cursor.fetchall()

            # Usuario por defecto (admin) para asignar puntos huérfanos
            default_user = User.objects.get(username="admin")

            # Crear un proyecto genérico por defecto si no existe
            default_project, _ = ProjectCatchments.objects.get_or_create(
                name="Proyecto Migración Legacy", defaults={"client": None}
            )

            for row in points:
                # La tabla legacy solo tiene id, title, frecuency
                # Asumimos valores por defecto para lo demás
                legacy_title = row["title"] if row["title"] else ""
                clean_title = legacy_title if legacy_title else "Sin título"

                # Revisión idempotente: si ya migramos este ID legacy, reutilizamos el punto
                existing_profile = ProfileDataConfigCatchment.objects.filter(
                    extra_config__legacy_id=row["id"]
                ).first()

                if existing_profile and existing_profile.point_catchment:
                    point = existing_profile.point_catchment
                    created = False
                    # Actualizamos campos básicos si aplica
                    point.title = clean_title
                    point.lat = point.lat or "-33.0"
                    point.lon = point.lon or "-70.0"
                    point.frecuency = (
                        str(row["frecuency"])
                        if row["frecuency"]
                        else (point.frecuency or "60")
                    )
                    point.project = point.project or default_project
                    point.owner_user = point.owner_user or default_user
                    point.save()
                else:
                    point = CatchmentPoint.objects.create(
                        title=clean_title,
                        lat="-33.0",
                        lon="-70.0",
                        frecuency=str(row["frecuency"]) if row["frecuency"] else "60",
                        project=default_project,
                        owner_user=default_user,
                    )
                    created = True

                # Crear perfil de configuración básico si no existe
                profile, _ = ProfileDataConfigCatchment.objects.get_or_create(
                    point_catchment=point
                )
                extra = profile.extra_config or {}
                extra["legacy_id"] = row["id"]
                profile.extra_config = extra
                profile.save()

                status = "✅ Creado" if created else "♻️ Actualizado"
                print(f"   - {status}: {point.title}")

            print("\n✨ Migración completada exitosamente.")
            print(f"   - Total Clientes procesados: {len(clients)}")
            print(f"   - Total Puntos procesados: {len(points)}")

    except Exception as e:
        print(f"\n❌ Error crítico durante la migración: {e}")
        import traceback

        traceback.print_exc()
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_legacy_data()
