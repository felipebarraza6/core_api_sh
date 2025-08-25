#!/bin/bash

# 🗑️ SCRIPT PARA LIMPIAR ARCHIVOS OBSOLETOS EN CONTROLLERS
# =========================================================

echo "🧹 INICIANDO LIMPIEZA DE ARCHIVOS OBSOLETOS..."
echo ""

# 📍 DIRECTORIO DE TRABAJO
CONTROLLERS_DIR="api/cronjobs/telemetry/controllers"
BACKUP_DIR="backups_obsoletos_$(date +%Y%m%d_%H%M%S)"

echo "📍 Directorio de controllers: $CONTROLLERS_DIR"
echo "📦 Directorio de backup: $BACKUP_DIR"
echo ""

# 🔍 PASO 1: VERIFICAR QUE ESTAMOS EN EL DIRECTORIO CORRECTO
if [ ! -d "$CONTROLLERS_DIR" ]; then
    echo "❌ ERROR: No se encontró el directorio $CONTROLLERS_DIR"
    echo "   Asegúrate de ejecutar este script desde la raíz del proyecto"
    exit 1
fi

echo "✅ Directorio de controllers encontrado"
echo ""

# 🔍 PASO 2: VERIFICAR QUE NO HAY REFERENCIAS A ARCHIVOS OBSOLETOS
echo "🔍 Verificando referencias a archivos obsoletos..."
echo ""

# Buscar referencias a archivos obsoletos
echo "📋 Buscando referencias a total_backup:"
grep -r "total_backup" api/cronjobs/telemetry/ 2>/dev/null || echo "   ✅ No se encontraron referencias"

echo ""
echo "📋 Buscando referencias a total.backup:"
grep -r "total\.backup" api/cronjobs/telemetry/ 2>/dev/null || echo "   ✅ No se encontraron referencias"

echo ""
echo "📋 Buscando referencias a total.bak:"
grep -r "total\.bak" api/cronjobs/telemetry/ 2>/dev/null || echo "   ✅ No se encontraron referencias"

echo ""

# 🔍 PASO 3: IDENTIFICAR ARCHIVOS OBSOLETOS
echo "📋 ARCHIVOS OBSOLETOS IDENTIFICADOS:"
echo ""

OBSOLETE_FILES=(
    "$CONTROLLERS_DIR/total.py.bak-20250813-180538"
    "$CONTROLLERS_DIR/total.py.backup"
    "$CONTROLLERS_DIR/total_backup.py"
)

for file in "${OBSOLETE_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "   ❌ $file (OBOLETO - ELIMINAR)"
    else
        echo "   ✅ $file (NO EXISTE)"
    fi
done

echo ""

# 🔍 PASO 4: VERIFICAR ARCHIVOS ACTIVOS
echo "📋 ARCHIVOS ACTIVOS (MANTENER):"
echo ""

ACTIVE_FILES=(
    "$CONTROLLERS_DIR/total.py"
    "$CONTROLLERS_DIR/flow.py"
    "$CONTROLLERS_DIR/nivel.py"
    "$CONTROLLERS_DIR/unified_processing.py"
    "$CONTROLLERS_DIR/unified_total_processing.py"
)

for file in "${ACTIVE_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "   ✅ $file (ACTIVO - MANTENER)"
    else
        echo "   ❌ $file (NO EXISTE - VERIFICAR)"
    fi
done

echo ""

# 🔍 PASO 5: CONFIRMAR ACCIÓN
echo "⚠️  ¿Deseas proceder con la limpieza?"
echo "   Esto eliminará los archivos obsoletos de forma permanente."
echo ""
read -p "   Escribe 'SI' para confirmar: " confirm

if [ "$confirm" != "SI" ]; then
    echo "❌ Limpieza cancelada por el usuario"
    exit 0
fi

echo ""

# 🔍 PASO 6: CREAR BACKUP DE SEGURIDAD
echo "📦 Creando backup de seguridad..."
mkdir -p "$BACKUP_DIR"

for file in "${OBSOLETE_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "   📋 Respaldando $file..."
        cp "$file" "$BACKUP_DIR/"
    fi
done

echo "✅ Backup creado en: $BACKUP_DIR"
echo ""

# 🔍 PASO 7: ELIMINAR ARCHIVOS OBSOLETOS
echo "🗑️  Eliminando archivos obsoletos..."
echo ""

for file in "${OBSOLETE_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "   🗑️  Eliminando $file..."
        rm "$file"
        if [ ! -f "$file" ]; then
            echo "      ✅ Eliminado correctamente"
        else
            echo "      ❌ Error al eliminar"
        fi
    fi
done

echo ""

# 🔍 PASO 8: VERIFICAR INTEGRIDAD
echo "🔍 Verificando integridad del sistema..."
echo ""

# Verificar que los archivos activos siguen funcionando
echo "📋 Probando importación de archivos activos..."

echo "   🔍 Probando total.py..."
python3 -c "from api.cronjobs.telemetry.controllers.total import total_m3; print('      ✅ total.py funciona correctamente')" 2>/dev/null || echo "      ❌ Error en total.py"

echo "   🔍 Probando flow.py..."
python3 -c "from api.cronjobs.telemetry.controllers.flow import instantaneous_flow; print('      ✅ flow.py funciona correctamente')" 2>/dev/null || echo "      ❌ Error en flow.py"

echo "   🔍 Probando nivel.py..."
python3 -c "from api.cronjobs.telemetry.controllers.nivel import nivel_mt; print('      ✅ nivel.py funciona correctamente')" 2>/dev/null || echo "      ❌ Error en nivel.py"

echo ""

# 🔍 PASO 9: MOSTRAR ESTADO FINAL
echo "📁 ESTADO FINAL DEL DIRECTORIO:"
echo ""

ls -la "$CONTROLLERS_DIR" | grep -E "\.(py|bak|backup)$" | while read line; do
    echo "   $line"
done

echo ""

# 🔍 PASO 10: RESUMEN DE ACCIONES
echo "📋 RESUMEN DE ACCIONES REALIZADAS:"
echo ""

echo "✅ ARCHIVOS ELIMINADOS:"
for file in "${OBSOLETE_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo "   🗑️  $file"
    fi
done

echo ""
echo "✅ ARCHIVOS MANTENIDOS:"
for file in "${ACTIVE_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "   🔒 $file"
    fi
done

echo ""
echo "📦 BACKUP CREADO:"
echo "   📁 $BACKUP_DIR"

echo ""
echo "🎉 ¡LIMPIEZA COMPLETADA EXITOSAMENTE!"
echo ""
echo "📞 PRÓXIMOS PASOS RECOMENDADOS:"
echo "   1. 🔍 Verificar que todos los cronjobs funcionan correctamente"
echo "   2. 🧪 Probar el script unificado: python ejecutar_cron_unificado_161.py"
echo "   3. 📋 Hacer commit de los cambios en git"
echo "   4. 🗑️  Eliminar el directorio de backup cuando estés seguro"
echo ""
echo "   git add ."
echo "   git commit -m 'Limpiar archivos obsoletos de controllers'"
echo ""
echo "🚀 ¡Tu código ahora está más limpio y organizado!"
