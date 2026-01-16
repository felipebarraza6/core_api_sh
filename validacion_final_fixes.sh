#!/bin/bash

echo "=========================================="
echo "VALIDACIÓN FINAL DE FIXES CRÍTICOS"
echo "=========================================="
echo ""

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

ERRORS=0

# 1. Verificar que no hay credentials hardcoded
echo "1️⃣  Verificando credentials..."
if grep -r "ZSQgCiDg7y" api/cronjobs/dga/ --include="*.py" 2>/dev/null; then
    echo -e "${RED}❌ Todavía hay password DGA hardcoded en cronjobs${NC}"
    ERRORS=$((ERRORS+1))
else
    echo -e "${GREEN}✅ Password DGA no está hardcoded${NC}"
fi

# 2. Verificar que utils/formatters existe
echo ""
echo "2️⃣  Verificando módulo formatters..."
if [ -f "api/core/utils/formatters.py" ]; then
    echo -e "${GREEN}✅ Módulo formatters.py existe${NC}"

    # Verificar que tiene las 3 funciones
    if grep -q "def format_number_with_thousands" api/core/utils/formatters.py && \
       grep -q "def format_decimal" api/core/utils/formatters.py && \
       grep -q "def calculate_variation_percentage" api/core/utils/formatters.py; then
        echo -e "${GREEN}✅ Todas las funciones presentes${NC}"
    else
        echo -e "${RED}❌ Faltan funciones en formatters.py${NC}"
        ERRORS=$((ERRORS+1))
    fi
else
    echo -e "${RED}❌ No existe api/core/utils/formatters.py${NC}"
    ERRORS=$((ERRORS+1))
fi

# 3. Verificar que pdf_generator importa de formatters
echo ""
echo "3️⃣  Verificando pdf_generator refactorizado..."
if grep -q "from api.core.utils.formatters import" api/core/reports/pdf_generator.py; then
    echo -e "${GREEN}✅ pdf_generator importa de formatters${NC}"
else
    echo -e "${RED}❌ pdf_generator no importa de formatters${NC}"
    ERRORS=$((ERRORS+1))
fi

# 4. Verificar que excel_utils importa de formatters
echo ""
echo "4️⃣  Verificando excel_utils refactorizado..."
if grep -q "from api.core.utils.formatters import" api/core/reports/excel_utils.py; then
    echo -e "${GREEN}✅ excel_utils importa de formatters${NC}"
else
    echo -e "${RED}❌ excel_utils no importa de formatters${NC}"
    ERRORS=$((ERRORS+1))
fi

# 5. Verificar que no hay print en core/
echo ""
echo "5️⃣  Verificando logging..."
if grep -rn "print(" api/core/ --include="*.py" | grep -v "__pycache__" | grep -v ".pyc" >/dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Todavía hay print() en core/${NC}"
    grep -rn "print(" api/core/ --include="*.py" | grep -v "__pycache__" | head -3
else
    echo -e "${GREEN}✅ No hay print() en core/${NC}"
fi

# 6. Verificar optimización admin
echo ""
echo "6️⃣  Verificando optimización admin..."
if grep -q "def get_queryset(self, request):" api/core/admin.py; then
    if grep -q "select_related" api/core/admin.py && grep -q "prefetch_related" api/core/admin.py; then
        echo -e "${GREEN}✅ InteractionDetailAdmin tiene get_queryset optimizado${NC}"
    else
        echo -e "${RED}❌ get_queryset existe pero sin optimizaciones${NC}"
        ERRORS=$((ERRORS+1))
    fi
else
    echo -e "${RED}❌ InteractionDetailAdmin no tiene get_queryset${NC}"
    ERRORS=$((ERRORS+1))
fi

# 7. Test de sintaxis Python
echo ""
echo "7️⃣  Verificando sintaxis Python..."
python3 -m py_compile api/core/admin.py 2>/dev/null && \
python3 -m py_compile api/core/reports/pdf_generator.py 2>/dev/null && \
python3 -m py_compile api/core/reports/excel_utils.py 2>/dev/null && \
python3 -m py_compile api/core/utils/formatters.py 2>/dev/null && \
python3 -m py_compile api/core/utils/flow_display.py 2>/dev/null

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Todos los archivos tienen sintaxis válida${NC}"
else
    echo -e "${RED}❌ Hay errores de sintaxis${NC}"
    ERRORS=$((ERRORS+1))
fi

# 8. Verificar commits
echo ""
echo "8️⃣  Verificando commits..."
COMMIT_COUNT=$(git log --oneline --since="2 hours ago" | wc -l)
if [ "$COMMIT_COUNT" -ge 6 ]; then
    echo -e "${GREEN}✅ Se realizaron $COMMIT_COUNT commits${NC}"
    echo ""
    echo -e "${BLUE}📝 Últimos commits:${NC}"
    git log --oneline --since="2 hours ago" | head -8
else
    echo -e "${YELLOW}⚠️  Solo $COMMIT_COUNT commits (esperado: 6+)${NC}"
fi

# RESUMEN
echo ""
echo "=========================================="
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✅ VALIDACIÓN EXITOSA - 0 errores${NC}"
    echo ""
    echo "🎉 Todos los fixes críticos están implementados correctamente"
    echo ""
    echo -e "${BLUE}Próximos pasos:${NC}"
    echo "  1. Rebuild de Django en producción:"
    echo "     ${YELLOW}docker-compose -f docker-compose.production.secure.yml build django${NC}"
    echo "     ${YELLOW}docker-compose -f docker-compose.production.secure.yml up -d --no-deps django${NC}"
    echo ""
    echo "  2. Verificar logs:"
    echo "     ${YELLOW}docker logs django_api_secure --tail=50${NC}"
    echo ""
    echo "  3. Validar en admin que carga rápido"
else
    echo -e "${RED}❌ VALIDACIÓN FALLÓ - $ERRORS errores${NC}"
    echo ""
    echo "Revisar los errores arriba y corregir antes de deploy"
fi
echo "=========================================="
