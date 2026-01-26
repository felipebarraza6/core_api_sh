"""API V2 URLs - Consolidated."""

from django.urls import include, path

from api.core.urls_v2 import urlpatterns as core_v2_urls
from api.crm.urls import router as crm_router
from api.chatbot.urls import urlpatterns as chatbot_urls
from api.telemetry.providers.urls import urlpatterns as providers_urls

# V2 namespaces for modern, optimized endpoints
urlpatterns = [
    # Core V2 endpoints (dashboard, batch telemetry, etc.)
    path("", include(core_v2_urls)),
    # CRM endpoints
    path("crm/", include(crm_router.urls)),
    # Chatbot endpoints
    path("chat-bot/", include(chatbot_urls)),
    # Providers endpoints
    path("providers/", include(providers_urls)),
]
