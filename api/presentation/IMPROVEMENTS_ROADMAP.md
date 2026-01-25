# Roadmap de Capacidades: Orquestación & Front-Agnostic

Este documento detalla la estrategia para lograr una abstracción total del Frontend ("Code Less") y mejorar las capacidades funcionales del sistema.

## 1. Mapeo de Ecosistema & Coherencia

| Capa                 | Responsabilidad      | Estado Actual      | Mejora Propuesta                                      |
| :------------------- | :------------------- | :----------------- | :---------------------------------------------------- |
| **Unified Gateway**  | Enrutamiento         | ✅ Sólido           | Agregar Rate Limiting por Tenant.                     |
| **Data Proxy**       | Acceso a Datos       | ✅ CRUD/Audit OK    | Soporte para `Annotate/Aggregate` (Sumas, Promedios). |
| **Dynamic Registry** | UI Definitions       | 🟡 Parcial (Vistas) | **Orquestador de Dashboards & KPIs**.                 |
| **Compliance**       | Regulación Formativa | 🔴 Oculto           | Exponer API unificada de estado de reportes.          |

## 2. Nueva Capacidad: "Backend-Defined Indicators"

Para lograr que el usuario pueda crear indicadores sin tocar código, se propone el modelo `DashboardWidget`.

### Modelo Propuesto: `DashboardWidget`
*   **dashboard**: FK a `ModuleView` (tipo Dashboard).
*   **widget_type**: `KPI_CARD`, `LINE_CHART`, `BAR_CHART`, `GAUGE`.
*   **title**: "Caudal Total L/s".
*   **data_source**: `/api/registry/proxy/telemetry/catchmentpoint/?aggregate=sum&field=flow`.
*   **refresh_interval**: 60 (segundos).
*   **config**: JSON para colores, umbrales de alerta, iconos.

### Flujo de Orquestación del Frontend
1.  Frontend carga `/api/registry/modules/{slug}/views/{dashboard}/`.
2.  Backend responde:
    ```json
    {
      "type": "DASHBOARD",
      "layout": "grid-3-cols",
      "widgets": [
        { "type": "KPI_CARD", "title": "Pozos Activos", "source": "...", "color": "green" },
        { "type": "GAUGE", "title": "Caudal vs Límite", "source": "...", "thresholds": [80, 90] }
      ]
    }
    ```
3.  Frontend renderiza componentes genéricos. **Cero código de negocio en el cliente.**

## 3. Listado de Mejoras (Next Steps)

1.  **Orquestador de Widgets**: Implementar modelo `DashboardWidget`.
2.  **Proxy Aggregations**: Permitir `?aggregate=sum` en el Data Proxy para alimentar los KPIs.
3.  **Global Search**: Un buscador unificado que consulte el Proxy para múltiples modelos a la vez.
4.  **Action Triggers**: Que un KPI en rojo dispare una `DynamicAction` (ej: enviar mail) automáticamente (Backend Trigger).

---
*Esta arquitectura convierte a SmartHydro en un "CMS de Telemetría", donde la construcción de paneles de control es una tarea administrativa, no de desarrollo.*
