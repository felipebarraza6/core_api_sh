from datetime import datetime, timedelta

import pytz
from django.db.models import Case, IntegerField, Prefetch, Sum, When
from django.utils import timezone
from rest_framework import serializers

from api.core.models import (
    CatchmentPoint,
    Client,
    DgaDataConfigCatchment,
    FileCatchment,
    NotificationsCatchment,
    ProfileDataConfigCatchment,
    ProfileIkoluCatchment,
    ProjectCatchments,
    RegisterPersons,
    ResponseNotificationsCatchment,
    TelemetryRecord,
    TypeFileCatchment,
    Variable,
)

from .interaction_detail import (
    TelemetryRecordSerializer as InteractionDetailModelSerializer,
)
from .interaction_detail import (
    TelemetryRecordSerializer as InteractionDetailModelSerializerNoProcessing,
)


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = "__all__"


class ProjectCatchmentsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectCatchments
        fields = "__all__"


class CatchmentPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatchmentPoint
        fields = "__all__"


class ProfileIkoluCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfileIkoluCatchment
        fields = "__all__"


class NotificationsCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationsCatchment
        fields = "__all__"


class ResponseDepthNotificationsCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResponseNotificationsCatchment
        fields = "__all__"
        depth = 1


class ResponseNotificationsCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResponseNotificationsCatchment
        fields = "__all__"


class TypeFileCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TypeFileCatchment
        fields = "__all__"


class FileCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileCatchment
        fields = "__all__"


class ProfileDataConfigCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfileDataConfigCatchment
        fields = "__all__"


class DgaDataConfigCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = DgaDataConfigCatchment
        fields = "__all__"


class DgaCronSerializer(serializers.ModelSerializer):
    class Meta:
        model = DgaDataConfigCatchment
        fields = (
            "send_dga",
            "standard",
            "type_dga",
            "code_dga",
            "flow_granted_dga",
            "total_granted_dga",
            "shac",
            "date_start_compliance",
            "date_created_code",
        )


class VariableCronSerializer(serializers.ModelSerializer):
    class Meta:
        model = Variable
        fields = (
            "id",
            "name",
            "internal_code",
            "unit",
            "scale_factor",
            "offset",
            "is_active",
        )


class CatchmentPointSerializerDetailCron(serializers.ModelSerializer):
    profile_data_config = serializers.SerializerMethodField("get_profile_data_config")
    project_info = serializers.SerializerMethodField()

    def get_project_info(self, obj):
        try:
            if obj.project and obj.project.client:
                return {
                    "project_name": obj.project.name,
                    "client_name": obj.project.client.name,
                }
        except Exception:
            pass
        return {"project_name": "N/A", "client_name": "N/A"}

    def get_profile_data_config(self, obj):
        profile = ProfileDataConfigCatchment.objects.filter(point_catchment=obj).first()
        if not profile:
            return {}

        # Mapeo simplificado para compatibilidad con scripts de ingesta legacy
        variables = Variable.objects.filter(point=obj, is_active=True)
        return {
            "token_service": profile.token_service or "",  # V3.1: Token real del proveedor
            "d3": float(profile.d3),
            "scheme": {
                "name": "V3 Dynamic Scheme",
                "variables": [
                    {
                        "id": v.id,
                        "str_variable": v.provider_key or v.internal_code,
                        "type_variable": self._map_internal_to_legacy_type(
                            v.internal_code
                        ),
                        "internal_code": v.internal_code,
                        "service": "V3",
                        "pulses_factor": (
                            v.scale_factor * 1000
                            if v.internal_code == "total"
                            else 1000
                        ),
                    }
                    for v in variables
                ],
            },
        }

    def _map_internal_to_legacy_type(self, code):
        mapping = {
            "total": "TOTALIZADO",
            "flow": "CAUDAL",
            "caudal": "CAUDAL",
            "nivel": "NIVEL",
            "water_table": "NIVEL",
        }
        return mapping.get(code, "OTHER")

    class Meta:
        model = CatchmentPoint
        fields = ("id", "title", "frecuency", "profile_data_config", "project_info")


class ProfileIkoluCatchmentRetrieveSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfileIkoluCatchment
        fields = ("entry_by_form", "m1", "m2", "m3", "m4", "m5", "m6")


class VariableConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = Variable
        fields = (
            "id",
            "name",
            "internal_code",
            "unit",
            "scale_factor",
            "offset",
            "is_active",
        )


class VariableSerializer(VariableConfigSerializer):
    pass


class DataConfigUserSerializer(serializers.ModelSerializer):
    variables = serializers.SerializerMethodField("get_variables")

    def get_variables(self, obj):
        if not obj or not obj.point_catchment:
            return []
        variables = Variable.objects.filter(point=obj.point_catchment, is_active=True)
        return VariableConfigSerializer(variables, many=True).data

    class Meta:
        model = ProfileDataConfigCatchment
        fields = (
            "d1",
            "d2",
            "d3",
            "d4",
            "d5",
            "d6",
            "addition",
            "date_start_telemetry",
            "date_delivery_act",
            "is_telemetry",
            "variables",
        )


class InteractionDetailModuleSerializer(serializers.ModelSerializer):
    date_time_medition = serializers.DateTimeField(
        source="timestamp", format="%Y-%m-%d %H:%M:%S"
    )

    class Meta:
        model = TelemetryRecord
        fields = (
            "date_time_medition",
            "metadata",
            "data",
            "send_dga",
            "return_dga",
            "n_voucher",
        )

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        data = instance.data
        representation["flow"] = data.get("flow", data.get("caudal", 0))
        representation["total"] = data.get("total", 0)
        representation["total_diff"] = data.get("total_diff", 0)
        representation["total_today_diff"] = data.get("total_today_diff", 0)
        representation["nivel"] = data.get("nivel", 0)
        representation["water_table"] = data.get("water_table", 0)
        representation["date_time_last_logger"] = instance.metadata.get(
            "last_logger_timestamp"
        )
        return representation


class CatchmentPointIkoluSerializer(serializers.ModelSerializer):
    profile_ikolu = serializers.SerializerMethodField("get_profile_ikolu")
    config_data = serializers.SerializerMethodField("get_config_data")
    dga = serializers.SerializerMethodField("get_dga")
    modules = serializers.SerializerMethodField("get_modules")

    def get_modules(self, obj):
        today = timezone.localtime(timezone.now()).date()
        yesterday = today - timedelta(days=1)

        # Obtener registros recientes
        base_qs = TelemetryRecord.objects.filter(point=obj).order_by("-timestamp")

        get_data_m1 = base_qs.first()
        get_data_m2 = base_qs.filter(send_dga=True)[:48]
        get_data_m22 = base_qs.filter(send_dga=True, timestamp__date=today)[:24]

        today_qs = base_qs.filter(timestamp__date=today)
        yesterday_qs = base_qs.filter(timestamp__date=yesterday)

        get_data_m3 = today_qs
        get_data_m4 = yesterday_qs

        first_data_today = today_qs.last()
        last_data_yesterday = yesterday_qs.first()

        # Files & Alerts
        get_files = FileCatchment.objects.filter(point_catchment=obj)
        get_alerts = NotificationsCatchment.objects.filter(
            point_catchment=obj, type_notification="ALERT"
        )

        modules = {
            "m1": (
                InteractionDetailModelSerializer(get_data_m1).data
                if get_data_m1
                else None
            ),
            "m2": self._serialize_light(get_data_m2),
            "m22": self._serialize_light(get_data_m22),
            "first_data_today": (
                InteractionDetailModelSerializer(first_data_today).data
                if first_data_today
                else None
            ),
            "today": self._serialize_light(get_data_m3),
            "yesterday": self._serialize_light(get_data_m4),
            "last_data_yesterday": (
                InteractionDetailModelSerializer(last_data_yesterday).data
                if last_data_yesterday
                else None
            ),
            "total_consumed_yesterday": yesterday_qs.aggregate(
                s=Sum("data__total_diff")
            )["s"]
            or 0,
            "total_consumed_today": today_qs.aggregate(s=Sum("data__total_diff"))["s"]
            or 0,
            "files": FileCatchmentDetailSerializer(get_files, many=True).data,
            "alerts": NotificationsCatchmentDetailSerializer(
                get_alerts, many=True
            ).data,
        }
        return modules

    def _serialize_light(self, records):
        if not records:
            return []
        data = []
        for r in records:
            item = {
                "date_time_medition": timezone.localtime(r.timestamp).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "flow": r.data.get("flow", r.data.get("caudal", 0)),
                "total": r.data.get("total", 0),
                "total_diff": r.data.get("total_diff", 0),
                "nivel": r.data.get("nivel", 0),
                "send_dga": r.send_dga,
                "n_voucher": r.n_voucher or "-",
            }
            data.append(item)
        return data

    def get_dga(self, obj):
        get_data = DgaDataConfigCatchment.objects.filter(point_catchment=obj).first()
        return DgaCronSerializer(get_data).data if get_data else {}

    def get_config_data(self, obj):
        get_data = ProfileDataConfigCatchment.objects.filter(
            point_catchment=obj
        ).first()
        return DataConfigUserSerializer(get_data).data if get_data else {}

    def get_profile_ikolu(self, obj):
        get_data = ProfileIkoluCatchment.objects.filter(point_catchment=obj).first()
        return (
            ProfileIkoluCatchmentRetrieveSerializer(get_data).data if get_data else {}
        )

    class Meta:
        model = CatchmentPoint
        fields = (
            "id",
            "title",
            "frecuency",
            "profile_ikolu",
            "config_data",
            "dga",
            "modules",
            "lat",
            "lon",
        )


class TypeFileCatchmentDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = TypeFileCatchment
        fields = ("name",)


class FileCatchmentDetailSerializer(serializers.ModelSerializer):
    created = serializers.DateTimeField(format="%Y-%m-%d %H:%M")
    type_file = TypeFileCatchmentDetailSerializer(read_only=True)

    class Meta:
        model = FileCatchment
        fields = ("id", "file", "name", "description", "type_file", "created")


class NotificationsCatchmentDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationsCatchment
        fields = ("id", "created", "title", "message", "type_variable", "type_alert")


class RegisterPersonsSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegisterPersons
        fields = "__all__"
