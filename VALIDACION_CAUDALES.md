# Validación de Cálculo de Caudales

**Fecha de creación**: 2025-01-XX  
**Estado**: En validación

## Funciones Implementadas

### 1. `calculate_daily_average_flow()`
- **Ubicación**: `api/cronjobs/dga/caudal_calculations.py`
- **Propósito**: Calcula caudal medio diario para estándar MEDIO
- **Lógica**: Promedio de todos los caudales del día anterior (00:00 a 23:59)
- **Estado**: ✅ Implementada, pendiente de validación

### 2. `calculate_flow_by_standard()`
- **Ubicación**: `api/cronjobs/dga/caudal_calculations.py`
- **Propósito**: Centraliza cálculo según estándar
- **Estado**: ✅ Implementada, pendiente de validación

## Tests Implementados

### Archivo: `tests/dga/test_caudal_calculations.py`

1. ✅ `test_calculate_daily_average_flow_medio` - Valida cálculo con 24 registros
2. ✅ `test_calculate_daily_average_flow_no_records` - Valida retorno 0.0 sin registros
3. ✅ `test_calculate_flow_by_standard_medio` - Valida uso para MEDIO
4. ✅ `test_calculate_flow_by_standard_mayor` - Valida que MAYOR usa fallback
5. ✅ `test_calculate_daily_average_flow_only_medio` - Valida que solo aplica a MEDIO

## Validación Pendiente

### Con Datos Reales

1. **Ejecutar análisis**:
   ```bash
   python manage.py analyze_caudal_dga --standard MEDIO --output analisis_medio.json
   ```

2. **Comparar métodos** para registros específicos:
   ```bash
   python manage.py analyze_caudal_dga --compare <register_id>
   ```

3. **Validar resultados**:
   - Comparar cálculo actual vs nuevo cálculo
   - Verificar que diferencias son razonables
   - Validar con múltiples puntos

### Integración Gradual

1. **Agregar flag de feature** en settings
2. **Modificar `_prepare_response_data()`** para usar nuevo cálculo si flag activo
3. **Validar en producción** con flag desactivado primero
4. **Activar gradualmente** por punto o por lote

## Casos de Prueba

### Caso 1: Punto con estándar MEDIO, día anterior completo
- **Entrada**: Registro con 24 registros del día anterior
- **Esperado**: Promedio de los 24 caudales
- **Estado**: ✅ Test implementado

### Caso 2: Punto con estándar MEDIO, sin registros del día anterior
- **Entrada**: Registro sin registros previos
- **Esperado**: 0.0
- **Estado**: ✅ Test implementado

### Caso 3: Punto con estándar MAYOR
- **Entrada**: Registro con estándar MAYOR
- **Esperado**: Usa cálculo actual (no modifica comportamiento)
- **Estado**: ✅ Test implementado

## Próximos Pasos

1. Ejecutar tests unitarios
2. Ejecutar análisis con datos reales
3. Documentar resultados
4. Integrar con flag de feature
5. Validar en staging/producción

