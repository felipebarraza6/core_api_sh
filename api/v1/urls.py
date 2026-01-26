"""API V1 URLs."""

from django.urls import include, path

from api.core.router import router as core_router

# V1 namespaces to maintain backward compatibility for legacy endpoints
urlpatterns = [
    path("", include(core_router.urls)),
]
