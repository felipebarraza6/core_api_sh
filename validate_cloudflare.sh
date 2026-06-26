#!/bin/bash
# Script de validación post-migración Cloudflare
# Fecha: 2026-01-28

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     VALIDACIÓN POST-MIGRACIÓN CLOUDFLARE - SmartHydro         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

DOMAIN="api.smarthydro.app"
ERRORS=0

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "════════════════════════════════════════════════════════════════"
echo "1. VERIFICANDO DNS"
echo "════════════════════════════════════════════════════════════════"

DNS_IP=$(nslookup $DOMAIN 2>/dev/null | grep -A1 "Name:" | grep "Address:" | tail -1 | awk '{print $2}')

if [ -z "$DNS_IP" ]; then
    echo -e "${RED}❌ DNS no resuelve${NC}"
    ERRORS=$((ERRORS+1))
else
    echo -e "${GREEN}✅ DNS resuelve a: $DNS_IP${NC}"

    # Verificar si es IP de Cloudflare (rangos comunes)
    if [[ $DNS_IP == 104.* ]] || [[ $DNS_IP == 172.* ]] || [[ $DNS_IP == 173.* ]]; then
        echo -e "${GREEN}✅ IP es de Cloudflare${NC}"
    else
        echo -e "${YELLOW}⚠️  IP NO parece ser de Cloudflare${NC}"
        echo "   Verifica que el proxy esté activado (naranja) en Cloudflare DNS"
    fi
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "2. VERIFICANDO SSL/HTTPS"
echo "════════════════════════════════════════════════════════════════"

HTTP_CODE=$(curl -I -s -o /dev/null -w "%{http_code}" https://$DOMAIN/admin/ 2>/dev/null)

if [ -z "$HTTP_CODE" ]; then
    echo -e "${RED}❌ No se puede conectar por HTTPS${NC}"
    ERRORS=$((ERRORS+1))
elif [ "$HTTP_CODE" == "200" ] || [ "$HTTP_CODE" == "301" ] || [ "$HTTP_CODE" == "302" ]; then
    echo -e "${GREEN}✅ HTTPS funciona (HTTP $HTTP_CODE)${NC}"
else
    echo -e "${RED}❌ HTTPS responde con error: HTTP $HTTP_CODE${NC}"
    ERRORS=$((ERRORS+1))
fi

# Verificar certificado
SSL_ISSUER=$(echo | openssl s_client -connect $DOMAIN:443 -servername $DOMAIN 2>/dev/null | openssl x509 -noout -issuer 2>/dev/null | grep -o "O = [^,]*" | cut -d= -f2 | xargs)

if [ -z "$SSL_ISSUER" ]; then
    echo -e "${YELLOW}⚠️  No se pudo verificar emisor del certificado${NC}"
else
    echo -e "${GREEN}✅ Certificado emitido por: $SSL_ISSUER${NC}"

    if [[ $SSL_ISSUER == *"Cloudflare"* ]] || [[ $SSL_ISSUER == *"Let's Encrypt"* ]]; then
        echo -e "${GREEN}✅ Certificado válido${NC}"
    fi
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "3. VERIFICANDO API ENDPOINTS"
echo "════════════════════════════════════════════════════════════════"

# Verificar /admin/
ADMIN_CODE=$(curl -I -s -o /dev/null -w "%{http_code}" https://$DOMAIN/admin/ 2>/dev/null)
if [ "$ADMIN_CODE" == "200" ] || [ "$ADMIN_CODE" == "302" ]; then
    echo -e "${GREEN}✅ /admin/ responde (HTTP $ADMIN_CODE)${NC}"
else
    echo -e "${RED}❌ /admin/ error: HTTP $ADMIN_CODE${NC}"
    ERRORS=$((ERRORS+1))
fi

# Verificar /api/
API_CODE=$(curl -I -s -o /dev/null -w "%{http_code}" https://$DOMAIN/api/ 2>/dev/null)
if [ "$API_CODE" == "200" ] || [ "$API_CODE" == "301" ]; then
    echo -e "${GREEN}✅ /api/ responde (HTTP $API_CODE)${NC}"
else
    echo -e "${YELLOW}⚠️  /api/ responde: HTTP $API_CODE${NC}"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "4. VERIFICANDO HEADERS CLOUDFLARE"
echo "════════════════════════════════════════════════════════════════"

CF_RAY=$(curl -I -s https://$DOMAIN/admin/ 2>/dev/null | grep -i "cf-ray" | cut -d: -f2 | xargs)

if [ -z "$CF_RAY" ]; then
    echo -e "${YELLOW}⚠️  No se detectó header CF-Ray${NC}"
    echo "   Verifica que el proxy de Cloudflare esté activo"
else
    echo -e "${GREEN}✅ Cloudflare está activo (CF-Ray: $CF_RAY)${NC}"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "5. VERIFICANDO CONTAINERS DOCKER"
echo "════════════════════════════════════════════════════════════════"

# Verificar que Django esté corriendo
if docker ps | grep -q django_api_secure; then
    echo -e "${GREEN}✅ Container django_api_secure está corriendo${NC}"

    # Verificar logs recientes
    ERROR_COUNT=$(docker logs django_api_secure --tail=50 2>&1 | grep -i "error\|exception\|traceback" | wc -l)
    if [ "$ERROR_COUNT" -gt 0 ]; then
        echo -e "${YELLOW}⚠️  Hay $ERROR_COUNT errores en logs recientes${NC}"
        echo "   Ejecuta: docker logs django_api_secure --tail=50"
    else
        echo -e "${GREEN}✅ Sin errores recientes en logs${NC}"
    fi
else
    echo -e "${RED}❌ Container django_api_secure NO está corriendo${NC}"
    ERRORS=$((ERRORS+1))
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "RESUMEN"
echo "════════════════════════════════════════════════════════════════"

if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✅ MIGRACIÓN EXITOSA - Todo funciona correctamente${NC}"
    echo ""
    echo "Próximos pasos recomendados:"
    echo "  1. Probar login en: https://$DOMAIN/admin/"
    echo "  2. Verificar API endpoints"
    echo "  3. Monitorear logs durante 1 hora"
    echo "  4. Configurar firewall rules en Cloudflare (opcional)"
else
    echo -e "${RED}❌ ERRORES DETECTADOS: $ERRORS${NC}"
    echo ""
    echo "Acciones recomendadas:"
    echo "  1. Ver logs: docker logs django_api_secure --tail=100"
    echo "  2. Verificar settings.py (ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS)"
    echo "  3. Verificar DNS en Cloudflare (proxy activo)"
    echo "  4. Verificar SSL mode en Cloudflare (debe ser 'Flexible' o 'Full')"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "COMANDOS ÚTILES"
echo "════════════════════════════════════════════════════════════════"
echo "Ver logs en tiempo real:"
echo "  docker logs -f django_api_secure"
echo ""
echo "Reiniciar Django:"
echo "  docker-compose -f docker-compose.production.secure.yml restart django"
echo ""
echo "Ver configuración Cloudflare:"
echo "  curl -I https://$DOMAIN/admin/"
echo ""
echo "════════════════════════════════════════════════════════════════"

exit $ERRORS
