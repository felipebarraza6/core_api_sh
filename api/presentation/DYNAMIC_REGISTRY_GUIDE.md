# Guía de Capacidades: Dynamic Registry (Server-Driven UI)

## ¿Qué es el Dynamic Registry?
Es el "cerebro UI" de SmartHydro. A diferencia de los sistemas tradicionales donde el Frontend está "hardcoded" (programado fijo), aquí **el Backend decide qué se muestra en pantalla**.

Esto permite crear nuevos módulos, tablas y formularios **sin necesidad de desplegar nueva versión de la App o Web**. Todo es configuración en base de datos.

## 🏗️ Arquitectura de 3 Niveles

### 1. SystemModule (El "Qué")
Define un bloque funcional grande.
*   **Ejemplo**: "Gestión de Pozos", "Auditoría", "CRM".
*   **Configuración**: Icono, Orden, Permisos requeridos.
*   **Poder**: Puedes "apagar" un módulo entero globalmente con un solo click (`is_active=False`).

### 2. ModuleView (El "Cómo")
Define las pantallas dentro de un módulo.
*   **Tipos Soportados**:
    *   `TABLE`: Grilla de datos con columnas y filtros.
    *   `FORM`: Formulario de creación/edición (basado en JSON Schema).
    *   `DASHBOARD`: Panel con KPIs y gráficas.
    *   `KANBAN`: Tablero de gestión de estados.
*   **Layout Config**: Un JSON que le dice al frontend: *"Dibuja una columna llamada 'Caudal' que muestre el campo 'flow' en color azul"*.

### 3. DynamicAction (La "Acción")
Define qué puede hacer el usuario en esa vista.
*   **Tipos**:
    *   `API_CALL`: Llamar a un endpoint (ej: "Paudsar Pozo").
    *   `NAVIGATE`: Ir a otra vista.
    *   `OPEN_MODAL`: Abrir ventana emergente.
*   **Flexibilidad**: Puedes agregar un botón "Exportar a PDF" a una tabla existente solo agregando un registro en base de datos.

## 🚀 ¿Qué puedes hacer HOY con esto?

1.  **Crear un ABM (CRUD) completo en minutos**:
    *   Creas el módulo.
    *   Defines una vista `TABLE` apuntando a `/api/points/`.
    *   Defines una vista `FORM` para crear nuevos.
    *   **Resultado**: Tienes gestión de datos funcional sin escribir una sola línea de React/Angular.

2.  **Personalizar por Rol**:
    *   El módulo "Configuración Avanzada" solo se envía en el JSON a usuarios `is_superuser`. Los demás ni siquiera saben que existe.

3.  **Dashboards "On-the-fly"**:
    *   Puedes crear una vista tipo `DASHBOARD` que consuma `/api/console/` y mostrarla como "landing" de un módulo ejecutivo.

## Ejemplo de Configuración JSON (Layout)

```json
{
  "columns": [
    { "field": "title", "label": "Nombre del Pozo", "type": "link" },
    { "field": "status", "label": "Estado", "type": "badge", "colors": {"ok": "green", "error": "red"} },
    { "field": "flow", "label": "Caudal (L/s)", "type": "number", "precision": 2 }
  ],
  "filters": [
    { "field": "region", "type": "select", "source": "/api/regions" }
  ]
}
```

---
*Este módulo transforma a SmartHydro de una "App Estática" a una "Plataforma Dinámica" capaz de evolucionar al ritmo del negocio.*
