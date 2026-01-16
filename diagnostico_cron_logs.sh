#!/bin/bash

# Script de diagnóstico para cron jobs y logs de SmartHydro
# Autor: Asistente IA
# Fecha: $(date)

set -e

log() {
    echo -e "\\033[0;32m[$(date +'%Y-%m-%d %H:%M:%S')] $1\\033[0m"
}

error() {
    echo -e "\\033[0;31m[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1\\033[0m"
}

warning() {
    echo -e "\\033[0;33m[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1\\033[0m"
}

echo "=========================================="
echo "🔍 DIAGNÓSTICO CRON JOBS Y LOGS SMARTHYDRO"
echo "=========================================="
echo ""

# 1. Verificar estado del contenedor de cron
log "1. Verificando estado del contenedor de cron..."
if docker ps | grep -q cron_jobs_secure; then
    log "✅ Contenedor cron_jobs_secure está ejecutándose"
    CONTAINER_STATUS=$(docker ps --format "table {{.Names}}\t{{.Status}}" | grep cron_jobs_secure)
    log "   Estado: $CONTAINER_STATUS"
else
    error "❌ Contenedor cron_jobs_secure NO está ejecutándose"
    exit 1
fi

# 2. Verificar logs del contenedor
log ""
log "2. Verificando logs del contenedor..."
RECENT_LOGS=$(docker logs cron_jobs_secure --tail 10 2>/dev/null | grep -E "(ERROR|WARNING|Exception)" || true)
if [ -n "$RECENT_LOGS" ]; then
    warning "⚠️ Errores recientes en logs del contenedor:"
    echo "$RECENT_LOGS"
else
    log "✅ No hay errores recientes en logs del contenedor"
fi

# 3. Verificar cron jobs instalados
log ""
log "3. Verificando cron jobs instalados..."
if docker exec cron_jobs_secure crontab -l 2>/dev/null | grep -q "django-cronjobs"; then
    log "✅ Cron jobs de Django están instalados"
    CRON_COUNT=$(docker exec cron_jobs_secure crontab -l 2>/dev/null | grep "django-cronjobs" | wc -l)
    log "   Total de cron jobs: $CRON_COUNT"
else
    error "❌ Cron jobs de Django NO están instalados"
fi

# 4. Verificar directorios de logs
log ""
log "4. Verificando directorios de logs..."
LOG_DIRS=("/tmp/smarthydro" "/var/log/smarthydro" "/opt/smarthydro/cron_logs")

for dir in "${LOG_DIRS[@]}"; do
    if docker exec cron_jobs_secure test -d "$dir" 2>/dev/null; then
        log "✅ Directorio $dir existe en contenedor"
        FILE_COUNT=$(docker exec cron_jobs_secure find "$dir" -name "*.log" -type f 2>/dev/null | wc -l)
        log "   Archivos .log: $FILE_COUNT"
    else
        warning "⚠️ Directorio $dir NO existe en contenedor"
    fi
done

# 5. Verificar archivos de logs específicos
log ""
log "5. Verificando archivos de logs específicos..."
LOG_FILES=("twin_1.log" "twin_5.log" "twin_60.log" "dga.log" "sma.log" "alerts.log" "cluster_backup.log")

for file in "${LOG_FILES[@]}"; do
    if docker exec cron_jobs_secure test -f "/tmp/smarthydro/$file" 2>/dev/null; then
        SIZE=$(docker exec cron_jobs_secure stat -c%s "/tmp/smarthydro/$file" 2>/dev/null)
        MTIME=$(docker exec cron_jobs_secure stat -c%y "/tmp/smarthydro/$file" 2>/dev/null)
        log "✅ $file existe (${SIZE} bytes, modificado: $MTIME)"
    else
        warning "⚠️ $file NO existe"
    fi
done

# 6. Verificar logs más recientes
log ""
log "6. Verificando logs más recientes..."
RECENT_TIME=$(date -d '5 minutes ago' +%s)
for file in "${LOG_FILES[@]}"; do
    if docker exec cron_jobs_secure test -f "/tmp/smarthydro/$file" 2>/dev/null; then
        FILE_TIME=$(docker exec cron_jobs_secure stat -c%Y "/tmp/smarthydro/$file" 2>/dev/null)
        if [ "$FILE_TIME" -gt "$RECENT_TIME" ]; then
            log "✅ $file se actualizó recientemente"
        else
            warning "⚠️ $file NO se ha actualizado recientemente"
        fi
    fi
done

# 7. Verificar script de rotación
log ""
log "7. Verificando script de rotación de logs..."
if docker exec cron_jobs_secure test -f "/usr/local/bin/rotate-cron-logs.sh" 2>/dev/null; then
    log "✅ Script rotate-cron-logs.sh existe"
    if docker exec cron_jobs_secure test -x "/usr/local/bin/rotate-cron-logs.sh" 2>/dev/null; then
        log "✅ Script rotate-cron-logs.sh es ejecutable"
    else
        warning "⚠️ Script rotate-cron-logs.sh NO es ejecutable"
    fi
else
    error "❌ Script rotate-cron-logs.sh NO existe"
fi

# 8. Verificar procesos cron activos
log ""
log "8. Verificando procesos cron activos..."
ACTIVE_CRONS=$(docker exec cron_jobs_secure ps aux | grep -E "(cron|manage.py crontab)" | grep -v grep | wc -l)
if [ "$ACTIVE_CRONS" -gt 0 ]; then
    log "✅ Hay $ACTIVE_CRONS procesos cron activos"
else
    warning "⚠️ No hay procesos cron activos"
fi

# 9. Verificar conectividad de base de datos
log ""
log "9. Verificando conectividad de base de datos..."
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
    log "✅ Base de datos accesible desde contenedor"
else
    error "❌ Base de datos NO accesible desde contenedor"
fi

# 10. Verificar permisos de logs
log ""
log "10. Verificando permisos de logs..."
for file in "${LOG_FILES[@]}"; do
    if docker exec cron_jobs_secure test -f "/tmp/smarthydro/$file" 2>/dev/null; then
        PERMS=$(docker exec cron_jobs_secure stat -c%a "/tmp/smarthydro/$file" 2>/dev/null)
        OWNER=$(docker exec cron_jobs_secure stat -c%U "/tmp/smarthydro/$file" 2>/dev/null)
        log "✅ $file: permisos $PERMS, propietario $OWNER"
    fi
done

# 11. Resumen de recomendaciones
log ""
log "11. Resumen y recomendaciones..."
echo "=========================================="
echo "📋 RESUMEN DEL DIAGNÓSTICO"
echo "=========================================="

# Contar problemas encontrados
ERRORS=0
WARNINGS=0

if ! docker ps | grep -q cron_jobs_secure; then
    ((ERRORS++))
fi

if ! docker exec cron_jobs_secure crontab -l 2>/dev/null | grep -q "django-cronjobs"; then
    ((ERRORS++))
fi

if ! docker exec cron_jobs_secure test -f "/usr/local/bin/rotate-cron-logs.sh" 2>/dev/null; then
    ((ERRORS++))
fi

if [ "$ACTIVE_CRONS" -eq 0 ]; then
    ((WARNINGS++))
fi

echo "❌ Errores encontrados: $ERRORS"
echo "⚠️ Advertencias encontradas: $WARNINGS"

if [ "$ERRORS" -eq 0 ] && [ "$WARNINGS" -eq 0 ]; then
    log "🎉 Sistema de cron jobs y logs funcionando correctamente"
elif [ "$ERRORS" -eq 0 ]; then
    log "✅ Sistema funcionando con algunas advertencias menores"
else
    error "❌ Se encontraron errores críticos que requieren atención"
fi

echo ""
echo "🔧 ACCIONES RECOMENDADAS:"
echo "1. Si hay errores críticos, reiniciar el contenedor: ./restart_cron.sh"
echo "2. Si el script de rotación no existe, reconstruir la imagen Docker"
echo "3. Monitorear logs regularmente: tail -f /opt/smarthydro/cron_logs/*.log"
echo "4. Verificar espacio en disco: df -h /opt/smarthydro/cron_logs"
echo ""

echo "=========================================="
echo "🏁 DIAGNÓSTICO COMPLETADO"
echo "=========================================="
