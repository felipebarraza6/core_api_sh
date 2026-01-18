from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from api.telemetry.models.catchment_points import (
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
    TypeFileCatchment,
)
from api.telemetry.models.telemetry import (
    CoreVariable,
    TelemetryRecord,
)

from .interaction_detail import (
    TelemetryRecordSerializer as InteractionDetailModelSerializer,
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
        model = CoreVariable
        fields = (
            "id",
            "name",
            "internal_code",
            "unit",
            "scale_factor",
            "offset",
            "operation",
            "formula",
            "sources",
            "priority",
            "is_virtual",
            "min_value",
            "max_value",
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

        # Serializar el perfil básico (incluyendo extra_config)
        profile_data = ProfileDataConfigCatchmentSerializer(profile).data

        # 1. Variables directas del punto
        point_variables = CoreVariable.objects.filter(point=obj, is_active=True)

        # 2. Variables heredadas del esquema (si existe)
        scheme_variables = []
        virtual_variables = []
        scheme_name = "Dynamic Scheme"

        if obj.processing_scheme:
            scheme_name = obj.processing_scheme.name
            scheme_variables = obj.processing_scheme.variables.filter(is_active=True)
            virtual_variables = obj.processing_scheme.virtual_variables.filter(
                is_active=True
            )

        # Combinar variables (las del punto tienen prioridad sobre las del esquema
        # si coinciden en internal_code)
        all_vars_dict = {}

        # Primero cargar las del esquema
        for v in scheme_variables:
            all_vars_dict[v.internal_code] = {
                "id": f"scheme_{v.id}",
                "str_variable": v.provider_key or v.internal_code,
                "type_variable": v.type_variable,
                "internal_code": v.internal_code,
                "service": "UNIFIED",
                "scale_factor": v.scale_factor,
                "offset": v.offset,
                "operation": v.operation,
                "formula": v.formula,
                "sources": v.sources,
                "priority": v.priority,
                "is_virtual": v.is_virtual,
                "min_value": v.min_value,
                "max_value": v.max_value,
                "configuration": v.configuration,
            }

        # Luego cargar/sobreescribir con las del punto
        for v in point_variables:
            all_vars_dict[v.internal_code] = {
                "id": v.id,
                "str_variable": v.provider_key or v.internal_code,
                "type_variable": v.type_variable,
                "internal_code": v.internal_code,
                "service": "UNIFIED",
                "scale_factor": v.scale_factor,
                "offset": v.offset,
                "operation": v.operation,
                "formula": v.formula,
                "sources": v.sources,
                "priority": v.priority,
                "is_virtual": v.is_virtual,
                "min_value": v.min_value,
                "max_value": v.max_value,
                "configuration": v.configuration,
            }

        # Construir lista final de variables procesables
        processed_variables = []
        for v_code, v_data in all_vars_dict.items():
            # Inyectar parámetros legacy esperados por unified_processing.py
            v_data["pulses_factor"] = v_data.get("configuration", {}).get(
                "pulses_factor", (v_data["scale_factor"] * 1000)
            )
            v_data["calculate_nivel"] = v_data.get("configuration", {}).get(
                "calculate_nivel", True
            )
            v_data["convert_to_lt"] = v_data.get("configuration", {}).get(
                "convert_to_lt", True
            )
            processed_variables.append(v_data)

        # Retornar estructura completa, incluyendo extra_config del perfil
        result = {
            "token_service": profile.token_service or "",
            "d3": float(profile.d3),
            "scheme": {
                "name": scheme_name,
                "variables": processed_variables,
                "virtual_variables": sorted(
                    [
                        {
                            "name": vv.name,
                            "internal_code": vv.internal_code,
                            "operation": vv.operation,
                            "sources": vv.sources,
                            "formula": vv.formula,
                            "priority": vv.priority,
                        }
                        for vv in virtual_variables
                    ],
                    key=lambda x: x["priority"],
                ),
            },
        }

        # Inyectar campos del perfil incluyendo extra_config
        if profile_data:
            result.update(profile_data)

        return result

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
        model = CoreVariable
        fields = (
            "id",
            "name",
            "internal_code",
            "unit",
            "scale_factor",
            "offset",
            "operation",
            "formula",
            "sources",
            "priority",
            "is_virtual",
            "min_value",
            "max_value",
            "is_active",
        )


class VariableSerializer(VariableConfigSerializer):
    pass


class DataConfigUserSerializer(serializers.ModelSerializer):
    variables = serializers.SerializerMethodField("get_variables")

    def get_variables(self, obj):
        if not obj or not obj.point_catchment:
            return []
        variables = CoreVariable.objects.filter(
            point=obj.point_catchment, is_active=True
        )
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
            "extra_config",
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
        if isinstance(data, dict):
            for key, value in data.items():
                representation[key] = value

        # Compatibilidad legacy
        if "flow" not in representation and "caudal" in representation:
            representation["flow"] = representation["caudal"]

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
            # Timestamp local
            dt_local = timezone.localtime(r.timestamp)

            item = {
                "date_time_medition": dt_local.strftime("%Y-%m-%d %H:%M:%S"),
                "send_dga": r.send_dga,
                "n_voucher": r.n_voucher or "-",
            }

            # Inyectar todos los datos dinámicos del JSONField
            if isinstance(r.data, dict):
                for key, val in r.data.items():
                    item[key] = val

            # Compatibilidad legacy (asegurar que 'flow' exista si hay 'caudal')
            if "flow" not in item and "caudal" in item:
                item["flow"] = item["caudal"]
            elif "flow" not in item:
                item["flow"] = 0

            # Asegurar que otros campos básicos existan para evitar errores en frontend
            if "total" not in item:
                item["total"] = 0
            if "nivel" not in item:
                item["nivel"] = 0
            if "total_diff" not in item:
                item["total_diff"] = 0

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
