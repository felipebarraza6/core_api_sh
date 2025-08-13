from django.db.models import Sum
from rest_framework import serializers

from api.core.models import InteractionDetail, ProfileDataConfigCatchment


class InteractionDetailModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = InteractionDetail
        fields = "__all__"

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        catchment_point = instance.catchment_point
        total_d6 = (
            ProfileDataConfigCatchment.objects.filter(
                point_catchment=catchment_point
            ).aggregate(total=Sum("d6"))["total"]
            or 0
        )

        # Ensure that representation['total'] is not None
        current_total = representation.get("total", 0)
        if current_total is None:
            current_total = 0

        # Convert both values to int, handling decimals properly
        total_d6_int = int(float(total_d6)) if total_d6 else 0
        current_total_int = int(float(current_total)) if current_total else 0

        representation["total"] = total_d6_int + current_total_int
        return representation


class InteractionDetailModelSerializerNoProcessing(serializers.ModelSerializer):
    class Meta:
        model = InteractionDetail
        fields = "__all__"
