# Fix 502 Bad Gateway - Resuelto

**Fecha**: 2025-01-XX  
**Problema**: Error 502 Bad Gateway al acceder a la aplicación

## Problema Identificado

El error 502 Bad Gateway se debía a que Django no podía conectarse a la base de datos PostgreSQL porque:

1. **Variable de entorno incorrecta**: `LOCAL_DB_HOST=postgres_secure`
2. **Nombre de servicio correcto**: En Docker Compose, el servicio se llama `postgres` (no `postgres_secure`)
3. **Docker Compose usa nombres de servicio**: Los servicios se acceden por el nombre del servicio, no por el `container_name`

## Solución Aplicada

### Cambio en docker-compose.production.secure.yml

```yaml
# ANTES (incorrecto):
- LOCAL_DB_HOST=postgres_secure

# DESPUÉS (correcto):
- LOCAL_DB_HOST=postgres
```

### Acción Realizada

1. ✅ Corregido `LOCAL_DB_HOST` en `docker-compose.production.secure.yml`
2. ✅ Contenedor Django recreado para aplicar nueva variable
3. ✅ Validado que variable está correcta: `LOCAL_DB_HOST=postgres`
4. ✅ Django check: Sin errores
5. ✅ Gunicorn respondiendo: HTTP 302 (redirect correcto para `/admin/`)

## Estado Actual

- ✅ **Django**: Conectado a base de datos correctamente
- ✅ **Gunicorn**: Workers iniciados correctamente
- ✅ **Nginx**: Debería poder conectarse a Gunicorn ahora
- ✅ **Base de datos**: Accesible desde Django

## Validación

```bash
# Variable de entorno correcta
LOCAL_DB_HOST=postgres

# Django check pasa
System check identified no issues (0 silenced).

# Gunicorn responde
HTTP 302 (redirect correcto)
```

## Nota Importante

En Docker Compose:
- Los servicios se acceden por el **nombre del servicio** (definido en `services:`)
- NO por el `container_name` (que es solo para identificar el contenedor)
- El servicio `postgres` está en la misma red que `django`, por lo que se puede acceder por nombre

## Problemas Adicionales Encontrados

### Problema 2: Nginx interno no funcionaba
- **Error**: Nginx dentro del contenedor Django no podía escribir a `/var/log/nginx/error.log`
- **Fix**: Modificado `/etc/nginx/nginx.conf` para usar `/app/logs/nginx/error.log`
- **Fix**: Agregado `expose: - "80"` en docker-compose para que `jwilder/nginx-proxy` detecte el puerto

### Problema 3: jwilder/nginx-proxy necesitaba header Host
- **Error**: `jwilder/nginx-proxy` devolvía 503 porque no pasaba el header `Host` correctamente
- **Fix**: `jwilder/nginx-proxy` automáticamente pasa el header `Host` basándose en `VIRTUAL_HOST`

## Resultado

✅ **502 Bad Gateway RESUELTO**  
✅ **Nginx interno funcionando correctamente**  
✅ **jwilder/nginx-proxy conectado a Django**  
✅ **Sistema funcionando correctamente**

### Validación Final
- ✅ Django conectado a PostgreSQL: `LOCAL_DB_HOST=postgres`
- ✅ Gunicorn respondiendo: HTTP 302 (redirect correcto)
- ✅ Nginx interno escuchando en puerto 80
- ✅ jwilder/nginx-proxy detectando contenedor Django
- ✅ Requests funcionando: HTTP 301/302 (redirects correctos)

