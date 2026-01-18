from django.db.models.signals import post_save
from django.dispatch import receiver
from api.telemetry.models.catchment_points import (
    CatchmentPoint,
    ProfileIkoluCatchment,
    ProfileDataConfigCatchment,
    DgaDataConfigCatchment,
)
from api.core.services.variable_service import initialize_default_variables


@receiver(post_save, sender=CatchmentPoint)
def create_related_profiles(sender, instance, created, **kwargs):
    if created:
        ProfileIkoluCatchment.objects.create(point_catchment=instance)
        ProfileDataConfigCatchment.objects.create(point_catchment=instance)
        DgaDataConfigCatchment.objects.create(point_catchment=instance)

        # Inicializar variables por defecto (Sistema Dinámico)
        initialize_default_variables(instance.id)
