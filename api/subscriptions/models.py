"""
Subscriptions Models
"""

from django.db import models
from django.conf import settings
from api.core.models.utils import ModelApi


class IkoluModule(ModelApi):
    """
    Módulos disponibles en la plataforma Ikolu.
    Reemplaza los campos m1-m7 hardcodeados en ProfileIkoluCatchment.
    """
    
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Código",
        help_text="Identificador único (ej: 'mi_pozo', 'dga', 'reportes')"
    )
    name = models.CharField(
        max_length=200,
        verbose_name="Nombre del Módulo"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Descripción"
    )
    
    # Configuración de acceso
    api_permission_codename = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Codename de Permiso",
        help_text="Permiso Django requerido para acceder a este módulo"
    )
    frontend_route = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Ruta Frontend",
        help_text="Ruta en el frontend Ikolu (ej: '/dashboard/mi-pozo')"
    )
    
    # Presentación
    icon = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Icono",
        help_text="Nombre del icono FontAwesome o similar"
    )
    color_code = models.CharField(
        max_length=20,
        default="#007bff",
        verbose_name="Color Hex"
    )
    
    # Comercial
    base_price_monthly = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Precio Mensual Base"
    )
    
    # Lógica
    is_core = models.BooleanField(
        default=False,
        verbose_name="Módulo Core",
        help_text="Los módulos core están siempre activos y no se pueden desactivar"
    )
    
    order = models.IntegerField(default=0, verbose_name="Orden de Visualización")
    is_active = models.BooleanField(default=True, verbose_name="Activo")
    
    class Meta:
        db_table = "subscriptions_module"
        verbose_name = "Módulo Ikolu"
        verbose_name_plural = "Módulos Ikolu"
        ordering = ['order', 'name']
    
    def __str__(self):
        return self.name


class SubscriptionPlan(ModelApi):
    """
    Planes de suscripción disponibles.
    Reemplaza SUBSCRIPTIONS_CHOICES hardcodeado.
    """
    
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Código",
        help_text="Identificador único (ej: 'MENSUAL', 'ANUAL')"
    )
    name = models.CharField(
        max_length=200,
        verbose_name="Nombre del Plan"
    )
    
    duration_months = models.IntegerField(
        verbose_name="Duración (meses)",
        help_text="1=Mensual, 3=Trimestral, 6=Semestral, 12=Anual"
    )
    
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name="Descuento (%)",
        help_text="Descuento sobre el precio base mensual"
    )
    
    is_active = models.BooleanField(default=True, verbose_name="Activo")
    order = models.IntegerField(default=0, verbose_name="Orden de Visualización")
    
    class Meta:
        db_table = "subscriptions_plan"
        verbose_name = "Plan de Suscripción"
        verbose_name_plural = "Planes de Suscripción"
        ordering = ['order', 'duration_months']
    
    def __str__(self):
        return self.name


class PointModuleAccess(ModelApi):
    """
    Acceso de un punto de captación a un módulo específico.
    Reemplaza ProfileIkoluCatchment con estructura dinámica.
    """
    
    point = models.ForeignKey(
        'telemetry.CatchmentPoint',
        on_delete=models.CASCADE,
        related_name='module_access',
        verbose_name="Punto de Captación"
    )
    module = models.ForeignKey(
        IkoluModule,
        on_delete=models.CASCADE,
        related_name='point_access',
        verbose_name="Módulo"
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='point_access',
        verbose_name="Plan de Suscripción"
    )
    
    # Fechas
    start_date = models.DateField(
        verbose_name="Fecha de Inicio"
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de Término",
        help_text="Dejar vacío para acceso indefinido"
    )
    
    # Estado
    is_active = models.BooleanField(
        default=True,
        verbose_name="Activo"
    )
    
    # Metadata
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='granted_module_access',
        verbose_name="Otorgado por"
    )
    notes = models.TextField(
        blank=True,
        verbose_name="Notas"
    )
    
    class Meta:
        db_table = "subscriptions_pointmoduleaccess"
        verbose_name = "Acceso a Módulo"
        verbose_name_plural = "Accesos a Módulos"
        unique_together = ('point', 'module')
        ordering = ['point', 'module__order']
    
    def __str__(self):
        return f"{self.point.title} - {self.module.name}"
    
    def is_valid(self):
        """Verifica si el acceso está vigente."""
        from django.utils import timezone
        if not self.is_active:
            return False
        if self.end_date and self.end_date < timezone.now().date():
            return False
        return True
