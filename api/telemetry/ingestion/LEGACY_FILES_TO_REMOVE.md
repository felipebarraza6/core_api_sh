# Archivos Legacy a Eliminar

Estos archivos han sido reemplazados por el sistema dinámico 100% configurable.

## Getters Legacy (Reemplazados por TelemetryProvider)

- `getters/tdata.py` - Reemplazado por `TelemetryProvider` con handler dinámico
- `getters/thingsio.py` - Reemplazado por `TelemetryProvider` con handler dinámico  
- `getters/tago.py` - Reemplazado por `TelemetryProvider` con handler dinámico

**Razón**: El sistema `TelemetryProvider` permite configurar cualquier proveedor desde la BD sin código.

## Procesadores Específicos (Reemplazados por FormulaEngine)

- `controllers/flow.py` - Reemplazado por `FormulaEngine` con fórmulas configurables
- `controllers/total.py` - Reemplazado por `FormulaEngine` con fórmulas configurables
- `controllers/nivel.py` - Reemplazado por `FormulaEngine` con fórmulas configurables

**Razón**: `FormulaEngine` permite definir cualquier procesamiento mediante fórmulas configurables desde la BD.

## Migración

1. Ejecutar `python manage.py migrate_to_dynamic` para migrar datos
2. Verificar que todos los puntos usen `FormulaEngine` correctamente
3. Eliminar estos archivos después de confirmar que todo funciona

## Nota

Los archivos se mantienen temporalmente para compatibilidad durante la transición.
Una vez confirmado que el sistema dinámico funciona al 100%, pueden eliminarse.
