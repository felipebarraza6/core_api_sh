"""
Comando de gestión para inicializar configuraciones del sistema.

Uso:
    python manage.py init_system_configs
"""

from django.core.management.base import BaseCommand
from api.core.services.config_service import ConfigService


class Command(BaseCommand):
    help = 'Inicializar configuraciones por defecto del sistema'

    def handle(self, *args, **options):
        self.stdout.write('Inicializando configuraciones del sistema...')

        results = ConfigService.initialize_defaults()

        created_count = sum(1 for v in results.values() if v)
        existing_count = len(results) - created_count

        self.stdout.write(
            self.style.SUCCESS(
                f'\n✅ Configuraciones inicializadas:\n'
                f'   - Creadas: {created_count}\n'
                f'   - Ya existían: {existing_count}\n'
                f'   - Total: {len(results)}'
            )
        )

        if created_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    '\n💡 Puedes revisar y ajustar estas configuraciones '
                    'en Django Admin > Configuraciones del Sistema'
                )
            )
