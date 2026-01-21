from rest_framework import serializers
from rest_framework.authtoken.models import Token
from rest_framework.validators import UniqueValidator
from django.contrib.auth import password_validation, authenticate
from django.db import models
from django.db.models import Prefetch
from .catchment_points import CatchmentPointSerializerDetailCron, CatchmentPointIkoluSerializer
from api.core.models import User
from api.crm.models import Person
from api.notifications.models import Notification
from api.documents.models import Document
from api.telemetry.models import CatchmentPoint, TelemetryRecord
from datetime import timedelta
import pytz

class RegisterPersonSerializers(serializers.ModelSerializer):
    class Meta:
        model = Person
        fields = '__all__'

class UserInfoModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('__all__')

class UserProfile(serializers.ModelSerializer):
    catchment_points = serializers.SerializerMethodField()

    def get_catchment_points(self, obj):
        user = self.context['user'].id
        from api.telemetry.models.telemetry import CoreVariable as Variable
        
        catchment_points = CatchmentPoint.objects.filter(
            models.Q(owner_user=user) | models.Q(users_viewers=user)
        ).select_related('technical_survey__project', 'owner_user').distinct().order_by('title')
        
        batch_data = {}
        cp_ids = [cp.id for cp in catchment_points]
        
        if cp_ids:
            from django.utils import timezone
            today = timezone.localtime(timezone.now()).date()
            yesterday = today - timedelta(days=1)
            
            latest_qs = TelemetryRecord.objects.filter(
                point__in=cp_ids
            ).order_by('point', '-timestamp').distinct('point')
            
            latest_map = {rec.point_id: rec for rec in latest_qs}
            batch_data['latest_records'] = latest_map
            today_map = {}
            yesterday_map = {}
            # Optimización simple para evitar loops complejos
            today_qs = TelemetryRecord.objects.filter(
                point__in=cp_ids,
                timestamp__gte=today
            ).order_by('timestamp')
            
            for rec in today_qs:
                if rec.point_id not in today_map:
                    today_map[rec.point_id] = []
                today_map[rec.point_id].append(rec)
            batch_data['today_records'] = today_map

            yesterday_qs = TelemetryRecord.objects.filter(
                point__in=cp_ids,
                timestamp__date=yesterday
            ).order_by('timestamp')
            
            for rec in yesterday_qs:
                if rec.point_id not in yesterday_map:
                    yesterday_map[rec.point_id] = []
                yesterday_map[rec.point_id].append(rec)
            batch_data['yesterday_records'] = yesterday_map
            
            files_map = {}
            for f in Document.objects.filter(point_catchment__in=cp_ids).select_related('point_catchment'):
                if f.point_catchment_id not in files_map:
                    files_map[f.point_catchment_id] = []
                files_map[f.point_catchment_id].append(f)
            batch_data['files'] = files_map

            alerts_map = {}
            for a in Notification.objects.filter(point_catchment__in=cp_ids, type_notification='ALERT'):
                if a.point_catchment_id not in alerts_map:
                    alerts_map[a.point_catchment_id] = []
                alerts_map[a.point_catchment_id].append(a)
            batch_data['alerts'] = alerts_map
            
            dga_start_date = today - timedelta(days=3)
            dga_map = {}
            for rec in TelemetryRecord.objects.filter(point__in=cp_ids, n_voucher__isnull=False, timestamp__gte=dga_start_date).order_by('-timestamp'):
                if rec.point_id not in dga_map:
                    dga_map[rec.point_id] = []
                dga_map[rec.point_id].append(rec)
            batch_data['dga_records'] = dga_map

        ctx = self.context.copy()
        if 'batch_data' not in ctx:
            ctx['batch_data'] = batch_data
            
        return CatchmentPointIkoluSerializer(
            catchment_points, 
            many=True,
            context=ctx
        ).data

    class Meta:
        model = User
        fields = ('id','username', 'first_name', 'last_name',
                  'email', 'catchment_points')

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
            raise serializers.ValidationError('Cuenta de usuario aun no verificada')
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
