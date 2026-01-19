#!/bin/bash

# Script de Monitoreo para SmartHydro en Producción
# Verifica el estado de todos los servicios y componentes

set -e

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Función de logging
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

info() {
    echo -e "${BLUE}[INFO] $1${NC}"
}

# Verificar servicios Docker
check_docker_services() {
    log "Verificando servicios Docker..."

    services=$(docker-compose -f docker-compose.production.yml ps --services --filter "status=running")

    expected_services=("nginx_proxy" "django_app" "celery_worker" "celery_beat" "mqtt_broker" "redis" "postgres")
    running_services=()

    for service in $services; do
        running_services+=("$service")
    done

    all_running=true
    for expected in "${expected_services[@]}"; do
        if [[ ! " ${running_services[*]} " =~ " ${expected} " ]]; then
            error "Servicio $expected no está ejecutándose"
            all_running=false
        fi
    done

    if $all_running; then
        log "✅ Todos los servicios Docker están ejecutándose"
    else
        error "❌ Algunos servicios Docker no están ejecutándose"
        return 1
    fi
}

# Verificar conectividad de base de datos
check_database() {
    log "Verificando conectividad de PostgreSQL..."

    if docker-compose -f docker-compose.production.yml exec -T postgres pg_isready -U smarthydro_user -d smarthydro_prod >/dev/null 2>&1; then
        log "✅ PostgreSQL está accesible"

        # Verificar estadísticas básicas
        db_stats=$(docker-compose -f docker-compose.production.yml exec -T postgres psql -U smarthydro_user -d smarthydro_prod -c "
            SELECT
                (SELECT count(*) FROM core_interactiondetail) as telemetry_records,
                (SELECT count(*) FROM core_datapoint) as data_points,
                (SELECT count(*) FROM core_supportticket WHERE status IN ('OPEN', 'IN_PROGRESS')) as open_tickets,
                (SELECT count(*) FROM core_iotdevice WHERE status = 'ONLINE') as online_devices;
        " -t -A)

        IFS='|' read -r telemetry_records data_points open_tickets online_devices <<< "$db_stats"

        info "📊 Estadísticas de BD:"
        info "   • Registros de telemetría: ${telemetry_records:-0}"
        info "   • Puntos de datos: ${data_points:-0}"
        info "   • Tickets abiertos: ${open_tickets:-0}"
        info "   • Dispositivos online: ${online_devices:-0}"

    else
        error "❌ PostgreSQL no está accesible"
        return 1
    fi
}

# Verificar Redis
check_redis() {
    log "Verificando Redis..."

    if docker-compose -f docker-compose.production.yml exec -T redis redis-cli ping | grep -q PONG; then
        log "✅ Redis está accesible"

        # Verificar estadísticas de Redis
        redis_info=$(docker-compose -f docker-compose.production.yml exec -T redis redis-cli info | grep -E "(connected_clients|used_memory_human|total_connections_received)")

        info "📊 Estadísticas de Redis:"
        echo "$redis_info" | while IFS=':' read -r key value; do
            info "   • $key: $value"
        done

    else
        error "❌ Redis no está accesible"
        return 1
    fi
}

# Verificar aplicación Django
check_django_app() {
    log "Verificando aplicación Django..."

    # Health check
    if curl -f -s http://localhost/health >/dev/null 2>&1; then
        log "✅ Endpoint de health check responde correctamente"
    else
        error "❌ Endpoint de health check no responde"
        return 1
    fi

    # API básica
    if curl -f -s http://localhost/api/v2/dashboard/summary/ -H "Authorization: Token test" >/dev/null 2>&1; then
        warning "⚠️  API responde (pero con token de test - verificar autenticación)"
    else
        log "✅ API requiere autenticación correctamente"
    fi

    # Verificar logs recientes de errores
    error_logs=$(docker-compose -f docker-compose.production.yml logs django_app 2>&1 | grep -i error | tail -5)
    if [ -n "$error_logs" ]; then
        warning "⚠️  Se encontraron errores recientes en logs de Django:"
        echo "$error_logs"
    else
        log "✅ No se encontraron errores recientes en logs de Django"
    fi
}

# Verificar Celery
check_celery() {
    log "Verificando Celery..."

    # Verificar workers activos
    active_workers=$(docker-compose -f docker-compose.production.yml exec -T celery_worker celery -A api inspect active 2>/dev/null | grep -c "celery@")
    if [ "$active_workers" -gt 0 ]; then
        log "✅ Celery workers activos: $active_workers"

        # Verificar tareas programadas
        scheduled_tasks=$(docker-compose -f docker-compose.production.yml exec -T celery_beat celery -A api inspect scheduled 2>/dev/null | wc -l)
        if [ "$scheduled_tasks" -gt 0 ]; then
            log "✅ Tareas programadas activas: $scheduled_tasks"
        else
            warning "⚠️  No se encontraron tareas programadas activas"
        fi

        # Verificar estadísticas de tareas
        task_stats=$(docker-compose -f docker-compose.production.yml exec -T celery_worker celery -A api inspect stats 2>/dev/null)
        if echo "$task_stats" | grep -q "total"; then
            log "✅ Estadísticas de tareas disponibles"
        fi

    else
        error "❌ No se encontraron workers de Celery activos"
        return 1
    fi
}

# Verificar MQTT Broker
check_mqtt() {
    log "Verificando MQTT Broker..."

    # Verificar conectividad MQTT básica
    if docker-compose -f docker-compose.production.yml exec -T mqtt_broker mosquitto_sub -t "health" -C 1 -h localhost -p 1883 >/dev/null 2>&1; then
        log "✅ MQTT Broker responde correctamente"
    else
        error "❌ MQTT Broker no responde"
        return 1
    fi

    # Verificar logs recientes
    mqtt_errors=$(docker-compose -f docker-compose.production.yml logs mqtt_broker 2>&1 | grep -i error | tail -3)
    if [ -n "$mqtt_errors" ]; then
        warning "⚠️  Se encontraron errores recientes en MQTT:"
        echo "$mqtt_errors"
    else
        log "✅ No se encontraron errores recientes en MQTT"
    fi
}

# Verificar Nginx
check_nginx() {
    log "Verificando Nginx..."

    if curl -f -s -I https://localhost/ 2>/dev/null | grep -q "200 OK"; then
        log "✅ Nginx responde correctamente en HTTPS"
    elif curl -f -s -I http://localhost/ 2>/dev/null | grep -q "301"; then
        log "✅ Nginx redirige HTTP a HTTPS correctamente"
    else
        error "❌ Nginx no responde correctamente"
        return 1
    fi
}

# Verificar sistema de archivos y permisos
check_filesystem() {
    log "Verificando sistema de archivos..."

    # Verificar logs
    if [ -d "logs" ] && [ -w "logs" ]; then
        log "✅ Directorio de logs accesible"
    else
        error "❌ Problemas con directorio de logs"
        return 1
    fi

    # Verificar backups
    if [ -d "backups" ]; then
        backup_count=$(find backups -name "*.json.gz" -mtime -7 | wc -l)
        info "📊 Backups recientes (última semana): $backup_count"
    else
        warning "⚠️  Directorio de backups no existe"
    fi

    # Verificar espacio en disco
    disk_usage=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ "$disk_usage" -gt 90 ]; then
        error "❌ Uso de disco crítico: ${disk_usage}%"
        return 1
    elif [ "$disk_usage" -gt 80 ]; then
        warning "⚠️  Uso de disco alto: ${disk_usage}%"
    else
        log "✅ Uso de disco aceptable: ${disk_usage}%"
    fi
}

# Generar reporte de estado
generate_status_report() {
    log "Generando reporte de estado completo..."

    report_file="status_report_$(date +%Y%m%d_%H%M%S).txt"

    {
        echo "=== REPORTE DE ESTADO - SmartHydro Producción ==="
        echo "Fecha: $(date)"
        echo ""

        echo "=== SERVICIOS DOCKER ==="
        docker-compose -f docker-compose.production.yml ps
        echo ""

        echo "=== ESTADÍSTICAS DE SISTEMA ==="
        echo "CPU: $(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1"%"}')"
        echo "Memoria: $(free -h | grep '^Mem:' | awk '{print $3 "/" $2}')"
        echo "Disco: $(df -h / | tail -1 | awk '{print $3 "/" $2 " (" $5 ")"}')"
        echo ""

        echo "=== CONEXIONES ACTIVAS ==="
        echo "MQTT: $(netstat -tln 2>/dev/null | grep -c :1883 || echo 'N/A')"
        echo "HTTP: $(netstat -tln 2>/dev/null | grep -c :80 || echo 'N/A')"
        echo "HTTPS: $(netstat -tln 2>/dev/null | grep -c :443 || echo 'N/A')"
        echo ""

    } > "$report_file"

    log "✅ Reporte generado: $report_file"
}

# Función principal
main() {
    echo "🔍 SmartHydro Production Monitoring Script"
    echo "=========================================="

    all_checks_passed=true

    # Ejecutar todas las verificaciones
    checks=(
        "check_docker_services"
        "check_database"
        "check_redis"
        "check_django_app"
        "check_celery"
        "check_mqtt"
        "check_nginx"
        "check_filesystem"
    )

    for check in "${checks[@]}"; do
        if ! $check; then
            all_checks_passed=false
        fi
        echo ""
    done

    # Generar reporte
    generate_status_report

    echo "=========================================="
    if $all_checks_passed; then
        log "🎉 TODAS LAS VERIFICACIONES PASARON"
        echo "Sistema funcionando correctamente"
        exit 0
    else
        error "❌ ALGUNAS VERIFICACIONES FALLARON"
        echo "Revisar los errores arriba y tomar acciones correctivas"
        exit 1
    fi
}

# Ejecutar función principal
main "$@"