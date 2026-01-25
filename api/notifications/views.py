from rest_framework import viewsets, permissions
from .models import Notification, NotificationResponse
from rest_framework import serializers

# Inline serializers for speed/simplicity as these are simple CRUDs
class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'

class NotificationResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationResponse
        fields = '__all__'

class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['point_catchment', 'is_active', 'is_read']

class NotificationResponseViewSet(viewsets.ModelViewSet):
    queryset = NotificationResponse.objects.all()
    serializer_class = NotificationResponseSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['notification']
