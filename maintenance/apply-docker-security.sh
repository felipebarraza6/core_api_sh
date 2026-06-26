#!/bin/bash
set -euo pipefail

# =============================================================================
# Script de aplicación segura de mejoras de seguridad Docker (Fase 3)
# =============================================================================
# IMPORTANTE: Ejecutar solo en ventana de mantenimiento.
# El script hace pull de nuevas imágenes, reinicia contenedores y verifica
# health checks. Si algo falla, intenta rollback automático.
#
# Uso:
#   chmod +x maintenance/apply-docker-security.sh
#   ./maintenance/apply-docker-security.sh
# =============================================================================

COMPOSE_FILE="docker-compose.production.secure.yml"
BACKUP_SUFFIX=".bak.$(date +%Y%m%d_%H%M%S)"

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_health() {
    local container=$1
    local max_attempts=${2:-30}
    local attempt=1

    log_info "Esperando health de $container..."
    while [ $attempt -le $max_attempts ]; do
        status=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "unknown")
        if [ "$status" = "healthy" ]; then
            log_info "$container está healthy ✅"
            return 0
        fi
        echo "  Intento $attempt/$max_attempts: status=$status"
        sleep 2
        attempt=$((attempt + 1))
    done

    log_error "$container NO se puso healthy después de $max_attempts intentos ❌"
    return 1
}

rollback() {
    log_warn "Iniciando ROLLBACK..."
    if [ -f "${COMPOSE_FILE}${BACKUP_SUFFIX}" ]; then
        cp "${COMPOSE_FILE}${BACKUP_SUFFIX}" "$COMPOSE_FILE"
        log_info "docker-compose restaurado desde backup"
    fi
    docker-compose -f "$COMPOSE_FILE" up -d
    log_info "Rollback completado. Revisa manualmente."
}

# =============================================================================
# PRE-CHECKS
# =============================================================================
log_info "Verificando pre-condiciones..."

if [ ! -f "$COMPOSE_FILE" ]; then
    log_error "No se encontró $COMPOSE_FILE"
    exit 1
fi

if [ "$(docker ps -q | wc -l)" -eq 0 ]; then
    log_error "No hay contenedores corriendo. ¿Estás en el servidor correcto?"
    exit 1
fi

# Backup de docker-compose
cp "$COMPOSE_FILE" "${COMPOSE_FILE}${BACKUP_SUFFIX}"
log_info "Backup creado: ${COMPOSE_FILE}${BACKUP_SUFFIX}"

# =============================================================================
# PASO 1: Pull de nuevas imágenes
# =============================================================================
log_info "Descargando nuevas imágenes..."
docker-compose -f "$COMPOSE_FILE" pull || {
    log_error "Falló docker-compose pull"
    exit 1
}

# =============================================================================
# PASO 2: Reiniciar Redis (con nueva contraseña)
# =============================================================================
log_info "Reiniciando redis_secure con autenticación..."
docker-compose -f "$COMPOSE_FILE" up -d --no-deps redis_secure

check_health redis_secure || {
    log_error "Redis no se recuperó. Abortando."
    rollback
    exit 1
}

# Verificar autenticación
REDIS_PASS=$(grep '^REDIS_PASSWORD=' .env | cut -d= -f2- | tr -d "'\"" || true)
if [ -n "$REDIS_PASS" ]; then
    if docker exec redis_secure redis-cli -a "$REDIS_PASS" ping | grep -q PONG; then
        log_info "Redis autenticación OK ✅"
    else
        log_error "Redis NO acepta la contraseña configurada ❌"
        rollback
        exit 1
    fi
else
    log_warn "No se pudo leer REDIS_PASSWORD de .env"
fi

# =============================================================================
# PASO 3: Reiniciar Django (nueva imagen + nuevos mounts)
# =============================================================================
log_info "Reiniciando django_api_secure..."
docker-compose -f "$COMPOSE_FILE" up -d --no-deps django

check_health django_api_secure 60 || {
    log_error "Django no se recuperó. Iniciando rollback..."
    rollback
    exit 1
}

# =============================================================================
# PASO 4: Reiniciar Cron (nueva imagen + usuario no-root + nuevos mounts)
# =============================================================================
log_info "Reiniciando cron_jobs_secure..."
docker-compose -f "$COMPOSE_FILE" up -d --no-deps cron

sleep 5
# El cron no tiene healthcheck que responda inmediatamente, verificamos logs
if docker logs --tail 20 cron_jobs_secure 2>&1 | grep -qi "error\|fail\|permission denied"; then
    log_error "Cron tiene errores en logs. Revisa manualmente."
else
    log_info "Cron reiniciado sin errores evidentes ✅"
fi

# =============================================================================
# PASO 5: Reiniciar nginx-proxy y letsencrypt (nuevas imágenes fijas)
# =============================================================================
log_info "Reiniciando nginx_proxy..."
docker-compose -f "$COMPOSE_FILE" up -d --no-deps nginx_proxy

check_health nginx_proxy 30 || {
    log_warn "nginx_proxy no reporta healthy aún. Puede tardar por SSL."
}

log_info "Reiniciando letsencrypt..."
docker-compose -f "$COMPOSE_FILE" up -d --no-deps letsencrypt

sleep 10

# =============================================================================
# PASO 6: Verificación final
# =============================================================================
log_info "Verificación final de contenedores..."
docker-compose -f "$COMPOSE_FILE" ps

# Health check externo
if curl -s -o /dev/null -w "%{http_code}" -L -H "Host: api.smarthydro.app" http://localhost/health/ | grep -q '200'; then
    log_info "API responde HTTP 200 desde nginx-proxy ✅"
else
    log_warn "API no responde 200. Revisa manualmente: docker logs django_api_secure"
fi

log_info "Aplicación de seguridad completada."
log_info "Revisa los logs: docker logs --tail 50 django_api_secure"
