"""
Google Chat Handler - Terminal Inteligente SmartHydro

Este módulo maneja todos los eventos de Google Chat:
- ADDED_TO_SPACE: Bienvenida con Card interactiva
- MESSAGE: Mensajes de texto y Slash Commands nativos
- CARD_CLICKED: Interacciones con botones de Cards

Requisitos para Slash Commands nativos:
  Registrar comandos en Google Cloud Console → Chat API → Configuration → Slash commands
"""

import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .llm import resolve_intent_and_respond, get_conversation_context, save_conversation_context
from .slash_commands import handle_slash_command
from .cards import build_help_card, build_text_response

logger = logging.getLogger(__name__)


def build_welcome_card():
    """Construye la Card de bienvenida."""
    return {
        "cardsV2": [{
            "cardId": "welcome_card",
            "card": {
                "header": {
                    "title": "🤖 Asistente SmartHydro",
                    "subtitle": "Terminal Inteligente de Telemetría",
                    "imageUrl": "https://www.gstatic.com/images/branding/product/2x/chat_48dp.png",
                    "imageType": "CIRCLE"
                },
                "sections": [
                    {
                        "header": "⚡ Comandos Rápidos",
                        "widgets": [{
                            "buttonList": {
                                "buttons": [
                                    {"text": "/estado", "onClick": {"action": {"function": "slash_estado"}}},
                                    {"text": "/alertas", "onClick": {"action": {"function": "slash_alertas"}}},
                                    {"text": "/ayuda", "onClick": {"action": {"function": "slash_ayuda"}}}
                                ]
                            }
                        }]
                    },
                    {
                        "header": "📖 Cómo usar",
                        "widgets": [
                            {"decoratedText": {"icon": {"knownIcon": "STAR"}, "text": "Escribe `/` para ver comandos disponibles"}},
                            {"decoratedText": {"icon": {"knownIcon": "BOOKMARK"}, "text": "`/cliente Iansa` → Ver resumen de cliente"}},
                            {"decoratedText": {"icon": {"knownIcon": "DESCRIPTION"}, "text": "`/punto P4` → Datos de un punto"}},
                            {"decoratedText": {"icon": {"knownIcon": "FLIGHT_TAKEOFF"}, "text": "`/dga Comasa` → Cumplimiento DGA"}}
                        ],
                        "collapsible": True,
                        "uncollapsibleWidgetsCount": 2
                    },
                    {
                        "widgets": [{
                            "textParagraph": {
                                "text": "💬 También puedes escribir en *lenguaje natural*:\n• `Iansa` → Resumen del cliente\n• `mediciones P4` → Últimas lecturas\n• `compara P1 con P4` → Comparar puntos"
                            }
                        }]
                    }
                ]
            }
        }]
    }


def handle_card_action(action_name, parameters, user_id):
    """
    Maneja las acciones de botones en Cards.
    
    Args:
        action_name: Nombre de la función invocada (ej: "slash_estado")
        parameters: Parámetros de la acción
        user_id: ID del usuario
        
    Returns:
        dict: Respuesta para Google Chat
    """
    # Mapeo de acciones a command IDs
    action_to_command = {
        'slash_estado': 1,
        'slash_alertas': 2,
        'slash_cliente': 3,
        'slash_punto': 4,
        'slash_dga': 5,
        'slash_historial': 6,
        'slash_config': 7,
        'slash_ranking': 8,
        'slash_compara': 9,
        'slash_ayuda': 10,
        'client_measurements': 3,  # Alias
        'trends': 6,  # Usar historial para tendencias
    }
    
    command_id = action_to_command.get(action_name)
    
    if command_id:
        # Extraer argumentos de parameters
        argument_text = ''
        if parameters:
            if isinstance(parameters, list):
                for param in parameters:
                    if param.get('key') in ('client', 'point', 'text'):
                        argument_text = param.get('value', '')
                        break
            elif isinstance(parameters, dict):
                argument_text = parameters.get('client') or parameters.get('point') or parameters.get('text', '')
        
        return handle_slash_command(command_id, argument_text, user_id)
    
    # Acción especial: enviar mensaje
    if action_name == 'send_message':
        text = ''
        if parameters:
            for param in parameters if isinstance(parameters, list) else [parameters]:
                if isinstance(param, dict) and param.get('key') == 'text':
                    text = param.get('value', '')
                    break
        
        if text:
            response = resolve_intent_and_respond(text, "Usuario", user_id)
            return build_text_response(response)
    
    logger.warning(f"Acción no reconocida: {action_name}")
    return build_text_response(f"Acción `{action_name}` no reconocida.")


@csrf_exempt
@require_POST
def google_chat_handler(request):
    """
    Endpoint principal para recibir eventos de Google Chat.
    
    Eventos soportados:
    - ADDED_TO_SPACE: Bot agregado a espacio/DM
    - REMOVED_FROM_SPACE: Bot removido
    - MESSAGE: Mensaje de usuario (texto o slash command)
    - CARD_CLICKED: Click en botón de Card
    """
    try:
        event = json.loads(request.body)
        event_type = event.get('type')
        
        logger.info(f"📨 Evento de Google Chat: {event_type}")

        # ========== ADDED_TO_SPACE ==========
        if event_type == 'ADDED_TO_SPACE':
            space_type = event.get('space', {}).get('type', 'UNKNOWN')
            logger.info(f"Bot agregado a espacio tipo: {space_type}")
            return JsonResponse(build_welcome_card())

        # ========== REMOVED_FROM_SPACE ==========
        elif event_type == 'REMOVED_FROM_SPACE':
            logger.info("Bot removido del espacio")
            return JsonResponse({})  # No response needed

        # ========== MESSAGE ==========
        elif event_type == 'MESSAGE':
            message = event.get('message', {})
            user = event.get('user', {})

            user_text = message.get('text', '').strip()
            user_name = user.get('displayName', 'Usuario')
            user_email = user.get('email', user_name)
            user_id = user_email or user_name
            
            # ✅ Limpiar mención del bot del texto (@Asistente SmartHydro, etc.)
            # Google Chat incluye la mención como parte del texto en chats grupales
            annotations = message.get('annotations', [])
            for annotation in annotations:
                if annotation.get('type') == 'USER_MENTION':
                    # Obtener el texto de la mención y removerlo
                    start_index = annotation.get('startIndex', 0)
                    length = annotation.get('length', 0)
                    if length > 0:
                        mention_text = user_text[start_index:start_index + length]
                        user_text = user_text.replace(mention_text, '', 1).strip()
            
            # También limpiar patrones comunes de mención manualmente
            import re
            # Remover @NombreBot al inicio del mensaje
            user_text = re.sub(r'^@[\w\s]+(?:smarthydro|asistente)[^\s]*\s*', '', user_text, flags=re.IGNORECASE).strip()
            
            # ✅ Detectar Slash Command nativo
            slash_command = message.get('slashCommand')
            
            if slash_command:
                try:
                    command_id = int(slash_command.get('commandId'))
                except (ValueError, TypeError):
                    command_id = 0
                    
                argument_text = message.get('argumentText', '').strip()
                
                logger.info(f"⚡ Slash Command ID={command_id}, args='{argument_text}'")
                
                response = handle_slash_command(command_id, argument_text, user_id)
                return JsonResponse(response)
            
            # ✅ Mensaje de texto normal -> LLM/Router
            logger.info(f"💬 Mensaje de {user_name}: '{user_text[:50]}...'")
            
            response_text = resolve_intent_and_respond(user_text, user_name, user_id)
            
            # Si la respuesta es un dict (Card), retornarla directamente
            if isinstance(response_text, dict):
                return JsonResponse(response_text)
            
            return JsonResponse({'text': response_text})

        # ========== CARD_CLICKED ==========
        elif event_type == 'CARD_CLICKED':
            user = event.get('user', {})
            user_email = user.get('email', user.get('displayName', 'Usuario'))
            user_id = user_email
            
            # Extraer información de la acción
            common = event.get('common', {})
            action_name = common.get('invokedFunction', '')
            parameters = common.get('parameters', [])
            
            logger.info(f"🖱️ Card clicked: action={action_name}, params={parameters}")
            
            response = handle_card_action(action_name, parameters, user_id)
            return JsonResponse(response)

        # ========== APP_COMMAND (Slash Commands nuevos) ==========
        elif event_type == 'APP_COMMAND':
            logger.info(f"🐛 DEBUG APP_COMMAND payload: {json.dumps(event)}")
            
            # Google Chat envía metadata en appCommandMetadata
            app_command_metadata = event.get('appCommandMetadata', {})
            try:
                # Intentar leer appCommandId (usado en Quick commands)
                command_id = app_command_metadata.get('appCommandId')
                if command_id is None:
                    # Alternativa: appCommand.id
                    app_command = event.get('appCommand', {})
                    command_id = app_command.get('id')
                
                command_id = int(command_id)
            except (ValueError, TypeError):
                command_id = 0
            
            # Intentar obtener argumentos si existen
            # En APP_COMMAND, los argumentos pueden venir de forma diferente dependiendo del cliente
            # Intento simple de obtener texto asociado si existe
            user = event.get('user', {})
            user_email = user.get('user', {}).get('email', user.get('displayName', 'Usuario'))
            user_id = user_email
            
            logger.info(f"⚡ Slash Command (APP_COMMAND) ID={command_id}")
            
            # Para Slash Commands sin argumentos en el evento, pasamos cadena vacía
            # Si Google Chat envía argumentos en el futuro, se pueden extraer de appCommand.get('parameters', [])
            argument_text = ""
            
            response = handle_slash_command(command_id, argument_text, user_id)
            return JsonResponse(response)

        # ========== WIDGET UPDATE (Dialogs) ==========
        elif event_type == 'WIDGET_UPDATED':
            # Para dialogs interactivos (futuro)
            logger.info("Widget updated event")
            return JsonResponse({})

        # ========== Evento no soportado ==========
        else:
            logger.warning(f"Evento no soportado: {event_type}")
            return JsonResponse({'text': f'Evento `{event_type}` no soportado.'})

    except json.JSONDecodeError as e:
        logger.error(f"Error parsing JSON: {e}")
        return JsonResponse({'text': 'Error: Formato de mensaje inválido.'}, status=400)
        
    except Exception as e:
        logger.error(f"Error procesando evento de Google Chat: {e}", exc_info=True)
        return JsonResponse({
            'text': '❌ Lo siento, ocurrió un error interno. Por favor intenta de nuevo.'
        }, status=500)
