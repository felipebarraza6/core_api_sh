"""
Cards Builder para Google Chat

Este módulo construye Cards interactivas (cardsV2) para respuestas visuales
en Google Chat. Las Cards incluyen headers, secciones, botones y widgets.

Documentación: https://developers.google.com/chat/api/reference/rest/v1/cards
"""

import re
from datetime import datetime
import pytz

chile_tz = pytz.timezone("America/Santiago")


def get_current_time():
    """Obtiene la hora actual en Chile."""
    return datetime.now(chile_tz).strftime("%H:%M")


def build_text_response(text):
    """Construye una respuesta de texto simple."""
    return {"text": text}


def build_error_card(title, message, suggestions=None):
    """
    Construye una Card de error con sugerencias opcionales.
    """
    widgets = [
        {
            "decoratedText": {
                "icon": {"knownIcon": "DESCRIPTION"},
                "text": message
            }
        }
    ]
    
    if suggestions:
        buttons = []
        for suggestion in suggestions[:3]:
            buttons.append({
                "text": suggestion,
                "onClick": {
                    "action": {
                        "function": "send_message",
                        "parameters": [{"key": "text", "value": suggestion}]
                    }
                }
            })
        widgets.append({"buttonList": {"buttons": buttons}})
    
    return {
        "cardsV2": [{
            "cardId": "error_card",
            "card": {
                "header": {
                    "title": f"⚠️ {title}",
                    "subtitle": "SmartHydro Assistant"
                },
                "sections": [{"widgets": widgets}]
            }
        }]
    }


def build_status_card(data_text):
    """
    Construye una Card de estado global.
    Parsea el texto de get_global_status() y lo convierte en widgets.
    """
    # Parsear secciones del texto
    sections = []
    
    # Header principal
    header = {
        "title": "🚦 Estado SmartHydro",
        "subtitle": f"Actualizado: {get_current_time()}",
        "imageUrl": "https://www.gstatic.com/images/branding/product/2x/chat_48dp.png",
        "imageType": "CIRCLE"
    }
    
    # Extraer métricas del texto
    lines = data_text.split('\n')
    current_section = None
    current_widgets = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Detectar headers de sección
        if '🔴' in line or '🟡' in line or '🟢' in line or '📊' in line:
            if current_section and current_widgets:
                sections.append({
                    "header": current_section,
                    "widgets": current_widgets,
                    "collapsible": len(current_widgets) > 3
                })
            current_section = line
            current_widgets = []
        elif line.startswith('•') or line.startswith('-'):
            # Item de lista
            current_widgets.append({
                "decoratedText": {
                    "text": line.replace('•', '').replace('-', '').strip()
                }
            })
        elif ':' in line and not line.startswith('http'):
            # Key-value
            parts = line.split(':', 1)
            if len(parts) == 2:
                current_widgets.append({
                    "decoratedText": {
                        "topLabel": parts[0].strip(),
                        "text": parts[1].strip()
                    }
                })
    
    # Agregar última sección
    if current_section and current_widgets:
        sections.append({
            "header": current_section,
            "widgets": current_widgets,
            "collapsible": len(current_widgets) > 3
        })
    
    # Si no se parsearon secciones, mostrar texto completo
    if not sections:
        sections = [{
            "widgets": [{
                "textParagraph": {"text": data_text[:2000]}
            }]
        }]
    
    # Agregar botones de acción
    sections.append({
        "widgets": [{
            "buttonList": {
                "buttons": [
                    {
                        "text": "🔔 Ver Alertas",
                        "onClick": {"action": {"function": "slash_alertas"}}
                    },
                    {
                        "text": "🔄 Actualizar",
                        "onClick": {"action": {"function": "slash_estado"}}
                    }
                ]
            }
        }]
    })
    
    return {
        "cardsV2": [{
            "cardId": "status_card",
            "card": {
                "header": header,
                "sections": sections
            }
        }]
    }


def build_notifications_card(data_text):
    """
    Construye una Card de notificaciones.
    """
    sections = []
    
    # Parsear notificaciones
    lines = data_text.split('\n')
    widgets = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Determinar icono según contenido
        icon = "BOOKMARK"
        if '🔴' in line or 'error' in line.lower() or 'desconec' in line.lower():
            icon = "CONFIRMATION_NUMBER_ICON"
        elif '✅' in line or 'reconec' in line.lower():
            icon = "STAR"
        elif '⚠️' in line:
            icon = "DESCRIPTION"
            
        widgets.append({
            "decoratedText": {
                "icon": {"knownIcon": icon},
                "text": line[:200]
            }
        })
    
    if not widgets:
        widgets = [{"textParagraph": {"text": "✅ No hay notificaciones pendientes"}}]
    
    sections.append({
        "header": "📬 Notificaciones Recientes",
        "widgets": widgets[:10]  # Limitar a 10
    })
    
    return {
        "cardsV2": [{
            "cardId": "notifications_card",
            "card": {
                "header": {
                    "title": "🔔 Alertas y Notificaciones",
                    "subtitle": f"Actualizado: {get_current_time()}"
                },
                "sections": sections
            }
        }]
    }


def build_client_card(client_name, data_text):
    """
    Construye una Card con resumen de cliente.
    """
    sections = []
    widgets = []
    
    # Parsear datos del cliente
    lines = data_text.split('\n')
    for line in lines:
        line = line.strip()
        if not line or line.startswith('━'):
            continue
            
        if '📊' in line or '🏢' in line or '*' in line:
            if widgets:
                sections.append({"widgets": widgets})
                widgets = []
            sections.append({
                "header": line.replace('*', '').strip()
            })
        elif ':' in line:
            parts = line.split(':', 1)
            widgets.append({
                "decoratedText": {
                    "topLabel": parts[0].replace('•', '').strip(),
                    "text": parts[1].strip()
                }
            })
        elif line.startswith('•') or line.startswith('-'):
            widgets.append({
                "decoratedText": {
                    "text": line.replace('•', '').replace('-', '').strip()
                }
            })
    
    if widgets:
        sections.append({"widgets": widgets})
    
    if not sections:
        sections = [{"widgets": [{"textParagraph": {"text": data_text[:2000]}}]}]
    
    # Botones de acción
    sections.append({
        "widgets": [{
            "buttonList": {
                "buttons": [
                    {
                        "text": "📊 Mediciones",
                        "onClick": {"action": {
                            "function": "client_measurements",
                            "parameters": [{"key": "client", "value": client_name}]
                        }}
                    },
                    {
                        "text": "📋 DGA",
                        "onClick": {"action": {
                            "function": "slash_dga",
                            "parameters": [{"key": "client", "value": client_name}]
                        }}
                    },
                    {
                        "text": "🏆 Ranking",
                        "onClick": {"action": {
                            "function": "slash_ranking",
                            "parameters": [{"key": "client", "value": client_name}]
                        }}
                    }
                ]
            }
        }]
    })
    
    return {
        "cardsV2": [{
            "cardId": "client_card",
            "card": {
                "header": {
                    "title": f"🏢 {client_name}",
                    "subtitle": "Resumen del cliente"
                },
                "sections": sections
            }
        }]
    }


def build_point_card(point_info, data_text):
    """
    Construye una Card con datos de un punto.
    """
    point_title = point_info.get('title', 'Punto')
    client_name = point_info.get('client', '')
    
    sections = []
    widgets = []
    
    # Parsear datos
    lines = data_text.split('\n')
    for line in lines:
        line = line.strip()
        if not line or line.startswith('━'):
            continue
            
        if ':' in line and not line.startswith('http'):
            parts = line.split(':', 1)
            key = parts[0].replace('•', '').replace('📊', '').replace('📅', '').strip()
            value = parts[1].strip()
            
            # Colorear según métrica
            icon = "DESCRIPTION"
            if 'caudal' in key.lower():
                icon = "FLIGHT_TAKEOFF"
            elif 'nivel' in key.lower():
                icon = "BOOKMARK"
            elif 'total' in key.lower():
                icon = "STAR"
            
            widgets.append({
                "decoratedText": {
                    "icon": {"knownIcon": icon},
                    "topLabel": key,
                    "text": value
                }
            })
    
    if widgets:
        sections.append({
            "header": "📊 Últimas Mediciones",
            "widgets": widgets[:8]
        })
    else:
        sections.append({
            "widgets": [{"textParagraph": {"text": data_text[:1500]}}]
        })
    
    # Botones de acción
    sections.append({
        "widgets": [{
            "buttonList": {
                "buttons": [
                    {
                        "text": "📈 Historial",
                        "onClick": {"action": {
                            "function": "slash_historial",
                            "parameters": [{"key": "point", "value": point_title}]
                        }}
                    },
                    {
                        "text": "⚙️ Config",
                        "onClick": {"action": {
                            "function": "slash_config",
                            "parameters": [{"key": "point", "value": point_title}]
                        }}
                    },
                    {
                        "text": "📉 Tendencia",
                        "onClick": {"action": {
                            "function": "trends",
                            "parameters": [{"key": "point", "value": point_title}]
                        }}
                    }
                ]
            }
        }]
    })
    
    return {
        "cardsV2": [{
            "cardId": "point_card",
            "card": {
                "header": {
                    "title": f"📍 {point_title}",
                    "subtitle": f"Cliente: {client_name}"
                },
                "sections": sections
            }
        }]
    }


def build_dga_card(client_name, data_text):
    """
    Construye una Card con cumplimiento DGA.
    """
    sections = []
    widgets = []
    
    lines = data_text.split('\n')
    current_header = None
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('━'):
            continue
        
        # Detectar headers
        if '📋' in line or '✅' in line or '❌' in line or '📊' in line:
            if current_header and widgets:
                sections.append({
                    "header": current_header,
                    "widgets": widgets,
                    "collapsible": len(widgets) > 5
                })
                widgets = []
            current_header = line
        else:
            widgets.append({
                "decoratedText": {"text": line[:200]}
            })
    
    if current_header and widgets:
        sections.append({
            "header": current_header,
            "widgets": widgets
        })
    
    if not sections:
        sections = [{"widgets": [{"textParagraph": {"text": data_text[:2000]}}]}]
    
    return {
        "cardsV2": [{
            "cardId": "dga_card",
            "card": {
                "header": {
                    "title": f"📋 Cumplimiento DGA",
                    "subtitle": f"Cliente: {client_name}"
                },
                "sections": sections
            }
        }]
    }


def build_history_card(point_name, data_text):
    """
    Construye una Card con historial de un punto.
    """
    sections = [{
        "header": f"📈 Historial - {point_name}",
        "widgets": [{"textParagraph": {"text": data_text[:3000]}}]
    }]
    
    # Botones
    sections.append({
        "widgets": [{
            "buttonList": {
                "buttons": [
                    {
                        "text": "📊 Datos actuales",
                        "onClick": {"action": {
                            "function": "slash_punto",
                            "parameters": [{"key": "point", "value": point_name}]
                        }}
                    }
                ]
            }
        }]
    })
    
    return {
        "cardsV2": [{
            "cardId": "history_card",
            "card": {
                "header": {
                    "title": f"📈 Historial",
                    "subtitle": point_name
                },
                "sections": sections
            }
        }]
    }


def build_config_card(point_name, data_text):
    """
    Construye una Card con configuración de un punto.
    """
    sections = []
    widgets = []
    
    lines = data_text.split('\n')
    for line in lines:
        line = line.strip()
        if not line or line.startswith('━'):
            continue
            
        if ':' in line:
            parts = line.split(':', 1)
            widgets.append({
                "decoratedText": {
                    "topLabel": parts[0].replace('•', '').strip(),
                    "text": parts[1].strip()
                }
            })
        elif line:
            widgets.append({
                "decoratedText": {"text": line}
            })
    
    if widgets:
        sections.append({
            "header": "⚙️ Configuración",
            "widgets": widgets[:15]
        })
    else:
        sections.append({
            "widgets": [{"textParagraph": {"text": data_text[:2000]}}]
        })
    
    return {
        "cardsV2": [{
            "cardId": "config_card",
            "card": {
                "header": {
                    "title": f"⚙️ Configuración",
                    "subtitle": point_name
                },
                "sections": sections
            }
        }]
    }


def build_ranking_card(client_name, data_text):
    """
    Construye una Card con ranking de consumo.
    """
    sections = []
    widgets = []
    
    lines = data_text.split('\n')
    position = 0
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('━'):
            continue
        
        if line.startswith(('1.', '2.', '3.', '4.', '5.')):
            position += 1
            medal = '🥇' if position == 1 else ('🥈' if position == 2 else ('🥉' if position == 3 else f'{position}.'))
            widgets.append({
                "decoratedText": {
                    "startIcon": {"knownIcon": "STAR" if position <= 3 else "BOOKMARK"},
                    "text": f"{medal} {line[2:].strip()}"
                }
            })
        elif ':' in line:
            parts = line.split(':', 1)
            widgets.append({
                "decoratedText": {
                    "topLabel": parts[0].strip(),
                    "text": parts[1].strip()
                }
            })
    
    if widgets:
        sections.append({
            "header": "🏆 Top Consumidores",
            "widgets": widgets[:10]
        })
    else:
        sections.append({
            "widgets": [{"textParagraph": {"text": data_text[:2000]}}]
        })
    
    return {
        "cardsV2": [{
            "cardId": "ranking_card",
            "card": {
                "header": {
                    "title": f"🏆 Ranking de Consumo",
                    "subtitle": f"Cliente: {client_name}"
                },
                "sections": sections
            }
        }]
    }


def build_compare_card(point1, point2, data_text):
    """
    Construye una Card de comparación entre puntos.
    """
    sections = [{
        "header": f"⚖️ {point1} vs {point2}",
        "widgets": [{"textParagraph": {"text": data_text[:3000]}}]
    }]
    
    return {
        "cardsV2": [{
            "cardId": "compare_card",
            "card": {
                "header": {
                    "title": "⚖️ Comparación de Puntos",
                    "subtitle": f"{point1} vs {point2}"
                },
                "sections": sections
            }
        }]
    }


def build_help_card(help_text):
    """
    Construye una Card de ayuda con comandos disponibles.
    """
    sections = []
    
    # Comandos rápidos
    quick_commands = [
        {"text": "/estado", "onClick": {"action": {"function": "slash_estado"}}},
        {"text": "/alertas", "onClick": {"action": {"function": "slash_alertas"}}},
        {"text": "/ayuda", "onClick": {"action": {"function": "slash_ayuda"}}}
    ]
    
    sections.append({
        "header": "⚡ Comandos Rápidos",
        "widgets": [{
            "buttonList": {"buttons": quick_commands}
        }]
    })
    
    # Texto de ayuda
    sections.append({
        "header": "📖 Guía Completa",
        "widgets": [{
            "textParagraph": {"text": help_text[:3500]}
        }],
        "collapsible": True,
        "uncollapsibleWidgetsCount": 1
    })
    
    return {
        "cardsV2": [{
            "cardId": "help_card",
            "card": {
                "header": {
                    "title": "🤖 Asistente SmartHydro",
                    "subtitle": "Guía de uso"
                },
                "sections": sections
            }
        }]
    }
