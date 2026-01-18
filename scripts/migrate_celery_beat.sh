#!/bin/bash

# Script para aplicar migraciones de django-celery-beat

echo "🔄 Aplicando migraciones de django-celery-beat..."

# Detectar si está en Docker o local
if docker ps | grep -q django_api_secure; then
    echo "✅ Detectado Docker - usando contenedor django_api_secure"
    docker exec django_api_secure python manage.py migrate django_celery_beat

    echo ""
    echo "✅ Migraciones aplicadas. Reiniciando servicios..."
    docker-compose -f docker-compose.production.secure.yml restart celery_beat

    echo ""
    echo "✅ Completado. Verifica el admin en http://localhost:8000/admin/"
else
    echo "⚠️  No se encontró contenedor Docker 'django_api_secure'"
    echo "Si el servidor está corriendo en otro puerto/proceso, ejecuta manualmente:"
    echo ""
    echo "  python manage.py migrate django_celery_beat"
    echo ""
    exit 1
fi
