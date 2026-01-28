"""
Management command para comparar datos entre cluster (fuente de verdad) y local.

Detecta discrepancias en configuraciones, especialmente tokens faltantes.
El cluster es la fuente correcta.

Uso:
    python manage.py compare_cluster_local
    python manage.py compare_cluster_local --point=173  # Solo un punto específico (ej: Coihues)
    python manage.py compare_cluster_local --sync       # Sincronizar desde cluster a local
"""

import os
import psycopg2
import psycopg2.extras
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Compara datos entre cluster (correcto) y local, detecta discrepancias'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sync',
            action='store_true',
            help='Sincronizar datos desde cluster a local',
        )
        parser.add_argument(
            '--point',
            type=int,
            help='Comparar solo un punto específico por ID',
        )
        parser.add_argument(
            '--table',
            type=str,
            choices=['ProfileDataConfigCatchment', 'DgaDataConfigCatchment', 'CatchmentPoint', 'all'],
            default='all',
            help='Tabla específica a comparar',
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

        # Validar que tenemos credenciales
        if not cluster_config["host"] or not cluster_config["password"]:
            raise Exception(
                "❌ Credenciales del cluster no configuradas. "
                "Verifica variables de entorno: CLUSTER_DB_HOST, CLUSTER_DB_PASSWORD"
            )

        return psycopg2.connect(**cluster_config)

    def compare_catchment_points(self, cluster_cursor, local_cursor, point_id=None):
        """Compara puntos de captación entre cluster y local."""
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write("COMPARANDO: CatchmentPoint")
        self.stdout.write('='*80)

        where_clause = f"WHERE id = {point_id}" if point_id else ""

        # Obtener datos del cluster (CORRECTO)
        cluster_cursor.execute(f"""
            SELECT id, title, project_id, owner_user_id, is_tdata, is_thethings, is_novus, frecuency
            FROM core_catchmentpoint
            {where_clause}
            ORDER BY id
        """)
        cluster_data = {row[0]: row for row in cluster_cursor.fetchall()}

        # Obtener datos del local
        local_cursor.execute(f"""
            SELECT id, title, project_id, owner_user_id, is_tdata, is_thethings, is_novus, frecuency
            FROM core_catchmentpoint
            {where_clause}
            ORDER BY id
        """)
        local_data = {row[0]: row for row in local_cursor.fetchall()}

        discrepancies = []

        # Comparar
        for point_id, cluster_row in cluster_data.items():
            if point_id not in local_data:
                self.stdout.write(self.style.ERROR(
                    f"❌ Punto ID:{point_id} ({cluster_row[1]}) existe en cluster pero NO en local"
                ))
                discrepancies.append(('missing', 'catchmentpoint', point_id, cluster_row))
            else:
                local_row = local_data[point_id]
                if cluster_row != local_row:
                    self.stdout.write(self.style.WARNING(
                        f"⚠️  Punto ID:{point_id} ({cluster_row[1]}) tiene datos diferentes:"
                    ))
                    # Mostrar diferencias campo por campo
                    fields = ['id', 'title', 'project_id', 'owner_user_id', 'is_tdata', 'is_thethings', 'is_novus', 'frecuency']
                    for i, field in enumerate(fields):
                        if cluster_row[i] != local_row[i]:
                            self.stdout.write(
                                f"   {field}: CLUSTER={cluster_row[i]} vs LOCAL={local_row[i]}"
                            )
                    discrepancies.append(('different', 'catchmentpoint', point_id, cluster_row, local_row))

        # Verificar puntos que están en local pero no en cluster
        for point_id in local_data:
            if point_id not in cluster_data:
                self.stdout.write(self.style.WARNING(
                    f"⚠️  Punto ID:{point_id} existe en local pero NO en cluster (podría ser nuevo)"
                ))

        if not discrepancies:
            self.stdout.write(self.style.SUCCESS("✅ Sin discrepancias en CatchmentPoint"))

        return discrepancies

    def compare_profile_data_config(self, cluster_cursor, local_cursor, point_id=None):
        """Compara ProfileDataConfigCatchment entre cluster y local."""
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write("COMPARANDO: ProfileDataConfigCatchment (TOKENS)")
        self.stdout.write('='*80)

        where_clause = f"WHERE point_catchment_id = {point_id}" if point_id else ""

        # Obtener datos del cluster (CORRECTO)
        cluster_cursor.execute(f"""
            SELECT id, point_catchment_id, token_service, is_telemetry, d1, d2, d3, d4, d5, d6, addition
            FROM core_profiledataconfigcatchment
            {where_clause}
            ORDER BY point_catchment_id
        """)
        cluster_data = {row[1]: row for row in cluster_cursor.fetchall()}  # key = point_catchment_id

        # Obtener datos del local
        local_cursor.execute(f"""
            SELECT id, point_catchment_id, token_service, is_telemetry, d1, d2, d3, d4, d5, d6, addition
            FROM core_profiledataconfigcatchment
            {where_clause}
            ORDER BY point_catchment_id
        """)
        local_data = {row[1]: row for row in local_cursor.fetchall()}

        discrepancies = []

        # Comparar
        for point_catchment_id, cluster_row in cluster_data.items():
            if point_catchment_id not in local_data:
                self.stdout.write(self.style.ERROR(
                    f"❌ Config para punto ID:{point_catchment_id} existe en cluster pero NO en local"
                ))
                discrepancies.append(('missing', 'profiledataconfig', point_catchment_id, cluster_row))
            else:
                local_row = local_data[point_catchment_id]

                # Verificar específicamente el token
                cluster_token = cluster_row[2]  # token_service
                local_token = local_row[2]

                if cluster_token != local_token:
                    token_status = ""
                    if not local_token or local_token.strip() == "":
                        token_status = " (LOCAL SIN TOKEN)"
                    elif not cluster_token or cluster_token.strip() == "":
                        token_status = " (CLUSTER SIN TOKEN)"
                    else:
                        token_status = " (TOKENS DIFERENTES)"

                    self.stdout.write(self.style.WARNING(
                        f"⚠️  Punto ID:{point_catchment_id}{token_status}"
                    ))
                    self.stdout.write(f"   CLUSTER token: '{cluster_token}'")
                    self.stdout.write(f"   LOCAL token:   '{local_token}'")
                    discrepancies.append(('token_diff', 'profiledataconfig', point_catchment_id, cluster_row, local_row))

                # Verificar otros campos importantes
                if cluster_row != local_row:
                    fields = ['id', 'point_catchment_id', 'token_service', 'is_telemetry', 'd1', 'd2', 'd3', 'd4', 'd5', 'd6', 'addition']
                    diffs = []
                    for i, field in enumerate(fields):
                        if cluster_row[i] != local_row[i] and field != 'token_service':  # Ya mostramos token
                            diffs.append(f"{field}: CLUSTER={cluster_row[i]} vs LOCAL={local_row[i]}")

                    if diffs:
                        self.stdout.write(self.style.WARNING(
                            f"   Otras diferencias en punto ID:{point_catchment_id}:"
                        ))
                        for diff in diffs:
                            self.stdout.write(f"      {diff}")

        # Verificar configs que están en local pero no en cluster
        for point_catchment_id in local_data:
            if point_catchment_id not in cluster_data:
                self.stdout.write(self.style.WARNING(
                    f"⚠️  Config para punto ID:{point_catchment_id} existe en local pero NO en cluster"
                ))

        if not discrepancies:
            self.stdout.write(self.style.SUCCESS("✅ Sin discrepancias en ProfileDataConfigCatchment"))

        return discrepancies

    def sync_from_cluster(self, discrepancies):
        """Sincroniza datos desde cluster a local."""
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write("SINCRONIZANDO DESDE CLUSTER A LOCAL")
        self.stdout.write('='*80)

        if not discrepancies:
            self.stdout.write(self.style.SUCCESS("✅ No hay discrepancias para sincronizar"))
            return

        self.stdout.write(f"\nSe encontraron {len(discrepancies)} discrepancias.")
        self.stdout.write("⚠️  Esto actualizará la base de datos local con datos del cluster.")

        # En Django management command, no podemos pedir input interactivo fácilmente
        # Así que simplemente procedemos si se pasó --sync

        self.stdout.write("\n🔄 Sincronizando...")

        with connection.cursor() as cursor:
            synced = 0
            for disc in discrepancies:
                disc_type = disc[0]
                table = disc[1]

                if table == 'profiledataconfig' and disc_type == 'token_diff':
                    point_id = disc[2]
                    cluster_row = disc[3]

                    # Actualizar token en local
                    cursor.execute("""
                        UPDATE core_profiledataconfigcatchment
                        SET token_service = %s
                        WHERE point_catchment_id = %s
                    """, (cluster_row[2], point_id))

                    self.stdout.write(f"✅ Punto ID:{point_id} - Token actualizado")
                    synced += 1

        self.stdout.write(f"\n✅ Sincronización completada: {synced} registros actualizados")

    def handle(self, *args, **options):
        """Ejecuta el comando."""
        self.stdout.write("\n" + "="*80)
        self.stdout.write("COMPARACIÓN CLUSTER (CORRECTO) vs LOCAL")
        self.stdout.write("="*80)

        try:
            # Conectar a cluster
            self.stdout.write("\n🔗 Conectando al cluster...")
            cluster_conn = self.get_cluster_connection()
            cluster_cursor = cluster_conn.cursor()
            self.stdout.write(self.style.SUCCESS("✅ Conectado al cluster"))

            # Conectar a local
            local_cursor = connection.cursor()

            point_id = options.get('point')
            table = options.get('table')

            all_discrepancies = []

            # Comparar tablas
            if table == 'all' or table == 'ProfileDataConfigCatchment':
                disc = self.compare_profile_data_config(cluster_cursor, local_cursor, point_id)
                all_discrepancies.extend(disc)

            if table == 'all' or table == 'CatchmentPoint':
                disc = self.compare_catchment_points(cluster_cursor, local_cursor, point_id)
                all_discrepancies.extend(disc)

            # Resumen
            self.stdout.write(f"\n{'='*80}")
            self.stdout.write("RESUMEN")
            self.stdout.write('='*80)
            self.stdout.write(f"Total discrepancias encontradas: {len(all_discrepancies)}")

            # Sincronizar si se solicitó
            if options['sync']:
                self.sync_from_cluster(all_discrepancies)
            elif all_discrepancies:
                self.stdout.write(self.style.WARNING(
                    "\n⚠️  Para sincronizar desde cluster a local, ejecuta:"
                ))
                self.stdout.write("   python manage.py compare_cluster_local --sync")

            # Cerrar conexiones
            cluster_cursor.close()
            cluster_conn.close()

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Error: {e}"))
            import traceback
            traceback.print_exc()

        self.stdout.write(f"\n{'='*80}")
        self.stdout.write("Comparación finalizada")
        self.stdout.write('='*80 + "\n")
