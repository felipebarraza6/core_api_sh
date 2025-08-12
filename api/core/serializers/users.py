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
        """
        user = self.context['user'].id
        catchment_points = CatchmentPoint.objects.filter(
            models.Q(owner_user=user) | models.Q(users_viewers=user)
        ).distinct().order_by('project','title')
        return CatchmentPointIkoluSerializer(catchment_points, many=True).data

    class Meta:
        """
        Meta class for UserProfile serializer.
        """
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
