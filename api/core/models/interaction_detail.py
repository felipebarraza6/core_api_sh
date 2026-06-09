"""InteractionDetail model."""

from django.db import models

from .catchment_points import CatchmentPoint, NotificationsCatchment
from .fields import AwareDateTimeField
from .utils import ModelApi


class InteractionDetail(ModelApi):
    """Interacción de detalle de la telemetria"""

    catchment_point = models.ForeignKey(
        CatchmentPoint, on_delete=models.CASCADE, verbose_name="Punto de captacion"
    )
    date_time_medition = AwareDateTimeField(
        max_length=800, blank=True, null=True, verbose_name="Fecha/hora medición"
    )
    date_time_last_logger = AwareDateTimeField(
        max_length=800, blank=True, null=True, verbose_name="Fecha/hora logger"
    )
    days_not_conection = models.IntegerField(
        default=0, verbose_name="Dias sin conexión"
    )
    is_partial = models.BooleanField(
        default=False, verbose_name="Desconexión parcial",
        help_text="True si hay variables fallando pero otras funcionando"
    )
    variable_details = models.JSONField(
        blank=True, null=True, verbose_name="Detalle de variables",
        help_text="JSON con el estado individual de cada variable"
    )

    # Almacenamiento flexible por variable (esquema dinámico)
    variable_values = models.JSONField(
        blank=True, null=True, default=dict,
        verbose_name="Valores por variable",
        help_text="JSON con los valores crudos de cada variable: {variable_id: valor}. Permite esquemas dinámicos sin alterar la BD."
    )

    # Caudal

    flow = models.DecimalField(
        default=0.0, verbose_name="Caudal(lt)", max_digits=10, decimal_places=2
    )

    # Totalizado
    pulses = models.IntegerField(default=0, verbose_name="Pulsos")
    total = models.CharField(
        max_length=400, blank=True, null=True, verbose_name="Total(m3)"
    )
    total_diff = models.IntegerField(default=0, verbose_name="Consumo(m3/h)")

    total_today_diff = models.IntegerField(default=0, verbose_name="Consumo hoy(m3)")

    # Nivel
    nivel = models.DecimalField(
        default=0.0, verbose_name="Nivel(mt)", max_digits=10, decimal_places=2
    )
    water_table = models.DecimalField(
        default=0.0, verbose_name="Nivel freático(mt)", max_digits=10, decimal_places=2
    )

    send_dga = models.BooleanField(default=False, verbose_name="Agregar a la cola DGA", db_index=True)

    return_dga = models.TextField(max_length=3000, blank=True, null=True)

    n_voucher = models.TextField(max_length=3000, blank=True, null=True)
    is_error = models.BooleanField(default=False, verbose_name="Error", db_index=True)

    # Retry persistente DGA (P1.6)
    dga_retry_count = models.IntegerField(
        default=0, verbose_name="Reintentos DGA persistentes",
        help_text="Contador de ciclos de reintento persistente (fuera del loop de 3 intentos inmediatos).",
    )
    dga_last_retry_at = models.DateTimeField(
        blank=True, null=True, verbose_name="Último reintento DGA",
        help_text="Timestamp del último ciclo de reintento persistente.",
    )

    notification = models.ForeignKey(
        NotificationsCatchment,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        verbose_name="Notificación",
    )

    class Meta:
        """Meta options."""

        verbose_name = "Telemetria"
        verbose_name_plural = "Registros Telemetria"
        
        indexes = [
            models.Index(fields=['catchment_point', 'date_time_medition']),
            models.Index(fields=['date_time_medition']),
            models.Index(fields=['send_dga', 'catchment_point', 'date_time_medition']),
            models.Index(fields=['is_error']),
            models.Index(fields=['send_dga', 'is_error', 'date_time_medition'], name='core_interact_dga_err_dt'),
        ]
        unique_together = ("catchment_point", "date_time_medition")

    def save(self, *args, **kwargs):
        from django.utils import timezone
        from datetime import datetime

        for field_name in ("date_time_medition", "date_time_last_logger"):
            value = getattr(self, field_name, None)
            if isinstance(value, datetime) and timezone.is_naive(value):
                setattr(self, field_name, timezone.make_aware(value))

        super().save(*args, **kwargs)

    def __str__(self):
        return str(self.catchment_point)
