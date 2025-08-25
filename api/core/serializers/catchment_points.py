from rest_framework import serializers
from api.core.models.catchment_points import (
    Client,
    ProjectCatchments,
    CatchmentPoint,
    ProfileIkoluCatchment,
    NotificationsCatchment,
    ResponseNotificationsCatchment,
    TypeFileCatchment,
    FileCatchment,
    ProfileDataConfigCatchment,
    DgaDataConfigCatchment,
    SchemesCatchment,
    Variable,
    RegisterPersons
)
from api.core.models.interaction_detail import InteractionDetail
from datetime import datetime, timedelta
from .interaction_detail import InteractionDetailModelSerializerNoProcessing, InteractionDetailModelSerializer
from django.db.models import Case, When, IntegerField


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = '__all__'


class ProjectCatchmentsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectCatchments
        fields = '__all__'


class CatchmentPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatchmentPoint
        fields = '__all__'


class ProfileIkoluCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfileIkoluCatchment
        fields = '__all__'


class NotificationsCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationsCatchment
        fields = '__all__'


class ResponseDepthNotificationsCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResponseNotificationsCatchment
        fields = '__all__'
        depth=1

class ResponseNotificationsCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResponseNotificationsCatchment
        fields = '__all__'


class TypeFileCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TypeFileCatchment
        fields = '__all__'


class FileCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileCatchment
        fields = '__all__'


class ProfileDataConfigCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfileDataConfigCatchment
        fields = '__all__'


class DgaCronSerializer(serializers.ModelSerializer):
    class Meta:
        model = DgaDataConfigCatchment
        fields = ('send_dga', 'standard', 'type_dga', 'code_dga', 'flow_granted_dga',
                  'total_granted_dga', 'shac', 'date_start_compliance', 'date_created_code',)


class VariableCronSerializer(serializers.ModelSerializer):
    class Meta:
        model = Variable
        fields = ('str_variable', 'type_variable', 'token_service', 'service',
                  'pulses_factor', 'addition', 'convert_to_lt', 'calculate_nivel',)


class SchemesCatchmentCronSerializer(serializers.ModelSerializer):
    """
    Serializer for SchemesCatchment with variables.
    """
    variables = serializers.SerializerMethodField()

    def get_variables(self, obj):
        """
        Retrieve and serialize variables for the given scheme catchment.
        """
        get_data = Variable.objects.filter(
            scheme_catchment=obj).all().order_by(
            Case(
                When(type_variable='TOTALIZADO', then=0),
                When(token_service__isnull=True, then=2),
                default=1,
                output_field=IntegerField()
            ),
            'type_variable',
            'token_service'
        )
        return VariableCronSerializer(get_data, many=True).data

    class Meta:
        model = SchemesCatchment
        fields = ('name', 'variables')


class ProfileDataConfigCatchmentRetrieveCronSerializer(serializers.ModelSerializer):
    scheme = serializers.SerializerMethodField('get_scheme')

    def get_scheme(self, obj):
        get_data = SchemesCatchment.objects.filter(
            points_catchment=obj.point_catchment).first()
        return SchemesCatchmentCronSerializer(get_data).data

    class Meta:
        model = ProfileDataConfigCatchment
        fields = ('token_service', "d3", 'scheme',)


class DgaDataConfigCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = DgaDataConfigCatchment
        fields = '__all__'


class SchemesCatchmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchemesCatchment
        fields = '__all__'


class VariableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Variable
        fields = '__all__'


class RegisterPersonsSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegisterPersons
        fields = '__all__'


class CatchmentPointSerializerDetailCron(serializers.ModelSerializer):
    profile_data_config = serializers.SerializerMethodField(
        'get_profile_data_config')

    def get_profile_data_config(self, obj):
        get_data = ProfileDataConfigCatchment.objects.filter(
            point_catchment=obj).first()
        return ProfileDataConfigCatchmentRetrieveCronSerializer(get_data).data

    class Meta:
        model = CatchmentPoint
        fields = ('id', 'title', 'frecuency',
                  'profile_data_config', )


class ProfileIkoluCatchmentRetrieveSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfileIkoluCatchment
        fields = ('entry_by_form', 'm1', 'm2', 'm3', 'm4', 'm5', 'm6')


class DataConfigUserSerializer(serializers.ModelSerializer):

    class Meta:
        model = ProfileDataConfigCatchment
        fields = ('d1', 'd2', 'd3', 'd4', 'd5','d6',
                  'date_start_telemetry', 'date_delivery_act','is_telemetry')


class InteractionDetailModuleSerializer(serializers.ModelSerializer):
    date_time_medition = serializers.DateTimeField(format="%Y-%d-%m %H:%M")

    class Meta:
        model = InteractionDetail
        fields = ('date_time_medition', 'date_time_last_logger', 'flow', 'total', 'total_diff', 'total_today_diff',
                  'nivel', 'water_table', 'send_dga', 'return_dga', 'n_voucher')


class TypeFileCatchmentDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = TypeFileCatchment
        fields = ('name',)


class FileCatchmentDetailSerializer(serializers.ModelSerializer):
    created = serializers.DateTimeField(format="%Y-%d-%m %H:%M")
    modified = serializers.DateTimeField(format="%Y-%d-%m %H:%M")
    type_file = serializers.SerializerMethodField('get_type_file')

    def get_type_file(self, obj):
        get_data = TypeFileCatchment.objects.filter(
            id=obj.type_file.id).first()
        return TypeFileCatchmentDetailSerializer(get_data).data

    class Meta:
        model = FileCatchment
        fields = ('id', 'file', 'name', 'description',
                  'type_file', 'created', 'modified')


class NotificationsCatchmentDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationsCatchment
        fields = ('id', 'created', 'title', 'message',
                  'type_variable', 'type_alert')


class CatchmentPointIkoluSerializer(serializers.ModelSerializer):
    profile_ikolu = serializers.SerializerMethodField(
        'get_profile_ikolu')
    config_data = serializers.SerializerMethodField(
        'get_config_data')
    dga = serializers.SerializerMethodField(
        'get_dga')
    modules = serializers.SerializerMethodField('get_modules')

    def get_modules(self, obj):
        """
        Retrieve the latest InteractionDetail for the given catchment point.
        """
        counter_total = 0

        
        
        


        get_data_m1 = InteractionDetail.objects.filter(
            catchment_point=obj.id).last()

       

        get_data_m2 = InteractionDetail.objects.filter(
            catchment_point=obj.id,
            return_dga__isnull=False,
        ).order_by('-date_time_medition').distinct('date_time_medition')[:48]

        get_data_m22 = InteractionDetail.objects.filter(
            catchment_point=obj.id,
            return_dga__isnull=False,
            date_time_medition__gte=datetime.now().date(),
        ).order_by('-date_time_medition').distinct('date_time_medition')[:24]

        today = datetime.now().date()
        yesterday = today - timedelta(days=1)

        # Filtrar registros del día de ayer
        data_yesterday = InteractionDetail.objects.filter(
            catchment_point=obj.id,
            date_time_medition__gte=yesterday,
            date_time_medition__lt=today,
        ).order_by('-date_time_medition').first()

        get_data_m3 = InteractionDetail.objects.filter(
            catchment_point=obj.id,
            date_time_medition__gte=today,
        ).order_by('-date_time_medition').distinct('date_time_medition')[:50]

        get_data_m4 = InteractionDetail.objects.filter(
            catchment_point=obj.id,
            date_time_medition__gte=yesterday,
            date_time_medition__lt=today,
        ).order_by('-date_time_medition').distinct('date_time_medition')
        
        

        get_files = FileCatchment.objects.filter(
            point_catchment=obj.id).all()

        first_data_today = InteractionDetail.objects.filter(
            catchment_point=obj.id,
            date_time_medition__gte=today,
        ).first()
       

        last_data_yesterday = InteractionDetail.objects.filter(
            catchment_point=obj.id,
            date_time_medition__gte=yesterday,
            date_time_medition__lt=today,
        ).last()

        first_data_yesterday = InteractionDetail.objects.filter(
            catchment_point=obj.id,
            date_time_medition__gte=yesterday,
        ).first()

        modules = {}

        total_consumed_yesterday = None
        if last_data_yesterday:
            try:
                if last_data_yesterday.total:
                    total_consumed_yesterday = int(last_data_yesterday.total_today_diff) 
                else:
                    total_consumed_yesterday = 0
            except ValueError:
                total_consumed_yesterday = 0

        total_consumed_today = None
        if first_data_today and get_data_m3:
            try:
                if get_data_m3[0].total is not None and first_data_today.total is not None:
                    total_consumed_today = int(get_data_m3[0].total) - int(first_data_today.total)
                else:
                    total_consumed_today = 0
            except ValueError:
                total_consumed_today = 0


        modules = {
            "m1": InteractionDetailModelSerializer(get_data_m1).data,
            "m2": InteractionDetailModelSerializerNoProcessing(get_data_m2, many=True).data,
            "m22": InteractionDetailModelSerializerNoProcessing(get_data_m22, many=True).data,
            "first_data_today": InteractionDetailModelSerializer(
                first_data_today, many=False
            ).data,
            "today": InteractionDetailModelSerializer(get_data_m3, many=True).data,
            "yesterday": InteractionDetailModelSerializer(get_data_m4, many=True).data,
            "last_data_yesterday": InteractionDetailModelSerializer(
                last_data_yesterday, many=False
            ).data,
            "total_consumed_yesterday": total_consumed_yesterday,
            "total_consumed_today": total_consumed_today,
            "files": FileCatchmentDetailSerializer(get_files, many=True).data,
            "alerts": NotificationsCatchmentDetailSerializer(
                NotificationsCatchment.objects.filter(
                    point_catchment=obj.id, type_notification='ALERT'
                ).all(),
                many=True
            ).data

        }

        return modules

    def get_dga(self, obj):
        get_data = DgaDataConfigCatchment.objects.filter(
            point_catchment=obj).first()
        return DgaCronSerializer(get_data).data

    def get_config_data(self, obj):
        get_data = ProfileDataConfigCatchment.objects.filter(
            point_catchment=obj).first()
        return DataConfigUserSerializer(get_data).data

    def get_profile_ikolu(self, obj):
        get_data = ProfileIkoluCatchment.objects.filter(
            point_catchment=obj).first()
        return ProfileIkoluCatchmentRetrieveSerializer(get_data).data

    class Meta:
        model = CatchmentPoint
        fields = ('id', 'title','frecuency',
                  'profile_ikolu', 'config_data', 'dga', 'modules', 'lat','lon')
