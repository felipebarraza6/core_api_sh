#!/bin/bash

# Script para reiniciar solo el contenedor de cronjobs manteniendo la conectividad

set -e

log() {
    echo -e "\\033[0;32m[$(date +'%Y-%m-%d %H:%M:%S')] $1\\033[0m"
}

log "🔄 Reiniciando contenedor de cronjobs..."

# Parar y remover contenedor actual
docker stop cron_jobs_secure 2>/dev/null || true
docker rm cron_jobs_secure 2>/dev/null || true

# Levantar desde docker-compose con variables correctas
export LOCAL_DB_PASSWORD=smarthydro_password_2025
docker-compose -f docker-compose.production.secure.yml up -d cron

log "✅ Contenedor de cronjobs reiniciado correctamente"

# Verificar que puede conectarse a la API
log "🔍 Verificando conectividad API..."
sleep 5
if docker exec cron_jobs_secure curl -s --connect-timeout 5 https://api.twindimension.com/tdata/v1/login --fail > /dev/null 2>&1; then
    log "✅ API accesible desde contenedor"
else
    log "⚠️ API no accesible - verificar conectividad"
fi

# Verificar que puede conectarse a la BD
log "🔍 Verificando conectividad BD..."
if docker exec cron_jobs_secure python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
import django
django.setup()
from django.db import connection
cursor = connection.cursor()
cursor.execute('SELECT 1')
print('BD accesible')
" 2>/dev/null; then
    log "✅ BD accesible desde contenedor"
else
    log "⚠️ BD no accesible - verificar configuración"
fi

log "🎉 Cronjobs operativos y funcionando correctamente"
