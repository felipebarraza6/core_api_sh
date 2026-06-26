#!/bin/bash
# Rotación de logs de cronjobs SmartHydro
# Ejecutar diariamente vía crontab (ya registrado en cron-entrypoint.sh)
#
# Rota logs en /var/log/smarthydro/*.log (volumen persistente Docker)
# /tmp/smarthydro es un symlink a /var/log/smarthydro

set -euo pipefail

LOG_DIR="/var/log/smarthydro"
RETAIN_DAYS=30
MAX_ROTATIONS=7

# Asegurar que el directorio existe
mkdir -p "$LOG_DIR"

# Rotar cada archivo .log
for logfile in "$LOG_DIR"/*.log; do
    [ -e "$logfile" ] || continue
    base=$(basename "$logfile" .log)

    # Shift rotaciones antiguas: .6.gz -> .7.gz, .5.gz -> .6.gz, etc.
    for i in $(seq $((MAX_ROTATIONS - 1)) -1 1); do
        j=$((i + 1))
        if [ -f "$LOG_DIR/${base}.log.${i}.gz" ]; then
            mv -f "$LOG_DIR/${base}.log.${i}.gz" "$LOG_DIR/${base}.log.${j}.gz"
        fi
    done

    # Rotar log actual -> .1 y comprimir
    if [ -s "$logfile" ]; then
        mv "$logfile" "$LOG_DIR/${base}.log.1"
        gzip -f "$LOG_DIR/${base}.log.1"
    fi
    
    # Crear log vacío nuevo (los cronjobs usan >> que lo creará automáticamente,
    # pero esto asegura permisos correctos si el contenedor corre como root)
    touch "$logfile"
    chmod 644 "$logfile"
done

# Eliminar rotaciones más allá del máximo
find "$LOG_DIR" -maxdepth 1 -name "*.log.*.gz" -regex ".*\.log\.[0-9]+\.gz$" | while read -r f; do
    num=$(echo "$f" | sed -E 's/.*\.log\.([0-9]+)\.gz$/\1/')
    if [ "$num" -gt "$MAX_ROTATIONS" ]; then
        rm -f "$f"
    fi
done

# Eliminar logs comprimidos más antiguos que RETAIN_DIAS
find "$LOG_DIR" -maxdepth 1 -name "*.log.*.gz" -mtime +"$RETAIN_DAYS" -delete

# Limpiar logs de rotación propios si crecen demasiado
if [ -f "$LOG_DIR/rotate.log" ]; then
    if [ "$(stat -f%z "$LOG_DIR/rotate.log" 2>/dev/null || stat -c%s "$LOG_DIR/rotate.log" 2>/dev/null || echo 0)" -gt 10485760 ]; then
        > "$LOG_DIR/rotate.log"
    fi
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') — Rotación completada"
