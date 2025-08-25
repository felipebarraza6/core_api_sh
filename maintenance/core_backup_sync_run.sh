#!/usr/bin/env bash
set -e -o pipefail

# Cargar tu .env (único archivo de config)
set -a
. /root/core_api_sh/.env
set +a

# Resolver URLs desde tu .env
SRC_URL="${REPLICA_DATABASE_URL:-${DATABASE_URL}}"
DST1_URL="${TELEMETRY_API_DATABASE_URL}"
DST2_URL="${DATA_STORE_TELEMETRY_DATABASE_URL}"

: "${SRC_URL:?Falta SRC_URL (REPLICA_DATABASE_URL o DATABASE_URL en tu .env)}"
: "${DST1_URL:?Falta TELEMETRY_API_DATABASE_URL en tu .env}"
: "${DST2_URL:?Falta DATA_STORE_TELEMETRY_DATABASE_URL en tu .env}"

SCHEMA=public
TS=$(date -u +%Y%m%dT%H0000Z)
BACKUP_DIR=/var/backups/core_hourly
OUT_SCHEMA_DIR="$BACKUP_DIR/core_${TS}_schema"
OUT_DATA_DIR="$BACKUP_DIR/core_${TS}_data"
LOG=/var/log/core_backup_sync.log

mkdir -p "$BACKUP_DIR" /var/log

echo "[$(date -u +%FT%TZ)] Preflight conexiones" | tee -a "$LOG"
psql "$SRC_URL"  -v ON_ERROR_STOP=1 -c "SELECT 1;" >/dev/null
psql "$DST1_URL" -v ON_ERROR_STOP=1 -c "SELECT 1;" >/dev/null
psql "$DST2_URL" -v ON_ERROR_STOP=1 -c "SELECT 1;" >/dev/null

echo "[$(date -u +%FT%TZ)] Dump esquema core_* (jobs=1)" | tee -a "$LOG"
nice -n 10 ionice -c2 -n7 pg_dump "$SRC_URL" \
  --format=directory --jobs=1 \
  --schema="$SCHEMA" --schema-only \
  -t "public.core_*" \
  --no-owner --no-privileges \
  -f "$OUT_SCHEMA_DIR"

echo "[$(date -u +%FT%TZ)] Dump datos core_* (jobs=1)" | tee -a "$LOG"
nice -n 10 ionice -c2 -n7 pg_dump "$SRC_URL" \
  --format=directory --jobs=1 \
  --data-only --disable-triggers \
  --schema="$SCHEMA" \
  -t "public.core_*" \
  --no-owner --no-privileges \
  -f "$OUT_DATA_DIR"

if command -v tar >/dev/null 2>&1; then
  tar -C "$BACKUP_DIR" -czf "$BACKUP_DIR/core_${TS}.tar.gz" "$(basename "$OUT_SCHEMA_DIR")" "$(basename "$OUT_DATA_DIR")"
  echo "[$(date -u +%FT%TZ)] Artifact: $BACKUP_DIR/core_${TS}.tar.gz" | tee -a "$LOG"
fi

prep_and_restore() {
  local dst_url="$1"; local name="$2"
  echo "[$(date -u +%FT%TZ)] Restore a ${name} (DROP+RECREATE core_* + datos, jobs=1)" | tee -a "$LOG"
  nice -n 10 ionice -c2 -n7 pg_restore --jobs=1 --clean --if-exists --no-owner --no-privileges -d "$dst_url" "$OUT_SCHEMA_DIR"
  nice -n 10 ionice -c2 -n7 pg_restore --jobs=1 --no-owner --no-privileges -d "$dst_url" "$OUT_DATA_DIR"
  echo "[$(date -u +%FT%TZ)] Verificación ${name}" | tee -a "$LOG"
  psql "$dst_url" -v ON_ERROR_STOP=1 -c "SELECT COUNT(*) AS core_tables FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'core_%';" >/dev/null
}

# Orden: primero telemetry_api, luego data_store_telemetry
prep_and_restore "$DST1_URL" "telemetry_api"
prep_and_restore "$DST2_URL" "data_store_telemetry"

echo "[$(date -u +%FT%TZ)] OK: core_ aplicado en ambos destinos (TS=$TS)" | tee -a "$LOG"
