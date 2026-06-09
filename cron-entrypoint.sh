#!/bin/bash
set -euo pipefail

echo "🚀 Iniciando cronjobs SmartHydro con verificación de BD..."

# Variables para Django
export DJANGO_SETTINGS_MODULE=api.settings
export LOCAL_DB_HOST="${LOCAL_DB_HOST:-postgres}"
export LOCAL_DB_NAME="${LOCAL_DB_NAME:-smarthydro_prod}"
export LOCAL_DB_USER="${LOCAL_DB_USER:-smarthydro_user}"
export LOCAL_DB_PASSWORD="${LOCAL_DB_PASSWORD:-}"
export LOCAL_DB_PORT="${LOCAL_DB_PORT:-5432}"

# Fallback: leer TDATA credentials de .env si no vienen por environment
if [ -z "${TDATA_USERNAME:-}" ] && [ -f /app/.env ]; then
    TDATA_USERNAME=$(grep '^TDATA_USERNAME=' /app/.env | cut -d= -f2- | tr -d "'\"" || true)
    export TDATA_USERNAME
fi
if [ -z "${TDATA_PASSWORD:-}" ] && [ -f /app/.env ]; then
    TDATA_PASSWORD=$(grep '^TDATA_PASSWORD=' /app/.env | cut -d= -f2- | tr -d "'\"" || true)
    export TDATA_PASSWORD
fi

# Preparar logs
mkdir -p /var/log/smarthydro
if [ -d /tmp/smarthydro ] && [ ! -L /tmp/smarthydro ]; then
  cp -an /tmp/smarthydro/. /var/log/smarthydro/ 2>/dev/null || true
  rm -rf /tmp/smarthydro
fi
ln -sfn /var/log/smarthydro /tmp/smarthydro
: > /tmp/smarthydro/django.log || true
for f in unified_twin_1 unified_twin_5 unified_twin_60 unified_nettra_60 unified_novus_60 dga sma alert_engine alert_dispatcher space_backup daily_bulletin daily_chat_report daily_active_tickets dga_mayor_hourly; do
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
# ✅ FIX CRÍTICO: crontab -r borra TODO el crontab (incluyendo residuos de reinicios previos)
# crontab remove solo borra los que django reconoce, dejando duplicados modificados
crontab -r 2>/dev/null || true
/usr/local/bin/python manage.py crontab add

# ✅ FIX: Escribir variables de entorno a archivo y usar source en crontab
# (evita "command too long" que ocurre al inyectar variables inline)
echo "📝 Configurando variables de entorno en crontab..."
TEMP_CRON=$(mktemp)
crontab -l > "$TEMP_CRON" 2>/dev/null || echo "" > "$TEMP_CRON"

# Crear archivo de entorno compartido
ENV_FILE="/app/.cron_env.sh"
cat > "$ENV_FILE" <<EOF
export LOCAL_DB_HOST='${LOCAL_DB_HOST}'
export LOCAL_DB_NAME='${LOCAL_DB_NAME}'
export LOCAL_DB_USER='${LOCAL_DB_USER}'
export LOCAL_DB_PASSWORD='${LOCAL_DB_PASSWORD}'
export LOCAL_DB_PORT='${LOCAL_DB_PORT}'
export USE_CLUSTER='${USE_CLUSTER:-false}'
export DJANGO_DEBUG='${DJANGO_DEBUG:-False}'
export DJANGO_SETTINGS_MODULE='api.settings'
export TDATA_USERNAME="${TDATA_USERNAME:-}"
export TDATA_PASSWORD="${TDATA_PASSWORD:-}"
EOF
chmod 600 "$ENV_FILE"

# Crear nuevo crontab con source del archivo de entorno
# ⚠️ IMPORTANTE: solo agregar source si NO está ya presente (evita duplicados al reiniciar)
NEW_CRON=$(mktemp)
SOURCE_PREFIX=". /app/.cron_env.sh && "

while IFS= read -r line; do
    # Si la línea contiene "crontab run"
    if echo "$line" | grep -q "crontab run"; then
        # Si YA tiene source, mantenerla tal cual
        if echo "$line" | grep -qE "source /app/.cron_env.sh|\. /app/.cron_env.sh"; then
            echo "$line" >> "$NEW_CRON"
        else
            # Extraer schedule (primeros 5 campos) y el resto
            SCHEDULE=$(echo "$line" | awk '{print $1, $2, $3, $4, $5}')
            REST=$(echo "$line" | awk '{for(i=6;i<=NF;i++) printf "%s ", $i; print ""}')
            # Reconstruir con source
            echo "${SCHEDULE} ${SOURCE_PREFIX}${REST}" >> "$NEW_CRON"
        fi
    elif echo "$line" | grep -q "rotate-cron-logs"; then
        # Mantener la línea de rotación sin modificar
        echo "$line" >> "$NEW_CRON"
    elif [ -n "$line" ]; then
        # Mantener otras líneas
        echo "$line" >> "$NEW_CRON"
    fi
done < "$TEMP_CRON"

# Agregar rotación de logs si no existe
if ! grep -q "rotate-cron-logs.sh" "$NEW_CRON"; then
    echo "0 0 * * * /usr/local/bin/rotate-cron-logs.sh > /var/log/smarthydro/rotate.log 2>&1" >> "$NEW_CRON"
fi

crontab "$NEW_CRON"
rm -f "$TEMP_CRON" "$NEW_CRON"

# Mostrar cronjobs instalados
echo "📋 Cronjobs instalados:"
crontab -l || true

# Iniciar cron en primer plano
echo "🔄 Iniciando cron daemon..."
exec cron -f
