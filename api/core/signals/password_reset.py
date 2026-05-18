"""
Signal receiver para enviar emails de recuperación de contraseña.
Se conecta a la señal reset_password_token_created de django_rest_passwordreset.
"""

import logging
from django.conf import settings
from django.core.mail import send_mail
from django.dispatch import receiver

try:
    from django_rest_passwordreset.signals import reset_password_token_created
except ImportError:
    reset_password_token_created = None

logger = logging.getLogger(__name__)


@receiver(reset_password_token_created)
def password_reset_token_created_signal(sender, instance, reset_password_token, *args, **kwargs):
    """
    Envía un email con el enlace para restablecer la contraseña.
    """
    if not reset_password_token:
        return

    token = reset_password_token.key
    user_email = reset_password_token.user.email

    # URL del frontend para resetear contraseña
    frontend_url = getattr(settings, 'FRONTEND_URL', 'https://ikolu.smarthydro.app')
    reset_url = f"{frontend_url}/reset-password?token={token}"

    subject = "Recuperación de contraseña - Ikolu App"

    message_plain = f"""Ikolu App - Gestión Inteligente de Aguas Subterráneas

Hola,

Has solicitado restablecer tu contraseña. Usa el siguiente enlace:

{reset_url}

O copia este código de verificación: {token}

Si no solicitaste este cambio, ignora este correo.

---
Ikolu App
Soporte: +56 9 3958 1688
https://ikolu.smarthydro.app
"""

    # Colores institucionales SmartHydro (azul corporativo oscuro)
    primary_blue = "#1e4a72"
    light_blue = "#2d6da3"
    bg_grey = "#f4f6f8"
    text_dark = "#1c2833"
    text_grey = "#5a6a7a"
    link_color = "#0d3b66"

    message_html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Recuperación de contraseña - Ikolu App</title>
</head>
<body style="margin: 0; padding: 0; background-color: {bg_grey}; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; -webkit-font-smoothing: antialiased;">
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <!-- Contenedor principal -->
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width: 600px; width: 100%; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08);">
                    <!-- Header con gradiente -->
                    <tr>
                        <td style="background: linear-gradient(135deg, {primary_blue} 0%, {light_blue} 100%); padding: 40px 40px 30px 40px; text-align: center;">
                            <!-- Logo texto -->
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center">
                                <tr>
                                    <td style="padding-bottom: 8px;">
                                        <div style="font-size: 28px; font-weight: 700; color: #ffffff; letter-spacing: -0.5px;">
                                            Ikolu App
                                        </div>
                                    </td>
                                </tr>
                                <tr>
                                    <td>
                                        <div style="font-size: 12px; color: rgba(255,255,255,0.85); letter-spacing: 2px; text-transform: uppercase;">
                                            Gestión Inteligente de Aguas
                                        </div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Línea decorativa -->
                    <tr>
                        <td style="height: 4px; background: linear-gradient(90deg, {primary_blue}, {light_blue});"></td>
                    </tr>

                    <!-- Contenido -->
                    <tr>
                        <td style="padding: 40px 48px 30px 48px;">
                            <h1 style="margin: 0 0 20px 0; font-size: 22px; font-weight: 600; color: {text_dark}; line-height: 1.3;">
                                Recuperación de contraseña
                            </h1>

                            <p style="margin: 0 0 24px 0; font-size: 15px; color: {text_grey}; line-height: 1.6;">
                                Hola,<br><br>
                                Recibimos una solicitud para restablecer tu contraseña. Hacé clic en el botón de abajo para continuar:
                            </p>

                            <!-- Botón CTA -->
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin: 32px 0;">
                                <tr>
                                    <td style="border-radius: 8px; background: linear-gradient(135deg, {primary_blue} 0%, {light_blue} 100%); text-align: center;">
                                        <a href="{reset_url}" style="display: inline-block; padding: 16px 40px; font-size: 15px; font-weight: 600; color: #ffffff; text-decoration: none; border-radius: 8px;">
                                            Restablecer mi contraseña
                                        </a>
                                    </td>
                                </tr>
                            </table>

                            <p style="margin: 24px 0 16px 0; font-size: 13px; color: {text_grey}; line-height: 1.5;">
                                Si el botón no funciona, copiá y pegá este enlace en tu navegador:
                            </p>

                            <p style="margin: 0 0 24px 0; padding: 14px 16px; background-color: #ffffff; border-radius: 6px; border: 1px solid #c8d6e5; word-break: break-all; font-size: 13px; color: {link_color}; font-family: 'Courier New', monospace; text-decoration: underline;">
                                {reset_url}
                            </p>

                            <p style="margin: 0 0 8px 0; font-size: 13px; color: {text_grey}; line-height: 1.5;">
                                También podés usar este código de verificación:
                            </p>

                            <p style="margin: 0 0 30px 0; padding: 12px 16px; background-color: {bg_grey}; border-radius: 6px; text-align: center; font-size: 18px; font-weight: 700; color: {text_dark}; font-family: 'Courier New', monospace; letter-spacing: 3px;">
                                {token}
                            </p>

                            <!-- Alerta de seguridad -->
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #fff8e6; border-radius: 8px; border-left: 3px solid #f0ad4e;">
                                <tr>
                                    <td style="padding: 14px 18px;">
                                        <p style="margin: 0; font-size: 12px; color: #856404; line-height: 1.5;">
                                            <strong>⚠️ ¿No solicitaste este cambio?</strong><br>
                                            Ignorá este correo. Tu contraseña actual seguirá siendo válida.
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="background-color: {bg_grey}; padding: 28px 48px; text-align: center; border-top: 1px solid #e8ecf0;">
                            <p style="margin: 0 0 8px 0; font-size: 13px; font-weight: 600; color: {text_dark};">
                                Ikolu App
                            </p>
                            <p style="margin: 0 0 12px 0; font-size: 12px; color: {text_grey}; line-height: 1.5;">
                                Gestión Inteligente de Aguas Subterráneas<br>
                                Monitoreo Avanzado y Cumplimiento Normativo
                            </p>
                            <p style="margin: 0 0 4px 0; font-size: 12px; color: {primary_blue};">
                                📞 Soporte: +56 9 3958 1688
                            </p>
                            <p style="margin: 0; font-size: 12px; color: {text_grey};">
                                🌐 <a href="https://ikolu.smarthydro.app" style="color: {link_color}; text-decoration: underline;">ikolu.smarthydro.app</a>
                            </p>
                        </td>
                    </tr>

                    <!-- Disclaimer -->
                    <tr>
                        <td style="padding: 16px 48px 24px 48px; text-align: center;">
                            <p style="margin: 0; font-size: 11px; color: #9aa5b1; line-height: 1.4;">
                                Este es un correo automático enviado desde <strong>no-reply@smarthydro.cl</strong>.<br>
                                No respondas a esta dirección.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

    try:
        send_mail(
            subject=subject,
            message=message_plain,
            from_email='no-reply@smarthydro.cl',
            recipient_list=[user_email],
            html_message=message_html,
            fail_silently=False,
        )
        logger.info(f"Email de recuperación enviado a {user_email}")
    except Exception as e:
        logger.error(f"Error enviando email de recuperación a {user_email}: {e}")
