"""
Management command para analizar cálculo de caudales DGA.

Uso:
    python manage.py analyze_caudal_dga --standard MEDIO
    python manage.py analyze_caudal_dga --register-id 123
    python manage.py analyze_caudal_dga --compare 123
"""
from django.core.management.base import BaseCommand
from api.cronjobs.dga.analysis.caudal_analysis import (
    analyze_current_caudal_calculation,
    analyze_medio_standard_requirements,
    compare_calculation_methods
)
import json


class Command(BaseCommand):
    help = 'Analiza cálculo de caudales para DGA (solo lectura, no modifica datos)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--standard',
            type=str,
            help='Analizar requisitos para un estándar específico (MEDIO, MAYOR, etc.)'
        )
        parser.add_argument(
            '--register-id',
            type=int,
            help='Analizar cálculo actual para un registro específico'
        )
        parser.add_argument(
            '--compare',
            type=int,
            help='Comparar cálculo actual vs requerido para un registro (solo MEDIO)'
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Archivo JSON para guardar resultados'
        )

    def handle(self, *args, **options):
        output_file = options.get('output')
        results = {}

        if options.get('standard'):
            standard = options['standard'].upper()
            self.stdout.write(f'Analizando requisitos para estándar {standard}...')
            
            if standard == 'MEDIO':
                results['medio_analysis'] = analyze_medio_standard_requirements()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ Analizados {len(results["medio_analysis"]["points_analyzed"])} puntos'
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Análisis para estándar {standard} aún no implementado')
                )

        if options.get('register_id'):
            register_id = options['register_id']
            self.stdout.write(f'Analizando registro {register_id}...')
            results['register_analysis'] = analyze_current_caudal_calculation(register_id)
            self.stdout.write(self.style.SUCCESS('✓ Análisis completado'))

        if options.get('compare'):
            register_id = options['compare']
            self.stdout.write(f'Comparando métodos para registro {register_id}...')
            results['comparison'] = compare_calculation_methods(register_id)
            if 'error' in results['comparison']:
                self.stdout.write(
                    self.style.ERROR(f'✗ {results["comparison"]["error"]}')
                )
            else:
                self.stdout.write(self.style.SUCCESS('✓ Comparación completada'))
                self.stdout.write(
                    f'  Diferencia: {results["comparison"]["difference"]:.2f} L/s '
                    f'({results["comparison"]["difference_percent"]:.1f}%)'
                )

        if not any([options.get('standard'), options.get('register_id'), options.get('compare')]):
            self.stdout.write(
                self.style.ERROR('Debe especificar --standard, --register-id o --compare')
            )
            return

        # Guardar resultados si se especificó archivo
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False, default=str)
            self.stdout.write(self.style.SUCCESS(f'✓ Resultados guardados en {output_file}'))
        else:
            # Mostrar resultados en consola
            self.stdout.write('\n' + '='*50)
            self.stdout.write('RESULTADOS:')
            self.stdout.write('='*50)
            self.stdout.write(json.dumps(results, indent=2, ensure_ascii=False, default=str))

