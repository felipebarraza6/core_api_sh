"""
Procesa la cola DGA para un punto específico con prioridad.

Uso:
    # Buscar por nombre (case-insensitive, contiene)
    python manage.py prioritize_dga_point --name "S3" --delay 0.5

    # Buscar por ID exacto
    python manage.py prioritize_dga_point --point-id 42 --delay 0.5

    # Solo ver estado sin enviar
    python manage.py prioritize_dga_point --name "S3" --dry-run
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from api.core.models import InteractionDetail, DgaDataConfigCatchment, CatchmentPoint
from api.cronjobs.dga.cron_dga import _validate_register, _get_dga_config, _prepare_response_data
from api.cronjobs.dga.send_data_dga import send
from api.cronjobs.utils.logging_config import dga_logger


class Command(BaseCommand):
    help = "Procesa registros pendientes DGA para un punto específico con prioridad"

    def add_arguments(self, parser):
        parser.add_argument(
            '--point-id',
            type=int,
            default=None,
            help='ID exacto del punto de captación',
        )
        parser.add_argument(
            '--name',
            type=str,
            default=None,
            help='Nombre/título del punto (búsqueda parcial, case-insensitive)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Máximo de registros a procesar (default: todos)',
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=0.5,
            help='Segundos de espera entre envíos (default: 0.5)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo muestra estado sin enviar',
        )

    def handle(self, *args, **options):
        point_id = options['point_id']
        name = options['name']
        limit = options['limit']
        delay = options['delay']
        dry_run = options['dry_run']

        if not point_id and not name:
            self.stdout.write(self.style.ERROR("Debes especificar --point-id o --name"))
            return

        # Buscar punto
        if point_id:
            try:
                punto = CatchmentPoint.objects.get(id=point_id)
            except CatchmentPoint.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"No existe punto con ID {point_id}"))
                return
        else:
            puntos = CatchmentPoint.objects.filter(title__icontains=name)
            if puntos.count() == 0:
                self.stdout.write(self.style.ERROR(f"No se encontró ningún punto con nombre que contenga '{name}'"))
                return
            elif puntos.count() > 1:
                self.stdout.write(self.style.WARNING(f"Se encontraron {puntos.count()} puntos con '{name}':"))
                for p in puntos:
                    self.stdout.write(f"  ID={p.id} | {p.title}")
                self.stdout.write(self.style.NOTICE("Usa --point-id para elegir uno específico"))
                return
            else:
                punto = puntos.first()

        self.stdout.write(self.style.NOTICE(
            f"Punto seleccionado: ID={punto.id} | '{punto.title}'"
        ))

        # Verificar configuración DGA
        dga_config = DgaDataConfigCatchment.objects.filter(point_catchment=punto).first()
        if not dga_config:
            self.stdout.write(self.style.ERROR(f"El punto {punto.id} NO tiene configuración DgaDataConfigCatchment"))
            return

        self.stdout.write(f"  Config DGA: type={dga_config.type_dga} | standard={dga_config.standard} | code_dga={dga_config.code_dga}")
        self.stdout.write(f"  send_dga={dga_config.send_dga} | rut_report={dga_config.rut_report_dga}")

        if not dga_config.send_dga:
            self.stdout.write(self.style.WARNING("¡ATENCIÓN! send_dga=False en la configuración del punto. No se enviará nada."))

        # Buscar registros pendientes
        qs = InteractionDetail.objects.filter(
            send_dga=True,
            catchment_point=punto
        ).order_by("date_time_medition")

        if limit:
            qs = qs[:limit]

        total = qs.count()
        self.stdout.write(self.style.NOTICE(f"\nRegistros pendientes para este punto: {total}"))

        if total == 0:
            # Revisar si hay errores
            errores = InteractionDetail.objects.filter(
                catchment_point=punto,
                is_error=True
            ).count()
            self.stdout.write(f"Registros con is_error=True: {errores}")
            return

        # Mostrar resumen de registros pendientes
        self.stdout.write("\nResumen de registros pendientes:")
        self.stdout.write("id | date_time_medition | pulses | total | total_diff | flow | water_table | is_error | dga_retry_count")
        for r in qs[:20]:
            self.stdout.write(
                f"{r.id} | {r.date_time_medition} | {r.pulses} | {r.total} | "
                f"{r.total_diff} | {r.flow} | {r.water_table} | {r.is_error} | {r.dga_retry_count}"
            )
        if total > 20:
            self.stdout.write(f"  ... y {total - 20} registros más")

        if dry_run:
            self.stdout.write(self.style.NOTICE("\nModo dry-run: no se enviará nada."))
            return

        # Procesar envíos
        self.stdout.write(self.style.NOTICE(f"\nIniciando envío de {total} registros (delay={delay}s)..."))
        success = 0
        error = 0
        duplicados = 0
        totalizador_cero = 0

        for register in qs.iterator() if not limit else qs:
            try:
                if not _validate_register(register):
                    error += 1
                    continue

                dga_cfg = _get_dga_config(register)
                if not dga_cfg:
                    error += 1
                    continue

                response_data = _prepare_response_data(register, dga_cfg)
                if not response_data:
                    error += 1
                    continue

                # Validar totalizador
                totalizador = response_data.get("total", "0")
                pulses = register.pulses
                if totalizador in (None, "", "0", "0.0") and pulses and int(pulses) > 0:
                    self.stdout.write(self.style.WARNING(
                        f"  [ADVERTENCIA] Registro {register.id}: totalizador='{totalizador}' pero pulses={pulses}. "
                        f"¿Está correcto?"
                    ))
                    totalizador_cero += 1

                self.stdout.write(
                    f"  Enviando {register.id}: fecha={response_data['date_time_medition']} "
                    f"totalizador={totalizador} caudal={response_data['flow']}"
                )

                resultado = send(response_data, delay_seconds=delay)

                if resultado:
                    success += 1
                else:
                    register.refresh_from_db()
                    if register.n_voucher and not register.send_dga:
                        duplicados += 1
                        success += 1
                    else:
                        error += 1

                if (success + error) % 50 == 0:
                    self.stdout.write(
                        f"  Progreso: {success + error}/{total} | OK={success} | Dup={duplicados} | Err={error}"
                    )

            except Exception as e:
                error += 1
                dga_logger.error(f"Error en priorización punto {punto.id} registro {register.id}: {e}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nFINALIZADO punto {punto.id} ({punto.title}): "
                f"{success + error + duplicados} procesados | {success} exitosos | "
                f"{duplicados} duplicados recuperados | {error} errores"
            )
        )
        if totalizador_cero > 0:
            self.stdout.write(self.style.WARNING(
                f"Se detectaron {totalizador_cero} registros con totalizador=0 pero pulses>0"
            ))
