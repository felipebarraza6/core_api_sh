# Plan de Transformación: Adiós al Legacy, Hola al Almacenamiento Dinámico

Este plan detalla la reestructuración completa del sistema para eliminar la rigidez de las tablas planas y permitir una configuración 100% dinámica desde Django Admin.

## 1. Rediseño del Modelo de Datos (Dynamic Schema)
Propongo simplificar y potenciar la relación de modelos:
- **`CatchmentPoint`**: Sigue siendo el eje central, pero eliminaremos campos redundantes.
- **`Variable`**: Se asocia directamente al punto. Cada variable tendrá:
  - `technical_name`: El nombre que viene del proveedor (ej: "temp_1", "flow_rate").
  - `display_name`: Nombre legible (ej: "Temperatura Pozo A").
  - `unit`: Unidad de medida.
  - `formula`: (Opcional) Lógica de cálculo dinámica.
- **`TelemetryRecord`**: Reemplazará a `InteractionDetail`. Tendrá una estructura ultra-limpia:
  - `point` (FK)
  - `timestamp`
  - `data` (JSONField): Guardará todos los valores de las variables de forma dinámica `{"temp_1": 25.4, "flow_rate": 120.5}`.

## 2. Gestión Total desde Django Admin
Haremos que el Admin sea la única herramienta necesaria:
- **Configuración In-line**: Podrás añadir, quitar o cambiar factores de escala de variables directamente desde la ficha del Punto de Captación.
- **Validación Automática**: El Admin validará que los nombres técnicos coincidan con lo que el punto está recibiendo.
- **Dashboard Integrado**: Ver las últimas mediciones en formato tabla/gráfico dentro del mismo Admin.

## 3. Migración de Datos Existentes
No perderemos nada de lo que trajimos de SQLite:
- Un script transformará los 14,861 registros actuales.
- Los valores de las columnas `flow`, `nivel`, `total` se moverán al nuevo `JSONField` bajo sus respectivos códigos de variable.

## 4. API V3: Consultas Dinámicas
Desarrollaremos una nueva API que:
- No dependa de campos fijos.
- Al consultar un punto, devuelva automáticamente todas sus variables configuradas con sus últimos valores.
- Esté preparada para que el nuevo Front-end que edites simplemente recorra el JSON recibido.

## 5. Próximos Pasos Técnicos
1.  Crear los nuevos modelos en `api/core/models/telemetry.py`.
2.  Desarrollar el script de migración `migrate_to_dynamic.py`.
3.  Actualizar el `IngestionManager` para que use este nuevo esquema.

¿Estás de acuerdo con este enfoque radical para limpiar el sistema?
