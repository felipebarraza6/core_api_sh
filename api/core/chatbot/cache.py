"""
Response Cache Module for SmartHydro Chatbot
=============================================

Implements intelligent caching of chatbot responses to reduce redundant
LLM calls and improve response times.

Features:
- TTL-based expiration (default 5 minutes)
- Hash-based keys for similar queries
- Automatic invalidation for time-sensitive data
"""

import hashlib
import logging
from django_redis import get_redis_connection

logger = logging.getLogger(__name__)

def _normalize_query(text):
    """
    Normaliza una consulta para generar una clave de caché consistente.
    """
    # Minúsculas y trim
    normalized = text.lower().strip()
    
    # Remover variaciones temporales que no afectan la respuesta
    time_words = ['hoy', 'ahora', 'actual', 'ultimo']
    for word in time_words:
        normalized = normalized.replace(word, '')
    
    # Limpiar espacios extra
    normalized = ' '.join(normalized.split())
    return normalized


def _get_cache_key(user_text, context_client=None, context_point=None):
    """
    Genera una clave de caché única basada en la consulta y contexto.
    """
    # Normalizar texto
    norm_text = _normalize_query(user_text)
    
    # Incluir contexto en la clave
    cache_input = f"{norm_text}|{context_client or ''}|{context_point or ''}"
    
    # Hash MD5 para clave compacta
    key_hash = hashlib.md5(cache_input.encode()).hexdigest()[:12]
    
    return f"chatbot:cache:{key_hash}"


def get_cached_response(user_text, context_client=None, context_point=None):
    """
    Intenta obtener una respuesta cacheada.
    
    Args:
        user_text: Texto de la consulta del usuario
        context_client: Cliente en foco (opcional)
        context_point: Punto en foco (opcional)
        
    Returns:
        str: Respuesta cacheada o None si no existe
    """
    try:
        con = get_redis_connection("default")
        cache_key = _get_cache_key(user_text, context_client, context_point)
        
        cached = con.get(cache_key)
        if cached:
            logger.info(f"✅ Cache hit for: {user_text[:50]}...")
            return cached.decode('utf-8') if isinstance(cached, bytes) else cached
        
        return None
    
    except Exception as e:
        logger.warning(f"Error reading from cache: {e}")
        return None


def cache_response(user_text, response_text, context_client=None, context_point=None, ttl=300):
    """
    Cachea una respuesta exitosa.
    
    Args:
        user_text: Texto de la consulta
        response_text: Texto de la respuesta
        context_client: Cliente en foco
        context_point: Punto en foco
        ttl: Time-to-live en segundos (default: 5 minutos)
    """
    try:
        # No cachear mensajes de error
        if any(err in response_text.lower() for err in ['error', 'no encontré', 'no encontrado']):
            return
        
        # No cachear respuestas muy cortas (probablemente incompletas)
        if len(response_text) < 20:
            return
        
        con = get_redis_connection("default")
        cache_key = _get_cache_key(user_text, context_client, context_point)
        
        con.setex(cache_key, ttl, response_text)
        logger.info(f"💾 Cached response for: {user_text[:50]}...")
    
    except Exception as e:
        logger.warning(f"Error caching response: {e}")


def should_cache(user_text):
    """
    Determina si una consulta debería ser cacheada.
    
    Queries time-sensitive (como "estado", "hoy", "ahora") no se cachean
    o usan TTL muy corto.
    """
    # Keywords que indican datos en tiempo real (no cachear o TTL corto)
    realtime_keywords = ['estado', 'drama', 'hoy', 'ahora', 'actual', 'último']
    
    norm = user_text.lower()
    if any(kw in norm for kw in realtime_keywords):
        return False
    
    # Consultas de configuración, historial, DGA son seguras para cachear
    return True


def get_cache_ttl(user_text):
    """
    Retorna el TTL apropiado según el tipo de consulta.
    """
    norm = user_text.lower()
    
    # Datos en tiempo real: 1 minuto
    if any(kw in norm for kw in ['estado', 'drama', 'alertas', 'novedades']):
        return 60
    
    # Mediciones: 3 minutos
    if any(kw in norm for kw in ['mediciones', 'hoy', 'actual']):
        return 180
    
    # Configuración, DGA, historial: 15 minutos
    if any(kw in norm for kw in ['config', 'dga', 'historial', 'parametro']):
        return 900
    
    # Default: 5 minutos
    return 300
