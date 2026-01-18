# Optimización y Consolidación del Sistema Dinámico

## 1. Eliminación de Lógica Hardcodeada (Mejora de Coherencia)
Se detectó una inconsistencia grave en `unified_processing.py` donde el punto ID 149 tiene lógica hardcodeada (`nivel - 17.0`).
- **Acción**: Eliminar el bloque `if point_catchment["id"] == 149` y reemplazarlo utilizando el campo `offset` o una `FORMULA` en el modelo `CoreVariable`.
- **Beneficio**: Elimina "números mágicos" y centraliza toda la lógica en la base de datos.

## 2. Optimización de Base de Datos (Mejora de Eficiencia)
El campo `data` en `TelemetryRecord` es un JSONField que actualmente no tiene un índice específico para búsquedas internas (como filtrar por `data__flow > X`).
- **Acción**: Agregar un `GinIndex` al campo `data` en el modelo `TelemetryRecord`.
- **Beneficio**: Acelera drásticamente las consultas que filtran o agregan valores dentro del JSON dinámico.

## 3. Validación de Fórmulas (Mejora Funcional)
Actualmente, si una fórmula está mal escrita, falla en tiempo de ejecución (ingesta).
- **Acción**: Implementar un validador en el método `clean()` o `save()` del modelo `CoreVariable`.
    - Verificar sintaxis básica (paréntesis balanceados).
    - Verificar que las variables referenciadas (`{var}`) existan en el punto o sean inputs válidos.
- **Beneficio**: Previene errores antes de que afecten la recolección de datos.

## 4. Consolidación de Configuración (Limpieza)
Existe duplicidad entre `ProfileDataConfigCatchment` (legacy) y `CoreVariable.configuration`.
- **Acción**: Actualizar `variable_service.py` para que la inicialización de variables priorice la configuración en `CoreVariable` y solo use `ProfileDataConfig` como fallback de migración.
- **Beneficio**: Clarifica cuál es la "fuente de la verdad" para la configuración del sistema.