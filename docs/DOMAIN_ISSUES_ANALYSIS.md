# Análisis de Problemas de Dominio - SmartHydro

**Fecha**: 2026-01-28

---

## 1. Error 525 en smarthydro.app (Dominio Raíz)

### 🔍 Diagnóstico

**Error reportado:**
```
HTTP/2 525 - SSL Handshake Failed
```

**Causa raíz:** El dominio `smarthydro.app` NO está configurado en este VPS.

### 📊 Configuración Actual

**Dominios configurados en Docker/nginx:**
- ✅ `api.smarthydro.app` - Configurado y funcionando
- ✅ `ikolu.smarthydro.app` - (si está configurado)
- ❌ `smarthydro.app` - NO configurado

**DNS actual:**
```bash
dig smarthydro.app +short
# Resultado: 172.67.169.192, 104.21.27.212 (IPs de Cloudflare)

dig api.smarthydro.app +short
# Resultado: 172.67.169.192, 104.21.27.212 (IPs de Cloudflare)
```

Ambos dominios apuntan a Cloudflare, pero:
- `api.smarthydro.app` → Cloudflare → VPS (nginx tiene configuración) → ✅ Funciona
- `smarthydro.app` → Cloudflare → VPS (nginx NO tiene configuración) → ❌ Error 525

### 🎯 Solución Depende del Uso

#### Escenario A: smarthydro.app apunta a OTRO servidor (más probable)
Si `smarthydro.app` debe apuntar a una landing page, frontend React, etc. en otro servidor:

**✅ NO HACER NADA** - El error 525 es esperado porque este VPS solo maneja `api.smarthydro.app`

**Acción requerida:** Verificar en Cloudflare que:
- El registro DNS para `smarthydro.app` apunte al servidor correcto
- Si es otro servidor, asegurarse que tenga SSL configurado correctamente

#### Escenario B: smarthydro.app debe funcionar en ESTE VPS
Si quieres que `smarthydro.app` también sirva la API Django:

**Solución:** Agregar el dominio al VIRTUAL_HOST

```bash
# 1. Editar .env
VIRTUAL_HOST=api.smarthydro.app,smarthydro.app
LETSENCRYPT_HOST=api.smarthydro.app,smarthydro.app

# 2. Recrear contenedor
docker-compose -f docker-compose.production.secure.yml up -d django

# 3. Esperar a que Let's Encrypt genere certificado
# (puede tomar 1-5 minutos)
```

También necesitas actualizar `settings.py`:
```python
ALLOWED_HOSTS = [
    "api.smarthydro.app",
    "smarthydro.app",  # ← Agregar
    ".smarthydro.app",
    "localhost",
    "127.0.0.1",
    "postgres",
]

CSRF_TRUSTED_ORIGINS = [
    "https://api.smarthydro.app",
    "https://smarthydro.app",  # ← Agregar
    "https://ikolu.smarthydro.app",
    "https://*.smarthydro.app",
]
```

### ⏳ ¿Es Temporal?

**SI el dominio debe apuntar a otro servidor:** Sí, es "temporal" en el sentido de que es un error esperado mientras se configura el otro servidor o los DNS se propagan.

**SI el dominio debe funcionar en este VPS:** No es temporal, necesita configuración adicional como se indica arriba.

---

## 2. Blacklist SMTP - _dc-mx.68c19006bcf2.smarthydro.app

### 🔍 Diagnóstico

**Dominio afectado:**
```
_dc-mx.68c19006bcf2.smarthydro.app
```

**Blacklist:** UCEPROTECTL3

**Error:** "Failed To Connect"

### 📊 Análisis

Este es un **registro MX de Cloudflare** (probablemente Email Routing de Cloudflare):
- `_dc-mx` = Cloudflare email routing record
- `68c19006bcf2` = ID único del registro
- Está en blacklist UCEPROTECTL3 (lista de IPs bloqueadas por spam)

### ⚠️ Impacto

**NO afecta:**
- ✅ La API de Django
- ✅ Las peticiones HTTPS
- ✅ Los headers de seguridad CSP
- ✅ El funcionamiento de la aplicación

**SÍ afecta:**
- ❌ Envío de emails SALIENTES desde este servidor
- ❌ Reputación del dominio para correo
- ❌ Posibles bounces de emails enviados

### 🎯 Soluciones

#### Opción 1: Usar servicio SMTP externo (RECOMENDADO)

Ya tienes configurado en `settings.py`:
```python
EMAIL_HOST = "s1042.use1.mysecurecloudhost.com"
EMAIL_PORT = 465
EMAIL_USE_SSL = True
EMAIL_HOST_USER = "notify@smarthydro.app"
```

**Verificar:** ¿Estás usando este SMTP externo o el local?

Si usas el externo (como parece), **NO tienes que hacer nada** - la blacklist no te afecta porque no envías emails desde este VPS.

#### Opción 2: Deshabilitar Email Routing en Cloudflare

Si no usas Cloudflare Email Routing:

1. Ir a Cloudflare Dashboard → Email → Email Routing
2. Deshabilitarlo si no se usa
3. Esperar 24-48 horas para que se actualicen las blacklists

#### Opción 3: Solicitar remoción de blacklist

Si realmente necesitas enviar emails desde el VPS:

1. Ir a https://www.uceprotect.net/en/rblcheck.php
2. Verificar la IP específica en blacklist
3. Seguir proceso de remoción (puede costar dinero con UCEPROTECT)
4. Implementar SPF/DKIM/DMARC correctamente

### 🔍 Verificar si te afecta

```bash
# Ver si estás enviando emails desde el VPS
docker logs django_api_secure | grep -i "email\|smtp" | tail -20

# Ver configuración de email actual
docker exec django_api_secure python manage.py shell -c "
from django.conf import settings
print('EMAIL_HOST:', settings.EMAIL_HOST)
print('EMAIL_PORT:', settings.EMAIL_PORT)
"
```

Si `EMAIL_HOST` es `s1042.use1.mysecurecloudhost.com`, entonces **no te afecta** la blacklist.

---

## 🎯 Resumen Ejecutivo

### Error 525 (smarthydro.app)

| Pregunta | Respuesta |
|----------|-----------|
| ¿Afecta la API? | ❌ NO - api.smarthydro.app funciona perfectamente |
| ¿Es temporal? | Depende - Si apunta a otro servidor, es esperado |
| ¿Requiere acción? | Solo si smarthydro.app debe funcionar en este VPS |
| ¿Urgente? | ❌ NO |

### Blacklist SMTP (_dc-mx)

| Pregunta | Respuesta |
|----------|-----------|
| ¿Afecta la API? | ❌ NO |
| ¿Afecta envío de emails? | Solo si envías desde el VPS (probablemente no) |
| ¿Requiere acción? | Solo si usas email routing local |
| ¿Urgente? | ❌ NO (si usas SMTP externo) |

---

## ✅ Conclusión

**Ambos problemas son INDEPENDIENTES de los headers CSP que acabamos de configurar.**

### Headers CSP: ✅ FUNCIONANDO CORRECTAMENTE
- django-csp instalado y activo
- Headers enviados correctamente
- Sucuri puede tardar 24h en actualizar cache

### Error 525: ⏳ DEPENDE
- Si smarthydro.app apunta a otro servidor: **es esperado**
- Si debe funcionar aquí: **necesita configuración adicional**

### Blacklist SMTP: ℹ️ PROBABLEMENTE NO TE AFECTA
- Si usas SMTP externo (s1042.use1.mysecurecloudhost.com): **ignorar**
- Si usas email routing local: **necesita atención**

---

## 🔧 Comandos de Verificación

```bash
# Verificar configuración de email
docker exec django_api_secure python manage.py shell -c "
from django.conf import settings;
print('EMAIL_HOST:', settings.EMAIL_HOST)
"

# Verificar si hay errores de email en logs
docker logs django_api_secure 2>&1 | grep -i "email\|smtp" | tail -30

# Ver dominios configurados en nginx
docker exec nginx_proxy cat /etc/nginx/conf.d/default.conf | grep server_name

# Verificar headers CSP (para confirmar que siguen funcionando)
curl -sI https://api.smarthydro.app/health/ | grep -i content-security-policy
```
