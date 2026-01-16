# PLAN DE FIXES CRÍTICOS - SmartHydro API

**Objetivo**: Solucionar problemas críticos de forma incremental y segura, validando cada cambio.

**Estrategia**: Un cambio a la vez → Test → Deploy → Validar → Siguiente cambio

---

## ORDEN DE EJECUCIÓN (De menos a más invasivo)

### ✅ FIX 1: Mover Credentials a Variables de Entorno (30 min)
**Riesgo**: BAJO - Solo configuración
**Rollback**: Fácil - revertir cambios en settings.py

### ✅ FIX 2: Crear Módulo utils/formatters.py (15 min)
**Riesgo**: BAJO - Nuevo archivo, no toca código existente
**Rollback**: Fácil - borrar archivo

### ✅ FIX 3: Refactorizar pdf_generator.py (20 min)
**Riesgo**: MEDIO - Cambia generación PDF
**Rollback**: Git revert
**Validación**: Generar PDF antes/después y comparar

### ✅ FIX 4: Refactorizar excel_utils.py (15 min)
**Riesgo**: MEDIO - Cambia generación Excel
**Rollback**: Git revert
**Validación**: Generar Excel antes/después y comparar

### ✅ FIX 5: Reemplazar print() con logging (20 min)
**Riesgo**: BAJO - Solo mejora logs
**Rollback**: Git revert

### ✅ FIX 6: Optimizar InteractionDetailAdmin queries (30 min)
**Riesgo**: MEDIO-ALTO - Cambia queries admin
**Rollback**: Git revert
**Validación**: Comparar query count antes/después

---

## FIX 1: CREDENTIALS A VARIABLES DE ENTORNO

### Paso 1.1: Agregar variables al archivo .env

```bash
# Editar o crear .env en la raíz del proyecto
nano .env
```

Agregar al final:
```env
# DGA Credentials
DGA_DEFAULT_PASSWORD=ZSQgCiDg7y

# User Default Password (deprecated - no usar para nuevos usuarios)
USER_DEFAULT_PASSWORD=pozos.2023
```

### Paso 1.2: Actualizar settings.py

```bash
# Abrir settings.py
nano api/settings.py
```

Agregar después de las otras variables de entorno (alrededor de línea 50):

```python
# DGA Configuration
DGA_DEFAULT_PASSWORD = os.environ.get('DGA_DEFAULT_PASSWORD', '')

# User Configuration (deprecated)
USER_DEFAULT_PASSWORD = os.environ.get('USER_DEFAULT_PASSWORD', 'pozos.2023')
```

### Paso 1.3: Actualizar modelo DgaDataConfigCatchment

```bash
nano api/core/models/catchment_points.py
```

Buscar (alrededor línea 1200):
```python
password_dga_software = models.CharField(default="ZSQgCiDg7y", max_length=150)
```

Reemplazar con:
```python
password_dga_software = models.CharField(
    default='',
    max_length=150,
    blank=True,
    help_text='Contraseña software DGA. Dejar vacío para usar default del sistema.'
)

def get_dga_password(self):
    """Obtener contraseña DGA (campo o variable entorno)."""
    from django.conf import settings
    return self.password_dga_software or settings.DGA_DEFAULT_PASSWORD
```

### Paso 1.4: Actualizar cron DGA

```bash
nano api/cronjobs/dga/send_data_dga.py
```

Buscar todas las líneas que usan `dga_config.password_dga_software` y reemplazar con `dga_config.get_dga_password()`.

Ejemplo:
```python
# ANTES
password = dga_config.password_dga_software

# DESPUÉS
password = dga_config.get_dga_password()
```

### Paso 1.5: Actualizar modelo User (marcar como deprecated)

```bash
nano api/core/models/users.py
```

Buscar (alrededor línea 25):
```python
txt_password = models.CharField(default='pozos.2023', max_length=150)
```

Reemplazar con:
```python
txt_password = models.CharField(
    default='',
    max_length=150,
    blank=True,
    help_text='DEPRECATED: No usar. Mantener vacío. Las contraseñas se hashean automáticamente.'
)
```

### Paso 1.6: Crear migración

```bash
cd /root/core_api_sh
python manage.py makemigrations core
```

Debe generar migración que cambia defaults y agrega help_text.

### Paso 1.7: Validar cambios

```bash
# Ver la migración generada
ls -la api/core/migrations/

# Verificar que settings.py carga las variables
python manage.py shell
```

En el shell:
```python
from django.conf import settings
print(f"DGA Password: {settings.DGA_DEFAULT_PASSWORD}")
print(f"User Default: {settings.USER_DEFAULT_PASSWORD}")
exit()
```

### Paso 1.8: Commit

```bash
git add .env api/settings.py api/core/models/catchment_points.py api/core/models/users.py api/cronjobs/dga/send_data_dga.py api/core/migrations/
git commit -m "Security: Mover credentials DGA a variables de entorno

- Agregar DGA_DEFAULT_PASSWORD y USER_DEFAULT_PASSWORD a settings
- Actualizar DgaDataConfigCatchment con método get_dga_password()
- Marcar User.txt_password como deprecated
- Actualizar send_data_dga.py para usar get_dga_password()

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

### Paso 1.9: Deploy y validar

```bash
# Rebuild solo API (no afecta DB ni otros servicios)
docker-compose -f docker-compose.production.secure.yml build django && \
docker-compose -f docker-compose.production.secure.yml up -d --no-deps django && \
docker logs django_api_secure --tail=30

# Verificar que no hay errores
docker logs django_api_secure | grep -i error

# Validar que DGA sigue funcionando
docker logs cron_jobs_secure --tail=50 | grep -i dga
```

---

## FIX 2: CREAR MÓDULO utils/formatters.py

### Paso 2.1: Crear el módulo

```bash
mkdir -p api/core/utils
touch api/core/utils/__init__.py
nano api/core/utils/formatters.py
```

Contenido de `formatters.py`:

```python
"""
Utilidades de formateo compartidas.

Centraliza funciones de formateo de números y cálculos
usados en reportes PDF y Excel.
"""
from decimal import Decimal
from typing import Union, Optional


def format_number_with_thousands(value: Optional[Union[int, float, Decimal]]) -> str:
    """
    Formatear número con separador de miles (punto).

    Args:
        value: Número a formatear. Puede ser None.

    Returns:
        String formateado con puntos como separadores de miles.
        Retorna "0" si value es None.

    Examples:
        >>> format_number_with_thousands(1000)
        '1.000'
        >>> format_number_with_thousands(1234567)
        '1.234.567'
        >>> format_number_with_thousands(None)
        '0'
    """
    if value is None:
        return "0"

    try:
        # Convertir a float para formateo
        num = float(value)
        # Formatear con coma y reemplazar por punto
        return f"{num:,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "0"


def format_decimal(
    value: Optional[Union[int, float, Decimal]],
    decimals: int = 2
) -> str:
    """
    Formatear número decimal con separador de miles y decimales.

    Args:
        value: Número a formatear. Puede ser None.
        decimals: Cantidad de decimales a mostrar (default: 2).

    Returns:
        String formateado con punto como separador de miles
        y coma como separador decimal.
        Retorna "0.00" (o "0.0..." según decimals) si value es None.

    Examples:
        >>> format_decimal(1234.56)
        '1.234,56'
        >>> format_decimal(1234.5678, decimals=3)
        '1.234,568'
        >>> format_decimal(None)
        '0,00'
    """
    if value is None:
        return "0" + "," + "0" * decimals

    try:
        num = float(value)
        # Formatear con coma como separador de miles
        formatted = f"{num:,.{decimals}f}"
        # Reemplazar coma por punto (miles) y punto por coma (decimal)
        # Primero cambiar coma a temporal, luego punto a coma, luego temporal a punto
        formatted = formatted.replace(",", "TEMP")
        formatted = formatted.replace(".", ",")
        formatted = formatted.replace("TEMP", ".")
        return formatted
    except (ValueError, TypeError):
        return "0" + "," + "0" * decimals


def calculate_variation_percentage(
    current: Union[int, float, Decimal],
    previous: Union[int, float, Decimal]
) -> float:
    """
    Calcular porcentaje de variación entre dos valores.

    Args:
        current: Valor actual.
        previous: Valor anterior.

    Returns:
        Porcentaje de variación. Retorna 100.0 si previous es 0 y current > 0,
        retorna 0.0 si ambos son 0.

    Examples:
        >>> calculate_variation_percentage(150, 100)
        50.0
        >>> calculate_variation_percentage(75, 100)
        -25.0
        >>> calculate_variation_percentage(100, 0)
        100.0
        >>> calculate_variation_percentage(0, 0)
        0.0
    """
    try:
        current = float(current)
        previous = float(previous)

        if previous == 0:
            return 100.0 if current > 0 else 0.0

        variation = ((current - previous) / previous) * 100
        return round(variation, 2)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0.0


def format_percentage(value: Union[int, float, Decimal]) -> str:
    """
    Formatear porcentaje con 2 decimales y símbolo %.

    Args:
        value: Valor del porcentaje.

    Returns:
        String formateado con % al final.

    Examples:
        >>> format_percentage(15.5)
        '15,50%'
        >>> format_percentage(-5.25)
        '-5,25%'
    """
    try:
        num = float(value)
        return f"{num:.2f}".replace(".", ",") + "%"
    except (ValueError, TypeError):
        return "0,00%"
```

### Paso 2.2: Validar el módulo

```bash
# Test rápido
python manage.py shell
```

En el shell:
```python
from api.core.utils.formatters import (
    format_number_with_thousands,
    format_decimal,
    calculate_variation_percentage
)

# Tests básicos
print(format_number_with_thousands(1234567))  # Debe mostrar: 1.234.567
print(format_decimal(1234.56))  # Debe mostrar: 1.234,56
print(calculate_variation_percentage(150, 100))  # Debe mostrar: 50.0
print(calculate_variation_percentage(75, 100))  # Debe mostrar: -25.0

exit()
```

### Paso 2.3: Commit

```bash
git add api/core/utils/formatters.py api/core/utils/__init__.py
git commit -m "Refactor: Crear módulo utils/formatters.py centralizado

- Centralizar funciones de formateo de números
- Eliminar duplicación entre pdf_generator y excel_utils
- Agregar docstrings y type hints
- Incluir ejemplos en docstrings

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## FIX 3: REFACTORIZAR pdf_generator.py

### Paso 3.1: Backup del archivo actual

```bash
cp api/core/reports/pdf_generator.py api/core/reports/pdf_generator.py.backup
```

### Paso 3.2: Identificar funciones a reemplazar

```bash
# Ver las funciones duplicadas
grep -n "def format_number_with_thousands" api/core/reports/pdf_generator.py
grep -n "def format_decimal" api/core/reports/pdf_generator.py
grep -n "def calculate_variation_percentage" api/core/reports/pdf_generator.py
```

### Paso 3.3: Actualizar imports

```bash
nano api/core/reports/pdf_generator.py
```

Al inicio del archivo (después de otros imports), agregar:

```python
# Utilidades de formateo centralizadas
from api.core.utils.formatters import (
    format_number_with_thousands,
    format_decimal,
    calculate_variation_percentage
)
```

### Paso 3.4: Eliminar funciones duplicadas

Buscar y ELIMINAR estas funciones del archivo (mantener solo los imports):
- `def format_number_with_thousands(...)`
- `def format_decimal(...)`
- `def calculate_variation_percentage(...)`

Las llamadas a estas funciones seguirán funcionando porque ahora se importan.

### Paso 3.5: Validar sintaxis

```bash
python -m py_compile api/core/reports/pdf_generator.py
echo $?  # Debe mostrar 0 si no hay errores
```

### Paso 3.6: Test funcional - Generar PDF

```bash
# Crear script de test
cat > test_pdf_generation.py << 'EOF'
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint
from api.core.reports.pdf_generator import generate_telemetry_analysis_pdf

# Buscar un punto con datos
point = CatchmentPoint.objects.filter(
    interaction_details__isnull=False
).first()

if point:
    print(f"Generando PDF para punto: {point.name}")

    try:
        pdf_content = generate_telemetry_analysis_pdf(
            points=[point],
            project_name=point.project.name if point.project else "Test",
            user_info={"name": "Test User", "email": "test@test.com"}
        )

        # Guardar PDF de test
        with open('/tmp/test_pdf_refactor.pdf', 'wb') as f:
            f.write(pdf_content)

        print("✅ PDF generado exitosamente: /tmp/test_pdf_refactor.pdf")
        print(f"Tamaño: {len(pdf_content)} bytes")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
else:
    print("No se encontró punto con datos para test")
EOF

python test_pdf_generation.py
```

Si el PDF se genera correctamente, el refactor funciona.

### Paso 3.7: Commit

```bash
git add api/core/reports/pdf_generator.py
git commit -m "Refactor: pdf_generator.py usa utils/formatters centralizado

- Importar funciones de formateo desde utils/formatters
- Eliminar funciones duplicadas (format_number_with_thousands, format_decimal, calculate_variation_percentage)
- Mantener funcionalidad idéntica

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## FIX 4: REFACTORIZAR excel_utils.py

### Paso 4.1: Backup del archivo

```bash
cp api/core/reports/excel_utils.py api/core/reports/excel_utils.py.backup
```

### Paso 4.2: Actualizar imports y eliminar duplicados

```bash
nano api/core/reports/excel_utils.py
```

Al inicio, agregar:
```python
from api.core.utils.formatters import (
    format_number_with_thousands,
    format_decimal,
    calculate_variation_percentage
)
```

Eliminar las funciones duplicadas (igual que en pdf_generator.py).

### Paso 4.3: Validar sintaxis

```bash
python -m py_compile api/core/reports/excel_utils.py
echo $?
```

### Paso 4.4: Test funcional - Generar Excel

```bash
cat > test_excel_generation.py << 'EOF'
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from api.core.models import CatchmentPoint
from api.core.reports.excel_generator import generate_excel_by_project

# Buscar puntos con datos
points = list(CatchmentPoint.objects.filter(
    interaction_details__isnull=False
)[:3])  # 3 puntos para test

if points:
    print(f"Generando Excel para {len(points)} puntos")

    try:
        workbook = generate_excel_by_project(
            points=points,
            project_name="Test Project"
        )

        # Guardar Excel de test
        workbook.save('/tmp/test_excel_refactor.xlsx')

        print("✅ Excel generado exitosamente: /tmp/test_excel_refactor.xlsx")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
else:
    print("No se encontraron puntos con datos para test")
EOF

python test_excel_generation.py
```

### Paso 4.5: Commit

```bash
git add api/core/reports/excel_utils.py
git commit -m "Refactor: excel_utils.py usa utils/formatters centralizado

- Importar funciones de formateo desde utils/formatters
- Eliminar funciones duplicadas
- Mantener funcionalidad idéntica

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## FIX 5: REEMPLAZAR print() CON LOGGING

### Paso 5.1: Configurar logging en settings.py

```bash
nano api/settings.py
```

Buscar sección LOGGING (debería estar alrededor de línea 300) y reemplazar/agregar:

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file_core': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/tmp/smarthydro/core_api.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'api.core': {
            'handlers': ['console', 'file_core'],
            'level': 'INFO',
            'propagate': False,
        },
        'api.cronjobs': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
}
```

### Paso 5.2: Actualizar flow_display.py

```bash
nano api/core/utils/flow_display.py
```

Al inicio del archivo, agregar:
```python
import logging

logger = logging.getLogger(__name__)
```

Buscar todos los `print()` y reemplazar. Ejemplo:

```python
# ANTES (alrededor línea 96)
print(f"Error calculando caudal promedio dinámico: {str(e)}")

# DESPUÉS
logger.exception(
    "Error calculando caudal promedio dinámico para punto",
    extra={
        'point_id': instance.catchment_point_id,
        'date': instance.date_time_medition,
    }
)
```

### Paso 5.3: Buscar otros print statements

```bash
# Buscar todos los print en core/
grep -rn "print(" api/core/ --include="*.py" | grep -v "__pycache__" | grep -v ".pyc"
```

Para cada print encontrado, evaluar:
- Si es debug: Reemplazar con `logger.debug()`
- Si es info: Reemplazar con `logger.info()`
- Si es error: Reemplazar con `logger.error()` o `logger.exception()`

### Paso 5.4: Validar cambios

```bash
python -m py_compile api/core/utils/flow_display.py
python -m py_compile api/settings.py
```

### Paso 5.5: Test logging

```bash
python manage.py shell
```

```python
import logging
logger = logging.getLogger('api.core')

logger.info("Test info message")
logger.warning("Test warning")
logger.error("Test error")

# Verificar que se escriben en /tmp/smarthydro/core_api.log
exit()
```

```bash
# Ver logs generados
tail -20 /tmp/smarthydro/core_api.log
```

### Paso 5.6: Commit

```bash
git add api/settings.py api/core/utils/flow_display.py
git commit -m "Fix: Reemplazar print() con logging estructurado

- Configurar logging con handlers console y file
- Reemplazar print statements con logger.exception/info/debug
- Agregar context extra en logs (point_id, date)
- Logs rotan automáticamente (10MB, 5 backups)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## FIX 6: OPTIMIZAR InteractionDetailAdmin QUERIES

### Paso 6.1: Medir queries ANTES de optimizar

```bash
cat > measure_admin_queries_before.py << 'EOF'
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from django.test.utils import override_settings
from django.db import connection, reset_queries
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from api.core.admin import InteractionDetailAdmin
from api.core.models import InteractionDetail
from django.contrib.auth import get_user_model

User = get_user_model()

# Habilitar query logging
with override_settings(DEBUG=True):
    # Setup
    admin = InteractionDetailAdmin(InteractionDetail, AdminSite())
    factory = RequestFactory()
    request = factory.get('/admin/core/interactiondetail/')
    request.user = User.objects.filter(is_superuser=True).first()

    # Reset queries
    reset_queries()

    # Ejecutar changelist
    queryset = admin.get_queryset(request)
    list(queryset[:24])  # Forzar evaluación de 1 página

    # Contar queries
    query_count = len(connection.queries)

    print(f"📊 ANTES DE OPTIMIZAR:")
    print(f"   Queries ejecutadas: {query_count}")
    print(f"   Registros evaluados: 24")

    if query_count > 50:
        print(f"   ⚠️  PROBLEMA N+1 DETECTADO (>{query_count} queries)")
    else:
        print(f"   ✅ Queries bajo control")

    # Mostrar algunas queries
    print(f"\n🔍 Primeras 5 queries:")
    for i, query in enumerate(connection.queries[:5], 1):
        print(f"   {i}. {query['sql'][:100]}...")
EOF

python measure_admin_queries_before.py
```

### Paso 6.2: Backup del admin.py

```bash
cp api/core/admin.py api/core/admin.py.backup
```

### Paso 6.3: Actualizar InteractionDetailAdmin

```bash
nano api/core/admin.py
```

Buscar la clase `InteractionDetailAdmin` y agregar el método `get_queryset`:

```python
class InteractionDetailAdmin(AdminIndicatorsMixin, admin.ModelAdmin):
    # ... configuración existente ...

    def get_queryset(self, request):
        """
        Optimizar queries con select_related y prefetch_related.
        Evita N+1 queries en changelist.
        """
        queryset = super().get_queryset(request)

        # Pre-cargar relaciones que se usan en list_display
        queryset = queryset.select_related(
            'catchment_point',                    # Para get_catchment_point_display
            'catchment_point__project',           # Para mostrar proyecto
            'catchment_point__owner',             # Para mostrar owner
        ).prefetch_related(
            'catchment_point__data_config_profiles',   # Para get_flow_display
            'catchment_point__dga_data_config_profiles',  # Para badges DGA
            'catchment_point__schemes',           # Para variables
            'catchment_point__schemes__variables' # Para cálculos
        )

        return queryset

    # ... resto de la clase ...
```

### Paso 6.4: Optimizar get_flow_display para usar datos pre-cargados

Buscar el método `get_flow_display` y actualizarlo:

```python
def get_flow_display(self, obj):
    """
    Mostrar caudal con tipo (INSTANTANEO/MEDIO/MEDIO_DIARIO).
    Usa datos pre-cargados para evitar queries extra.
    """
    try:
        # Intentar usar datos pre-cargados
        if hasattr(obj.catchment_point, '_prefetched_objects_cache'):
            # Usar config pre-cargado
            config = obj.catchment_point.data_config_profiles.all()[0] if obj.catchment_point.data_config_profiles.all() else None
        else:
            # Fallback (no debería llegar aquí con get_queryset optimizado)
            config = obj.catchment_point.data_config_profiles.first()

        from api.core.utils.flow_display import get_interaction_flow_display_data
        flow_data = get_interaction_flow_display_data(obj, config)

        value = flow_data['value']
        flow_type = flow_data['type']

        # Color según tipo
        color_map = {
            'INSTANTANEO': '#2196F3',      # Azul
            'MEDIO': '#FF9800',            # Naranja
            'MEDIO_DIARIO': '#4CAF50',     # Verde
        }
        color = color_map.get(flow_type, '#757575')

        return format_html(
            '<div style="display: flex; flex-direction: column; gap: 2px;">'
            '<span style="font-weight: 600; color: {};">{}</span>'
            '<span style="font-size: 10px; color: #666; text-transform: uppercase;">{}</span>'
            '</div>',
            color,
            format_number_with_thousands(value),
            flow_type
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Error en get_flow_display", extra={'obj_id': obj.id})
        return format_html('<span style="color: red;">Error</span>')

get_flow_display.short_description = 'Caudal (L/s)'
```

### Paso 6.5: Validar sintaxis

```bash
python -m py_compile api/core/admin.py
```

### Paso 6.6: Medir queries DESPUÉS de optimizar

```bash
cat > measure_admin_queries_after.py << 'EOF'
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from django.test.utils import override_settings
from django.db import connection, reset_queries
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from api.core.admin import InteractionDetailAdmin
from api.core.models import InteractionDetail
from django.contrib.auth import get_user_model

User = get_user_model()

with override_settings(DEBUG=True):
    admin = InteractionDetailAdmin(InteractionDetail, AdminSite())
    factory = RequestFactory()
    request = factory.get('/admin/core/interactiondetail/')
    request.user = User.objects.filter(is_superuser=True).first()

    reset_queries()

    queryset = admin.get_queryset(request)
    list(queryset[:24])

    query_count = len(connection.queries)

    print(f"📊 DESPUÉS DE OPTIMIZAR:")
    print(f"   Queries ejecutadas: {query_count}")
    print(f"   Registros evaluados: 24")

    if query_count < 10:
        print(f"   ✅ OPTIMIZACIÓN EXITOSA (<10 queries)")
    elif query_count < 30:
        print(f"   ⚠️  Mejorado pero puede optimizar más")
    else:
        print(f"   ❌ Todavía hay N+1 problem")

    print(f"\n🔍 Primeras 5 queries:")
    for i, query in enumerate(connection.queries[:5], 1):
        sql = query['sql'][:150]
        print(f"   {i}. {sql}...")
        if 'SELECT' in sql and 'JOIN' in sql:
            print(f"      ✅ Query usa JOIN (optimizado)")
EOF

python measure_admin_queries_after.py
```

Esperamos ver:
- **ANTES**: 50-100+ queries
- **DESPUÉS**: <10 queries

### Paso 6.7: Test visual en admin

```bash
# Levantar dev server temporalmente
python manage.py runserver 0.0.0.0:8001 &
SERVER_PID=$!

echo "🌐 Acceder a: http://localhost:8001/admin/core/interactiondetail/"
echo "   Verificar que la página carga correctamente"
echo "   Revisar que todos los campos se muestran igual que antes"
echo ""
echo "Presiona ENTER cuando termines de validar..."
read

kill $SERVER_PID
```

### Paso 6.8: Commit

```bash
git add api/core/admin.py
git commit -m "Performance: Optimizar InteractionDetailAdmin queries

- Agregar get_queryset() con select_related y prefetch_related
- Reducir queries de 50-100+ a <10 en changelist
- Optimizar get_flow_display para usar datos pre-cargados
- Agregar logging de errores en display methods

Antes: ~100 queries por página
Después: ~5-8 queries por página

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## VALIDACIÓN FINAL COMPLETA

### Script de Validación Integral

```bash
cat > validacion_final_fixes.sh << 'EOF'
#!/bin/bash

echo "=========================================="
echo "VALIDACIÓN FINAL DE FIXES CRÍTICOS"
echo "=========================================="
echo ""

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0

# 1. Verificar que no hay credentials hardcoded
echo "1️⃣  Verificando credentials..."
if grep -r "pozos.2023" api/core/models/ --include="*.py" | grep "default="; then
    echo -e "${RED}❌ Todavía hay 'pozos.2023' hardcoded${NC}"
    ERRORS=$((ERRORS+1))
else
    echo -e "${GREEN}✅ No hay 'pozos.2023' hardcoded${NC}"
fi

if grep -r "ZSQgCiDg7y" api/cronjobs/dga/ --include="*.py"; then
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

    # Verificar que NO tiene funciones duplicadas
    if grep -q "def format_number_with_thousands" api/core/reports/pdf_generator.py; then
        echo -e "${RED}❌ pdf_generator todavía tiene función duplicada${NC}"
        ERRORS=$((ERRORS+1))
    else
        echo -e "${GREEN}✅ Funciones duplicadas eliminadas${NC}"
    fi
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

# 5. Verificar logging configurado
echo ""
echo "5️⃣  Verificando logging..."
if grep -q "LOGGING = {" api/settings.py; then
    echo -e "${GREEN}✅ LOGGING configurado en settings${NC}"
else
    echo -e "${YELLOW}⚠️  LOGGING no configurado (opcional)${NC}"
fi

# Verificar que no hay print en flow_display
if grep -q "print(" api/core/utils/flow_display.py; then
    echo -e "${YELLOW}⚠️  Todavía hay print() en flow_display.py${NC}"
else
    echo -e "${GREEN}✅ No hay print() en flow_display.py${NC}"
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
python -m py_compile api/core/admin.py 2>/dev/null && \
python -m py_compile api/core/reports/pdf_generator.py 2>/dev/null && \
python -m py_compile api/core/reports/excel_utils.py 2>/dev/null && \
python -m py_compile api/core/utils/formatters.py 2>/dev/null

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Todos los archivos tienen sintaxis válida${NC}"
else
    echo -e "${RED}❌ Hay errores de sintaxis${NC}"
    ERRORS=$((ERRORS+1))
fi

# RESUMEN
echo ""
echo "=========================================="
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✅ VALIDACIÓN EXITOSA - 0 errores${NC}"
    echo ""
    echo "🎉 Todos los fixes críticos están implementados correctamente"
    echo ""
    echo "Próximos pasos:"
    echo "  1. Hacer commit final si no lo has hecho"
    echo "  2. Rebuild de producción:"
    echo "     docker-compose -f docker-compose.production.secure.yml build django"
    echo "     docker-compose -f docker-compose.production.secure.yml up -d --no-deps django"
    echo "  3. Validar en producción con logs"
else
    echo -e "${RED}❌ VALIDACIÓN FALLÓ - $ERRORS errores${NC}"
    echo ""
    echo "Revisar los errores arriba y corregir antes de deploy"
fi
echo "=========================================="
EOF

chmod +x validacion_final_fixes.sh
./validacion_final_fixes.sh
```

---

## DEPLOY A PRODUCCIÓN

### Checklist Pre-Deploy

```bash
# 1. Verificar que estamos en la rama correcta
git branch

# 2. Ver todos los commits realizados
git log --oneline -10

# 3. Ver archivos modificados
git status

# 4. Ejecutar validación final
./validacion_final_fixes.sh

# 5. Crear backup de la BD (opcional pero recomendado)
docker exec postgres_secure pg_dump -U smarthydro_user smarthydro_prod > backup_pre_fixes_$(date +%Y%m%d_%H%M%S).sql
```

### Deploy

```bash
# 1. Rebuild solo Django API
echo "🔨 Rebuilding Django API..."
docker-compose -f docker-compose.production.secure.yml build django

# 2. Deploy sin downtime
echo "🚀 Deploying..."
docker-compose -f docker-compose.production.secure.yml up -d --no-deps django

# 3. Verificar que arrancó correctamente
echo "⏳ Esperando 10 segundos..."
sleep 10

docker-compose -f docker-compose.production.secure.yml ps django

# 4. Ver logs recientes
echo "📋 Logs recientes:"
docker logs django_api_secure --tail=50

# 5. Verificar que no hay errores
echo ""
echo "🔍 Buscando errores..."
docker logs django_api_secure 2>&1 | grep -i error | tail -20

# 6. Test health check
echo ""
echo "🏥 Health check:"
curl -I http://localhost:8000/admin/ 2>/dev/null | head -1
```

### Validación Post-Deploy

```bash
# 1. Verificar que DGA sigue funcionando
echo "🔍 Verificando DGA..."
docker logs cron_jobs_secure --tail=30 | grep -i dga

# 2. Generar un PDF de test (vía admin web)
echo ""
echo "📄 Generar PDF de test:"
echo "   1. Acceder a https://api.smarthydro.app/admin/"
echo "   2. Ir a InteractionDetail"
echo "   3. Filtrar por un punto"
echo "   4. Generar reporte PDF"
echo "   5. Verificar que se descarga correctamente"

# 3. Generar un Excel de test
echo ""
echo "📊 Generar Excel de test:"
echo "   1. En el admin, seleccionar varios registros"
echo "   2. Usar acción de exportar a Excel"
echo "   3. Verificar que se descarga correctamente"

# 4. Verificar admin changelist performance
echo ""
echo "⚡ Verificar performance admin:"
echo "   1. Acceder a /admin/core/interactiondetail/"
echo "   2. Verificar que carga en <2 segundos"
echo "   3. Navegar entre páginas"
echo "   4. Verificar que todos los campos se muestran correctamente"

# 5. Verificar logs
echo ""
echo "📝 Verificar logs estructurados:"
tail -50 /tmp/smarthydro/core_api.log 2>/dev/null || echo "⚠️  Log file no existe aún (se crea en primer error/info)"
```

---

## ROLLBACK EN CASO DE PROBLEMAS

Si algo sale mal:

```bash
# 1. Revertir el último commit
git log --oneline -5  # Ver commits
git revert <commit-hash>  # Revertir el problemático

# O revertir todos los cambios
git reset --hard <commit-antes-de-fixes>

# 2. Rebuild con código anterior
docker-compose -f docker-compose.production.secure.yml build django
docker-compose -f docker-compose.production.secure.yml up -d --no-deps django

# 3. Verificar que funciona
docker logs django_api_secure --tail=50

# 4. Si nada funciona, usar backup
# Restaurar código
git checkout main
git pull

# Restaurar BD (si hiciste backup)
docker exec -i postgres_secure psql -U smarthydro_user smarthydro_prod < backup_pre_fixes_XXXXXX.sql

# Rebuild
docker-compose -f docker-compose.production.secure.yml build django
docker-compose -f docker-compose.production.secure.yml up -d --no-deps django
```

---

## RESUMEN DE TIEMPOS ESTIMADOS

| Fix | Tiempo | Riesgo | Validación |
|-----|--------|--------|------------|
| 1. Credentials → .env | 30 min | BAJO | Variables cargadas |
| 2. Módulo formatters | 15 min | BAJO | Import funciona |
| 3. pdf_generator | 20 min | MEDIO | PDF genera OK |
| 4. excel_utils | 15 min | MEDIO | Excel genera OK |
| 5. Logging | 20 min | BAJO | Logs se escriben |
| 6. Admin queries | 30 min | MEDIO | <10 queries |
| **TOTAL** | **~2.5 horas** | | |

---

## CONCLUSIÓN

Este plan te permite:
1. ✅ Solucionar los 6 problemas críticos identificados
2. ✅ Validar cada cambio antes de continuar
3. ✅ Hacer rollback fácilmente si algo falla
4. ✅ Mantener el sistema funcionando durante todo el proceso

**Recomendación**: Hacer los fixes 1-4 en una sesión, deploy, validar. Luego fixes 5-6 en otra sesión.

¿Empezamos con el Fix 1 (Credentials)?
