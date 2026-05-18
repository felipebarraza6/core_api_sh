"""
Throttles personalizados para la API Ikolu.
"""
from rest_framework.throttling import AnonRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """
    Throttle restrictivo para el endpoint de login.
    Previene fuerza bruta contra credenciales.
    """
    rate = "10/minute"
    scope = "login"
