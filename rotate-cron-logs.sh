#!/bin/bash
# Rotate and compress old cron logs daily
# Keeps last 7 days of logs

LOG_DIR="/tmp/smarthydro"
DAYS_TO_KEEP=7

# Ensure log directory exists
mkdir -p "$LOG_DIR"

cd "$LOG_DIR" || exit 1

# Compress logs older than 1 day
find . -name "*.log" -mtime +1 -exec gzip -f {} \;

# Delete compressed logs older than DAYS_TO_KEEP days
find . -name "*.log.gz" -mtime +$DAYS_TO_KEEP -delete

echo "[$(date)] Log rotation completed"
