"""
Deduplicación local de cola DGA sin consultar API externa.

Para cada punto+hora en cola, si existe al menos un registro con voucher,
marca todos los demás como enviados copiando el comprobante.

Uso:
    python manage.py deduplicate_dga_queue
"""

from django.core.management.base import BaseCommand
from django.db.models import Count

from api.core.models import InteractionDetail


class Command(BaseCommand):
    help = "Deduplica la cola DGA localmente copiando vouchers entre registros del mismo punto+hora"

    def handle(self, *args, **options):
        cola = InteractionDetail.objects.filter(send_dga=True)
        total_inicial = cola.count()

        self.stdout.write(self.style.NOTICE(f"Registros en cola inicial: {total_inicial}"))

        # Paso 1: obtener combinaciones punto+hora en cola con mas de 1 registro
        combos = (
            cola.values("catchment_point_id", "date_time_medition")
            .annotate(total=Count("id"))
            .filter(total__gt=1)
            .order_by("catchment_point_id", "date_time_medition")
        )

        limpiados = 0
        grupos_procesados = 0

        for combo in combos.iterator():
            pid = combo["catchment_point_id"]
            dt = combo["date_time_medition"]

            # Buscar voucher existente para este punto+hora (cualquier registro, no solo en cola)
            referencia = InteractionDetail.objects.filter(
                catchment_point_id=pid,
                date_time_medition=dt,
                n_voucher__isnull=False,
            ).exclude(n_voucher="").first()

            if not referencia:
                continue  # No hay voucher de referencia

            # Marcar todos los de la cola del mismo punto+hora como enviados
            updated = InteractionDetail.objects.filter(
                catchment_point_id=pid,
                date_time_medition=dt,
                send_dga=True,
            ).update(
                send_dga=False,
                n_voucher=referencia.n_voucher,
                return_dga="Deduplicado localmente",
            )

            if updated > 0:
                limpiados += updated
                grupos_procesados += 1

            if grupos_procesados % 500 == 0:
                self.stdout.write(
                    f"  Grupos: {grupos_procesados} | Registros limpiados: {limpiados}"
                )

        total_final = InteractionDetail.objects.filter(send_dga=True).count()

        self.stdout.write(
            self.style.SUCCESS(
                f"FINALIZADO: {grupos_procesados} grupos deduplicados | "
                f"{limpiados} registros limpiados | "
                f"Cola: {total_inicial} → {total_final}"
            )
        )
