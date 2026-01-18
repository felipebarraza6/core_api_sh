#!/bin/bash

# Script de Deployment para SmartHydro en Producción
# Este script automatiza el despliegue completo del sistema

set -e  # Salir si cualquier comando falla

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

    # Verificar Docker
    if ! command -v docker &> /dev/null; then
        error "Docker no está instalado. Instálalo primero."
        exit 1
    fi

    # Verificar Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        error "Docker Compose no está instalado. Instálalo primero."
        exit 1
    fi

    # Verificar archivo .env
    if [ ! -f ".env" ]; then
        error "Archivo .env no encontrado. Copia env.production.example a .env y configura las variables."
        exit 1
    fi

    # Verificar certificados SSL
    if [ ! -d "ssl" ]; then
        warning "Directorio ssl no encontrado. Creando estructura básica..."
        mkdir -p ssl
        warning "Recuerda colocar tus certificados SSL en ssl/smarthydro.crt y ssl/smarthydro.key"
    fi

    log "Prerrequisitos verificados correctamente"
}

# Crear directorios necesarios
create_directories() {
    log "Creando directorios necesarios..."

    mkdir -p logs
    mkdir -p backups
    mkdir -p monitoring/prometheus
    mkdir -p monitoring/grafana/provisioning/datasources
    mkdir -p monitoring/grafana/provisioning/dashboards
    mkdir -p monitoring/grafana/dashboards

    log "Directorios creados"
}

# Construir imágenes Docker
build_images() {
    log "Construyendo imágenes Docker..."

    # Construir imagen de la aplicación
    docker-compose -f docker-compose.production.yml build --no-cache

    log "Imágenes construidas correctamente"
}

# Iniciar servicios base (sin aplicación)
start_infrastructure() {
    log "Iniciando infraestructura base..."

    # Iniciar PostgreSQL y Redis primero
    docker-compose -f docker-compose.production.yml up -d postgres redis

    # Esperar a que las bases de datos estén listas
    log "Esperando a que PostgreSQL esté listo..."
    for i in {1..30}; do
        if docker-compose -f docker-compose.production.yml exec -T postgres pg_isready -U smarthydro_user -d smarthydro_prod 2>/dev/null; then
            break
        fi
        sleep 2
    done

    log "Esperando a que Redis esté listo..."
    for i in {1..15}; do
        if docker-compose -f docker-compose.production.yml exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
            break
        fi
        sleep 1
    done

    # Iniciar MQTT broker
    docker-compose -f docker-compose.production.yml up -d mqtt_broker

    log "Infraestructura base iniciada"
}

# Ejecutar migraciones y setup inicial
run_initial_setup() {
    log "Ejecutando setup inicial..."

    # Ejecutar migraciones
    docker-compose -f docker-compose.production.yml run --rm django_app python manage.py migrate

    # Crear superusuario si no existe
    log "Creando superusuario..."
    docker-compose -f docker-compose.production.yml run --rm django_app python manage.py shell -c "
from django.contrib.auth import get_user_model
from api.core.models import SystemConfiguration
import os

User = get_user_model()

# Crear superusuario si no existe
if not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser(
        username='admin',
        email=os.environ.get('ADMIN_EMAIL', 'admin@smarthydro.app'),
        password=os.environ.get('ADMIN_PASSWORD', 'admin123'),
        first_name='Admin',
        last_name='SmartHydro'
    )
    print('Superusuario creado')

# Configurar sistema
from api.core.config.constants_and_sync_config import setup_provider_configurations
setup_provider_configurations()
print('Configuraciones iniciales completadas')
"

    log "Setup inicial completado"
}

# Iniciar aplicación completa
start_application() {
    log "Iniciando aplicación completa..."

    # Iniciar todos los servicios
    docker-compose -f docker-compose.production.yml up -d

    # Esperar a que la aplicación esté lista
    log "Esperando a que la aplicación esté lista..."
    for i in {1..30}; do
        if curl -f http://localhost/health 2>/dev/null; then
            break
        fi
        sleep 3
    done

    log "Aplicación iniciada correctamente"
}

# Ejecutar tests post-deployment
run_post_deployment_tests() {
    log "Ejecutando tests post-deployment..."

    # Ejecutar tests del sistema
    docker-compose -f docker-compose.production.yml run --rm django_app python test_constants_and_sync.py

    log "Tests completados"
}

# Mostrar información de acceso
show_access_info() {
    log "=== INFORMACIÓN DE ACCESO ==="
    echo ""
    echo "🌐 Aplicación: https://api.smarthydro.app"
    echo "👑 Admin: https://api.smarthydro.app/admin/"
    echo "👤 Usuario: admin / admin123 (CAMBIAR INMEDIATAMENTE)"
    echo ""
    echo "📊 Monitoreo:"
    echo "   • Flower (Celery): https://api.smarthydro.app/flower/"
    echo "   • Grafana: http://localhost:3000 (admin / ${GRAFANA_ADMIN_PASSWORD})"
    echo "   • Prometheus: http://localhost:9090"
    echo ""
    echo "🔌 Servicios:"
    echo "   • MQTT Broker: localhost:1883"
    echo "   • PostgreSQL: localhost:5432"
    echo "   • Redis: localhost:6379"
    echo ""
    echo "📝 Logs:"
    echo "   docker-compose -f docker-compose.production.yml logs -f [service]"
    echo "   docker-compose -f docker-compose.production.yml logs -f django_app"
    echo ""
    warning "⚠️  IMPORTANTE: Cambiar la contraseña del admin inmediatamente!"
    warning "⚠️  Configurar certificados SSL antes de producción real!"
}

# Función principal
main() {
    echo "🚀 SmartHydro Production Deployment Script"
    echo "=========================================="
    echo ""

    case "${1:-deploy}" in
        "deploy")
            check_prerequisites
            create_directories
            build_images
            start_infrastructure
            run_initial_setup
            start_application
            run_post_deployment_tests
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
            docker-compose -f docker-compose.production.yml down
            ;;
        "restart")
            log "Reiniciando servicios..."
            docker-compose -f docker-compose.production.yml restart
            ;;
        "logs")
            docker-compose -f docker-compose.production.yml logs -f "${2:-django_app}"
            ;;
        "backup")
            log "Ejecutando backup..."
            docker-compose -f docker-compose.production.yml run --rm django_app python manage.py backup_database
            ;;
        "status")
            docker-compose -f docker-compose.production.yml ps
            ;;
        *)
            echo "Uso: $0 {deploy|infrastructure|setup|start|stop|restart|logs|backup|status}"
            echo ""
            echo "Comandos:"
            echo "  deploy        - Despliegue completo"
            echo "  infrastructure- Solo infraestructura (DB, Redis, MQTT)"
            echo "  setup         - Setup inicial (migraciones, configuración)"
            echo "  start         - Iniciar aplicación completa"
            echo "  stop          - Detener todos los servicios"
            echo "  restart       - Reiniciar servicios"
            echo "  logs [service]- Ver logs (por defecto django_app)"
            echo "  backup        - Ejecutar backup de base de datos"
            echo "  status        - Ver estado de servicios"
            exit 1
    esac
}

# Ejecutar función principal
main "$@"