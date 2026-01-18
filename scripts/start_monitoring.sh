#!/bin/bash
# Script de inicio rápido para sistema de monitoreo SmartHydro

set -e

echo "🚀 SmartHydro - Iniciando Sistema de Monitoreo"
echo "================================================"
echo ""

# Verificar si Docker está corriendo
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker no está corriendo"
    echo "   Inicia Docker Desktop y vuelve a ejecutar este script"
    exit 1
fi

echo "✅ Docker está corriendo"
echo ""

# Crear red si no existe
echo "📡 Verificando red Docker..."
if ! docker network inspect smarthydro_network > /dev/null 2>&1; then
    echo "   Creando red 'smarthydro_network'..."
    docker network create smarthydro_network
    echo "   ✅ Red creada"
else
    echo "   ✅ Red 'smarthydro_network' existe"
fi
echo ""

# Conectar Django a la red si no está conectado
echo "🔗 Verificando conexión de Django..."
if docker ps --format '{{.Names}}' | grep -q "django_api_secure\|smarthydro_django_dev"; then
    DJANGO_CONTAINER=$(docker ps --format '{{.Names}}' | grep -E "django_api_secure|smarthydro_django_dev" | head -1)

    if ! docker network inspect smarthydro_network --format '{{range .Containers}}{{.Name}}{{"\n"}}{{end}}' | grep -q "$DJANGO_CONTAINER"; then
        echo "   Conectando $DJANGO_CONTAINER a la red..."
        docker network connect smarthydro_network "$DJANGO_CONTAINER"
        echo "   ✅ $DJANGO_CONTAINER conectado"
    else
        echo "   ✅ $DJANGO_CONTAINER ya está conectado"
    fi
else
    echo "   ⚠️  No se encontró contenedor Django corriendo"
    echo "   El sistema de monitoreo se iniciará, pero necesitarás iniciar Django después"
fi
echo ""

# Instalar prometheus-client si es necesario
echo "📦 Verificando dependencia prometheus-client..."
if docker ps --format '{{.Names}}' | grep -q "django_api_secure\|smarthydro_django_dev"; then
    DJANGO_CONTAINER=$(docker ps --format '{{.Names}}' | grep -E "django_api_secure|smarthydro_django_dev" | head -1)

    if ! docker exec "$DJANGO_CONTAINER" pip list 2>/dev/null | grep -q "prometheus-client"; then
        echo "   Instalando prometheus-client en $DJANGO_CONTAINER..."
        docker exec "$DJANGO_CONTAINER" pip install prometheus-client>=0.15.0
        echo "   ✅ prometheus-client instalado"
    else
        echo "   ✅ prometheus-client ya está instalado"
    fi
fi
echo ""

# Levantar stack de monitoreo
echo "🎯 Iniciando servicios de monitoreo..."
docker-compose -f docker-compose.monitoring.yml up -d

echo ""
echo "⏳ Esperando a que los servicios estén listos (10 segundos)..."
sleep 10
echo ""

# Verificar estado
echo "📊 Estado de servicios:"
docker-compose -f docker-compose.monitoring.yml ps

echo ""
echo "✅ Sistema de monitoreo iniciado correctamente!"
echo ""
echo "================================================"
echo "📍 URLs de Acceso:"
echo "================================================"
echo ""
echo "🔵 Grafana (Dashboards)"
echo "   URL: http://localhost:3000"
echo "   Usuario: admin"
echo "   Password: smarthydro2026"
echo ""
echo "🟠 Prometheus (Métricas)"
echo "   URL: http://localhost:9090"
echo "   Targets: http://localhost:9090/targets"
echo "   Rules: http://localhost:9090/rules"
echo ""
echo "🔴 Alertmanager (Alertas)"
echo "   URL: http://localhost:9093"
echo ""
echo "🟢 Django Metrics"
echo "   URL: http://localhost:8000/metrics/"
echo ""
echo "================================================"
echo "📚 Comandos Útiles:"
echo "================================================"
echo ""
echo "# Ver logs de Prometheus"
echo "docker logs -f smarthydro_prometheus"
echo ""
echo "# Ver logs de Grafana"
echo "docker logs -f smarthydro_grafana"
echo ""
echo "# Detener todo"
echo "docker-compose -f docker-compose.monitoring.yml down"
echo ""
echo "# Reiniciar Prometheus"
echo "docker-compose -f docker-compose.monitoring.yml restart prometheus"
echo ""
echo "================================================"
echo "⚠️  Configuración Pendiente:"
echo "================================================"
echo ""
echo "1. Editar monitoring/alertmanager/alertmanager.yml"
echo "   - Configurar credenciales SMTP para alertas por email"
echo "   - Cambiar direcciones de email de destino"
echo ""
echo "2. Cambiar password de Grafana en docker-compose.monitoring.yml"
echo "   - Buscar GF_SECURITY_ADMIN_PASSWORD"
echo ""
echo "3. Ver documentación completa en:"
echo "   monitoring/README.md"
echo ""
echo "================================================"

# Verificar endpoint de métricas
echo "🧪 Verificando endpoint de métricas Django..."
if curl -s http://localhost:8000/metrics/ | grep -q "smarthydro"; then
    echo "✅ Endpoint /metrics/ funciona correctamente"
    echo ""
    echo "Métricas disponibles:"
    curl -s http://localhost:8000/metrics/ | grep "^smarthydro" | head -5
    echo "..."
else
    echo "⚠️  No se pudieron obtener métricas de Django"
    echo "   Verifica que Django esté corriendo y que el endpoint /metrics/ esté configurado"
fi

echo ""
echo "🎉 ¡Listo! Abre http://localhost:3000 para ver los dashboards"
echo ""
