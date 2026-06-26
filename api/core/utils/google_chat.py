
import requests
import logging
from django.conf import settings
from datetime import datetime

logger = logging.getLogger(__name__)

# LEGACY: Las URLs de webhook ahora se configuran en settings/env.
# Los canales configurables usan AlertChannel desde la BD (ver alert_dispatcher.py).

def send_google_chat_message(text, webhook_url=None):
    """
    Envía un mensaje simple a Google Chat.
    Args:
        text: Mensaje a enviar
        webhook_url: URL del webhook (opcional, usa settings.GOOGLE_CHAT_WEBHOOK_URL)
    """
    url = webhook_url or settings.GOOGLE_CHAT_WEBHOOK_URL
    if not url:
        logger.warning("Google Chat Webhook URL not configured (settings.GOOGLE_CHAT_WEBHOOK_URL).")
        return False

    try:
        response = requests.post(
            url,
            json={"text": text},
            timeout=5
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Error sending Google Chat message: {e}")
        return False


def send_dga_chat_message(text):
    """
    Envía un mensaje al canal de reportes DGA.
    """
    return send_google_chat_message(text, webhook_url=settings.GOOGLE_CHAT_DGA_WEBHOOK_URL)

