#!/bin/bash
# scripts/import_db_portable.sh

# Exit on error
set -e

DB_FILE="backups/portable_db_data.sql"

if [ ! -f "$DB_FILE" ]; then
    echo "❌ Error: File $DB_FILE not found!"
    exit 1
fi

echo "⚠️  WARNING: This will OVERWRITE the current development database."
read -p "Are you sure? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 1
fi

echo "📦 Importing database from $DB_FILE..."

# Import the database
cat "$DB_FILE" | docker exec -i -e PGPASSWORD=dev_password_123 postgres_dev psql -U smarthydro_dev_user smarthydro_dev

echo "✅ Database imported successfully!"
