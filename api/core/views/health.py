"""Health check and status endpoints without authentication"""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from api.core.tasks.health_tasks import ping_celery


@csrf_exempt
def health_check(request):
    """
    Health check endpoint for monitoring and toolbox audits.

    Returns:
        200 OK with JSON containing status, service name, and timestamp
        No authentication required
        No database queries
    """
    return JsonResponse({
        'status': 'ok',
        'service': 'SmartHydro API',
        'timestamp': timezone.now().isoformat()
    })


@csrf_exempt
def celery_health_check(request):
    """
    Health check de Celery: encola una tarea de prueba y espera respuesta.

    Returns:
        200 OK si Celery responde correctamente
        503 Service Unavailable si no se puede contactar al broker/worker
    """
    try:
        result = ping_celery.delay()
        response_data = result.get(timeout=10)
        return JsonResponse({
            'status': 'ok',
            'celery': 'ok',
            'task_id': response_data.get('task_id'),
            'result': response_data.get('pong'),
            'timestamp': timezone.now().isoformat()
        })
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({
            'status': 'error',
            'celery': 'unavailable',
            'error': str(exc),
            'timestamp': timezone.now().isoformat()
        }, status=503)


@csrf_exempt
def index(request):
    """
    Root endpoint providing basic system information.

    Returns:
        200 OK with JSON containing service info and available endpoints
        No authentication required
        No database queries
    """
    return JsonResponse({
        'service': 'SmartHydro API',
        'version': '1.0',
        'status': 'operational',
        'endpoints': {
            'legacy_api': '/api/',
            'optimized_api': '/api/ik/',
            'admin': '/admin/',
            'health': '/health/'
        },
        'timestamp': timezone.now().isoformat()
    })
