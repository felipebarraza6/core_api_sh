# Trazabilidad de Datos & Control de Acceso

Este diagrama explica cómo viaja un dato desde el hardware hasta la pantalla del usuario, y cómo el sistema decide qué mostrar.

## 1. Definición de Roles (User Types)

SmartHydro maneja 3 arquetipos de usuario principales:

| Rol                     | Descripción                                         | Permisos Clave                                               |
| :---------------------- | :-------------------------------------------------- | :----------------------------------------------------------- |
| **Cliente / User**      | Dueño de los pozos. Solo ve sus datos.              | `view_dashboard`, `view_catchmentpoint` (Filtered by Tenant) |
| **Operador (Internal)** | Equipo de Soporte/Hardware. Configura dispositivos. | `change_device`, `view_telemetry_raw`, `manage_alerts`       |
| **Admin / CRM**         | Gestión Comercial. Facturación y altas.             | `view_client`, `add_subscription`, `view_auditlog`           |

## 2. Flujo de Datos (Device -> DB)

```mermaid
graph LR
    HW[Hardware Device] -->|MQTT Publish| BROKER[Mosquitto Broker]
    BROKER -->|Subscribe| WORKER[Celery Ingestion Task]
    WORKER -->|Parse & Normalize| MODEL[Telemetry Models]
    MODEL -->|Save| DB[(PostgreSQL)]
    
    subgraph "Validation Layer"
    WORKER --> CHECK{Check Schema}
    CHECK -->|Valid| DB
    CHECK -->|Invalid| LOG[Error Log]
    end
```

## 3. Flujo de Visualización (DB -> User Screen)

Aquí es donde **Dynamic Registry** actúa como el "Portero".

```mermaid
graph TD
    USER((Usuario)) -->|Login| AUTH[Auth Service]
    AUTH -->|Token| API[Unified Gateway]
    
    API -->|1. Get Menu| REGISTRY[Dynamic Registry]
    REGISTRY -->|Check Perms| DB_CONF[SystemModule DB]
    
    DB_CONF -->|Filter Modules| MENU[JSON Menu]
    MENU --> USER
    
    USER -->|2. Click 'Pozos'| FE[Frontend Widget]
    FE -->|3. Get Data| PROXY[Universal Data Proxy]
    
    PROXY -->|Check 'view_catchmentpoint'| PERM_GUARD{Has Perm?}
    PERM_GUARD -->|Yes| RESOLVE[Resolve Model]
    PERM_GUARD -->|No| 403[Forbidden]
    
    RESOLVE -->|Query + Filter| PG[(PostgreSQL)]
    PG -->|Result JSON| FE
```

## 4. Auditoría (Traceability)

Cada acción de escritura (Create/Update/Delete) genera una "sombra":

*   **Usuario**: `juan.perez@cliente.com`
*   **Acción**: `UPDATE`
*   **Recurso**: `AlertConfig (ID: 55)`
*   **Cambio**: `limit: 50 -> 60`
*   **Timestamp**: `2026-01-24 18:30:00`

Esto queda grabado en la tabla `AuditLog` y es consultable solo por usuarios con permiso `view_auditlog`.
