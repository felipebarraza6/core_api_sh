#!/usr/bin/env python3
import os
import sys
import django

# Agregar el directorio actual al path
sys.path.insert(0, os.path.dirname(__file__))

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

# Variables de entorno necesarias
os.environ['LOCAL_DB_NAME'] = 'smarthydro_dev'
os.environ['LOCAL_DB_USER'] = 'smarthydro_user'
os.environ['LOCAL_DB_PASSWORD'] = 'dev_password_123'
os.environ['LOCAL_DB_HOST'] = 'localhost'
os.environ['LOCAL_DB_PORT'] = '5432'
os.environ['DJANGO_DEBUG'] = 'True'
os.environ['USE_CLUSTER'] = 'false'

try:
    from core.models import User
    from django.core.management import execute_from_command_line

    # Verificar si ya existe un superusuario
    if User.objects.filter(username='admin').exists():
        print('ℹ️ El superusuario "admin" ya existe')
    else:
        # Crear superusuario
        user = User.objects.create_superuser(
            username='admin',
            email='admin@smarthydro.cl',
            password='admin123'
        )
        print('✅ Superusuario creado exitosamente!')
        print('   Usuario: admin')
        print('   Email: admin@smarthydro.cl')
        print('   Contraseña: admin123')

except Exception as e:
    print(f'❌ Error al crear superusuario: {e}')
    import traceback
    traceback.print_exc()