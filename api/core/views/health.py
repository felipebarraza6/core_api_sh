from django.http import JsonResponse
from django.db import connection

def health_check(request):
    """
    Simple health check endpoint to verify that the application and database are running.
    """
    health_status = {
        "status": "healthy",
        "database": "connected",
        "services": {
            "django": "ok"
        }
    }
    
    # Check database connection
    try:
        connection.ensure_connection()
        if not connection.is_usable():
             health_status["database"] = "unusable"
             health_status["status"] = "degraded"
    except Exception as e:
        health_status["database"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"
        return JsonResponse(health_status, status=503)

    return JsonResponse(health_status)
