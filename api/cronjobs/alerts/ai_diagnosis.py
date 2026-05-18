"""
Generador de diagnósticos con IA para alertas de desconexión.

Usa Gemini para analizar el contexto de un punto desconectado y entregar
un informe con posibles causas y recomendaciones.
"""

import logging
import os
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# Intentar importar Gemini (mismo patrón que api/core/chatbot/llm.py)
# Suprimir FutureWarning del paquete deprecado hasta migrar a google.genai
import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore", FutureWarning)
    try:
        import google.generativeai as genai
        HAS_GEMINI = True
    except Exception as e:
        HAS_GEMINI = False
        logger.warning(f"google-generativeai no disponible: {e}")


def generate_disconnection_diagnosis(point, last_record, days_disconnected: int) -> Optional[str]:
    """
    Genera un diagnóstico con IA para un punto desconectado.

    Args:
        point: CatchmentPoint
        last_record: último InteractionDetail
        days_disconnected: días sin conexión

    Returns:
        Texto del diagnóstico o None si falla.
    """
    if not HAS_GEMINI:
        logger.warning("Gemini no disponible, skipping IA diagnosis")
        return None

    api_key = getattr(settings, 'GEMINI_API_KEY', os.environ.get('GEMINI_API_KEY'))
    if not api_key:
        logger.warning("GEMINI_API_KEY no configurada")
        return None

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")

        # Contexto básico
        client_name = point.project.client.name if point.project and point.project.client else "Desconocido"
        project_name = point.project.name if point.project else "Sin proyecto"

        # Frecuencia
        freq = getattr(point, 'frecuency', None)
        freq_str = f"{freq} min" if freq else "Desconocida"

        # Última medición
        last_med = last_record.date_time_medition.isoformat() if last_record and last_record.date_time_medition else "N/A"

        prompt = f"""Actúa como un ingeniero de soporte técnico de telemetría hidrológica.

Un punto de captación está desconectado. Analiza los antecedentes y responde en máximo 3 líneas:
1. ¿Es posible resolver esto a nivel de software/telemetría (configuración, token, frecuencia, dashboard, etc.)? Si sí, indica qué revisar.
2. Si NO es posible por software, indica claramente: "Derivar a hardware de campo".
3. NO incluyas nivel de urgencia ni acciones de campo (batería, antena, etc.) a menos que sea una recomendación de software.

Datos del punto:
- Nombre: {point.title}
- Cliente: {client_name}
- Proyecto: {project_name}
- Días sin conexión: {days_disconnected}
- Frecuencia esperada: {freq_str}
- Última medición registrada: {last_med}

Responde SOLO el análisis, sin saludos ni explicaciones adicionales. Usa español."""

        response = model.generate_content(prompt)
        diagnosis = response.text.strip() if response and response.text else None
        logger.info(f"[AI_DIAGNOSIS] Diagnóstico generado para punto {point.id}: {diagnosis[:80]}...")
        return diagnosis

    except Exception as e:
        logger.error(f"[AI_DIAGNOSIS] Error generando diagnóstico para punto {point.id}: {e}")
        return None
