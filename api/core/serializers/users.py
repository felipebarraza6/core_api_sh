# Django REST Framework
from rest_framework import serializers
from rest_framework.authtoken.models import Token
from rest_framework.validators import UniqueValidator

# Django
from django.contrib.auth import password_validation, authenticate
from django.core.validators import RegexValidator
from django.db import models  # Importar models
from .catchment_points import CatchmentPointSerializerDetailCron, CatchmentPointIkoluSerializer

# Models
from api.core.models import User, RegisterPersons, CatchmentPoint
from api.core.models.interaction_detail import InteractionDetail
from api.core.models.catchment_points import FileCatchment, NotificationsCatchment
from datetime import datetime, timedelta
import pytz


class RegisterPersonSerializers(serializers.ModelSerializer):
    class Meta:
        model = RegisterPersons
        fields = '__all__'


class UserInfoModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('__all__')


class UserProfile(serializers.ModelSerializer):
    """
    Serializer for user profile information.
    """
    catchment_points = serializers.SerializerMethodField()

    def get_catchment_points(self, obj):
        """
        Retrieve catchment points if the user is authorized.
        ✅ Optimización: Usar select_related y prefetch_related para evitar N+1 queries.
        ✅ MEJORADO: Optimización agresiva con prefetch_related para mejorar rendimiento con grandes volúmenes.
        """
        user = self.context['user'].id
        # ✅ Optimización: select_related para project y owner_user
        # ✅ MEJORADO: Prefetch más agresivo para optimizar serialización masiva
        # ✅ prefetch_related para relaciones ManyToMany y ForeignKey inversas
        from django.db.models import Prefetch
        from api.core.models import ProfileDataConfigCatchment, SchemesCatchment, Variable, ProfileIkoluCatchment, DgaDataConfigCatchment
        
        catchment_points = CatchmentPoint.objects.filter(
            models.Q(owner_user=user) | models.Q(users_viewers=user)
        ).select_related('project', 'owner_user').prefetch_related(
            # ✅ Optimización: Prefetch específico para ProfileIkoluCatchment
            Prefetch(
                'ikolu_profiles',
                queryset=ProfileIkoluCatchment.objects.only(
                    'point_catchment_id', 'entry_by_form', 'm1', 'm2', 'm3', 'm4', 'm5', 'm6'
                )
            ),
            # ✅ Optimización: Prefetch específico para ProfileDataConfigCatchment
            Prefetch(
                'data_config_profiles',
                queryset=ProfileDataConfigCatchment.objects.only(
                    'point_catchment_id', 'd1', 'd2', 'd3', 'd4', 'd5', 'd6',
                    'date_start_telemetry', 'date_delivery_act', 'is_telemetry'
                )
            ),
            # ✅ Optimización: Prefetch específico para DgaDataConfigCatchment
            Prefetch(
                'dga_data_config_profiles',
                queryset=DgaDataConfigCatchment.objects.only(
                    'point_catchment_id', 'send_dga', 'standard', 'type_dga', 'code_dga',
                    'flow_granted_dga', 'total_granted_dga', 'shac', 'date_start_compliance',
                    'date_created_code'
                )
            ),
            # ✅ Optimización: Prefetch anidado para Schemes y Variables
            Prefetch(
                'schemes',
                queryset=SchemesCatchment.objects.prefetch_related(
                    Prefetch(
                        'variables',  # ✅ FIX: Cambiar variable_set por variables (related_name correcto)
                        queryset=Variable.objects.only(
                            'id', 'str_variable', 'label', 'type_variable', 'service',
                            'pulses_factor', 'convert_to_lt', 'calculate_nivel',
                            'token_service', 'scheme_catchment_id'
                        )
                    )
                )
            )
        ).distinct().order_by('project','title')
        
        # ✅ BATCH FETCHING STRATEGY (Optimización Fase 2)
        # En lugar de que el serializer hijo haga N queries, hacemos las queries aquí
        # para todos los puntos y las pasamos en memoria.
        
        batch_data = {}
        cp_ids = [cp.id for cp in catchment_points]
        
        if cp_ids:
            from django.utils import timezone
            today = timezone.localtime(timezone.now()).date()
            yesterday = today - timedelta(days=1)
            
            # 1. Latest Record per Point (Distinct on catchment_point)
            # Solo Postgres soporta distinct('field'), asumimos Postgres por el entorno
            latest_qs = InteractionDetail.objects.filter(
                catchment_point__in=cp_ids
            ).order_by('catchment_point', '-date_time_medition').distinct('catchment_point')
            
            # Map: point_id -> record
            latest_map = {rec.catchment_point_id: rec for rec in latest_qs}
            batch_data['latest_records'] = latest_map

            # 2. Today's Records (All records for consumption calc)
            today_qs = InteractionDetail.objects.filter(
                catchment_point__in=cp_ids,
                date_time_medition__range=(today, timezone.now())
            ).order_by('date_time_medition')
            
            # Map: point_id -> list of records
            today_map = {}
            for rec in today_qs:
                if rec.catchment_point_id not in today_map:
                    today_map[rec.catchment_point_id] = []
                today_map[rec.catchment_point_id].append(rec)
            batch_data['today_records'] = today_map

            # 3. Yesterday's Records
            yesterday_qs = InteractionDetail.objects.filter(
                catchment_point__in=cp_ids,
                date_time_medition__date=yesterday
            ).order_by('date_time_medition')
            
            yesterday_map = {}
            for rec in yesterday_qs:
                if rec.catchment_point_id not in yesterday_map:
                    yesterday_map[rec.catchment_point_id] = []
                yesterday_map[rec.catchment_point_id].append(rec)
            batch_data['yesterday_records'] = yesterday_map
            
            # 4. Files
            files_qs = FileCatchment.objects.filter(point_catchment__in=cp_ids).select_related('point_catchment')
            files_map = {}
            for f in files_qs:
                if f.point_catchment_id not in files_map:
                    files_map[f.point_catchment_id] = []
                files_map[f.point_catchment_id].append(f)
            batch_data['files'] = files_map

            # 5. Alerts
            alerts_qs = NotificationsCatchment.objects.filter(
                point_catchment__in=cp_ids, 
                type_notification='ALERT'
            )
            alerts_map = {}
            for a in alerts_qs:
                if a.point_catchment_id not in alerts_map:
                    alerts_map[a.point_catchment_id] = []
                alerts_map[a.point_catchment_id].append(a)
            batch_data['alerts'] = alerts_map
            
            # 6. DGA Data (Last 48 records approx)
            # Fetching last 2 days of DGA data for all points
            # Lógica simplificada para batch: traer data DGA de los últimos 3 días
            dga_start_date = today - timedelta(days=3)
            dga_qs = InteractionDetail.objects.filter(
                catchment_point__in=cp_ids,
                return_dga__isnull=False,
                date_time_medition__gte=dga_start_date
            ).order_by('-date_time_medition')
            
            dga_map = {}
            # Como vamos a necesitar los últimos 48, recolectamos todo en lista y luego sliceamos en el hijo
            for rec in dga_qs:
                if rec.catchment_point_id not in dga_map:
                    dga_map[rec.catchment_point_id] = []
                dga_map[rec.catchment_point_id].append(rec)
            batch_data['dga_records'] = dga_map

        # ✅ MEJORADO: Pasar contexto con user y batch_data para optimizaciones adicionales
        ctx = self.context.copy()
        if 'batch_data' not in ctx:
            ctx['batch_data'] = batch_data
            
        return CatchmentPointIkoluSerializer(
            catchment_points, 
            many=True,
            context=ctx
        ).data

    class Meta:
        """
        Meta class for UserProfile serializer.
        """
        model = User
        fields = ('id','username', 'first_name', 'last_name',
                  'email', 'is_superuser', 'is_staff', 'is_client_admin', 'catchment_points')


class CatchmentPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatchmentPoint
        fields = '__all__'


class UserModelSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = '__all__'


class UserLoginSerializer(serializers.Serializer):

    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, max_length=64)

    def validate(self, data):
        user = authenticate(username=data['email'], password=data['password'])
        if not user:
            raise serializers.ValidationError('Credenciales Invalidas')
        if not user.is_verified:
            raise serializers.ValidationError(
                'Cuenta de usuario aun no verificada')
        self.context['user'] = user
        return data

    def create(self, data):
        token, created = Token.objects.get_or_create(user=self.context['user'])
        return self.context['user'], token.key


class UserSignUpSerializer(serializers.Serializer):

    email = serializers.EmailField(
        validators=[UniqueValidator(queryset=User.objects.all())]
    )

    username = serializers.CharField(
        min_length=4,
        max_length=20,
        validators=[UniqueValidator(queryset=User.objects.all())]
    )
    password = serializers.CharField(min_length=8, max_length=64)
    password_confirmation = serializers.CharField(min_length=8, max_length=64)

    def validate(self, data):
        passwd = data['password']
        passwd_conf = data['password_confirmation']
        if passwd != passwd_conf:
            raise serializers.ValidationError("Contraseñas no coinciden")
        password_validation.validate_password(passwd)
        return data

    def create(self, data):
        data.pop('password_confirmation')
        user = User.objects.create_user(**data, is_active=True)
        return user
