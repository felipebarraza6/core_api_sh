#!/bin/bash
# Script básico para rotación de logs de cron
# Este archivo se ejecuta periódicamente para rotar logs

LOG_DIR="/tmp/smarthydro"
MAX_SIZE=10485760  # 10MB

# Función para rotar log si es muy grande
rotate_log() {
    local log_file="$1"
    if [ -f "$log_file" ]; then
        local size=$(stat -f%z "$log_file" 2>/dev/null || stat -c%s "$log_file" 2>/dev/null)
        if [ "$size" -gt "$MAX_SIZE" ]; then
            mv "$log_file" "${log_file}.old"
            touch "$log_file"
            echo "$(date): Log rotated due to size > ${MAX_SIZE} bytes" >> "$log_file"
        fi
    fi
}

# Rotar logs principales
rotate_log "$LOG_DIR/django.log"
rotate_log "$LOG_DIR/twin_1.log"
rotate_log "$LOG_DIR/twin_5.log"
rotate_log "$LOG_DIR/twin_10.log"
rotate_log "$LOG_DIR/twin_60.log"
rotate_log "$LOG_DIR/nettra_60.log"
rotate_log "$LOG_DIR/nettra_5.log"
rotate_log "$LOG_DIR/novus_60.log"
rotate_log "$LOG_DIR/dga.log"
rotate_log "$LOG_DIR/sma.log"
rotate_log "$LOG_DIR/cluster_backup.log"
rotate_log "$LOG_DIR/alerts.log"
rotate_log "$LOG_DIR/daily_bulletin.log"
rotate_log "$LOG_DIR/daily_chat_report.log"
rotate_log "$LOG_DIR/dga_mayor_hourly.log"