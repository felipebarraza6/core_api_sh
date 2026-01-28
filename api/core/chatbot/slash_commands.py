"""
Slash Commands Handler para Google Chat

Este módulo maneja los Slash Commands nativos de Google Chat.
Los comandos deben registrarse en Google Cloud Console:
  Google Cloud Console → APIs & Services → Google Chat API → Configuration → Slash commands

Command IDs registrados:
  1: /estado    - Estado global de puntos
  2: /alertas   - Notificaciones activas  
  3: /cliente   - Resumen de cliente (requiere nombre)
  4: /punto     - Datos de un punto (requiere nombre)
  5: /dga       - Cumplimiento DGA (requiere cliente)
  6: /historial - Historial de punto (requiere nombre)
  7: /config    - Configuración de punto (requiere nombre)
  8: /ranking   - Top consumidores (requiere cliente)
  9: /compara   - Comparar dos puntos (requiere "P1 vs P2")
  10: /ayuda    - Menú de ayuda
  11: /analisis_total - Auditoría completa de telemetría (30 días)
"""

import logging
import re
from .tools import (
    get_global_status, get_recent_notifications, get_client_summary,
    get_point_latest_data, get_dga_compliance, get_point_history,
    get_point_config, get_client_ranking, compare_points, get_help_menu,
    search_points, get_client_measurements, get_telemetry_audit
)
from .cards import (
    build_status_card, build_notifications_card, build_client_card,
    build_point_card, build_dga_card, build_history_card,
    build_config_card, build_ranking_card, build_compare_card,
    build_help_card, build_error_card, build_text_response
)
from .llm import get_conversation_context, save_conversation_context

logger = logging.getLogger(__name__)

# Mapeo de Command IDs a handlers
COMMAND_HANDLERS = {
    1: 'handle_estado',
    2: 'handle_alertas',
    3: 'handle_cliente',
    4: 'handle_punto',
    5: 'handle_dga',
    6: 'handle_historial',
    7: 'handle_config',
    8: 'handle_ranking',
    9: 'handle_compara',
    10: 'handle_ayuda',
    11: 'handle_analisis_total',
}


def handle_slash_command(command_id, argument_text, user_id):
    """
    Procesa un Slash Command nativo de Google Chat.
    
    Args:
        command_id: ID numérico del comando (1-10)
        argument_text: Texto después del comando (ej: "Iansa" en "/cliente Iansa")
        user_id: ID del usuario para contexto
        
    Returns:
        dict: Respuesta en formato Google Chat (text o cardsV2)
    """
    handler_name = COMMAND_HANDLERS.get(command_id)
    
    if not handler_name:
        return build_error_card(
            "Comando no reconocido",
            f"El comando con ID {command_id} no está configurado."
        )
    
    handler = globals().get(handler_name)
    if handler:
        try:
            return handler(argument_text, user_id)
        except Exception as e:
            logger.error(f"Error en slash command {command_id}: {e}")
            return build_error_card(
                "Error al procesar comando",
                str(e)
            )
    
    return build_error_card("Handler no encontrado", handler_name)


def handle_estado(argument_text, user_id):
    """
    /estado - Muestra el estado global de todos los puntos.
    """
    data = get_global_status()
    return build_status_card(data)


def handle_alertas(argument_text, user_id):
    """
    /alertas - Muestra las notificaciones activas.
    """
    data = get_recent_notifications()
    return build_notifications_card(data)


def handle_cliente(argument_text, user_id):
    """
    /cliente <nombre> - Muestra resumen de un cliente.
    """
    if not argument_text:
        # Intentar usar contexto
        context = get_conversation_context(user_id)
        argument_text = context.get('last_client')
        
        if not argument_text or argument_text == 'ninguno':
            return build_error_card(
                "Cliente requerido",
                "Uso: `/cliente <nombre>`\n\nEjemplo: `/cliente Iansa`",
                suggestions=["/cliente Iansa", "/cliente Comasa", "/ayuda"]
            )
    
    # Actualizar contexto
    context = get_conversation_context(user_id)
    context['last_client'] = argument_text
    save_conversation_context(user_id, context)
    
    data = get_client_summary(argument_text)
    return build_client_card(argument_text, data)


def handle_punto(argument_text, user_id):
    """
    /punto <nombre> - Muestra datos de un punto específico.
    """
    context = get_conversation_context(user_id)
    last_client = context.get('last_client')
    
    if not argument_text:
        last_point = context.get('last_point')
        if last_point:
            argument_text = last_point
        else:
            return build_error_card(
                "Punto requerido",
                "Uso: `/punto <nombre>`\n\nEjemplo: `/punto P4`",
                suggestions=["/punto P1", "/punto P4", "/estado"]
            )
    
    # Buscar el punto
    points = search_points(argument_text, context_client=last_client)
    
    if not points:
        return build_error_card(
            "Punto no encontrado",
            f"No encontré ningún punto llamado '{argument_text}'.",
            suggestions=["/estado", "/ayuda"]
        )
    
    if len(points) == 1:
        point = points[0]
        # Actualizar contexto
        context['last_point'] = point['title']
        context['last_client'] = point['client']
        save_conversation_context(user_id, context)
        
        data = get_point_latest_data(point['id'])
        return build_point_card(point, data)
    
    # Múltiples puntos - mostrar opciones
    options = [f"{p['title']} ({p['client']})" for p in points[:6]]
    return build_error_card(
        f"Múltiples puntos: '{argument_text}'",
        "¿Cuál necesitas?\n• " + "\n• ".join(options),
        suggestions=[f"/punto {points[0]['title']}", f"/cliente {points[0]['client']}"]
    )


def handle_dga(argument_text, user_id):
    """
    /dga <cliente> - Muestra cumplimiento DGA de un cliente.
    """
    if not argument_text:
        context = get_conversation_context(user_id)
        argument_text = context.get('last_client')
        
        if not argument_text or argument_text == 'ninguno':
            return build_error_card(
                "Cliente requerido",
                "Uso: `/dga <cliente>`\n\nEjemplo: `/dga Iansa`",
                suggestions=["/dga Iansa", "/cliente Iansa", "/ayuda"]
            )
    
    # Actualizar contexto
    context = get_conversation_context(user_id)
    context['last_client'] = argument_text
    save_conversation_context(user_id, context)
    
    data = get_dga_compliance(argument_text)
    return build_dga_card(argument_text, data)


def handle_historial(argument_text, user_id):
    """
    /historial <punto> - Muestra historial de un punto.
    """
    context = get_conversation_context(user_id)
    last_client = context.get('last_client')
    
    if not argument_text:
        last_point = context.get('last_point')
        if last_point:
            argument_text = last_point
        else:
            return build_error_card(
                "Punto requerido",
                "Uso: `/historial <punto>`\n\nEjemplo: `/historial P4`",
                suggestions=["/punto P4", "/estado", "/ayuda"]
            )
    
    # Actualizar contexto
    context['last_point'] = argument_text
    save_conversation_context(user_id, context)
    
    data = get_point_history(argument_text, context_client=last_client)
    return build_history_card(argument_text, data)


def handle_config(argument_text, user_id):
    """
    /config <punto> - Muestra configuración de un punto.
    """
    context = get_conversation_context(user_id)
    last_client = context.get('last_client')
    
    if not argument_text:
        last_point = context.get('last_point')
        if last_point:
            argument_text = last_point
        else:
            return build_error_card(
                "Punto requerido",
                "Uso: `/config <punto>`\n\nEjemplo: `/config P4`",
                suggestions=["/punto P4", "/estado", "/ayuda"]
            )
    
    context['last_point'] = argument_text
    save_conversation_context(user_id, context)
    
    data = get_point_config(argument_text, context_client=last_client)
    return build_config_card(argument_text, data)


def handle_ranking(argument_text, user_id):
    """
    /ranking <cliente> - Top consumidores de un cliente.
    """
    if not argument_text:
        context = get_conversation_context(user_id)
        argument_text = context.get('last_client')
        
        if not argument_text or argument_text == 'ninguno':
            return build_error_card(
                "Cliente requerido",
                "Uso: `/ranking <cliente>`\n\nEjemplo: `/ranking Iansa`",
                suggestions=["/ranking Iansa", "/cliente Iansa", "/ayuda"]
            )
    
    context = get_conversation_context(user_id)
    context['last_client'] = argument_text
    save_conversation_context(user_id, context)
    
    data = get_client_ranking(argument_text, metric='CONSUME')
    return build_ranking_card(argument_text, data)


def handle_compara(argument_text, user_id):
    """
    /compara <punto1> vs <punto2> - Compara dos puntos.
    """
    if not argument_text or ' vs ' not in argument_text.lower():
        return build_error_card(
            "Formato incorrecto",
            "Uso: `/compara <punto1> vs <punto2>`\n\nEjemplo: `/compara P1 vs P4`",
            suggestions=["/compara P1 vs P4", "/punto P1", "/ayuda"]
        )
    
    # Parsear puntos
    parts = re.split(r'\s+vs\s+', argument_text, flags=re.IGNORECASE)
    if len(parts) != 2:
        return build_error_card(
            "Formato incorrecto",
            "Necesito exactamente dos puntos separados por 'vs'",
            suggestions=["/compara P1 vs P4"]
        )
    
    point1 = parts[0].strip()
    point2 = parts[1].strip()
    
    context = get_conversation_context(user_id)
    last_client = context.get('last_client')
    
    data = compare_points(point1, point2, context_client=last_client)
    return build_compare_card(point1, point2, data)


def handle_ayuda(argument_text, user_id):
    """
    /ayuda - Muestra el menú de ayuda.
    """
    data = get_help_menu()
    return build_help_card(data)


def handle_analisis_total(argument_text, user_id):
    """
    /analisis_total - Auditoría completa de telemetría (30 días).
    Muestra TODOS los puntos con anomalías sin truncar.
    """
    data = get_telemetry_audit(days=30, show_all=True)
    return build_text_response(data)
