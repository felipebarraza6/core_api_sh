# 🐳 INSTRUCCIONES PARA LEVANTAR DOCKER - SMARTHYDRO

**Archivo de configuración**: `docker-compose.production.secure.yml`
**Ambiente**: Producción segura

---

## 🚀 LEVANTAMIENTO INICIAL

### Paso 1: Crear archivo `.env`

```bash
cat > .env << 'EOF'
# Base de datos local (CAMBIAR A TU PASSWORD)
LOCAL_DB_PASSWORD=tu_password_super_seguro_123

# Dominio (CAMBIAR A TU DOMINIO)
VIRTUAL_HOST=api.smarthydro.app
LETSENCRYPT_HOST=api.smarthydro.app
LETSENCRYPT_EMAIL=admin@smarthydro.app

# Cluster (si lo necesitas)
USE_CLUSTER=false
CLUSTER_DB_HOST=tu_cluster_host
CLUSTER_DB_PASSWORD=tu_cluster_password
EOF
```

### Paso 2: Build de la imagen Django

```bash
# Build de imagen con Dockerfile
docker-compose -f docker-compose.production.secure.yml build

# Verify that build was successful
docker images | grep smarthydro
```

### Paso 3: Crear directorios de volúmenes

```bash
# Crear directorios para persistencia de datos
sudo mkdir -p /opt/smarthydro/postgres_data
sudo mkdir -p /opt/smarthydro/postgres_logs
sudo mkdir -p /opt/smarthydro/django_static
sudo mkdir -p /opt/smarthydro/django_media
sudo mkdir -p /opt/smarthydro/django_logs
sudo mkdir -p /opt/smarthydro/cron_logs

# Permisos correctos
sudo chmod -R 755 /opt/smarthydro
sudo chown -R 999:999 /opt/smarthydro/postgres_data
```

### Paso 4: Levantar servicios

```bash
# Levantar todos los servicios (en background)
docker-compose -f docker-compose.production.secure.yml up -d

# Ver que todos estén corriendo
docker-compose -f docker-compose.production.secure.yml ps

# Ver logs en tiempo real
docker-compose -f docker-compose.production.secure.yml logs -f
```

---

## 🔍 VERIFICACIÓN POST-LEVANTAMIENTO

### Verificar que servicios estén HEALTHY

```bash
# Ver estado detallado
docker-compose -f docker-compose.production.secure.yml ps

# Esperado:
# nginx_proxy     - healthy
# postgres        - healthy
# django          - healthy
# cron            - healthy
```

### Acceder al Dashboard

```
https://api.smarthydro.app/admin/
```

**Usuario admin**:
- Username: `admin`
- Password: `admin` (CAMBIAR EN PRODUCCIÓN)

---

## 🔧 COMANDOS ÚTILES

### Ver logs

```bash
# Logs de Django
docker-compose -f docker-compose.production.secure.yml logs django

# Logs de PostgreSQL
docker-compose -f docker-compose.production.secure.yml logs postgres

# Logs de Cron
docker-compose -f docker-compose.production.secure.yml logs cron

# Logs en tiempo real (últimas 100 líneas)
docker-compose -f docker-compose.production.secure.yml logs -f --tail=100
```

### Ejecutar comandos Django

```bash
# Ejecutar manage.py
docker-compose -f docker-compose.production.secure.yml exec django python manage.py [comando]

# Ejemplos:
docker-compose -f docker-compose.production.secure.yml exec django python manage.py migrate
docker-compose -f docker-compose.production.secure.yml exec django python manage.py createsuperuser
docker-compose -f docker-compose.production.secure.yml exec django python manage.py collectstatic
```

### Detener/Reiniciar servicios

```bash
# Parar todos los servicios
docker-compose -f docker-compose.production.secure.yml down

# Reiniciar servicios específicos
docker-compose -f docker-compose.production.secure.yml restart django
docker-compose -f docker-compose.production.secure.yml restart postgres
docker-compose -f docker-compose.production.secure.yml restart cron

# Parar pero mantener volúmenes
docker-compose -f docker-compose.production.secure.yml down --volumes
```

---

## 🐛 TROUBLESHOOTING

### 1. PostgreSQL no inicia

```bash
# Ver logs
docker-compose -f docker-compose.production.secure.yml logs postgres

# Solución: Permisos en /opt/smarthydro
sudo chmod -R 755 /opt/smarthydro
sudo chown -R 999:999 /opt/smarthydro/postgres_data

# Reiniciar
docker-compose -f docker-compose.production.secure.yml restart postgres
```

### 2. Django no conecta a BD

```bash
# Verificar que postgres esté healthy
docker-compose -f docker-compose.production.secure.yml ps

# Ver logs de Django
docker-compose -f docker-compose.production.secure.yml logs django

# Reintentar conectar
docker-compose -f docker-compose.production.secure.yml restart django
```

### 3. Nginx no expone puertos

```bash
# Verificar que nginx esté corriendo
docker ps | grep nginx

# Verificar puertos
docker port nginx_proxy

# Esperado: 0.0.0.0:80->80, 0.0.0.0:443->443
```

### 4. Error en Dashboard: "Template error"

```bash
# Validar que template sea correcto
docker-compose -f docker-compose.production.secure.yml exec django python manage.py shell
# Dentro de Python shell:
from django.template import loader
template = loader.get_template('admin/dashboard.html')
# Si no hay error, template está OK

# Si hay error, revisar templates/admin/dashboard.html
```

---

## 📊 MONITOREO

### Ver consumo de recursos

```bash
docker stats
```

### Backup de BD

```bash
# Backup de PostgreSQL
docker-compose -f docker-compose.production.secure.yml exec postgres pg_dump -U smarthydro_user smarthydro_prod > backup_$(date +%Y%m%d_%H%M%S).sql
```

---

## 🔐 SEGURIDAD

### Cambiar password por defecto

```bash
# Entrar al shell Django
docker-compose -f docker-compose.production.secure.yml exec django python manage.py shell

# Dentro de Python:
from django.contrib.auth.models import User
user = User.objects.get(username='admin')
user.set_password('nuevo_password_seguro')
user.save()
```

### Ver variables de entorno

```bash
docker-compose -f docker-compose.production.secure.yml config | grep POSTGRES
```

---

## ✅ CHECKLIST FINAL

- [ ] `.env` creado con passwords seguros
- [ ] Directorios `/opt/smarthydro` creados
- [ ] `docker-compose build` ejecutado
- [ ] `docker-compose up -d` ejecutado
- [ ] Todos los servicios están HEALTHY
- [ ] Dashboard accesible en https://api.smarthydro.app/admin/
- [ ] Password de admin cambiad
- [ ] Logs analizados sin errores

---

## 🚨 EN CASO DE EMERGENCIA

### Parar todo y resetear

```bash
# Parar servicios
docker-compose -f docker-compose.production.secure.yml down

# Limpiar datos (⚠️ CUIDADO - BORRA TODO)
sudo rm -rf /opt/smarthydro/*

# Recrear desde cero
# Seguir pasos del 3 en adelante
```

---

**Documento creado**: 14 Diciembre 2025
**Status**: ✅ LISTO PARA PRODUCCIÓN
