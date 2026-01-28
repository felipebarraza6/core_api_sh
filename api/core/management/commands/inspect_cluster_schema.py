"""
Management command para inspeccionar el esquema del cluster vs local.

Muestra qué columnas existen en cada tabla en ambas bases de datos.

Uso:
    python manage.py inspect_cluster_schema
    python manage.py inspect_cluster_schema --table=core_profiledataconfigcatchment
"""

import os
import psycopg2
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Inspecciona esquema de tablas en cluster vs local'

    def add_arguments(self, parser):
        parser.add_argument(
            '--table',
            type=str,
            help='Tabla específica a inspeccionar',
        )

    def get_cluster_connection(self):
        """Obtiene conexión al cluster."""
        cluster_config = {
            "host": os.environ.get("CLUSTER_DB_HOST"),
            "port": os.environ.get("CLUSTER_DB_PORT", "25060"),
            "user": os.environ.get("CLUSTER_DB_USER", "api_principal"),
            "password": os.environ.get("CLUSTER_DB_PASSWORD", ""),
            "database": os.environ.get("CLUSTER_DB_NAME", "telemetry_api"),
            "sslmode": os.environ.get("CLUSTER_DB_SSLMODE", "require"),
        }

        if not cluster_config["host"] or not cluster_config["password"]:
            raise Exception("❌ Credenciales del cluster no configuradas")

        return psycopg2.connect(**cluster_config)

    def get_table_schema(self, cursor, table_name):
        """Obtiene el esquema de una tabla."""
        cursor.execute("""
            SELECT column_name, data_type, character_maximum_length, is_nullable
            FROM information_schema.columns
            WHERE table_name = %s AND table_schema = 'public'
            ORDER BY ordinal_position
        """, (table_name,))

        return cursor.fetchall()

    def get_row_count(self, cursor, table_name):
        """Obtiene el conteo de filas de una tabla."""
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            return cursor.fetchone()[0]
        except:
            return "N/A"

    def inspect_table(self, cluster_cursor, local_cursor, table_name):
        """Inspecciona una tabla específica."""
        self.stdout.write(f"\n{'='*100}")
        self.stdout.write(f"TABLA: {table_name}")
        self.stdout.write('='*100)

        # Obtener esquemas
        cluster_schema = self.get_table_schema(cluster_cursor, table_name)
        local_schema = self.get_table_schema(local_cursor, table_name)

        # Obtener conteos
        cluster_count = self.get_row_count(cluster_cursor, table_name)
        local_count = self.get_row_count(local_cursor, table_name)

        if not cluster_schema and not local_schema:
            self.stdout.write(self.style.WARNING(
                f"⚠️  Tabla '{table_name}' no existe ni en cluster ni en local"
            ))
            return

        if not cluster_schema:
            self.stdout.write(self.style.WARNING(
                f"⚠️  Tabla '{table_name}' NO existe en CLUSTER (pero sí en local)"
            ))

        if not local_schema:
            self.stdout.write(self.style.WARNING(
                f"⚠️  Tabla '{table_name}' NO existe en LOCAL (pero sí en cluster)"
            ))

        # Mostrar conteos
        self.stdout.write(f"\n📊 Conteo de registros:")
        self.stdout.write(f"   CLUSTER: {cluster_count:,}")
        self.stdout.write(f"   LOCAL:   {local_count:,}")

        if cluster_count != local_count:
            diff = abs(cluster_count - local_count)
            self.stdout.write(self.style.WARNING(
                f"   ⚠️  Diferencia: {diff:,} registros"
            ))

        # Convertir a diccionarios para comparar
        cluster_cols = {col[0]: col for col in cluster_schema}
        local_cols = {col[0]: col for col in local_schema}

        # Columnas en ambos
        common_cols = set(cluster_cols.keys()) & set(local_cols.keys())

        # Columnas solo en cluster
        cluster_only = set(cluster_cols.keys()) - set(local_cols.keys())

        # Columnas solo en local
        local_only = set(local_cols.keys()) - set(cluster_cols.keys())

        # Mostrar columnas comunes
        if common_cols:
            self.stdout.write(f"\n✅ Columnas en ambos ({len(common_cols)}):")
            for col_name in sorted(common_cols):
                cluster_col = cluster_cols[col_name]
                local_col = local_cols[col_name]

                if cluster_col[1] != local_col[1]:  # data_type diferente
                    self.stdout.write(self.style.WARNING(
                        f"   ⚠️  {col_name}: CLUSTER={cluster_col[1]} vs LOCAL={local_col[1]}"
                    ))
                else:
                    self.stdout.write(f"   {col_name}: {cluster_col[1]}")

        # Mostrar columnas solo en cluster
        if cluster_only:
            self.stdout.write(self.style.ERROR(
                f"\n❌ Columnas SOLO en CLUSTER ({len(cluster_only)}):"
            ))
            for col_name in sorted(cluster_only):
                col = cluster_cols[col_name]
                self.stdout.write(f"   {col_name}: {col[1]}")

        # Mostrar columnas solo en local
        if local_only:
            self.stdout.write(self.style.WARNING(
                f"\n⚠️  Columnas SOLO en LOCAL ({len(local_only)}):"
            ))
            for col_name in sorted(local_only):
                col = local_cols[col_name]
                self.stdout.write(f"   {col_name}: {col[1]}")

    def handle(self, *args, **options):
        """Ejecuta el comando."""
        self.stdout.write("\n" + "="*100)
        self.stdout.write("INSPECCIÓN DE ESQUEMA: CLUSTER vs LOCAL")
        self.stdout.write("="*100)

        try:
            # Conectar a cluster
            self.stdout.write("\n🔗 Conectando al cluster...")
            cluster_conn = self.get_cluster_connection()
            cluster_cursor = cluster_conn.cursor()
            self.stdout.write(self.style.SUCCESS("✅ Conectado al cluster"))

            # Conectar a local
            local_cursor = connection.cursor()

            # Tablas a inspeccionar
            tables = [
                'core_catchmentpoint',
                'core_profiledataconfigcatchment',
                'core_dgadataconfigcatchment',
                'core_profileikolucatchment',
            ]

            specific_table = options.get('table')
            if specific_table:
                tables = [specific_table]

            # Inspeccionar cada tabla
            for table in tables:
                self.inspect_table(cluster_cursor, local_cursor, table)

            # Cerrar conexiones
            cluster_cursor.close()
            cluster_conn.close()

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Error: {e}"))
            import traceback
            traceback.print_exc()

        self.stdout.write(f"\n{'='*100}")
        self.stdout.write("Inspección finalizada")
        self.stdout.write('='*100 + "\n")
