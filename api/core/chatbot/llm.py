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
    get_telemetry_audit
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
    if not HAS_GEMINI:
        return f"Hola {user_name}. Actualmente mi motor de inteligencia está en mantenimiento (falta SDK). Pero puedo decirte que recibí: '{user_text}'"

    api_key = getattr(settings, 'GEMINI_API_KEY', os.environ.get('GEMINI_API_KEY'))
    
    if not api_key:
        return "Configuración incompleta: falta GEMINI_API_KEY en los ajustes del servidor."

    # Obtener contexto previo
    if not user_id:
        user_id = user_name
    
    context = get_conversation_context(user_id)
    last_client = context.get('last_client', 'ninguno')
    last_points = context.get('last_points', [])
    last_point = context.get('last_point', None)
    
    # ✅ CAPA 0: Caché de Respuestas (Nuevo - máxima prioridad)
    cached_response = get_cached_response(user_text, last_client, last_point)
    if cached_response:
        logger.info(f"⚡ Returning cached response for: {user_text[:30]}...")
        return cached_response
    
    import time
    start_time = time.time()
    
    # ===== CAPA 1: Intent Router (Pre-clasificación Determinista) =====
    routed_intent = get_routed_intent(user_text)
    
    if routed_intent:
        result = None
        
        if routed_intent == "GLOBAL_STATUS":
            result = get_global_status()
        elif routed_intent == "NOTIFICATIONS":
            result = get_recent_notifications()
        elif routed_intent == "HELP":
            result = get_help_menu()
        elif routed_intent == "METRICS":
            result = get_metrics_summary()
        elif routed_intent == "CLEAR_CONTEXT":
            clear_conversation_context(user_id)
            result = "✅ Contexto limpiado. ¿En qué puedo ayudarte ahora?"

        elif routed_intent == "TELEMETRY_AUDIT":
            result = get_telemetry_audit(days=30, show_all=True)

        elif routed_intent == "RANKING":
            # Intentar extraer param
            clean = re.sub(r'\b(ranking|top|consumo)\b', '', user_text, flags=re.IGNORECASE).strip()
            target = clean if clean else last_client
            if target and target != 'ninguno':
                result = get_client_ranking(target, metric='CONSUME')
                
        elif routed_intent == "STATS":
            clean = re.sub(r'\b(stats|estadisticas|consumo)\b', '', user_text, flags=re.IGNORECASE).strip()
            target = clean if clean else last_client
            if target and target != 'ninguno':
                result = get_client_stats(target)
                
        elif routed_intent == "ANOMALIES":
            clean = re.sub(r'\b(anomalias|pegados)\b', '', user_text, flags=re.IGNORECASE).strip()
            target = clean if clean else last_client
            if target and target != 'ninguno':
                result = get_stuck_points(target)
                
        elif routed_intent == "TRENDS":
            clean = re.sub(r'\b(tendencia|comportamiento|como viene)\b', '', user_text, flags=re.IGNORECASE).strip()
            target = clean if clean else last_point
            if target:
                result = get_timeseries_analysis(target, context_client=last_client)
                
        elif routed_intent == "HISTORY":
            clean = re.sub(r'\b(ver|mostrar|traer|historial|datos|registros)\b', '', user_text, flags=re.IGNORECASE).strip()
            if clean:
                result = get_point_history(clean, context_client=last_client)
            elif last_point:
                result = get_point_history(last_point, context_client=last_client)
            elif last_client and last_client != 'ninguno':
                result = get_client_measurements(last_client)

        elif routed_intent == "CONFIG":
            clean = re.sub(r'\b(ver|mostrar|dame|configuracion|configuración|config|parametros)\b', '', user_text, flags=re.IGNORECASE).strip()
            target = clean if clean else last_point
            if target:
                result = get_point_config(target, context_client=last_client)

        elif routed_intent == "DGA":
            clean = re.sub(r'\b(dga|normativa|cumplimiento|vouchers)\b', '', user_text, flags=re.IGNORECASE).strip()
            target = clean if clean else last_client
            if target and target != 'ninguno':
                result = get_dga_compliance(target)

        elif routed_intent == "MEASUREMENTS":
            clean = re.sub(r'\b(ver|mostrar|dame|mediciones|lecturas|datos|del dia|hoy|variables)\b', '', user_text, flags=re.IGNORECASE).strip()
            if clean:
                # 1. Buscar como punto específico
                pts = search_points(clean, context_client=last_client)
                if len(pts) == 1:
                    # MATCH EXACTO PUNTO -> Guardar contexto
                    p_data = pts[0]
                    context['last_client'] = p_data['client']
                    context['last_point'] = p_data['title']
                    save_conversation_context(user_id, context)
                    result = get_point_latest_data(p_data['id'])
                elif len(pts) > 1:
                    # Multiples puntos -> Listar para desambiguar
                    # INTELIGENCIA: Si todos son del mismo cliente, guardar contexto cliente
                    unique_clients = set(p['client'] for p in pts)
                    if len(unique_clients) == 1:
                        context['last_client'] = list(unique_clients)[0]
                        save_conversation_context(user_id, context)
                        
                    result = f"Encontré {len(pts)} puntos para '{clean}'. ¿Cuál necesitas?\n"
                    for p in pts[:6]:
                        result += f"• {p['title']} ({p['client']})\n"
                else:
                    # 2. Si no es punto, probar como cliente
                    result = get_client_measurements(clean)
                    # Si tuvo éxito (no error), actualizar contexto de cliente
                    if "No encontré" not in result:
                         context['last_client'] = clean # Aproximado, idealmente normalizar
                         save_conversation_context(user_id, context)
            
            elif last_point:
                 # Usar último punto en contexto
                 pts = search_points(last_point, context_client=last_client)
                 if pts:
                    result = get_point_latest_data(pts[0]['id'])
            elif last_client and last_client != 'ninguno':
                 result = get_client_measurements(last_client)
        
        if result:
            # Registrar métrica de éxito del Router
            elapsed_ms = (time.time() - start_time) * 1000
            log_query_metric(user_id, user_text, "ROUTER", elapsed_ms, intent=routed_intent)
            return result

    # ===== CAPA 1.5: Búsqueda Determinista de Clientes (Anti-sesgo) =====
    if len(user_text.strip()) < 30:
        from api.core.models.catchment_points import Client
        norm_text = user_text.strip().lower()
        # Buscar match exacto de cliente
        client_obj = Client.objects.filter(name__iexact=norm_text).first()
        if client_obj:
            context['last_client'] = client_obj.name
            elapsed_ms = (time.time() - start_time) * 1000
            log_query_metric(user_id, user_text, "ROUTER", elapsed_ms, intent="CLIENT_SEARCH")
            return get_client_summary(client_obj.name)

    # ===== CAPA 1.6: Búsqueda Determinista de Puntos (Selección Rápida) =====
    if len(user_text.strip()) < 20: 
        # Si es corto, puede ser una selección de punto (ej: "P4", "Pozo 1")
        # Buscamos coincidencias exactas o muy fuertes en el TÍTULO
        pts_short = search_points(user_text.strip(), context_client=last_client)
        # Filtramos para ver si hay un match de título exacto (case insensitive)
        exact_matches = [p for p in pts_short if p['title'].lower() == user_text.strip().lower()]
        
        target_point = None
        if len(exact_matches) == 1:
            target_point = exact_matches[0]
        elif not exact_matches and len(pts_short) == 1:
            # Si no hay exacto pero hay solo uno similar (ej: "p 4" -> "P4")
            target_point = pts_short[0]
            
        if target_point:
            # ACTUALIZAR CONTEXTO
            context['last_client'] = target_point['client']
            context['last_point'] = target_point['title']
            save_conversation_context(user_id, context)
            
            elapsed_ms = (time.time() - start_time) * 1000
            log_query_metric(user_id, user_text, "ROUTER", elapsed_ms, intent="POINT_SELECTION")
            
            # Devolvemos latest data (asumimos que es lo que quiere al nombrar el punto)
            return get_point_latest_data(target_point['id'])
        
        # Si hay múltiples exactos (ej: P4 en Iansa y P4 en FPC), listar para desambiguar
        if len(exact_matches) > 1:
            elapsed_ms = (time.time() - start_time) * 1000
            log_query_metric(user_id, user_text, "ROUTER", elapsed_ms, intent="POINT_AMBIGUOUS")
            res = f"Existen {len(exact_matches)} puntos llamados '{user_text.strip()}'. ¿Cuál cliente?\n"
            for p in exact_matches[:6]:
                 res += f"• {p['title']} ({p['client']})\n"
            return res

    # ===== CAPA 2: LLM Fallback (Para consultas complejas o sin match) =====
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            'gemini-2.0-flash',
            system_instruction="""Asistente técnico SmartHydro especializado en telemetría de agua.
Unidades: Caudal (L/s), Total (m³), Nivel (m).
Jerga: Cliente→Proyecto→Punto. DGA=Fiscalización/Vouchers.
Tono: Técnico, profesional, directo."""
        )

        # ✅ OPTIMIZACIÓN: Prompt compacto (de 350 a ~150 tokens, -57% costos)
        prompt = f"""Contexto: Cliente='{last_client}', Punto='{context.get('last_point', 'ninguno')}'.
Usuario: {user_name}. Query: "{user_text}"

Tags disponibles:
[HELP], [GLOBAL_STATUS], [NOTIFICATIONS], [METRICS]
[CLIENT:X], [MEASUREMENTS:X], [DGA:X], [CONFIG:X], [HISTORY:X]
[STATS:X], [RANKING:X|CONSUMO], [TRENDS:X], [ANOMALIES:X], [COMPARE:P1|P2]
[SEARCH:term], [PROJECT_MEASUREMENTS:Cli|Proy], [ALERTS:X]

Reglas:
- "ayuda"→[HELP], "estado"→[GLOBAL_STATUS], "novedades"→[NOTIFICATIONS]
- Si menciona cliente diferente→[CLIENT:NuevoCliente]
- Si pide datos→[MEASUREMENTS:X] o [HISTORY:X]
- Si nombre solo→usar contexto actual ({last_client})
- Responde con 1 tag o texto breve. Sin repetir contexto."""

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

        # 0. Despachar ayuda PRIORITARIO
        if "[HELP]" in ai_text:
            return log_and_return(get_help_menu(), "HELP")

        if "[CLEAR_CONTEXT]" in ai_text:
            clear_conversation_context(user_id)
            return log_and_return("✅ Contexto limpiado. ¿En qué puedo ayudarte ahora?", "CLEAR_CONTEXT")

        # 1. Status Global y Notificaciones
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

