from rest_framework import serializers

from api.core.models import TelemetryRecord


class TelemetryRecordSerializer(serializers.ModelSerializer):
    """Serializer para registros de telemetría."""

    class Meta:
        model = TelemetryRecord
        fields = "__all__"

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        # Mapear campos dinámicos a la raíz para compatibilidad con frontend
        data = instance.data
        if isinstance(data, dict):
            for key, value in data.items():
                representation[key] = value

        # Asegurar compatibilidad con nombres legacy si no existen
        if "flow" not in representation and "caudal" in representation:
            representation["flow"] = representation["caudal"]

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
