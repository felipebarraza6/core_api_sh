#!/bin/bash

# Script simple para desarrollo local
# Inicia solo los servicios básicos

set -e

echo "🚀 Iniciando SmartHydro en desarrollo local (modo simple)"
echo "======================================================="

# Función para verificar si un puerto está abierto
wait_for_port() {
    local host=$1
    local port=$2
    local timeout=30

    echo "Esperando a que $host:$port esté disponible..."
    for i in $(seq 1 $timeout); do
        if nc -z $host $port 2>/dev/null; then
            echo "$host:$port está listo!"
            return 0
        fi
        sleep 1
    done
    echo "Timeout esperando $host:$port"
    return 1
}

# Iniciar PostgreSQL y Redis
echo "Iniciando PostgreSQL y Redis..."
docker-compose -f docker-compose.dev.yml up -d postgres redis

# Esperar a que estén listos
wait_for_port localhost 5432 || exit 1
wait_for_port localhost 6379 || exit 1

# Crear base de datos si no existe
echo "Configurando base de datos..."
docker-compose -f docker-compose.dev.yml exec -T postgres bash -c "
PGPASSWORD=dev_password_123 psql -U smarthydro_dev_user -d postgres -c \"
SELECT 'CREATE DATABASE smarthydro_dev OWNER smarthydro_dev_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'smarthydro_dev')\;\" |
PGPASSWORD=dev_password_123 psql -U smarthydro_dev_user -d postgres"

# Ejecutar migraciones
echo "Ejecutando migraciones..."
docker-compose -f docker-compose.dev.yml run --rm django_app python manage.py migrate --settings=api.settings

# Crear superusuario
echo "Creando superusuario..."
docker-compose -f docker-compose.dev.yml run --rm django_app python manage.py shell --settings=api.settings -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser('admin', 'admin@smarthydro.local', 'admin123')
    print('Superusuario creado: admin / admin123')
else:
    print('Superusuario ya existe')
"

# Iniciar Django
echo "Iniciando Django..."
docker-compose -f docker-compose.dev.yml up -d django_app

echo ""
echo "🎉 ¡SmartHydro está listo!"
echo ""
echo "🌐 Aplicación: http://localhost:8000"
echo "👑 Admin:      http://localhost:8000/admin/"
echo "   Usuario: admin / admin123"
echo ""
echo "🛑 Para detener: docker-compose -f docker-compose.dev.yml down"
echo "📊 Ver logs:    docker-compose -f docker-compose.dev.yml logs -f django_app"