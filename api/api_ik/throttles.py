"""
Throttles personalizados para la API Ikolu.
"""
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """
    Throttle restrictivo para el endpoint de login.
    Previene fuerza bruta contra credenciales.
    """
    rate = "10/minute"
    scope = "login"


class BackfillRateThrottle(UserRateThrottle):
    """
    Throttle para el endpoint de backfill histórico.
    Es costoso (consulta APIs externas), por lo que se limita fuertemente.
    """
    rate = "5/minute"
    scope = "backfill"


class BatchRateThrottle(UserRateThrottle):
    """
    Throttle para endpoints batch (telemetry, stats).
    Consultan interactiondetail con múltiples puntos.
    """
    rate = "30/minute"
    scope = "batch"


class SummaryRateThrottle(UserRateThrottle):
    """
    Throttle para endpoints de resumen (points_summary, point_summary, my_points).
    Muy usados por el frontend del Centro de Control.
    """
    rate = "60/minute"
    scope = "summary"


class DashboardRateThrottle(UserRateThrottle):
    """
    Throttle para endpoints de dashboard (stats, calendar).
    """
    rate = "30/minute"
    scope = "dashboard"


class TicketRateThrottle(UserRateThrottle):
    """
    Throttle para endpoints de tickets (CRUD + comentarios + asignación).
    """
    rate = "120/minute"
    scope = "ticket"


class PublicReadRateThrottle(AnonRateThrottle):
    """
    Throttle para endpoints públicos de solo lectura (announcements).
    """
    rate = "30/minute"
    scope = "public_read"
