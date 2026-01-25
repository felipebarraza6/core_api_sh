import os
import logging
import re
import json
from django.conf import settings
from .tools import (
    search_points, get_point_latest_data, get_client_summary, 
    get_client_measurements, get_point_status_summary, get_dga_compliance,
    get_project_measurements, get_point_config, get_client_alerts,
    get_point_history, get_client_errors, get_global_status,
    get_recent_notifications, compare_points, get_client_stats,
    get_client_ranking, get_stuck_points, get_help_menu, get_timeseries_analysis,
    get_aggregated_metrics
)
from .intent_router import get_routed_intent
from .metrics import log_query_metric, get_metrics_summary
from .cache import get_cached_response, cache_response, get_cache_ttl

logger = logging.getLogger(__name__)

# Intentar importar el SDK de Google Generative AI
try:
    import google.generativeai as genai
    HAS_GEMINI = True
except Exception as e:
    HAS_GEMINI = False
    logger.warning(f"Error al importar google-generativeai: {e}")

# Cache global de arquitectura
ROOT_MAP_CONTEXT = ""

def load_root_map():
    global ROOT_MAP_CONTEXT
    if ROOT_MAP_CONTEXT: return ROOT_MAP_CONTEXT
    try:
        path = os.path.join(settings.BASE_DIR, 'api', 'ROOT_MAP.md')
        with open(path, 'r') as f:
            ROOT_MAP_CONTEXT = f.read()[:2000] # Limite caracteres
    except:
        ROOT_MAP_CONTEXT = "No architecture map available."
    return ROOT_MAP_CONTEXT


def get_conversation_context(user_id):
    """Obtiene el contexto de la conversación desde Redis."""
    try:
        from django_redis import get_redis_connection
        con = get_redis_connection("default")
        context_key = f"chatbot_context:{user_id}"
        context_data = con.get(context_key)
        
        if context_data:
            return json.loads(context_data)
        return {}
    except Exception as e:
        logger.warning(f"Error obteniendo contexto: {e}")
        return {}


def save_conversation_context(user_id, context):
    """Guarda el contexto de la conversación en Redis (TTL 15 minutos)."""
    try:
        from django_redis import get_redis_connection
        con = get_redis_connection("default")
        context_key = f"chatbot_context:{user_id}"
        con.setex(context_key, 900, json.dumps(context))  # 15 minutos
    except Exception as e:
        logger.warning(f"Error guardando contexto: {e}")


def clear_conversation_context(user_id):
    """Limpia el contexto de la conversación."""
    try:
        from django_redis import get_redis_connection
        con = get_redis_connection("default")
        context_key = f"chatbot_context:{user_id}"
        con.delete(context_key)
    except Exception as e:
        logger.warning(f"Error limpiando contexto: {e}")


def resolve_intent_and_respond(user_text, user_name="Usuario", user_id=None):
    """
    Usa Gemini con contexto conversacional para entender qué quiere el usuario.
    ✅ OPTIMIZACIÓN: Incluye caché de respuestas para queries repetidas.
    """
    # ... (rest of logic)

    # ... (skipping to LLM prompt section)
    # ===== CAPA 2: LLM Fallback (Para consultas complejas o sin match) =====
    try:
        genai.configure(api_key=api_key)
        
        arch_context = load_root_map()
        
        model = genai.GenerativeModel(
            'gemini-2.0-flash',
            system_instruction=f"""Asistente de Análisis Avanzado SmartHydro (Español).
Analiza contextos de telemetría de agua para proveer estadísticas rápidas y precisas.
Arquitectura Base: {arch_context[:500]}...

OBJETIVO:
Tu misión es facilitar la toma de decisiones basada en datos. Entiende contextos en ESPAÑOL CHILENO.
Siempre prioriza agrupar datos (sumas, promedios) cuando el usuario pregunte por periodos.

ROLES Y TONO:
- Soporte Interno: Técnico, preciso, ofrece datos de configuración.
- Cliente/Usuario: Ejecutivo, enfocado en "Cuánto agua usé" y "Tengo multas de la DGA?".

HERRAMIENTAS DE ANÁLISIS (Tags):
[AGGREGATE:target|func|field] -> Úsalo para preguntas como "Cuánto sumó...", "Promedio de...", "Total de...".
[STATS:X] -> Para resumen general de un cliente.
[TRENDS:X] -> Para proyección y comportamiento futuro.
[CONFIG:X] -> Para detalles técnicos de hardware.

Reglas de Inferencia:
- "Cuanto se consumió en total hoy": [AGGREGATE:X|sum|consumo]
- "Como se comportó el nivel": [AGGREGATE:X|avg|nivel] o [TRENDS:X]
- "Hay algo raro?": [ANOMALIES:X]
"""
        )


        # ✅ OPTIMIZACIÓN: Prompt compacto
        prompt = f"""Contexto: Cliente='{last_client}', Punto='{context.get('last_point', 'ninguno')}'.
Usuario: {user_name}. Query: "{user_text}"
Responde con 1 tag o texto breve.
"""

        response = model.generate_content(prompt)
        ai_text = response.text
        
        # Función auxiliar para registrar métrica, cachear y retornar
        def log_and_return(response_text, intent_name=None):
            elapsed_ms = (time.time() - start_time) * 1000
            log_query_metric(user_id, user_text, "LLM", elapsed_ms, intent=intent_name)
            
            # ✅ OPTIMIZACIÓN: Cachear respuesta exitosa
            ttl = get_cache_ttl(user_text)
            cache_response(user_text, response_text, last_client, last_point, ttl)
            
            return response_text

        # Handler de Nuevo Intent: Aggregation
        if "[AGGREGATE:" in ai_text:
            match = re.search(r'\[AGGREGATE:(.*?)\|(.*?)\|(.*?)\]', ai_text)
            if match:
                target = match.group(1).strip()
                func = match.group(2).strip()
                field = match.group(3).strip()
                if target.lower() in ('ninguno', 'actual', ''): target = last_point or last_client
                return log_and_return(get_aggregated_metrics(target, func, field, context_client=last_client), "AGGREGATE")

        # 0. Despachar ayuda PRIORITARIO
        if "[HELP]" in ai_text:
            return log_and_return(get_help_menu(), "HELP")

        if "[CLEAR_CONTEXT]" in ai_text:
            clear_conversation_context(user_id)
            return log_and_return("✅ Contexto limpiado. ¿En qué puedo ayudarte ahora?", "CLEAR_CONTEXT")

        # ... (Resto de handlers se mantienen igual) ...
        if "[NOTIFICATIONS]" in ai_text:
            return log_and_return(get_recent_notifications(), "NOTIFICATIONS")

        if "[TRENDS:" in ai_text:
            match = re.search(r'\[TRENDS:(.*?)\]', ai_text)
            if match:
                point_name = match.group(1).strip()
                # Guardar contexto de punto
                context['last_point'] = point_name
                save_conversation_context(user_id, context)
                return log_and_return(get_timeseries_analysis(point_name, context_client=last_client), "TRENDS")
        
        if "[GLOBAL_STATUS]" in ai_text:
            return log_and_return(get_global_status(), "GLOBAL_STATUS")

        # 2. Rankings
        if "[RANKING:" in ai_text:
            match = re.search(r'\[RANKING:(.*?)\|(.*?)\]', ai_text)
            if match:
                cl_name = match.group(1).strip()
                metric = match.group(2).strip()
                if cl_name.lower() in ('ninguno', 'actual', '', 'null'): cl_name = last_client
                m_code = 'CONSUME' if 'CONSUMO' in metric.upper() else 'FLOW'
                return log_and_return(get_client_ranking(cl_name, metric=m_code), "RANKING")

        # 3. Búsqueda de punto específico
        if "[SEARCH:" in ai_text:
            match = re.search(r'\[SEARCH:(.*?)\]', ai_text)
            if match:
                point_query = match.group(1).strip()
                found_points = search_points(point_query, context_client=last_client)
                
                if not found_points:
                    return log_and_return(f"No encontré ningún punto que coincida con '{point_query}'. ¿Podrías verificar el nombre?", "SEARCH_EMPTY")
                
                if len(found_points) == 1:
                    # Guardar contexto
                    p_data = found_points[0]
                    context['last_point'] = p_data['title']
                    context['last_client'] = p_data['client']
                    save_conversation_context(user_id, context)
                    return log_and_return(get_point_latest_data(p_data['id']), "SEARCH_POINT")
                else:
                    res = "Encontré varios puntos similares. ¿A cuál te refieres?\n"
                    for p in found_points[:8]:
                        is_context = last_client and last_client.lower() in p['client'].lower()
                        prefix = "🔹" if is_context else "•"
                        res += f"{prefix} {p['title']} (Cliente: {p['client']})\n"
                    return log_and_return(res, "SEARCH_MULTIPLE")

        # 4. Mediciones de proyecto específico
        if "[PROJECT_MEASUREMENTS:" in ai_text:
            match = re.search(r'\[PROJECT_MEASUREMENTS:(.*?)\|(.*?)\]', ai_text)
            if match:
                client_name = match.group(1).strip()
                project_name = match.group(2).strip()
                context['last_client'] = client_name
                save_conversation_context(user_id, context)
                return log_and_return(get_project_measurements(client_name, project_name), "PROJECT_MEASUREMENTS")

        # 5. Mediciones de cliente completo
        if "[MEASUREMENTS:" in ai_text:
            match = re.search(r'\[MEASUREMENTS:(.*?)\]', ai_text)
            if match:
                client_name = match.group(1).strip()
                context['last_client'] = client_name
                save_conversation_context(user_id, context)
                return log_and_return(get_client_measurements(client_name), "MEASUREMENTS")

        # 6. DGA compliance
        if "[DGA:" in ai_text:
            match = re.search(r'\[DGA:(.*?)\]', ai_text)
            if match:
                client_name = match.group(1).strip()
                context['last_client'] = client_name
                save_conversation_context(user_id, context)
                return log_and_return(get_dga_compliance(client_name), "DGA")

        # 7. Configuración de punto
        if "[CONFIG:" in ai_text:
            match = re.search(r'\[CONFIG:(.*?)\]', ai_text)
            if match:
                point_name = match.group(1).strip()
                context['last_point'] = point_name
                save_conversation_context(user_id, context)
                return log_and_return(get_point_config(point_name, context_client=last_client), "CONFIG")

        # 8. Historial de punto
        if "[HISTORY:" in ai_text:
            match = re.search(r'\[HISTORY:(.*?)\]', ai_text)
            if match:
                point_name = match.group(1).strip()
                context['last_point'] = point_name
                save_conversation_context(user_id, context)
                return log_and_return(get_point_history(point_name, context_client=last_client), "HISTORY")

        # 9. Alertas de cliente
        if "[ALERTS:" in ai_text:
            match = re.search(r'\[ALERTS:(.*?)\]', ai_text)
            if match:
                cl_name = match.group(1).strip()
                if cl_name.lower() in ('ninguno', 'actual', ''): cl_name = last_client
                return log_and_return(get_client_alerts(cl_name), "ALERTS")

        # 10. Estadísticas de cliente
        if "[STATS:" in ai_text:
            match = re.search(r'\[STATS:(.*?)\]', ai_text)
            if match:
                cl_name = match.group(1).strip()
                if cl_name.lower() in ('ninguno', 'actual', ''): cl_name = last_client
                return log_and_return(get_client_stats(cl_name), "STATS")

        # 11. Comparación entre puntos
        if "[COMPARE:" in ai_text:
            match = re.search(r'\[COMPARE:(.*?)\|(.*?)\]', ai_text)
            if match:
                p1 = match.group(1).strip()
                p2 = match.group(2).strip()
                return log_and_return(compare_points(p1, p2, context_client=last_client), "COMPARE")

        # 12. Anomalías / Puntos pegados
        if "[ANOMALIES:" in ai_text:
            match = re.search(r'\[ANOMALIES:(.*?)\]', ai_text)
            if match:
                cl_name = match.group(1).strip()
                if cl_name.lower() in ('ninguno', 'actual', ''): cl_name = last_client
                return log_and_return(get_stuck_points(cl_name), "ANOMALIES")

        # 13. Lista de puntos de cliente
        if "[CLIENT:" in ai_text:
            match = re.search(r'\[CLIENT:(.*?)\]', ai_text)
            if match:
                client_name = match.group(1).strip()
                context['last_client'] = client_name
                save_conversation_context(user_id, context)
                return log_and_return(get_client_summary(client_name), "CLIENT")

        # Si no hay tags, es una respuesta directa
        return log_and_return(ai_text, "LLM_DIRECT")

    except Exception as e:
        logger.error(f"Error en Gemini: {e}")
        if "429" in str(e) or "quota" in str(e).lower():
            return "⚠️ He alcanzado mi límite de consultas. Por favor, espera unos segundos e inténtalo de nuevo."

