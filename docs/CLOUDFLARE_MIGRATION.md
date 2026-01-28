# 🚀 MIGRACIÓN A CLOUDFLARE - SmartHydro

**Fecha:** 2026-01-28
**Tiempo estimado:** 15 minutos

---

## 📋 PASO 1: CLOUDFLARE UI (5 minutos)

### 1.1 Agregar dominio a Cloudflare

```
1. Ir a: https://dash.cloudflare.com/
2. Click: "Add a site"
3. Ingresar: smarthydro.app
4. Seleccionar plan: Free
5. Click: "Continue"
```

### 1.2 Cambiar nameservers

Cloudflare te dará 2 nameservers, ejemplo:
```
kate.ns.cloudflare.com
tim.ns.cloudflare.com
```

**Ir a tu registrador de dominios** (GoDaddy, Namecheap, etc.) y cambiar:
```
ANTES: ns1.turegistrador.com, ns2.turegistrador.com
DESPUÉS: kate.ns.cloudflare.com, tim.ns.cloudflare.com
```

⏱️ **Esperar 5-30 minutos** (puede tardar hasta 24h pero usualmente es rápido)

### 1.3 Configurar SSL en Cloudflare

```
1. En Cloudflare Dashboard → SSL/TLS
2. Seleccionar modo: "Flexible"
3. Activar: "Always Use HTTPS"
4. Activar: "Automatic HTTPS Rewrites"
```

### 1.4 DNS Records (verificar)

En Cloudflare → DNS → Records, verificar que exista:
```
Type    Name    Content              Proxy Status
A       api     IP_DE_TU_SERVIDOR    Proxied (naranja)
```

Si no existe, agregarlo:
```
Type: A
Name: api
IPv4 address: [TU IP DEL SERVIDOR]
Proxy status: Proxied ✅ (naranja)
TTL: Auto
```

---

## 📝 PASO 2: CAMBIOS EN CÓDIGO (3 minutos)

### 2.1 Actualizar settings.py

Abrir: `/root/core_api_sh/api/settings.py`

**Buscar línea 29-35 y reemplazar:**

```python
# ANTES:
ALLOWED_HOSTS = [
    "api.smarthydro.app",
    "ikolu.smarthydro.app",
    "localhost",
    "127.0.0.1",
    "postgres",
]

# DESPUÉS:
ALLOWED_HOSTS = [
    "api.smarthydro.app",
    "ikolu.smarthydro.app",
    "localhost",
    "127.0.0.1",
    "postgres",
    ".smarthydro.app",  # Cualquier subdominio
]
```

**Buscar línea 28 y reemplazar:**

```python
# ANTES:
CSRF_TRUSTED_ORIGINS = ["https://*.smarthydro.app", "https://api.smarthydro.app", "https://ikolu.smarthydro.app"]

# DESPUÉS:
CSRF_TRUSTED_ORIGINS = [
    "https://api.smarthydro.app",
    "https://ikolu.smarthydro.app",
    "https://smarthydro.app",
    "https://*.smarthydro.app",
]
```

**Agregar después de línea 45 (después de SECURE_HSTS_PRELOAD):**

```python
# Cloudflare: Confiar en proxy headers
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
```

### 2.2 NO necesitas cambiar docker-compose

El `docker-compose.production.secure.yml` funciona bien con Cloudflare.
Let's Encrypt seguirá funcionando (aunque Cloudflare también maneja SSL).

---

## 🔄 PASO 3: REBUILD CONTAINERS (2 minutos)

```bash
# 1. Rebuild solo API (el cambio está en settings.py)
docker-compose -f docker-compose.production.secure.yml build django

# 2. Reiniciar Django
docker-compose -f docker-compose.production.secure.yml up -d --no-deps django

# 3. Verificar logs
docker logs django_api_secure --tail=50
```

---

## ✅ PASO 4: VALIDACIÓN (5 minutos)

### 4.1 Verificar DNS

```bash
# Debe mostrar IPs de Cloudflare (104.x.x.x o 172.x.x.x)
nslookup api.smarthydro.app
```

### 4.2 Verificar SSL

```bash
# Debe mostrar: HTTP/2 200 (o 301/302)
curl -I https://api.smarthydro.app/admin/
```

### 4.3 Verificar API

```bash
# Debe responder correctamente
curl https://api.smarthydro.app/api/
```

### 4.4 Verificar en navegador

Abrir: https://api.smarthydro.app/admin/
- ✅ Debe cargar sin errores SSL
- ✅ Debe mostrar login de Django
- ✅ Certificado debe ser de Cloudflare

---

## 🐛 SOLUCIÓN DE PROBLEMAS

### Error: "400 Bad Request"

```bash
# Ver logs de Django
docker logs django_api_secure --tail=100 | grep -i "host"

# Solución: Agregar más hosts en ALLOWED_HOSTS
# Editar settings.py y agregar: "*" temporalmente
```

### Error: "CSRF token missing"

```python
# Verificar en settings.py:
CSRF_TRUSTED_ORIGINS = [
    "https://api.smarthydro.app",
    "https://*.smarthydro.app",
]
```

### Error: Redirect loop

```
# En Cloudflare Dashboard:
# SSL/TLS → Overview → Cambiar de "Flexible" a "Full"
```

### Error: "Server not found"

```bash
# DNS aún no propagó, esperar más tiempo
# Verificar:
dig api.smarthydro.app
```

---

## 📞 COMANDOS DE EMERGENCIA

### Rollback DNS (si algo falla)

```
Volver a nameservers originales en tu registrador
Esperar 5-30 minutos
```

### Ver logs en tiempo real

```bash
docker logs -f django_api_secure
```

### Reiniciar todo

```bash
docker-compose -f docker-compose.production.secure.yml restart django
```

---

## ✅ CHECKLIST FINAL

- [ ] DNS cambiado a nameservers de Cloudflare
- [ ] DNS propagado (nslookup muestra IPs de Cloudflare)
- [ ] SSL configurado en Cloudflare ("Flexible")
- [ ] settings.py actualizado (ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS)
- [ ] Proxy headers configurados (USE_X_FORWARDED_HOST)
- [ ] Django container rebuildeado
- [ ] https://api.smarthydro.app/admin/ funciona
- [ ] API endpoints responden correctamente
- [ ] Certificado SSL válido en navegador
- [ ] No hay errores en logs de Django

---

## 🎯 RESUMEN DE LO QUE HACE CLOUDFLARE

**ANTES (sin Cloudflare):**
```
Cliente → IP_Servidor → nginx-proxy → Django
         [Let's Encrypt SSL]
```

**DESPUÉS (con Cloudflare):**
```
Cliente → Cloudflare → IP_Servidor → nginx-proxy → Django
         [CF SSL]     [Let's Encrypt SSL]
```

**Beneficios:**
- ✅ DDoS protection automático
- ✅ CDN global (caché de archivos estáticos)
- ✅ Firewall de aplicación web (WAF)
- ✅ Analytics gratis
- ✅ Oculta IP real del servidor
- ✅ SSL gratis y automático

---

**¿Listo? Cuando cambies los DNS, avísame y te ayudo con cualquier problema en tiempo real.**
