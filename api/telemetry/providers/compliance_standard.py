from django.db import models
from api.core.models.utils import ModelApi
from datetime import datetime

class ComplianceStandard(ModelApi):
    """
    Estándar de cumplimiento con frecuencia configurable.
    Reemplaza los estándares hardcodeados MAYOR/MEDIO/MENOR/CMP.
    """
    code = models.CharField(
        max_length=50, 
        unique=True,
        help_text="Código corto (ej: MAYOR, MEDIO, MENOR, CMP)"
    )
    name = models.CharField(
        max_length=100,
        help_text="Nombre descriptivo (ej: Estándar Mayor)"
    )
    description = models.TextField(blank=True)
    
    # Frecuencia de envío
    FREQUENCY_CHOICES = [
        ('hourly', 'Por hora'),
        ('daily', 'Diario'),
        ('monthly', 'Mensual'),
        ('semestral', 'Semestral'),
        ('custom', 'Personalizado'),
    ]
    frequency_type = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        default='daily'
    )
    
    # Configuración de timing
    hour = models.IntegerField(
        default=0,
        help_text="Hora del envío (0-23)"
    )
    minute = models.IntegerField(
        default=0,
        help_text="Minuto del envío (0-59)"
    )
    day_of_month = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Día del mes para el envío (1-31)"
    )
    months = models.JSONField(
        default=list,
        blank=True,
        help_text="Lista de meses para envío (ej: [1, 7] para semestral)"
    )
    
    # Expresión cron informativa
    cron_expression = models.CharField(
        max_length=100, 
        blank=True,
        help_text="Expresión cron equivalente (informativo)"
    )
    
    # Metadata para reportes
    records_per_period = models.IntegerField(
        default=1,
        help_text="Cantidad de datos esperados por período"
    )
    
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'compliance_standard'
        verbose_name = "Estándar de Cumplimiento"
        verbose_name_plural = "Estándares de Cumplimiento"
        ordering = ['code']

    def __str__(self):
        return f"{self.name} ({self.code})"

    def matches_time(self, dt: datetime) -> bool:
        """
        Verifica si el datetime coincide con el patrón de envío del estándar.
        """
        if not self.is_active:
            return False

        # Validamos minuto siempre
        if dt.minute != self.minute:
            return False

        if self.frequency_type == 'hourly':
            return True
        
        # Validamos hora para daily en adelante
        if dt.hour != self.hour:
            return False

        if self.frequency_type == 'daily':
            return True
        
        # Validamos día para monthly en adelante
        if self.day_of_month is not None and dt.day != self.day_of_month:
            return False

        if self.frequency_type == 'monthly':
            return True
        
        # Validamos mes para semestral
        if self.frequency_type == 'semestral':
            return dt.month in self.months
        
        return False
