"""
Vistas del portal de documentación pública.

Sirven HTML estático con CSS inline (sin dependencias externas)
para evitar problemas de CSP y garantizar que cargue siempre.
"""
from django.views.generic import TemplateView


class DocsPortalView(TemplateView):
    """Portal de documentación técnica SmartHydro API."""

    template_name = "docs/index.html"


class SalesDocsPortalView(TemplateView):
    """Portal de ventas y casos de uso SmartHydro."""

    template_name = "docs/sales.html"


class MathContextDocsPortalView(TemplateView):
    """Portal de contexto matemático e investigación SmartHydro."""

    template_name = "docs/math.html"
