#!/bin/bash
set -euo pipefail

echo "🚀 Iniciando cronjobs SmartHydro con verificación de BD..."

# Variables para Django
export DJANGO_SETTINGS_MODULE=api.settings
export LOCAL_DB_HOST="${LOCAL_DB_HOST:-postgres_secure}"
export LOCAL_DB_NAME="${LOCAL_DB_NAME:-smarthydro_prod}"
export LOCAL_DB_USER="${LOCAL_DB_USER:-smarthydro_user}"
export LOCAL_DB_PASSWORD="${LOCAL_DB_PASSWORD:-}"
export LOCAL_DB_PORT="${LOCAL_DB_PORT:-5432}"

# Preparar logs
mkdir -p /var/log/smarthydro
if [ -d /tmp/smarthydro ] && [ ! -L /tmp/smarthydro ]; then
  cp -an /tmp/smarthydro/. /var/log/smarthydro/ 2>/dev/null || true
  rm -rf /tmp/smarthydro
fi
ln -sfn /var/log/smarthydro /tmp/smarthydro
: > /tmp/smarthydro/django.log || true
for f in twin_1 twin_5 twin_60 nettra_5 nettra_60 novus_60 dga sma alerts cluster_backup; do
  touch "/tmp/smarthydro/${f}.log"
done

# Esperar a que la BD esté lista usando Django (SELECT 1) con reintentos
python - <<'PY'
import os, time, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE','api.settings')
try:
    import django
    django.setup()
    from django.db import connection
except Exception as e:
    print(f"❌ Error inicializando Django: {e}")
    sys.exit(1)

retries = int(os.environ.get('DB_WAIT_RETRIES', '30'))
delay = float(os.environ.get('DB_WAIT_DELAY', '5'))
for i in range(1, retries+1):
    try:
        with connection.cursor() as c:
            c.execute('SELECT 1')
        print('✅ BD lista')
        sys.exit(0)
    except Exception as e:
        print(f"⏳ BD no lista (intento {i}/{retries}): {e}")
        time.sleep(delay)
print('❌ Timeout esperando BD')
sys.exit(1)
PY

# Registrar cronjobs de Django limpiando primero para evitar duplicados
echo "⚙️ Instalando cronjobs de Django (clean + add)..."
/usr/local/bin/python manage.py crontab remove || true
/usr/local/bin/python manage.py crontab add
( crontab -l 2>/dev/null; echo "0 0 * * * /usr/local/bin/rotate-cron-logs.sh > /var/log/smarthydro/rotate.log 2>&1" ) | crontab -

# Mostrar cronjobs instalados
echo "📋 Cronjobs instalados:"
crontab -l || true

# Iniciar cron en primer plano
echo "🔄 Iniciando cron daemon..."
exec cron -f
