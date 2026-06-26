#!/usr/bin/env python
"""
Script para testear la integración de Gmail API.
Uso: python manage.py shell < scripts/test_gmail_api.py
"""

import os
import sys
from django.conf import settings
from django.core.mail import send_mail, EmailMultiAlternatives

print("\n" + "="*60)
print("TEST: Integración de Gmail API")
print("="*60 + "\n")

# 1. Verificar configuración
print("[1] Verificando configuración...")
print(f"    - EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
print(f"    - DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")
print(f"    - GOOGLE_DELEGATED_USER: {settings.GOOGLE_DELEGATED_USER}")
print(f"    - GOOGLE_SERVICE_ACCOUNT_FILE: {settings.GOOGLE_SERVICE_ACCOUNT_FILE}")

# 2. Verificar que el archivo JSON existe
print("\n[2] Verificando archivo de credenciales...")
if os.path.exists(settings.GOOGLE_SERVICE_ACCOUNT_FILE):
    print(f"    ✓ Archivo encontrado: {settings.GOOGLE_SERVICE_ACCOUNT_FILE}")
else:
    print(f"    ✗ ERROR: Archivo NO encontrado: {settings.GOOGLE_SERVICE_ACCOUNT_FILE}")
    sys.exit(1)

# 3. Intentar conectar a Gmail API
print("\n[3] Intentando conectar a Gmail API...")
try:
    from api.utils.gmail import GmailApiBackend
    backend = GmailApiBackend()
    print("    ✓ Conexión a Gmail API exitosa")
except Exception as e:
    print(f"    ✗ ERROR: {e}")
    sys.exit(1)

# 4. Enviar email de test
print("\n[4] Enviando correo de prueba...")
try:
    recipient = os.environ.get("TEST_EMAIL_RECIPIENT", "raymundoanavalon@smarthydro.cl")

    send_mail(
        subject="[TEST] Integración Gmail API - SmartHydro",
        message=f"""
Este es un correo de prueba para validar la integración de Gmail API.

Información del test:
- Backend: {settings.EMAIL_BACKEND}
- Remitente: {settings.DEFAULT_FROM_EMAIL}
- Destinatario: {recipient}
- Fecha: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Si recibiste este correo, significa que la integración funciona correctamente.

---
SmartHydro - Sistema de Monitoreo Hidrológico
        """,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[recipient],
        fail_silently=False,
    )
    print(f"    ✓ Correo enviado a {recipient}")
except Exception as e:
    print(f"    ✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 5. Enviar email con HTML
print("\n[5] Enviando correo con HTML...")
try:
    msg = EmailMultiAlternatives(
        subject="[TEST] Correo con HTML - SmartHydro",
        body="Este es el texto plano del correo.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient]
    )
    msg.attach_alternative(
        """
        <h2>Prueba de Correo HTML</h2>
        <p>Este es un correo de <strong>prueba</strong> con formato HTML.</p>
        <ul>
            <li>Prueba 1: OK</li>
            <li>Prueba 2: OK</li>
            <li>Prueba 3: OK</li>
        </ul>
        """,
        "text/html"
    )
    msg.send()
    print(f"    ✓ Correo HTML enviado a {recipient}")
except Exception as e:
    print(f"    ✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*60)
print("✓ TODOS LOS TESTS PASARON")
print("="*60)
print("\nNota: Revisa tu buzón en:", recipient)
