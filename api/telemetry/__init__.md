# 💧 Telemetry App (Data Core)

**Responsabilidad**: Almacenamiento histórico, Definición de Activos y Cálculo Matemático.
**Estado**: ✅ ACTIVO (Refactorizado)

## 🧠 Propósito
Ser la fuente de verdad de los datos hidrológicos. Ya NO maneja la conexión con módems (eso es `api.ingestion`), sino que recibe datos limpios y los guarda.

## 📦 Componentes Clave

1.  **Modelos de Activos**:
    *   `CatchmentPoint`: El pozo/estanque físico.
    *   `CoreVariable`: Qué se mide (Caudal, Nivel).
    
2.  **Motor de Cálculo (`FormulaEngine`)**:
    *   Aplica fórmulas matemáticas (`{pulsos} * factor`) a los datos crudos.
    *   Calcula derivadas (Caudal Promedio, Acumulados).

3.  **Histo-Storage**:
    *   `TelemetryRecord`: Tabla particionada (idealmente) con millones de registros.

## 🔗 Relación con Ingestion
`Ingestion` (Conectividad) -> Empuja Datos -> `Telemetry` (Procesa y Guarda).
