from rest_framework import serializers

from api.core.models import TelemetryRecord


class TelemetryRecordSerializer(serializers.ModelSerializer):
    """Serializer para registros de telemetría V3."""

    class Meta:
        model = TelemetryRecord
        fields = "__all__"

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        # Mapear campos dinámicos a la raíz para compatibilidad con frontend
        data = instance.data
        representation["flow"] = data.get("flow", data.get("caudal", 0))
        representation["total"] = data.get("total", 0)
        representation["total_diff"] = data.get("total_diff", 0)
        representation["total_today_diff"] = data.get("total_today_diff", 0)
        representation["nivel"] = data.get("nivel", 0)
        representation["water_table"] = data.get("water_table", 0)
        representation["pulses"] = data.get("pulses", 0)

        # Mapear timestamps
        representation["date_time_medition"] = instance.timestamp
        representation["date_time_last_logger"] = instance.metadata.get(
            "last_logger_timestamp"
        )

        return representation


class InteractionDetailModelSerializer(TelemetryRecordSerializer):
    """Alias para mantener compatibilidad con código existente."""

    pass


class InteractionDetailModelSerializerNoProcessing(TelemetryRecordSerializer):
    """Alias para mantener compatibilidad con código existente."""

    pass
