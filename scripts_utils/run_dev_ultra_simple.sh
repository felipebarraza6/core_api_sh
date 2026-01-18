#!/bin/bash

# Script ultra-simple para desarrollo local
# Inicia Django con runserver directamente

set -e

echo "🚀 SmartHydro Ultra-Simple Development Mode"
echo "==========================================="

# Verificar que Python esté disponible
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 no está instalado"
    exit 1
fi

# Verificar que pip esté disponible
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 no está instalado"
    exit 1
fi

# Instalar dependencias básicas si no existen
echo "Verificando dependencias..."
cd api

# Instalar solo las dependencias más críticas
pip3 install django djangorestframework psycopg2-binary redis

# Verificar que tenemos las variables de entorno
if [ ! -f "../.env" ]; then
    echo "❌ Archivo .env no encontrado"
    exit 1
fi

# Exportar variables de entorno
export $(grep -v '^#' ../.env | xargs)

echo "Iniciando Django con runserver..."
python3 manage.py runserver 0.0.0.0:8000