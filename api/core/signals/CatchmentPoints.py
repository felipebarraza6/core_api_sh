from django.db.models.signals import post_save
from django.dispatch import receiver
from api.core.models.catchment_points import CatchmentPoint, ProfileIkoluCatchment, ProfileDataConfigCatchment, DgaDataConfigCatchment


@receiver(post_save, sender=CatchmentPoint)
def create_related_profiles(sender, instance, created, **kwargs):
    if created:
        ProfileIkoluCatchment.objects.create(point_catchment=instance)
        ProfileDataConfigCatchment.objects.create(point_catchment=instance)
        DgaDataConfigCatchment.objects.create(point_catchment=instance)
