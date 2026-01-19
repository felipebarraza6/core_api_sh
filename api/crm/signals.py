"""
CRM Signals
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import CrmTask, Project


@receiver(post_save, sender=CrmTask)
def activate_telemetry_on_install_complete(sender, instance, created, **kwargs):
    """
    Automatización: Cuando se COMPLETA una tarea de INSTALACIÓN,
    se activa la telemetría del proyecto asociado y el estado del proyecto pasa a ACTIVO.
    """
    if instance.task_type == "INSTALLATION" and instance.status == "COMPLETED":
        project = instance.project
        
        # 1. Cambiar estado del proyecto a ACTIVO si estaba en progreso
        if project.status == "IN_PROGRESS":
            project.status = "ACTIVE"
            # Si no tenía fecha de inicio real, la seteamos hoy
            if not project.start_date:
                project.start_date = timezone.now().date()
            project.save(update_fields=["status", "start_date"])

        # 2. Activar telemetría en todos los puntos del proyecto
        # Buscamos los puntos asociados al proyecto
        for point in project.catchment_points.all():
            # Buscamos o creamos la configuración de datos
            # Nota: Usamos filter().first() para evitar excepciones si la relación inversa no es directa o hay multiples
            # Pero CatchmentPoint -> data_config_profiles es Reverse ForeignKey
            # Asumimos que hay al menos un perfil de datos principal.
            
            # Iteramos sobre los perfiles de configuración de datos de este punto
            for config in point.data_config_profiles.all():
                if not config.is_telemetry:
                    config.is_telemetry = True
                    if not config.date_start_telemetry:
                        config.date_start_telemetry = timezone.now().date()
                    config.save(update_fields=["is_telemetry", "date_start_telemetry"])
