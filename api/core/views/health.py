"""Health check and status endpoints without authentication"""
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone


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
