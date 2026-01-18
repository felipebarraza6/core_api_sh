#!/bin/bash

# Script de Deployment para SmartHydro en Desarrollo Local
# Versión simplificada para testing local

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
    echo -e "${RED}[ERROR] $1${NC}" >&2
}

warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

info() {
    echo -e "${BLUE}[INFO] $1${NC}"
}

# Verificar prerrequisitos
check_prerequisites() {
    log "Verificando prerrequisitos..."

    if ! command -v docker &> /dev/null; then
        error "Docker no está instalado"
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        error "Docker Compose no está instalado"
        exit 1
    fi

    if [ ! -f ".env" ]; then
        error "Archivo .env no encontrado"
        exit 1
    fi

    log "Prerrequisitos verificados"
}

# Crear directorios necesarios
create_directories() {
    log "Creando directorios necesarios..."
    mkdir -p ssl logs backups monitoring/prometheus monitoring/grafana/provisioning/datasources monitoring/grafana/dashboards
    log "Directorios creados"
}

# Construir imágenes
build_images() {
    log "Construyendo imágenes Docker..."
    docker-compose -f docker-compose.dev.yml build --no-cache
    log "Imágenes construidas"
}

# Iniciar infraestructura
start_infrastructure() {
    log "Iniciando infraestructura base..."
    docker-compose -f docker-compose.dev.yml up -d postgres redis
    sleep 10  # Esperar un poco más para desarrollo

    log "Esperando a PostgreSQL..."
    for i in {1..20}; do
        if docker-compose -f docker-compose.dev.yml exec -T postgres pg_isready -U smarthydro_dev_user -d smarthydro_dev >/dev/null 2>&1; then
            break
        fi
        sleep 3
    done

    log "Infraestructura lista"
}

# Setup inicial
run_initial_setup() {
    log "Ejecutando setup inicial..."

    # Ejecutar migraciones
    docker-compose -f docker-compose.dev.yml run --rm django_app python manage.py migrate

    # Crear superusuario
    log "Creando superusuario..."
    docker-compose -f docker-compose.dev.yml run --rm django_app python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser('admin', 'admin@smarthydro.local', 'admin123')
    print('Superusuario creado: admin / admin123')
else:
    print('Superusuario ya existe')
"

    log "Setup completado"
}

# Iniciar aplicación completa
start_application() {
    log "Iniciando aplicación completa..."
    docker-compose -f docker-compose.dev.yml up -d
    sleep 5

    log "Esperando a que la aplicación esté lista..."
    for i in {1..15}; do
        if curl -f -s http://localhost/health >/dev/null 2>&1; then
            break
        fi
        sleep 3
    done

    log "Aplicación iniciada"
}

# Mostrar información de acceso
show_access_info() {
    log "=== ACCESO AL SISTEMA DE DESARROLLO ==="
    echo ""
    echo "🌐 API Principal:"
    echo "   • HTTP:  http://localhost/api/"
    echo "   • HTTPS: https://localhost/api/"
    echo ""
    echo "👑 Django Admin:"
    echo "   • HTTP:  http://localhost/admin/"
    echo "   • HTTPS: https://localhost/admin/"
    echo "   • Usuario: admin / admin123"
    echo ""
    echo "📊 Monitoreo:"
    echo "   • Grafana:    http://localhost:3000 (admin / admin123)"
    echo "   • Prometheus: http://localhost:9090"
    echo ""
    echo "🔌 Servicios:"
    echo "   • MQTT Broker: localhost:1883"
    echo "   • PostgreSQL:  localhost:5432"
    echo "   • Redis:       localhost:6379"
    echo ""
    echo "📝 Comandos útiles:"
    echo "   • Ver logs:     docker-compose -f docker-compose.dev.yml logs -f django_app"
    echo "   • Detener:      docker-compose -f docker-compose.dev.yml down"
    echo "   • Reiniciar:    docker-compose -f docker-compose.dev.yml restart"
    echo ""
    warning "⚠️  ESTO ES PARA DESARROLLO LOCAL - NO USAR EN PRODUCCIÓN"
}

# Función principal
main() {
    echo "🚀 SmartHydro Development Deployment"
    echo "===================================="

    case "${1:-deploy}" in
        "deploy")
            check_prerequisites
            create_directories
            build_images
            start_infrastructure
            run_initial_setup
            start_application
            show_access_info
            ;;
        "infrastructure")
            check_prerequisites
            start_infrastructure
            ;;
        "setup")
            run_initial_setup
            ;;
        "start")
            start_application
            ;;
        "stop")
            log "Deteniendo servicios..."
            docker-compose -f docker-compose.dev.yml down
            ;;
        "restart")
            log "Reiniciando servicios..."
            docker-compose -f docker-compose.dev.yml restart
            ;;
        "logs")
            docker-compose -f docker-compose.dev.yml logs -f "${2:-django_app}"
            ;;
        "status")
            docker-compose -f docker-compose.dev.yml ps
            ;;
        *)
            echo "Uso: $0 {deploy|infrastructure|setup|start|stop|restart|logs|status}"
            exit 1
    esac
}

main "$@"