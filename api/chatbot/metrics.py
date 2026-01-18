import logging
import json
from datetime import datetime
from django.conf import settings

logger = logging.getLogger(__name__)

def _get_redis():
    try:
        from django_redis import get_redis_connection
        return get_redis_connection("default")
    except:
        return None

METRICS_KEY = "chatbot:metrics:buffer"
MAX_BUFFER_SIZE = 1000

def log_query_metric(user_id, query_text, resolution_type, response_time_ms, intent=None):
    """Registra una métrica en Redis."""
    metric = {
        'timestamp': datetime.now().isoformat(),
        'user_id': str(user_id)[:20],
        'query_preview': query_text[:50] if query_text else "",
        'resolution': resolution_type,
        'intent': intent,
        'response_time_ms': round(response_time_ms, 2)
    }
    
    con = _get_redis()
    if con:
        try:
            con.lpush(METRICS_KEY, json.dumps(metric))
            con.ltrim(METRICS_KEY, 0, MAX_BUFFER_SIZE - 1)
        except Exception as e:
            logger.warning(f"Error guardando métrica en Redis: {e}")
    
    logger.info(f"[METRIC] {resolution_type} | {response_time_ms:.0f}ms | {intent or 'LLM'} | {query_text[:30]}")

def get_metrics_summary():
    """Genera resumen desde Redis."""
    con = _get_redis()
    metrics = []
    if con:
        try:
            raw_data = con.lrange(METRICS_KEY, 0, -1)
            metrics = [json.loads(m) for m in raw_data]
        except Exception as e:
            logger.warning(f"Error leyendo métricas de Redis: {e}")

    if not metrics:
        return "📊 *Métricas del Chatbot*\n\nAún no hay datos suficientes para generar un reporte. (Se limpian al reiniciar si no hay Redis)"
    
    total = len(metrics)
    router_count = sum(1 for m in metrics if m['resolution'] == 'ROUTER')
    llm_count = sum(1 for m in metrics if m['resolution'] == 'LLM')
    
    router_pct = (router_count / total * 100)
    llm_pct = (llm_count / total * 100)
    
    router_times = [m['response_time_ms'] for m in metrics if m['resolution'] == 'ROUTER']
    llm_times = [m['response_time_ms'] for m in metrics if m['resolution'] == 'LLM']
    
    avg_router = sum(router_times) / len(router_times) if router_times else 0
    avg_llm = sum(llm_times) / len(llm_times) if llm_times else 0
    
    intent_counts = {}
    for m in metrics:
        intent = m.get('intent') or 'LLM_FALLBACK'
        intent_counts[intent] = intent_counts.get(intent, 0) + 1
    
    top_intents = sorted(intent_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    
    res = "📊 *Métricas de Rendimiento del Chatbot*\n"
    res += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    res += f"📈 *Resumen General* (Últimas {total} consultas)\n"
    res += f"   • Intent Router (gratis): {router_count} ({router_pct:.1f}%)\n"
    res += f"   • LLM Gemini (tokens): {llm_count} ({llm_pct:.1f}%)\n\n"
    res += f"⏱️ *Tiempos de Respuesta*\n"
    res += f"   • Router promedio: {avg_router:.0f}ms\n"
    res += f"   • LLM promedio: {avg_llm:.0f}ms\n\n"
    res += f"🎯 *Top Intenciones*\n"
    for intent, count in top_intents:
        pct = (count / total * 100)
        res += f"   • {intent}: {count} ({pct:.1f}%)\n"
    
    tokens_saved = router_count * 100
    cost_saved = (tokens_saved / 1000) * 0.00015
    res += f"\n💰 *Estimación de Ahorro*\n"
    res += f"   • Tokens ahorrados: ~{tokens_saved:,}\n"
    res += f"   • Costo evitado: ~${cost_saved:.4f} USD\n"
    
    return res

def clear_metrics():
    con = _get_redis()
    if con:
        con.delete(METRICS_KEY)
    return "✅ Métricas limpiadas."
