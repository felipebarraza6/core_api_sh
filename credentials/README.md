# Credenciales de Google Service Account

## ⚠️ SEGURIDAD

**NUNCA versionar este directorio a Git.** Los archivos aquí contienen claves privadas.

Este directorio contiene las credenciales necesarias para autenticarse con Google APIs:
- `google_service_account_key.json` - Service Account Key (generada en Google Cloud Console)

## Requisitos previos

1. **Google Cloud Console**
   - Service account con Gmail API habilitada
   - Archivo JSON descargado desde: Project → Service Accounts → Keys → Create new key

2. **Google Admin Console** (para Google Workspace)
   - Domain-wide delegation configurada para la service account
   - Scopes: `https://mail.google.com/`
   - Cliente delegado apunta a: `soporte@smarthydro.cl`

## Instalación en Producción (VPS)

```bash
# En el VPS, crear directorio seguro
sudo mkdir -p /opt/smarthydro/credentials
sudo chmod 700 /opt/smarthydro/credentials

# Copiar el archivo JSON
sudo cp google_service_account_key.json /opt/smarthydro/credentials/
sudo chmod 600 /opt/smarthydro/credentials/google_service_account_key.json
sudo chown www-data:www-data /opt/smarthydro/credentials/google_service_account_key.json

# Actualizar settings.py para apuntar a:
# GOOGLE_SERVICE_ACCOUNT_FILE = '/opt/smarthydro/credentials/google_service_account_key.json'
```

## Configuración en Django

En `api/settings.py`:
```python
GOOGLE_SERVICE_ACCOUNT_FILE = '/opt/smarthydro/credentials/google_service_account_key.json'
GOOGLE_DELEGATED_USER = 'soporte@smarthydro.cl'  # Cuenta que envía los correos
DEFAULT_FROM_EMAIL = 'soporte@smarthydro.cl'
```

## Uso en Django

```python
from django.core.mail import send_mail, EmailMultiAlternatives

# Envío simple
send_mail(
    subject='Reporte',
    message='Contenido...',
    from_email='soporte@smarthydro.cl',
    recipient_list=['usuario@example.com'],
)

# Con HTML y adjuntos
msg = EmailMultiAlternatives(
    'Asunto',
    'Texto plano',
    'soporte@smarthydro.cl',
    ['usuario@example.com']
)
msg.attach_alternative('<p>HTML</p>', 'text/html')
msg.attach_file('/ruta/al/archivo.xlsx')
msg.send()
```

## Troubleshooting

| Error | Causa | Solución |
|-------|-------|----------|
| `File not found` | Ruta incorrecta del JSON | Verificar `GOOGLE_SERVICE_ACCOUNT_FILE` |
| `invalid_grant` | Service account no delegada | Revisar Google Admin Console → Domain-wide delegation |
| `403 Forbidden` | Permisos insuficientes | La cuenta delegada debe existir en Google Workspace |
| Timeout | Firewall bloquea Google | Permitir salida a `mail.google.com:443` |

## Renovación de credenciales

Si necesitas renovar la clave (cada 90 días recomendado):

1. Google Cloud Console → Service Accounts → Seleccionar cuenta → Keys → Create new key
2. Descargar el nuevo JSON
3. Reemplazar `google_service_account_key.json`
4. Reiniciar el servicio Django en producción

---

**Documentación**: [Gmail API - Python Quickstart](https://developers.google.com/gmail/api/guides/sending)
