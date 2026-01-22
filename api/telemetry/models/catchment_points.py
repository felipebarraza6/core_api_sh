"""Catchment Points and Profiles."""

from django.db import models

from api.core.models.users import User
from api.core.models.utils import ModelApi


class CatchmentPoint(ModelApi):
    """Catchment points model."""

    # Dispositivo físico instalado en este punto
    device = models.ForeignKey(
        "infrastructure.Device",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="catchment_points",
        verbose_name="Dispositivo IoT",
        help_text="Dispositivo físico (logger/datalogger) instalado en este punto. Puede estar vacío si el punto no tiene equipo asignado."
    )

    project = models.ForeignKey(
        "crm.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="points",
        verbose_name="Proyecto",
        help_text="Proyecto al que pertenece este punto de captación."
    )
    
    # Punto generado desde un levantamiento técnico
    technical_survey = models.OneToOneField(
        "crm.TechnicalSurvey",
        related_name="generated_point",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Levantamiento Técnico de Origen",
        help_text="El levantamiento técnico que originó este punto de captación."
    )
    
    point_code = models.CharField(
        max_length=100, blank=True, null=True, verbose_name="Código de Punto"
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
    
    # Documentos adjuntos (Planos, resoluciones, fotos históricas)
    documents = models.ManyToManyField(
        "documents.Document",
        blank=True,
        related_name="bi_catchment_points",
        verbose_name="Archivos Adjuntos"
    )

    lat = models.CharField(
        max_length=300, blank=True, null=True, verbose_name="latitud"
    )

    lon = models.CharField(
        max_length=300, blank=True, null=True, verbose_name="longitud"
    )

    addition = models.IntegerField(
        default=0,
        verbose_name="Adición Acumulada (Reset)",
        help_text="Valor acumulado automáticamente cuando el sensor se reinicia."
    )

    is_active = models.BooleanField(
        default=True, verbose_name="Activo", help_text="Si el punto está habilitado para telemetría."
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

    @property
    def frequency_minutes(self):
        """Helper to get frequency in minutes"""
        return self.frequency.minutes if self.frequency else 60

    @property
    def is_thethings(self):
        """Check if point uses TheThings provider"""
        return self.configuration_values.filter(field__code='provider', value='thethings').exists()

    @property
    def is_novus(self):
        """Check if point uses Novus provider"""
        return self.configuration_values.filter(field__code='provider', value='novus').exists()

    @property
    def is_tdata(self):
        """Check if point uses TData provider"""
        return self.configuration_values.filter(field__code='provider', value='tdata').exists()

    @property
    def client(self):
        """Alias for owner_user to maintain backward compatibility"""
        return self.owner_user

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
