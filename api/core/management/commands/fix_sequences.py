"""
Management command para reparar secuencias de PostgreSQL.

Cuando las secuencias de auto-incremento están desincronizadas, Django intenta
crear registros con IDs que ya existen, causando errores de IntegrityError.

Este comando resetea las secuencias a los valores correctos.

Uso:
    python manage.py fix_sequences
    python manage.py fix_sequences --models ProfileDataConfigCatchment,DgaDataConfigCatchment
"""

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Repara secuencias de auto-incremento de PostgreSQL'

    def add_arguments(self, parser):
        parser.add_argument(
            '--models',
            type=str,
            help='Modelos específicos a arreglar (separados por coma)',
        )

    def reset_sequence(self, table_name, id_column='id'):
        """Resetea la secuencia de una tabla."""
        with connection.cursor() as cursor:
            # Obtener el máximo ID actual
            cursor.execute(f"SELECT MAX({id_column}) FROM {table_name}")
            result = cursor.fetchone()
            max_id = result[0] if result else None

            if max_id is None:
                max_id = 0

            # Obtener el nombre de la secuencia
            sequence_name = f"{table_name}_{id_column}_seq"

            # Resetear la secuencia
            cursor.execute(f"SELECT setval('{sequence_name}', {max_id + 1}, false)")

            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ {table_name}: secuencia reseteada a {max_id + 1}"
                )
            )

    def handle(self, *args, **options):
        """Ejecuta el comando."""
        self.stdout.write("\n" + "="*80)
        self.stdout.write("REPARACIÓN DE SECUENCIAS DE POSTGRESQL")
        self.stdout.write("="*80)

        # Definir tablas a reparar
        tables_to_fix = [
            'core_profiledataconfigcatchment',
            'core_dgadataconfigcatchment',
            'core_profileikolucatchment',
            'core_catchmentpoint',
            'core_interactiondetail',
            'core_notificationscatchment',
        ]

        # Si se especificaron modelos específicos
        if options['models']:
            model_map = {
                'ProfileDataConfigCatchment': 'core_profiledataconfigcatchment',
                'DgaDataConfigCatchment': 'core_dgadataconfigcatchment',
                'ProfileIkoluCatchment': 'core_profileikolucatchment',
                'CatchmentPoint': 'core_catchmentpoint',
                'InteractionDetail': 'core_interactiondetail',
            }

            specified_models = [m.strip() for m in options['models'].split(',')]
            tables_to_fix = [model_map[m] for m in specified_models if m in model_map]

        self.stdout.write(f"\n🔧 Reparando {len(tables_to_fix)} tablas...")

        for table in tables_to_fix:
            try:
                self.reset_sequence(table)
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ Error en {table}: {e}")
                )

        self.stdout.write("\n" + "="*80)
        self.stdout.write(self.style.SUCCESS("✅ Reparación de secuencias completada"))
        self.stdout.write("="*80 + "\n")
