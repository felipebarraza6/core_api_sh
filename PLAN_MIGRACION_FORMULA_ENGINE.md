# 🔄 Plan de Migración a FormulaEngine 100% Dinámico

**Objetivo:** Eliminar TODA la lógica hardcodeada de procesamiento y usar SOLO FormulaEngine

---

## 📊 Estado Actual (PROBLEMÁTICO)

### Archivos con Lógica Hardcodeada

```
api/telemetry/ingestion/controllers/
├─ unified_processing.py
│  ├─ process_totalizado_variable()      ❌ Hardcodeado
│  ├─ process_nivel_variable()           ❌ Hardcodeado
│  ├─ process_caudal_variable()          ❌ Hardcodeado
│  └─ process_caudal_promedio_variable() ❌ Hardcodeado
│
└─ processing/
   ├─ caudal.py          ❌ ELIMINAR
   ├─ nivel.py           ❌ ELIMINAR
   ├─ totalized.py       ❌ ELIMINAR
   └─ utils.py           ❌ ELIMINAR (si solo tiene funciones hardcodeadas)
```

### Problema

```python
# ❌ ACTUAL: Lógica duplicada y hardcodeada
if variable.type_variable == "TOTALIZADO":
    result = process_totalizado_variable(...)  # Función hardcodeada
elif variable.type_variable == "NIVEL":
    result = process_nivel_variable(...)       # Función hardcodeada
elif variable.type_variable == "CAUDAL":
    result = process_caudal_variable(...)      # Función hardcodeada
```

---

## 🎯 Estado Deseado (100% DINÁMICO)

### Arquitectura Target

```
api/telemetry/
├─ models/
│  └─ telemetry.py
│     └─ CoreVariable                   # Definición de variables
│
├─ processing/
│  └─ formula_engine.py                 # ✅ ÚNICO motor de procesamiento
│
└─ ingestion/
   └─ controllers/
      └─ unified_processing.py
         └─ process_variable()           # ✅ Genérico, usa FormulaEngine
```

### Solución

```python
# ✅ NUEVO: Todo via FormulaEngine
def process_variable(variable: CoreVariable, raw_data: dict, context: dict):
    """
    Procesa CUALQUIER variable usando FormulaEngine.
    Sin importar si es caudal, nivel, totalizado o custom.
    """
    if variable.operation == "PHYSICAL":
        # Valor directo del sensor con transformación simple
        raw_value = raw_data.get(variable.provider_key)
        return raw_value * variable.scale_factor + variable.offset

    elif variable.operation == "FORMULA":
        # Evaluar fórmula dinámica
        return FormulaEngine.evaluate(variable.formula, context)

    elif variable.operation in ["SUM", "DIFF", "AVG", "MUL", "MIN", "MAX"]:
        # Operaciones sobre variables fuente
        source_values = [context.get(src) for src in variable.sources]
        return apply_operation(variable.operation, source_values)
```

---

## 🔨 Pasos de Migración

### FASE 1: Preparar FormulaEngine Mejorado

#### 1.1. Extender FormulaEngine

**Archivo:** `api/telemetry/processing/formula_engine.py`

```python
class FormulaEngine:
    """Motor universal de procesamiento de variables."""

    @staticmethod
    def evaluate(formula: str, context: dict) -> Any:
        """
        Evalúa una fórmula con el contexto dado.

        Args:
            formula: Expresión matemática con variables en {var}
            context: Diccionario con valores de variables

        Returns:
            Resultado de la evaluación

        Ejemplos:
            >>> FormulaEngine.evaluate("{a} + {b}", {"a": 5, "b": 3})
            8
            >>> FormulaEngine.evaluate("({pulsos} * {factor}) / 1000",
            ...                        {"pulsos": 1500, "factor": 0.5})
            0.75
        """
        # Implementación actual (ya existe)
        ...

    @staticmethod
    def apply_operation(operation: str, values: list) -> Any:
        """
        Aplica una operación sobre una lista de valores.

        Args:
            operation: "SUM", "DIFF", "AVG", "MUL", "MIN", "MAX"
            values: Lista de valores numéricos

        Returns:
            Resultado de la operación

        Ejemplos:
            >>> FormulaEngine.apply_operation("SUM", [1, 2, 3])
            6
            >>> FormulaEngine.apply_operation("AVG", [10, 20, 30])
            20.0
        """
        if operation == "SUM":
            return sum(values)
        elif operation == "DIFF":
            return values[0] - sum(values[1:])
        elif operation == "AVG":
            return sum(values) / len(values)
        elif operation == "MUL":
            result = 1
            for v in values:
                result *= v
            return result
        elif operation == "MIN":
            return min(values)
        elif operation == "MAX":
            return max(values)
        else:
            raise ValueError(f"Operación no soportada: {operation}")

    @staticmethod
    def get_previous_value(point_id: int, variable_code: str,
                          hours_back: int = 1) -> Optional[float]:
        """
        Obtiene el valor previo de una variable.

        Útil para cálculos de diferencias (consumos, cambios, etc.)

        Args:
            point_id: ID del punto
            variable_code: Código de la variable
            hours_back: Horas hacia atrás a buscar

        Returns:
            Valor previo o None si no existe
        """
        from api.telemetry.models import TelemetryRecord
        from datetime import datetime, timedelta

        cutoff = datetime.now() - timedelta(hours=hours_back)
        record = TelemetryRecord.objects.filter(
            point_id=point_id,
            timestamp__lte=cutoff
        ).order_by('-timestamp').first()

        if record:
            return record.data.get(variable_code)
        return None
```

---

### FASE 2: Migrar CoreVariable a Fórmulas

#### 2.1. Script de Migración

**Archivo:** `api/telemetry/management/commands/migrate_to_formula_engine.py`

```python
from django.core.management.base import BaseCommand
from api.telemetry.models import CoreVariable


class Command(BaseCommand):
    help = 'Migra variables hardcodeadas a fórmulas dinámicas'

    def handle(self, *args, **options):
        # Migrar variables TOTALIZADO
        totalized_vars = CoreVariable.objects.filter(type_variable="TOTALIZADO")
        for var in totalized_vars:
            var.operation = "FORMULA"
            var.formula = "({pulsos} * {factor}) / 1000"
            var.context = {
                "factor": var.scale_factor or var.pulses_factor or 1.0
            }
            var.save()
            self.stdout.write(f"✅ Migrado: {var.internal_code}")

        # Migrar variables NIVEL
        nivel_vars = CoreVariable.objects.filter(type_variable="NIVEL")
        for var in nivel_vars:
            var.operation = "FORMULA"
            var.formula = "{profundidad_pozo} - {nivel_medido}"
            # Asumiendo que d1 es profundidad del pozo
            var.context = {
                "profundidad_pozo": var.point.d1 if hasattr(var.point, 'd1') else 50.0
            }
            var.save()
            self.stdout.write(f"✅ Migrado: {var.internal_code}")

        # Migrar variables CAUDAL
        caudal_vars = CoreVariable.objects.filter(type_variable="CAUDAL")
        for var in caudal_vars:
            var.operation = "PHYSICAL"  # Caudal suele ser directo
            # scale_factor y offset ya están en el modelo
            var.save()
            self.stdout.write(f"✅ Migrado: {var.internal_code}")

        # Migrar variables CAUDAL_PROMEDIO
        promedio_vars = CoreVariable.objects.filter(type_variable="CAUDAL_PROMEDIO")
        for var in promedio_vars:
            var.operation = "FORMULA"
            var.formula = "AVG_WINDOW({caudal}, window_minutes={window})"
            var.context = {
                "window": 60  # 60 minutos por defecto
            }
            var.sources = ["caudal"]
            var.save()
            self.stdout.write(f"✅ Migrado: {var.internal_code}")

        self.stdout.write(self.style.SUCCESS('✅ Migración completada'))
```

---

### FASE 3: Refactorizar unified_processing.py

#### 3.1. Nueva Función Genérica

**Archivo:** `api/telemetry/ingestion/controllers/unified_processing.py`

```python
from api.telemetry.processing.formula_engine import FormulaEngine


def process_variable(variable: CoreVariable, raw_data: dict,
                    context: dict) -> Any:
    """
    Procesa una variable usando FormulaEngine.

    Args:
        variable: Instancia de CoreVariable
        raw_data: Datos crudos del proveedor
        context: Contexto con todas las variables ya procesadas

    Returns:
        Valor procesado de la variable
    """
    # 1. Extraer valor crudo si es necesario
    if variable.operation == "PHYSICAL":
        raw_value = raw_data.get(variable.provider_key)
        if raw_value is None:
            return None
        return raw_value * variable.scale_factor + variable.offset

    # 2. Evaluar fórmula dinámica
    elif variable.operation == "FORMULA":
        # Combinar contexto de la variable con el contexto general
        full_context = {**context, **variable.context}

        # Agregar valores de variables fuente al contexto
        for source_var in variable.sources:
            if source_var in raw_data:
                full_context[source_var] = raw_data[source_var]
            elif source_var in context:
                full_context[source_var] = context[source_var]

        # Evaluar la fórmula
        return FormulaEngine.evaluate(variable.formula, full_context)

    # 3. Operaciones sobre variables fuente
    elif variable.operation in ["SUM", "DIFF", "AVG", "MUL", "MIN", "MAX"]:
        source_values = []
        for source_var in variable.sources:
            val = context.get(source_var) or raw_data.get(source_var)
            if val is not None:
                source_values.append(val)

        if not source_values:
            return None

        return FormulaEngine.apply_operation(variable.operation, source_values)

    # 4. Operación no reconocida
    else:
        raise ValueError(f"Operación no soportada: {variable.operation}")


def process_point_telemetry(point_id: int, raw_data: dict) -> dict:
    """
    Procesa todos los datos de telemetría de un punto.

    Args:
        point_id: ID del punto
        raw_data: Datos crudos del proveedor/equipo

    Returns:
        Diccionario con todas las variables procesadas
    """
    # 1. Obtener variables activas ordenadas por prioridad
    variables = CoreVariable.objects.filter(
        point_id=point_id,
        is_active=True
    ).order_by('priority', 'id')

    # 2. Contexto para almacenar resultados
    context = {}

    # 3. Procesar cada variable en orden
    for variable in variables:
        try:
            value = process_variable(variable, raw_data, context)

            # Validar rango si está definido
            if value is not None:
                if variable.min_value is not None and value < variable.min_value:
                    # Valor fuera de rango mínimo
                    value = None
                elif variable.max_value is not None and value > variable.max_value:
                    # Valor fuera de rango máximo
                    value = None

            # Agregar al contexto para variables dependientes
            if value is not None:
                context[variable.internal_code] = value

        except Exception as e:
            # Log error pero continuar procesando otras variables
            print(f"Error procesando {variable.internal_code}: {e}")
            context[variable.internal_code] = None

    return context
```

---

### FASE 4: Eliminar Código Hardcodeado

#### 4.1. Archivos a Eliminar

```bash
# Eliminar módulos de procesamiento hardcodeado
rm -rf api/telemetry/ingestion/controllers/processing/
```

#### 4.2. Limpiar unified_processing.py

```python
# ELIMINAR estas funciones de unified_processing.py:
# - process_totalizado_variable()     [línea ~283]
# - process_nivel_variable()          [línea ~370]
# - process_caudal_variable()         [línea ~447]
# - process_caudal_promedio_variable()[línea ~479]

# ELIMINAR estos imports:
# from .processing.totalized import process_totalizado_variable
# from .processing.nivel import process_nivel_variable
# from .processing.caudal import process_caudal_variable, ...
```

---

## 📋 Checklist de Migración

### Pre-migración
- [ ] Backup de la base de datos
- [ ] Documentar variables actuales
- [ ] Crear tests para verificar resultados idénticos

### Migración
- [ ] Extender FormulaEngine con operaciones faltantes
- [ ] Crear comando migrate_to_formula_engine
- [ ] Ejecutar migración de variables
- [ ] Refactorizar unified_processing.py
- [ ] Actualizar todas las llamadas a funciones hardcodeadas
- [ ] Eliminar módulos de processing/

### Post-migración
- [ ] Ejecutar tests de regresión
- [ ] Verificar que los datos procesados sean idénticos
- [ ] Actualizar documentación
- [ ] Entrenar equipo en nuevo sistema

---

## 🧪 Tests de Validación

```python
# tests/telemetry/test_formula_migration.py

def test_totalizado_migration():
    """Verifica que TOTALIZADO con fórmula da mismo resultado que hardcodeado."""
    # Datos de prueba
    raw_data = {"pulsos": 1500}

    # Resultado hardcodeado (antiguo)
    old_result = (1500 * 0.5) / 1000  # = 0.75

    # Resultado con fórmula (nuevo)
    variable = CoreVariable(
        operation="FORMULA",
        formula="({pulsos} * {factor}) / 1000",
        context={"factor": 0.5}
    )
    new_result = FormulaEngine.evaluate(variable.formula,
                                       {**raw_data, **variable.context})

    assert old_result == new_result


def test_nivel_migration():
    """Verifica que NIVEL con fórmula da mismo resultado que hardcodeado."""
    raw_data = {"nivel_medido": 3.2}

    # Resultado hardcodeado (antiguo)
    old_result = 50.0 - 3.2  # = 46.8

    # Resultado con fórmula (nuevo)
    variable = CoreVariable(
        operation="FORMULA",
        formula="{profundidad_pozo} - {nivel_medido}",
        context={"profundidad_pozo": 50.0}
    )
    new_result = FormulaEngine.evaluate(variable.formula,
                                       {**raw_data, **variable.context})

    assert old_result == new_result
```

---

## 🎯 Resultado Final

### Antes (Hardcodeado)
```python
# ❌ Código específico para cada tipo
if type_variable == "TOTALIZADO":
    result = (pulsos * factor) / 1000
elif type_variable == "NIVEL":
    result = d1 - nivel_medido
elif type_variable == "CAUDAL":
    result = valor_crudo * scale
```

### Después (Dinámico)
```python
# ✅ TODO pasa por FormulaEngine
result = process_variable(variable, raw_data, context)
```

### Ventajas
- ✅ Un solo lugar para mantener lógica de procesamiento
- ✅ Agregar nuevas variables = configuración, NO código
- ✅ Testing simplificado (solo FormulaEngine)
- ✅ Mismo método en ingesta, reportes, alertas, compliance
- ✅ Diferenciación competitiva

---

**PRÓXIMO PASO:** ¿Ejecuto esta migración ahora o prefieres revisarla primero?
