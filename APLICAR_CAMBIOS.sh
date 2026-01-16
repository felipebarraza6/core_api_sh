#!/bin/bash
# Script para aplicar las mejoras del dashboard y admin
# SmartHydro - Control de Telemetría

echo "🚀 Aplicando mejoras del Dashboard y Admin..."
echo ""

cd /root/core_api_sh

# Verificar que los templates estén presentes
echo "📁 Verificando templates..."
if [ -f "templates/admin/base_site.html" ] && [ -f "templates/admin/dashboard.html" ]; then
    echo "✅ Templates encontrados"
else
    echo "❌ Error: Templates no encontrados"
    exit 1
fi

# Reconstruir la imagen Docker
echo ""
echo "🔨 Reconstruyendo imagen Docker..."
docker-compose -f docker-compose.production.secure.yml build django

if [ $? -eq 0 ]; then
    echo "✅ Imagen reconstruida exitosamente"
else
    echo "❌ Error al reconstruir la imagen"
    exit 1
fi

# Reiniciar el contenedor
echo ""
echo "🔄 Reiniciando contenedor Django..."
docker-compose -f docker-compose.production.secure.yml stop django
docker-compose -f docker-compose.production.secure.yml rm -f django
docker-compose -f docker-compose.production.secure.yml up -d django

# Esperar a que el contenedor esté listo
echo ""
echo "⏳ Esperando a que el contenedor esté listo..."
sleep 10

# Verificar estado
echo ""
echo "📊 Verificando estado del contenedor..."
docker-compose -f docker-compose.production.secure.yml ps django

# Verificar que los templates estén en el contenedor
echo ""
echo "🔍 Verificando templates en el contenedor..."
docker exec django_api_secure ls -la /app/templates/admin/ 2>/dev/null

echo ""
echo "✅ ¡Cambios aplicados exitosamente!"
echo ""
echo "🎯 URLs disponibles:"
echo "   - Dashboard: https://tu-dominio.com/admin/dashboard/"
echo "   - Admin: https://tu-dominio.com/admin/"
echo "   - Monitoreo: https://tu-dominio.com/admin/telemetry-monitoring/"
echo ""
echo "📝 Ver documentación completa en: MEJORAS_DASHBOARD_ADMIN.md"

