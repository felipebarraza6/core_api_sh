"""URls Core"""
from django.contrib import admin
from django.urls import path, include, re_path

from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve


# Cambia a tu título personalizado
admin.site.site_header = "Control Telemetria"
admin.site.site_title = "Control Telemetria"  # Cambia a tu título personalizado
admin.site.index_title = "Control Telemetria"

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(('api.core.router', 'api'), namespace='api')),
    re_path(r'^media/(?P<path>.*)$', serve,
            {'document_root': settings.MEDIA_ROOT}),
    path('api/password_reset/', include('django_rest_passwordreset.urls', namespace='password_reset')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
