"""
Vistas personalizadas para Django Admin (Simplificadas)
======================================================

Este archivo se ha simplificado temporalmente para facilitar la migración
al nuevo sistema dinámico V3.
"""

import logging
from django.http import JsonResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)

def safe_float(value, default=0.0):
    """Convierte un valor a float de forma segura."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default
