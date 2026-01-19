#!/bin/bash
# Configuración para desarrollo local
export LOCAL_DB_NAME=smarthydro_dev
export LOCAL_DB_USER=smarthydro_user
export LOCAL_DB_PASSWORD=dev_password_123
export LOCAL_DB_HOST=localhost
export LOCAL_DB_PORT=5432
export DJANGO_DEBUG=True
export USE_CLUSTER=false
export DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
export DJANGO_SECRET_KEY=dev-secret-key-change-in-production
export GEMINI_API_KEY=