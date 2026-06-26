from django.db.models.signals import post_save
from django.dispatch import receiver
from api.core.models.catchment_points import CatchmentPoint, ProfileIkoluCatchment, ProfileDataConfigCatchment, DgaDataConfigCatchment


@receiver(post_save, sender=CatchmentPoint)
def create_related_profiles(sender, instance, created, **kwargs):
    if created:
        ProfileIkoluCatchment.objects.create(point_catchment=instance)
        ProfileDataConfigCatchment.objects.create(point_catchment=instance)
        DgaDataConfigCatchment.objects.create(point_catchment=instance)


@receiver(post_save, sender=ProfileIkoluCatchment)
def sync_form_to_telemetry(sender, instance, **kwargs):
    """
    Cuando un punto se marca como 'ingreso por formulario', desactiva telemetría
    y sincroniza la configuración DGA para evitar inconsistencias.
    """
    if not instance.entry_by_form:
        return

    point = instance.point_catchment
    if not point:
        return

    # 1. Desactivar telemetría automática
    data_config = ProfileDataConfigCatchment.objects.filter(point_catchment=point).first()
    if data_config and data_config.is_telemetry:
        data_config.is_telemetry = False
        data_config.save(update_fields=["is_telemetry"])

    # 2. Sincronizar DGA standard a FORMULARIO
    dga_config = DgaDataConfigCatchment.objects.filter(point_catchment=point).first()
    if dga_config and dga_config.standard != "FORMULARIO":
        dga_config.standard = "FORMULARIO"
        dga_config.save(update_fields=["standard"])
