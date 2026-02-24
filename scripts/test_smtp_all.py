import os
import django
import smtplib
from django.conf import settings

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "api.settings")
django.setup()

def test_smtp_variants():
    hosts = ["s1042.use1.mysecurecloudhost.com", "mail.smarthydro.app"]
    ports = [465, 587, 25]
    passwords = ["notify.2025", "notifiy.2025"]
    user = "notify@smarthydro.app"
    recipient = "felipebarraza@smarthydro.cl"
    
    print(f"🔍 Probando variantes de SMTP para {user}...")
    
    for host in hosts:
        for port in ports:
            for pwd in passwords:
                print(f"\n--- Probando {host}:{port} con pwd {'...' if pwd else 'None'} ---")
                try:
                    if port == 465:
                        print("🔒 Usando SMTP_SSL...")
                        server = smtplib.SMTP_SSL(host, port, timeout=10)
                    else:
                        print("🔓 Usando SMTP + STARTTLS...")
                        server = smtplib.SMTP(host, port, timeout=10)
                        if port == 587:
                            server.starttls()
                    
                    server.login(user, pwd)
                    print("✅ ¡LOGIN EXITOSO!")
                    
                    # Probar envío
                    msg = f"Subject: Prueba SMTP Exitosa\n\nPrueba desde host {host} puerto {port}"
                    server.sendmail(user, [recipient], msg)
                    print("🚀 ¡CORREO ENVIADO!")
                    server.quit()
                    return # Si funciona, terminamos
                    
                except Exception as e:
                    print(f"❌ Falló: {type(e).__name__}: {e}")
                    try:
                        server.quit()
                    except:
                        pass

if __name__ == "__main__":
    test_smtp_variants()
