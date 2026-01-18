# Implementación de Variables y Procesamiento Dinámico Unificado

Este plan detalla la transición hacia un sistema donde las variables de telemetría y su procesamiento sean completamente dinámicos y autogestionados por punto de captación.

## 1. Evolución del Modelo CoreVariable
Transformaremos `CoreVariable` en un modelo híbrido que soporte tanto datos físicos como cálculos dinámicos.

- **Nuevos Campos**:
    - `operation`: Define el tipo de procesamiento (`PHYSICAL`, `SUM`, `DIFF`, `MUL`, `AVG`, `FORMULA`).
    - `formula`: Almacena la expresión matemática (ej: `({var1} + {var2}) * 0.5`).
    - `sources`: Lista de códigos internos de los que depende esta variable.
    - `priority`: Orden de ejecución para asegurar que las variables dependientes se calculen después de sus orígenes.
    - `is_virtual`: Flag para identificar variables que no vienen directamente de un sensor.

## 2. Refactorización del Motor de Ingesta
Actualizaremos la lógica en [tasks/telemetry.py](file:///Users/felipebarraza/projects/core_api_sh/api/core/tasks/telemetry.py) y [unified_processing.py](file:///Users/felipebarraza/projects/core_api_sh/api/telemetry/ingestion/controllers/unified_processing.py):

- **Orden de Procesamiento**:
    1. **Variables Físicas**: Se obtienen de los proveedores (TWIN, NETTRA, etc.) y se procesan (escalado, offset).
    2. **Variables de Procesamiento Especial**: (Totalizados, Caudales Promedio, Niveles) usando los controladores existentes.
    3. **Variables Virtuales/Fórmulas**: Se ejecutan en orden de `priority` permitiendo cálculos en cadena.
- **Evaluación Segura**: Mantendremos el uso de un entorno restringido para `eval()` garantizando seguridad.

## 3. Automatización de Variables por Defecto
Implementaremos un mecanismo (Signal de Django o Service) que:
- Al crear un nuevo `CatchmentPoint`, cree automáticamente las variables estándar: `total`, `flow`, `nivel`.
- Configure sus parámetros base según el perfil del punto (ej: `pulses_factor` desde el perfil).

## 4. Impacto en Endpoints y Serializers
- **Serialización Dinámica**: Los serializers de `CatchmentPoint` y `TelemetryRecord` leerán dinámicamente el diccionario `data` y la configuración de `CoreVariable`, eliminando campos hardcoded.
- **Configuración Dinámica**: El endpoint de configuración permitirá editar fórmulas y dependencias directamente.

## 5. Validación y Compatibilidad
- **Migración de Datos**: Se asegurará que las variables existentes se marquen como `PHYSICAL` o según su `type_variable` actual.
- **Verificación**: Realizaremos pruebas de ingesta con fórmulas personalizadas para validar que el impacto en los endpoints sea inmediato.

¿Deseas que proceda con la implementación de estos cambios?
