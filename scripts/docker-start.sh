#!/bin/bash

# Script de inicio para SmartHydro Django App
# Este script es usado por la imagen Docker existente

set -e

# Esperar a que la base de datos esté lista
echo "Esperando a que PostgreSQL esté listo..."
python -c "
import socket
import time
import os

host = os.environ.get('LOCAL_DB_HOST', 'postgres')
port = 5432

for i in range(30):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        if result == 0:
            print('PostgreSQL está listo!')
            break
    except:
        pass
    time.sleep(1)
else:
    print('Timeout esperando PostgreSQL')
"

# Ejecutar migraciones si es necesario
echo "Ejecutando migraciones..."
python manage.py migrate --noinput

# Recolectar archivos estáticos
echo "Recolectando archivos estáticos..."
python manage.py collectstatic --noinput

# Crear superusuario si no existe (solo en desarrollo)
if [ "$ENVIRONMENT" = "development" ]; then
    echo "Verificando superusuario..."
    python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser('admin', 'admin@smarthydro.local', 'admin123')
    print('Superusuario creado: admin / admin123')
else:
    print('Superusuario ya existe')
"
fi

# Iniciar Gunicorn
echo "Iniciando Gunicorn..."
exec gunicorn --config gunicorn_config.py --bind 0.0.0.0:8000 api.wsgi:application