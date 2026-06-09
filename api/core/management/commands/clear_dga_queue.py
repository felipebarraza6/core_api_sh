"""
Limpieza masiva de cola DGA.

Procesa registros pendientes en la cola DGA, enviándolos con delay configurable.
Si la DGA responde que ya existe (duplicado), recupera el comprobante y lo marca como enviado.

Uso:
    python manage.py clear_dga_queue --limit 100 --delay 0.5
    python manage.py clear_dga_queue --delay 0.5
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from api.core.models import InteractionDetail, DgaDataConfigCatchment
from api.cronjobs.dga.cron_dga import _validate_register, _get_dga_config, _prepare_response_data
from api.cronjobs.dga.send_data_dga import send
from api.cronjobs.utils.logging_config import dga_logger


class Command(BaseCommand):
    help = "Procesa registros pendientes de la cola DGA masivamente"

    def add_arguments(self, parser):
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
            '--recientes',
            action='store_true',
            help='Procesar solo registros de últimas 24h (prioridad)',
        )
        parser.add_argument(
            '--backlog',
            action='store_true',
            help='Procesar solo backlog (>24h)',
        )

    def handle(self, *args, **options):
        limit = options['limit']
        delay = options['delay']
        solo_recientes = options['recientes']
        solo_backlog = options['backlog']

        puntos_con_dga_activo = DgaDataConfigCatchment.objects.filter(
            send_dga=True
        ).values_list('point_catchment_id', flat=True)

        qs = InteractionDetail.objects.filter(
            send_dga=True,
            catchment_point_id__in=puntos_con_dga_activo
        ).exclude(catchment_point=1)

        if solo_recientes:
            limite = timezone.now() - timedelta(hours=24)
            qs = qs.filter(date_time_medition__gte=limite)
            self.stdout.write(self.style.NOTICE("Modo: solo recientes (ultimas 24h)"))
        elif solo_backlog:
            limite = timezone.now() - timedelta(hours=24)
            qs = qs.filter(date_time_medition__lt=limite)
            self.stdout.write(self.style.NOTICE("Modo: solo backlog (>24h)"))

        total = qs.count()
        if limit:
            qs = qs.order_by("date_time_medition")[:limit]
            self.stdout.write(self.style.NOTICE(f"Procesando {limit} de {total} registros en cola (delay={delay}s)..."))
        else:
            qs = qs.order_by("date_time_medition")
            self.stdout.write(self.style.NOTICE(f"Procesando {total} registros en cola (delay={delay}s)..."))

        success = 0
        error = 0
        duplicados = 0
        procesados = 0

        for register in qs.iterator():
            procesados += 1
            try:
                if not _validate_register(register):
                    error += 1
                    continue

                dga_config = _get_dga_config(register)
                if not dga_config:
                    error += 1
                    continue

                response_data = _prepare_response_data(register, dga_config)
                if not response_data:
                    error += 1
                    continue

                resultado = send(response_data, delay_seconds=delay)

                if resultado:
                    success += 1
                else:
                    # Revisar si fue marcado como duplicado (send retorna True para duplicados)
                    # o si quedó con error
                    register.refresh_from_db()
                    if register.n_voucher and not register.send_dga:
                        duplicados += 1
                        success += 1  # Considerado exitoso
                    elif register.is_error:
                        error += 1
                    else:
                        error += 1

                if procesados % 50 == 0:
                    self.stdout.write(
                        f"  Procesados: {procesados} | Exitosos: {success} | Duplicados: {duplicados} | Errores: {error}"
                    )

            except Exception as e:
                error += 1
                dga_logger.error(f"Error en limpieza masiva registro {register.id}: {e}")

        self.stdout.write(
            self.style.SUCCESS(
                f"FINALIZADO: {procesados} procesados | {success} exitosos | {duplicados} duplicados recuperados | {error} errores"
            )
        )
