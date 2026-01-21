"""Catchment Points views."""

from django_filters import rest_framework as filters
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from api.telemetry.models.telemetry import CoreVariable
from api.telemetry.models.catchment_points import (
    CatchmentPoint,
)
from api.crm.models import Client, Project, Person
from api.notifications.models import Notification, NotificationResponse
from api.documents.models import DocumentType, Document

from api.core.serializers.catchment_points import (
    CatchmentPointIkoluSerializer,
    CatchmentPointSerializer,
    CatchmentPointSerializerDetailCron,
    ClientSerializer,
    DocumentSerializer,
    NotificationSerializer,
    ProjectSerializer,
    PersonSerializer,
    NotificationResponseDetailSerializer,
    NotificationResponseSerializer,
    DocumentTypeSerializer,
    VariableSerializer,
)


class ClientViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    lookup_field = "id"


class ProjectViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    lookup_field = "id"


class CatchmentPointViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = CatchmentPoint.objects.select_related(
        "owner_user"
    )
    serializer_class = CatchmentPointSerializer
    lookup_field = "id"

    def get_serializer_class(self):
        if self.action in ["retrieve"]:
            return CatchmentPointIkoluSerializer
        return CatchmentPointSerializer


# ProfileIkoluCatchmentViewSet removed


class NotificationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = Notification.objects.all().order_by("-created")
    serializer_class = NotificationSerializer
    lookup_field = "id"

    class FilterNotification(filters.FilterSet):
        class Meta:
            model = Notification
            fields = {
                "point_catchment": ["exact"],
                "type_variable": ["exact"],
                "type_notification": ["exact"],
                "type_alert": ["exact"],
                "is_active": ["exact"],
                "is_read": ["exact"],
                "is_response": ["exact"],
                "is_finish": ["exact"],
                "is_wait": ["exact"],
            }

    filterset_class = FilterNotification


class NotificationResponseViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = NotificationResponse.objects.all().order_by("-created")
    serializer_class = NotificationResponseSerializer
    lookup_field = "id"

    def get_serializer_class(self):
        if self.action in ["list"]:
            return NotificationResponseDetailSerializer
        return NotificationResponseSerializer


class DocumentTypeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = DocumentType.objects.all()
    serializer_class = DocumentTypeSerializer
    lookup_field = "id"


class DocumentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    lookup_field = "id"


# ProfileDataConfigCatchmentViewSet removed




class CoreVariableViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = CoreVariable.objects.all()
    serializer_class = VariableSerializer
    lookup_field = "id"
    filterset_fields = ["point", "internal_code", "is_active", "is_virtual"]


class PersonViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = (filters.DjangoFilterBackend,)
    queryset = Person.objects.all()
    serializer_class = PersonSerializer
    lookup_field = "id"
