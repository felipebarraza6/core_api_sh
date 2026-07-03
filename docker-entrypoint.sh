#!/bin/bash
set -e

# Crear directorio de logs si no existe
mkdir -p /app/logs
# touch /app/logs/django.log
# chmod 755 /app/logs
# chmod 644 /app/logs/django.log

# ✅ FIX: Crear directorio de media para adjuntos de tickets
mkdir -p /app/media/tickets

# ✅ FIX: Crear directorio de logs de Nginx en /app/logs (tiene permisos)
mkdir -p /app/logs/nginx
touch /app/logs/nginx/error.log
touch /app/logs/nginx/access.log
chmod 755 /app/logs/nginx
chmod 644 /app/logs/nginx/error.log
chmod 644 /app/logs/nginx/access.log

# ✅ FIX: Crear symlinks para que Nginx pueda escribir (si es necesario)
# Pero mejor: modificar nginx.conf para usar /app/logs/nginx

# SIEMPRE ejecutar collectstatic al iniciar Django
if [ "$1" != "cron" ]; then
    echo "🔧 Ejecutando collectstatic..."
    python manage.py collectstatic --noinput --clear
    echo "✅ Archivos estáticos listos"
fi

# Si el comando es 'cron', instalar cronjobs y ejecutar cron
if [ "$1" = "cron" ]; then
    echo "Instalando cronjobs..."
    python manage.py crontab add
    echo "Mostrando cronjobs instalados:"
    python manage.py crontab show
    echo "Iniciando cron daemon..."
    # Ejecutar cron en foreground para mantener el contenedor activo
    cron && tail -f /var/log/cron.log /tmp/smarthydro/*.log
else
    # ✅ RENDIMIENTO: Iniciar Nginx en background si no es cron
    # Nginx sirve archivos estáticos y hace proxy a Gunicorn
    echo "🚀 Iniciando Nginx..."
    # ✅ FIX: Crear directorio /app/logs/nginx (nginx.conf ya está configurado para usar esto)
    mkdir -p /app/logs/nginx
    # chmod 755 /app/logs/nginx
    # touch /app/logs/nginx/error.log /app/logs/nginx/access.log
    # chmod 644 /app/logs/nginx/error.log /app/logs/nginx/access.log
    # Verificar que la configuración sea válida
    # nginx -t || echo "⚠️ Advertencia: nginx -t falló"
    # Iniciar Nginx
    # nginx &
    # sleep 2
    # Verificar que Nginx esté corriendo
    # if pgrep -x nginx > /dev/null; then
    #     echo "✅ Nginx iniciado correctamente"
    # else
    #     echo "⚠️ Advertencia: Nginx no se inició, pero continuando con Gunicorn..."
    # fi
    
    # Ejecutar el comando normal (Gunicorn) - este será el proceso principal
    exec "$@"
fi
