#!/bin/bash
set -e

# Crear directorio de logs si no existe
mkdir -p /tmp/smarthydro
touch /tmp/smarthydro/django.log

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
    # Ejecutar el comando normal
    exec "$@"
fi
