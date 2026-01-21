from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from api.telemetry.models.catchment_points import (
    CatchmentPoint,
)
from api.crm.models import Client, Project, Person
from api.notifications.models import Notification, NotificationResponse
from api.documents.models import DocumentType, Document
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


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = "__all__"


class CatchmentPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatchmentPoint
        fields = "__all__"


# Legacy profile serializers removed


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = "__all__"


class NotificationResponseDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationResponse
        fields = "__all__"
        depth = 1


class NotificationResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationResponse
        fields = "__all__"


class DocumentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentType
        fields = "__all__"


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = "__all__"


# Legacy configuration serializer removed




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
        # Updated to use dynamic configuration system (V3)
        # instead of the legacy ProfileDataConfigCatchment model.
        
        config_dict = obj.get_config_dict()
        
        # Inyectar parámetros legacy si existen en la configuración dinámica
        # o usar valores por defecto seguros.
        result = {
            "token_service": config_dict.get("token_service", ""),
            "d3": float(config_dict.get("d3", 0.0)),
            "is_telemetry": obj.is_active,
            "extra_config": config_dict,
        }

        # variables heredadas del esquema
        scheme_variables = []
        virtual_variables = []
        scheme_name = obj.processing_scheme.name if obj.processing_scheme else "Dynamic Scheme"

        if obj.processing_scheme:
            scheme_variables = obj.processing_scheme.variables.filter(is_active=True)
            virtual_variables = obj.processing_scheme.virtual_variables.filter(is_active=True)

        all_vars_dict = {}
        for v in scheme_variables:
            all_vars_dict[v.internal_code] = v.id # basic map
            
        result["scheme"] = {
            "name": scheme_name,
            "variables": [], # To be filled if needed or handled by processor
            "virtual_variables": []
        }
        
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
        fields = ("id", "title", "frequency_minutes", "profile_data_config", "project_info")


# Retrieve serializer removed


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


# Legacy DataConfigUserSerializer removed


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
            "date_time_medition",
            "metadata",
            "data",
            "compliance_status",
            "is_error",
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
    modules = serializers.SerializerMethodField("get_modules")

    def get_modules(self, obj):
        today = timezone.localtime(timezone.now()).date()
        yesterday = today - timedelta(days=1)

        # Obtener registros recientes
        base_qs = TelemetryRecord.objects.filter(point=obj).order_by("-timestamp")

        get_data_m1 = base_qs.first()
        # Registros con compliance (DGA/SMA)
        get_data_m2 = base_qs.exclude(compliance_status={})[:48]
        get_data_m22 = base_qs.exclude(compliance_status={}, timestamp__date=today)[:24]

        today_qs = base_qs.filter(timestamp__date=today)
        yesterday_qs = base_qs.filter(timestamp__date=yesterday)

        get_data_m3 = today_qs
        get_data_m4 = yesterday_qs

        first_data_today = today_qs.last()
        last_data_yesterday = yesterday_qs.first()

        # Files & Alerts
        get_files = Document.objects.filter(point_catchment=obj)
        get_alerts = Notification.objects.filter(
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
            "files": DocumentDetailSerializer(get_files, many=True).data,
            "alerts": NotificationDetailSerializer(
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
                "compliance_status": r.compliance_status,
                "n_voucher": r.compliance_status.get('dga', {}).get('voucher', '-'),
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


    def get_config_data(self, obj):
        # Now returns dynamic configuration values
        config_dict = obj.get_config_dict()
        return {
            "is_telemetry": obj.is_active,
            "extra_config": config_dict,
            **config_dict
        }

    def get_profile_ikolu(self, obj):
        # Now dynamically fetches active modules from the subscriptions app
        from api.subscriptions.models import PointModuleAccess
        
        active_access = PointModuleAccess.objects.filter(
            point=obj, 
            is_active=True
        ).select_related('module')
        
        # Map dynamic modules to legacy return format for frontend compatibility
        profile = {
            "entry_by_form": False,
            "m1": False, "m2": False, "m3": False, "m4": False, "m5": False, "m6": False, "m7": False
        }
        
        module_mapping = {
            "mi_pozo": "m1",
            "dga": "m2",
            "reportes": "m3",
            "graficos": "m4",
            "indicadores": "m5",
            "alarmas": "m6",
            "documentos": "m7"
        }
        
        for access in active_access:
            code = access.module.code
            if code in module_mapping:
                profile[module_mapping[code]] = True
            # Also include the dynamic code itself
            profile[code] = True
            
        return profile

    class Meta:
        model = CatchmentPoint
        fields = (
            "id",
            "title",
            "frequency_minutes",
            "profile_ikolu",
            "config_data",
            "modules",
            "lat",
            "lon",
        )


class DocumentTypeDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentType
        fields = ("name",)


class DocumentDetailSerializer(serializers.ModelSerializer):
    created = serializers.DateTimeField(format="%Y-%m-%d %H:%M")
    document_type = DocumentTypeDetailSerializer(read_only=True)

    class Meta:
        model = Document
        fields = ("id", "file", "name", "description", "document_type", "created")


class NotificationDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "created", "title", "message", "type_variable", "type_alert")


class PersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Person
        fields = "__all__"
