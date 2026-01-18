# Esquemas de Telemetría: Unificación de Lógica Existente y Abstracción Avanzada

Entiendo perfectamente: el nuevo sistema **no debe reinventar la rueda**, sino encapsular y potenciar el procesamiento que ya tienes (Totalizados, Niveles, Caudales, etc.). El objetivo es que la lógica de `unified_processing.py` se aplique de forma masiva y reutilizable.

## Implementación Técnica Orientada a la Continuidad:

### 1. Modelos que Soportan tu Lógica Actual (api/core/models/telemetry.py)
- **TelemetryScheme**: Definirá el "perfil" del punto.
- **SchemeVariable**: 
    - Tendrá el campo `type_variable` (TOTALIZADO, NIVEL, CAUDAL, etc.) para heredar tu lógica actual.
    - **Configuración Dinámica**: Un campo JSON guardará los parámetros específicos que ya usas (`pulses_factor`, `d3`, `calculate_nivel`, etc.).
    - Esto garantiza que **todo el procesamiento actual sea compatible al 100%**.
- **Variables Virtuales**: Definiciones abstractas (ej: Sumas o Restas de variables del esquema) para un manejo avanzado y único.

### 2. Motor de Ingesta Inteligente (unified_processing.py)
- Refactorizaré `save_telemetry_data` para que:
    1. Identifique si el punto tiene un **Esquema**.
    2. Si lo tiene, cargue las definiciones del esquema y las pase por tus funciones de procesamiento existentes (`process_totalizado_variable`, `process_nivel_variable`, etc.).
    3. Calcule las **Variables Virtuales** (ej: sumatorias de flujos) de forma automática.
    4. Permita que las variables manuales del punto sigan funcionando como casos especiales o excepciones.

### 3. Abstracción Única y Avanzada
- **Variables Virtuales Abstractas**: Podrás crear una variable `Consumo_Neto` a nivel de esquema que reste dos `internal_codes`. Esta lógica se aplicará a todos los puntos del esquema sin escribir una línea de código adicional por punto.
- **Centralización**: Si decides cambiar cómo se calcula un `TOTALIZADO` para un tipo de sensor, lo cambias en el **Esquema** y se actualiza en todos los puntos asociados inmediatamente.

### 4. Migración de Casos Existentes
- Crearé una herramienta para convertir tus configuraciones actuales en Esquemas reutilizables, de modo que no pierdas nada de lo que ya tienes funcionando, pero ganes el poder de gestionarlo de forma masiva.

## Resumen del Beneficio:
Tu lógica de negocio (el "cómo" se procesa cada dato) se mantiene intacta, pero el "dónde" se configura pasa de estar disperso punto por punto a estar centralizado en **Esquemas Reutilizables**.

¿Procedo con la creación de estos modelos y la actualización del motor de procesamiento manteniendo tu lógica actual?