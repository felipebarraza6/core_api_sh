"""
Vista para exportar métricas Prometheus
"""
from django.http import HttpResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from api.core.metrics import update_all_metrics


def prometheus_metrics(request):
    """
    Endpoint /metrics para Prometheus
    Actualiza y exporta todas las métricas
    """
    # Actualizar métricas desde la base de datos
    update_all_metrics()

    # Generar salida en formato Prometheus
    metrics = generate_latest()

    return HttpResponse(
        metrics,
        content_type=CONTENT_TYPE_LATEST
    )
