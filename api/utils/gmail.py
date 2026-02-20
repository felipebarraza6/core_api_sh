"""
Backend de envío de correo usando Gmail API.
Compatible con Django send_mail() y send_mass_mail().
"""

import os
import base64
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from django.conf import settings
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class GmailApiBackend:
    """
    Backend de envío de correo usando Gmail API.
    Compatible con Django send_mail() y send_mass_mail().
    """

    def __init__(self):
        self.service = self._get_service()

    def _get_service(self):
        """Construir cliente autenticado de Gmail API."""
        try:
            # Cargar credenciales desde archivo JSON
            creds = service_account.Credentials.from_service_account_file(
                settings.GOOGLE_SERVICE_ACCOUNT_FILE,
                scopes=['https://mail.google.com/']
            )
            # Delegar a la cuenta que enviará los correos
            delegated = creds.with_subject(settings.GOOGLE_DELEGATED_USER)
            return build('gmail', 'v1', credentials=delegated)
        except Exception as e:
            logger.error(f"Error al inicializar Gmail API: {e}")
            raise

    def send_messages(self, email_messages):
        """
        Enviar lista de mensajes de correo.

        Args:
            email_messages: Lista de objetos EmailMessage de Django

        Returns:
            int: Número de mensajes enviados correctamente
        """
        if not email_messages:
            return 0

        sent = 0
        for message in email_messages:
            try:
                # Convertir mensaje a bytes y codificar en base64
                raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
                body = {'raw': raw}

                # Enviar a través de Gmail API
                result = self.service.users().messages().send(
                    userId='me',
                    body=body
                ).execute()

                sent += 1
                logger.info(f"Correo enviado exitosamente: {message.subject} → {', '.join(message.to)}")

            except HttpError as e:
                error_msg = f"Gmail API error ({e.resp.status}): {e.content.decode()}"
                logger.error(error_msg)
                raise
            except Exception as e:
                error_msg = f"Error general al enviar correo: {e}"
                logger.error(error_msg)
                raise

        logger.info(f"Total de correos enviados: {sent}/{len(email_messages)}")
        return sent

    def open(self):
        """Hook para el protocolo de Django mail backend."""
        pass

    def close(self):
        """Hook para el protocolo de Django mail backend."""
        pass
