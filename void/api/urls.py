"""URLs for void API."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views
from .viewsets import (
    AlertRuleViewSet,
    AlertTriggerViewSet,
    ComplianceAuthorityViewSet,
    ComplianceStandardViewSet,
    DeviceViewSet,
    PointComplianceProfileViewSet,
    PointViewSet,
    ProjectViewSet,
    ProviderViewSet,
    VoidUserProfileViewSet,
)

router = DefaultRouter()
router.register(r"users", VoidUserProfileViewSet, basename="voiduserprofile")
router.register(r"projects", ProjectViewSet, basename="project")
router.register(r"points", PointViewSet, basename="point")
router.register(r"devices", DeviceViewSet, basename="device")
router.register(r"providers", ProviderViewSet, basename="provider")
router.register(r"alerts/rules", AlertRuleViewSet, basename="alertrule")
router.register(r"alerts/triggers", AlertTriggerViewSet, basename="alerttrigger")
router.register(r"compliance/authorities", ComplianceAuthorityViewSet, basename="complianceauthority")
router.register(r"compliance/standards", ComplianceStandardViewSet, basename="compliancestandard")
router.register(r"compliance/profiles", PointComplianceProfileViewSet, basename="pointcomplianceprofile")

app_name = "void"

urlpatterns = [
    path("auth/", include("void.api.auth.urls")),
    path("health/", views.health_check, name="health"),
    path("ingest/", views.ingest_reading, name="ingest"),
    path("compliance/submit/", views.compliance_submit, name="compliance_submit"),
    path("compliance/submissions/", views.compliance_submissions, name="compliance_submissions"),
    path("compliance/queue/", views.compliance_queue, name="compliance_queue"),
    path("", include(router.urls)),
]
