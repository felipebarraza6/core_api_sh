import os
import django
from django.core.mail import send_mail
from django.conf import settings

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
django.setup()

def debug_email():
    print("📧 Iniciando depuración de correo...")
    print(f"Host: {settings.EMAIL_HOST}")
    print(f"Port: {settings.EMAIL_PORT}")
    print(f"User: {settings.EMAIL_HOST_USER}")
    print(f"From: {settings.DEFAULT_FROM_EMAIL}")
    
    subject = "Prueba de Depuración SMTP - SmartHydro"
    message = "Este es un correo de prueba para verificar la configuración SMTP."
    recipient_list = ['sporte@smarthydro.cl', 'felipebarraza@smarthydro.cl']
    
    try:
        print("⏳ Intentando enviar correo (fail_silently=False)...")
        result = send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            recipient_list,
            fail_silently=False
        )
        print(f"✅ Resultado de send_mail: {result}")
        if result:
            print("🚀 El correo parece haberse enviado correctamente desde Django.")
        else:
            print("❓ El correo no se envió (resultado 0).")
    except Exception as e:
        print(f"❌ Error al enviar correo: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_email()
