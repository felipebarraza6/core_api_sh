#!/bin/bash
# scripts/export_db_portable.sh

# Exit on error
set -e

echo "📦 Exporting database for portability..."

# Ensure backups directory exists
mkdir -p backups

# Dump the database
# Using --clean --if-exists to make cleanup easier on import
docker exec -e PGPASSWORD=dev_password_123 postgres_dev pg_dump \
    -U smarthydro_dev_user \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges \
    smarthydro_dev > backups/portable_db_data.sql

echo "✅ Database exported to backups/portable_db_data.sql"
echo "👉 You can now commit this file to move your data to another machine."
