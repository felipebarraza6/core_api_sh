"""Catchment Points and Profiles."""

from django.db import models

from api.core.models.users import User
from api.core.models.utils import ModelApi

# Import moved models
from api.crm.models import Project


class CatchmentPoint(ModelApi):
    """Catchment points model."""

    project = models.ForeignKey(
        Project,
        related_name="catchment_points",
        on_delete=models.CASCADE,
        verbose_name="Proyecto",
    )
    title = models.CharField(
        max_length=200, blank=True, null=True, verbose_name="Nombre"
    )

    owner_user = models.ForeignKey(
        User,
        related_name="owned_catchment_points",
        on_delete=models.CASCADE,
        verbose_name="Propietario",
    )
    users_viewers = models.ManyToManyField(
        User, verbose_name="usuario", related_name="viewed_catchment_points", blank=True
    )

    lat = models.CharField(
        max_length=300, blank=True, null=True, verbose_name="latitud"
    )

    lon = models.CharField(
        max_length=300, blank=True, null=True, verbose_name="longitud"
    )

    # [DEPRECATED] Use SamplingFrequency model instead.
    # Keep choices for backward compatibility until migration is complete.
    FRECUENCY_OPTIONS = [
        ("1", "1 minuto"),
        ("5", "5 minutos"),
        ("10", "10 minutos"),
        ("60", "60 minutos"),
    ]

    # [DEPRECATED] Use ForeignKey 'frequency' field instead.
    frecuency = models.CharField(
        blank=True,
        null=True,
        max_length=300,
        choices=FRECUENCY_OPTIONS,
        verbose_name="Frecuencia (Legacy)",
        default="60",
        help_text="[DEP] Use el campo 'frequency' (FK) en su lugar."
    )

    processing_scheme = models.ForeignKey(
        "telemetry.TelemetryScheme",
        related_name="catchment_points",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name="Esquema de Telemetría",
        help_text="Esquema reutilizable de procesamiento para este punto.",
    )

    # Nuevos campos dinámicos
    configuration_scheme = models.ForeignKey(
        "telemetry.ConfigurationScheme",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="points",
        verbose_name="Esquema de Configuración",
        help_text="Plantilla de configuración para este punto (pozo, sensor, etc.)"
    )

    frequency = models.ForeignKey(
        "telemetry.SamplingFrequency",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="points",
        verbose_name="Frecuencia de Muestreo",
        help_text="Frecuencia dinámica de muestreo"
    )

    class Meta:
        """Meta data catchment points"""

        db_table = "core_catchmentpoint"
        verbose_name = "Punto de captacion"
        verbose_name_plural = "Puntos de captacion"

    def __str__(self):
        return f"{self.title} - {self.owner_user}"

    def get_config_dict(self) -> dict:
        """
        Obtiene todas las configuraciones del punto como diccionario para fórmulas.
        
        Returns:
            Dict con formato {field_code: value}
        """
        return {
            cv.field.code: cv.value
            for cv in self.configuration_values.select_related('field')
        }


class ProfileIkoluCatchment(ModelApi):
    """Ikolu Status Profile."""

    point_catchment = models.ForeignKey(
        CatchmentPoint,
        related_name="ikolu_profiles",
        on_delete=models.CASCADE,
        verbose_name="Punto de captacion",
    )
    entry_by_form = models.BooleanField(
        default=False, verbose_name="Ingreso por formulario"
    )
    m1 = models.BooleanField(default=True, verbose_name="MODULO: Mi Pozo")

    m2 = models.BooleanField(default=False, verbose_name="MODULO: DGA")

    SUBSCRIPTIONS_CHOICES = [
        ("MENSUAL", "mensual"),
        ("TRIMESTRAL", "trimestral"),
        ("SEMESTRAL", "semestral"),
        ("ANUAL", "anual"),
    ]

    m3 = models.BooleanField(default=False, verbose_name="MODULO: Datos y reportes")
    m3_start_subscription = models.DateField(
        blank=True,
        null=True,
        verbose_name="Fecha inicio suscripción MODULO: Datos y reportes",
    )
    m3_type_subscriptions = models.CharField(
        max_length=300,
        blank=True,
        null=True,
        choices=SUBSCRIPTIONS_CHOICES,
        verbose_name="Tipo de suscripción MODULO: Datos y reportes",
    )

    m4 = models.BooleanField(default=False, verbose_name="MODULO: Graficos")
    m4_start_subscription = models.DateField(
        blank=True, null=True, verbose_name="Fecha inicio suscripción MODULO: Graficos"
    )
    m4_type_subscriptions = models.CharField(
        max_length=300,
        blank=True,
        null=True,
        choices=SUBSCRIPTIONS_CHOICES,
        verbose_name="Tipo de suscripción MODULO: Graficos",
    )

    m5 = models.BooleanField(default=False, verbose_name="MODULO: Indicadores")
    m5_start_subscription = models.DateField(
        blank=True,
        null=True,
        verbose_name="Fecha inicio suscripción MODULO: Indicadores",
    )
    m5_type_subscriptions = models.CharField(
        max_length=300,
        blank=True,
        null=True,
        choices=SUBSCRIPTIONS_CHOICES,
        verbose_name="Tipo de suscripción MODULO: Indicadores",
    )

    m6 = models.BooleanField(default=False, verbose_name="MODULO: Alarmas")
    m6_start_subscription = models.DateField(
        blank=True, null=True, verbose_name="Fecha inicio suscripción MODULO: Alarmas"
    )
    m6_type_subscriptions = models.CharField(
        max_length=300,
        blank=True,
        null=True,
        choices=SUBSCRIPTIONS_CHOICES,
        verbose_name="Tipo de suscripción MODULO: Alarmas",
    )

    m7 = models.BooleanField(default=False, verbose_name="MODULO: Documentos")
    m7_start_subscription = models.DateField(
        blank=True,
        null=True,
        verbose_name="Fecha inicio suscripción MODULO: Documentos",
    )
    m7_type_subscriptions = models.CharField(
        max_length=300,
        blank=True,
        null=True,
        choices=SUBSCRIPTIONS_CHOICES,
        verbose_name="Tipo de suscripción MODULO: Documentos",
    )

    class Meta:
        """Meta data profile ikolu"""

        db_table = "core_profileikolucatchment"
        verbose_name = "Perfil Ikolu"
        verbose_name_plural = "Perfiles Ikolu"

    def __str__(self):
        return f"{self.point_catchment}"


class ProfileDataConfigCatchment(ModelApi):
    """Data Configuration Profile."""

    point_catchment = models.ForeignKey(
        CatchmentPoint,
        related_name="data_config_profiles",
        on_delete=models.CASCADE,
        verbose_name="Punto de captacion",
        blank=True,
        null=True,
    )
    d1 = models.DecimalField(
        default=0.0, verbose_name="Profundidad(mt)", max_digits=5, decimal_places=2
    )
    d2 = models.DecimalField(
        default=0.0,
        verbose_name="Posicionamiento de bomba(mt)",
        max_digits=5,
        decimal_places=2,
    )
    d3 = models.DecimalField(
        default=0.0,
        verbose_name="Posicionamiento nivel(mt)",
        max_digits=5,
        decimal_places=2,
    )
    d4 = models.DecimalField(
        default=0.0,
        verbose_name="Diametro ducto salida bomba(pulg)",
        max_digits=5,
        decimal_places=2,
    )
    d5 = models.DecimalField(
        default=0.0,
        verbose_name="Diametro flujometro(pulg)",
        max_digits=5,
        decimal_places=2,
    )
    d6 = models.IntegerField(
        default=0.0, verbose_name="Caudalimetro inicial", blank=True, null=True
    )
    is_telemetry = models.BooleanField(default=False, verbose_name="Activar telemetría")
    date_start_telemetry = models.DateField(
        blank=True, null=True, verbose_name="Fecha inicio telemetria"
    )
    date_delivery_act = models.DateField(
        blank=True, null=True, verbose_name="Fecha acta de entrega"
    )
    addition = models.IntegerField(
        default=0,
        verbose_name="Adicion (Reset)",
        help_text="Valor acumulado automáticamente cuando el sensor se reinicia (glitch/reset)."
    )

    # Telemetry Provider Token (Unified Dynamic System)
    token_service = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Token del Proveedor de Telemetría",
        help_text=(
            "Token para TData, TheThings, Tago, etc. "
            "según el proveedor configurado"
        ),
    )

    extra_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Configuración Dinámica",
        help_text=(
            "Variables dinámicas. Soporta formato simple {'k': 1.5} "
            "o extendido {'k': {'value': 1.5, 'unit': 'm', 'prefix': 'H='}}."
        ),
    )

    class Meta:
        """Meta data profile data config"""

        db_table = "core_profiledataconfigcatchment"
        verbose_name = "Configuracion de datos"
        verbose_name_plural = "Configuracion de datos"

    def __str__(self):
        return f"{self.point_catchment}"



