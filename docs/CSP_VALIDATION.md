# Validación de Configuración CSP (Content Security Policy)

## ✅ Estado de los Cambios

### 1. Dependencias
- **django-csp>=3.8,<4.0.0** ✅ Agregado a `api/requirements.txt` (línea 37)
- **Estado**: Presente en requirements pero NO instalado en contenedor actual

### 2. Configuración en settings.py
**Ubicación**: `api/settings.py` líneas 57-69

```python
# Content Security Policy (CSP) - Security Headers
# Configuración balanceada: API restrictiva + Admin funcional
CSP_DEFAULT_SRC = ("'none'",)  # Bloquear todo por defecto
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'")  # Admin necesita JS inline
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", "https://fonts.googleapis.com")
CSP_IMG_SRC = ("'self'", "data:")  # Imágenes propias + data URIs
CSP_FONT_SRC = ("'self'", "https://fonts.gstatic.com", "data:")
CSP_CONNECT_SRC = ("'self'",)  # Solo conexiones AJAX al mismo origen
CSP_OBJECT_SRC = ("'none'",)  # Bloquear objetos (Flash, etc.)
CSP_BASE_URI = ("'self'",)  # Restringir base URI
CSP_FRAME_SRC = ("'none'",)  # No permitir iframes
CSP_FRAME_ANCESTORS = ("'none'",)  # No permitir ser embebido
CSP_FORM_ACTION = ("'self'",)  # Solo enviar formularios al mismo origen
```

**Estado**: ✅ Configurado correctamente

### 3. Middleware CSP
**Ubicación**: `api/settings.py` línea 220

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "csp.middleware.CSPMiddleware",  # ✅ Content Security Policy
    "django.middleware.gzip.GZipMiddleware",
    ...
]
```

**Orden**: ✅ Correcto (después de Security y WhiteNoise, antes de GZip)

### 4. Otros Cambios de Seguridad

#### Cloudflare Proxy Headers
```python
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
```
**Estado**: ✅ Configurado

#### ALLOWED_HOSTS
```python
ALLOWED_HOSTS = [
    "api.smarthydro.app",
    "ikolu.smarthydro.app",
    ".smarthydro.app",  # ✅ Cualquier subdominio
    "localhost",
    "127.0.0.1",
    "postgres",
]
```
**Estado**: ✅ Configurado con soporte Cloudflare

#### Redis Connection
```python
"LOCATION": "redis://redis_secure:6379/1"  # ✅ Actualizado
```
**Estado**: ✅ Apuntando al contenedor correcto

## 📋 Análisis de Políticas CSP

### Políticas Restrictivas (Alta Seguridad)
✅ `CSP_DEFAULT_SRC = ("'none'",)` - Bloquea todo por defecto
✅ `CSP_OBJECT_SRC = ("'none'",)` - No plugins (Flash, Java, etc.)
✅ `CSP_FRAME_SRC = ("'none'",)` - No iframes
✅ `CSP_FRAME_ANCESTORS = ("'none'",)` - No puede ser embebido
✅ `CSP_BASE_URI = ("'self'",)` - Solo base URI propias
✅ `CSP_FORM_ACTION = ("'self'",)` - Solo enviar a mismo origen

### Políticas Funcionales (Django Admin Compatible)
✅ `CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'")` - Permite JS del admin
✅ `CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", "https://fonts.googleapis.com")`
✅ `CSP_IMG_SRC = ("'self'", "data:")` - Imágenes locales + data URIs
✅ `CSP_FONT_SRC = ("'self'", "https://fonts.gstatic.com", "data:")`
✅ `CSP_CONNECT_SRC = ("'self'",)` - AJAX solo al mismo origen

### ⚠️ Consideraciones de Seguridad

**'unsafe-inline' en SCRIPT_SRC y STYLE_SRC**:
- **Necesario** para Django Admin funcione (scripts y estilos inline)
- **Alternativa**: Usar nonces/hashes (complejo, requiere cambios en templates)
- **Mitigación**: El admin está protegido por autenticación

**Google Fonts (fonts.googleapis.com, fonts.gstatic.com)**:
- **Necesario** para Jazzmin (tema del admin)
- **Seguridad**: Dominios confiables de Google
- **Alternativa**: Hospedar fuentes localmente (más complejo)

## 🚀 Pasos para Aplicar

### 1. Verificar Cambios en Git
```bash
git status
git diff api/settings.py
```

### 2. Rebuild del Contenedor Django (REQUERIDO)
```bash
# OPCIÓN 1: Rebuild solo API (más rápido)
docker-compose -f docker-compose.production.secure.yml build django && \
docker-compose -f docker-compose.production.secure.yml up -d --no-deps django

# OPCIÓN 2: Rebuild API + Cron (si hay cambios compartidos)
docker-compose -f docker-compose.production.secure.yml build django cron && \
docker-compose -f docker-compose.production.secure.yml up -d --no-deps django cron
```

### 3. Verificar Instalación de django-csp
```bash
docker exec django_api_secure pip list | grep csp
# Debe mostrar: django-csp    3.x.x
```

### 4. Verificar Headers CSP en Producción
```bash
# Verificar que los headers CSP se envíen
curl -I https://api.smarthydro.app/admin/ | grep -i "content-security-policy"

# Debe mostrar algo como:
# Content-Security-Policy: default-src 'none'; script-src 'self' 'unsafe-inline'; ...
```

### 5. Verificar Logs
```bash
# Ver logs del contenedor
docker logs django_api_secure --tail=100

# NO debe haber errores relacionados con CSP
```

### 6. Probar el Admin
```bash
# 1. Abrir https://api.smarthydro.app/admin/
# 2. Login debe funcionar correctamente
# 3. Estilos y JavaScript deben cargar sin errores
# 4. Abrir consola del navegador (F12) y verificar que no haya errores CSP
```

## 🔍 Validación de Headers HTTP Esperados

### Headers que Django/django-csp debe enviar:
```
Content-Security-Policy: default-src 'none'; script-src 'self' 'unsafe-inline';
  style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data:;
  font-src 'self' https://fonts.gstatic.com data:; connect-src 'self';
  object-src 'none'; base-uri 'self'; frame-src 'none';
  frame-ancestors 'none'; form-action 'self'
```

### Headers que nginx-proxy debe enviar (conf/security_proxy.conf):
```
X-Frame-Options: SAMEORIGIN
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
```

### Headers de Django Security (settings.py):
```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

## ✅ Checklist Final

- [x] django-csp agregado a requirements.txt
- [x] Políticas CSP configuradas en settings.py
- [x] CSPMiddleware agregado a MIDDLEWARE
- [x] Políticas balanceadas (API restrictiva + Admin funcional)
- [x] Cloudflare proxy headers configurados
- [x] ALLOWED_HOSTS actualizado con wildcard
- [x] Redis connection actualizada
- [ ] **PENDIENTE**: Rebuild del contenedor para instalar django-csp
- [ ] **PENDIENTE**: Verificar headers CSP en producción
- [ ] **PENDIENTE**: Probar admin en navegador

## 📚 Referencias

- [django-csp Documentation](https://django-csp.readthedocs.io/)
- [CSP Header Reference](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP)
- [Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html)
