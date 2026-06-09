"""Status and monitoring views for SmartHydro API."""

import time
import os
from datetime import timedelta
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import connection
from django.core.cache import cache


@login_required
@csrf_exempt
def status_json(request):
    """JSON endpoint for monitoring tools and API integrations."""
    start_time = time.time()

    # Check all services
    services = {
        'api': check_api(),
        'database': check_database(),
        'cache': check_redis(),
        'cronjobs': check_cronjobs()
    }

    # Get system statistics
    stats = get_system_statistics()

    # Determine overall status
    overall_status = determine_overall_status(services)

    response_time = (time.time() - start_time) * 1000

    return JsonResponse({
        'status': overall_status,
        'timestamp': timezone.now().isoformat(),
        'response_time_ms': round(response_time, 2),
        'services': services,
        'statistics': stats
    })


@login_required
@csrf_exempt
def status_dashboard(request):
    """HTML dashboard for clients to view system status."""
    start_time = time.time()

    # Check all services
    services = {
        'api': check_api(),
        'database': check_database(),
        'cache': check_redis(),
        'cronjobs': check_cronjobs()
    }

    # Get system statistics
    stats = get_system_statistics()

    # Determine overall status
    overall_status = determine_overall_status(services)

    response_time = (time.time() - start_time) * 1000

    context = {
        'status': overall_status,
        'timestamp': timezone.now(),
        'response_time': round(response_time, 2),
        'services': services,
        'statistics': stats,
        'auto_refresh': 30  # seconds
    }

    return render(request, 'status/dashboard.html', context)


def check_api():
    """Check Django API health."""
    return {
        'status': 'operational',
        'name': 'SmartHydro API',
        'description': 'REST API principal',
        'icon': '🔌'
    }


def check_database():
    """Check PostgreSQL database connection."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        # Get connection count
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_stat_activity")
            conn_count = cursor.fetchone()[0]

        return {
            'status': 'operational',
            'name': 'PostgreSQL',
            'description': 'Base de datos principal',
            'connections': conn_count,
            'icon': '🗄️'
        }
    except Exception as e:
        return {
            'status': 'outage',
            'name': 'PostgreSQL',
            'description': 'Base de datos principal',
            'error': str(e),
            'icon': '🗄️'
        }


def check_redis():
    """Check Redis cache connection."""
    try:
        # Try to set and get a test key
        cache.set('health_check', 'ok', 10)
        result = cache.get('health_check')

        return {
            'status': 'operational' if result == 'ok' else 'degraded',
            'name': 'Redis Cache',
            'description': 'Sistema de caché',
            'icon': '⚡'
        }
    except Exception as e:
        return {
            'status': 'degraded',
            'name': 'Redis Cache',
            'description': 'Sistema de caché',
            'error': str(e),
            'icon': '⚡'
        }


def check_cronjobs():
    """Check cronjob status by reading log file timestamps."""
    try:
        log_files = [
            '/tmp/smarthydro/unified_twin_1.log',
            '/tmp/smarthydro/dga.log',
            '/tmp/smarthydro/sma.log'
        ]

        recent_activity = False
        for log_file in log_files:
            if os.path.exists(log_file):
                try:
                    mtime = os.path.getmtime(log_file)
                    age = time.time() - mtime
                    if age < 600:  # Modified in last 10 minutes
                        recent_activity = True
                        break
                except (OSError, IOError):
                    continue

        status = 'operational' if recent_activity else 'degraded'

        return {
            'status': status,
            'name': 'Cronjobs',
            'description': 'Tareas programadas (telemetría, DGA, SMA)',
            'active': recent_activity,
            'icon': '⏱️'
        }
    except Exception as e:
        return {
            'status': 'degraded',
            'name': 'Cronjobs',
            'description': 'Tareas programadas',
            'error': str(e),
            'icon': '⏱️'
        }


def get_system_statistics():
    """Get system statistics from database."""
    from api.core.models import CatchmentPoint, InteractionDetail

    try:
        total_points = CatchmentPoint.objects.count()
        # 'Activo' = punto con telemetría habilitada (criterio usado por management)
        active_points = CatchmentPoint.objects.filter(
            data_config_profiles__is_telemetry=True
        ).distinct().count()

        # Records in last 24h
        yesterday = timezone.now() - timedelta(hours=24)
        records_24h = InteractionDetail.objects.filter(
            date_time_medition__gte=yesterday
        ).count()

        # DGA queue size (pending DGA transmission)
        dga_queue = InteractionDetail.objects.filter(
            send_dga=True
        ).exclude(catchment_point=1).count()

        return {
            'total_points': total_points,
            'active_points': active_points,
            'records_24h': records_24h,
            'dga_queue': dga_queue
        }
    except Exception:
        # Graceful fallback if query fails
        return {
            'total_points': 0,
            'active_points': 0,
            'records_24h': 0,
            'dga_queue': 0
        }


def determine_overall_status(services):
    """Determine overall system status from individual service statuses."""
    statuses = [s['status'] for s in services.values()]

    if any(s == 'outage' for s in statuses):
        return 'outage'
    elif any(s == 'degraded' for s in statuses):
        return 'degraded'
    else:
        return 'operational'
