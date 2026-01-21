# Diagrama de Arquitectura: App CRM V2.0

Este documento describe la arquitectura y el flujo de datos del módulo de CRM (Customer Relationship Management) dentro de SmartHydro.

---

## 1. Visión General

El módulo CRM gestiona el ciclo de vida completo de un proyecto, desde la captación del cliente (prospecto) hasta la operación activa del sistema de telemetría. Está diseñado para integrar las áreas **comercial**, **técnica** y **operativa**.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                    MÓDULO CRM V2.0                                   │
│                                                                                      │
│  ┌───────────────┐                                                                   │
│  │    CLIENT     │ ────────┬─────────────────────────────────────────────────────┐   │
│  │               │         │                                                     │   │
│  │  • JobPosition│◄────────┤ (cargos por cliente)                                │   │
│  └───────────────┘         │                                                     │   │
│         │                  │                                                     │   │
│         │ 1:N              │                                                     │   │
│         ▼                  │                                                     │   │
│  ┌───────────────┐         │                                                     │   │
│  │    PROJECT    │◄────────┘                                                     │   │
│  │               │                                                               │   │
│  └───────────────┘                                                               │   │
│         │                                                                        │   │
│         ├──────────────────┬──────────────────┬─────────────────────┐            │   │
│         │ 1:N              │ 1:N              │ 1:N                 │ 1:N        │   │
│         ▼                  ▼                  ▼                     ▼            │   │
│  ┌──────────────┐   ┌─────────────┐   ┌─────────────┐       ┌─────────────┐      │   │
│  │TechnicalSurvey│  │  CrmTask    │   │ ProjectCost │       │   Person    │      │   │
│  │  (dinámico)  │   │             │   │             │       │  (contacto) │      │   │
│  └──────────────┘   └─────────────┘   └─────────────┘       └─────────────┘      │   │
│         │                 │                 │                       │            │   │
│         │ 1:1             │ 1:N             │                       │            │   │
│         ▼                 ▼                 ▼                       ▼            │   │
│  ┌──────────────┐   ┌─────────────┐   ┌─────────────┐       ┌─────────────┐      │   │
│  │CatchmentPoint│   │TaskResponse │   │  CostType   │       │ JobPosition │      │   │
│  │ (Telemetry)  │   │ + Documents │   │ (Ing/Egreso)│       │ (del cliente│      │   │
│  └──────────────┘   └─────────────┘   └─────────────┘       └─────────────┘      │   │
│                                                                                  │   │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Modelos de Datos (Entidades)

### 2.1. Cliente y Cargos

| Modelo         | Descripción                                                        | Relación Clave           |
| :------------- | :----------------------------------------------------------------- | :----------------------- |
| `Client`       | Empresa o persona natural (prospecto o cliente activo).            | `1:N` → `Project`, `JobPosition` |
| `JobPosition`  | **NUEVO:** Cargos definidos por cada cliente.                      | `N:1` → `Client`         |
| `Person`       | Contacto asociado a un proyecto.                                   | `N:1` → `Project`, `JobPosition` |

### 2.2. Proyecto

| Modelo     | Descripción                                               | Relación Clave                             |
| :--------- | :-------------------------------------------------------- | :----------------------------------------- |
| `Project`  | Proyecto de instalación con estado de ciclo de vida.      | `N:1` → `Client`, `1:N` → `TechnicalSurvey`, `CrmTask`, `ProjectCost`, `Person` |

### 2.3. Costos (Ingresos y Egresos)

| Modelo            | Descripción                                                       | Relación Clave           |
| :---------------- | :---------------------------------------------------------------- | :----------------------- |
| `CostCategory`    | Categoría interna (Hardware, Mano de Obra, etc.).                 | `1:N` → `CostSubCategory` |
| `CostSubCategory` | Subcategoría de costo.                                            | `N:1` → `CostCategory`   |
| `CostType`        | **NUEVO:** Tipo de flujo (📈 Ingreso / 📉 Egreso).                | `1:N` → `CostSubType`    |
| `CostSubType`     | **NUEVO:** Subtipos de ingreso/egreso.                            | `N:1` → `CostType`       |
| `ProjectCost`     | Línea de costo con doble clasificación (categoría + tipo flujo).  | `N:1` → `Project`, `CostCategory`, `CostType` |

### 2.4. Tareas

| Modelo            | Descripción                                                       | Relación Clave           |
| :---------------- | :---------------------------------------------------------------- | :----------------------- |
| `TaskCategory`    | Categoría de tarea (Comercial, Técnica, etc.).                    | `1:N` → `TaskSubCategory` |
| `TaskSubCategory` | Subcategoría de tarea.                                            | `N:1` → `TaskCategory`   |
| `TaskType`        | **NUEVO:** Tipo de tarea (Visita, Llamada, Instalación, etc.).    | `1:N` → `TaskSubType`    |
| `TaskSubType`     | **NUEVO:** Subtipos de tarea.                                     | `N:1` → `TaskType`       |
| `CrmTask`         | Tarea con doble clasificación + documentos adjuntos.              | `N:1` → `Project`, `TaskCategory`, `TaskType` |
| `TaskResponse`    | **NUEVO:** Respuesta a una tarea con archivos adjuntos.           | `N:1` → `CrmTask`, `M:N` → `Document` |

### 2.5. Levantamiento Técnico (Dinámico)

| Modelo                  | Descripción                                                   | Relación Clave           |
| :---------------------- | :------------------------------------------------------------ | :----------------------- |
| `SurveyFieldType`       | **NUEVO:** Tipo de dato (texto, entero, decimal, fecha, etc.)| —                        |
| `SurveyFieldDefinition` | **NUEVO:** Definición de campo con tipo, grupo, validaciones.| `N:1` → `SurveyFieldType` |
| `TechnicalSurvey`       | Levantamiento técnico con campos dinámicos en `dynamic_data`.| `N:1` → `Project`, `1:1` → `CatchmentPoint` |

---

## 3. Estructura de Costos

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                              COSTOS DE PROYECTO                               │
│                                                                               │
│    ┌─────────────────────────┐          ┌─────────────────────────┐           │
│    │     CATEGORÍA           │          │       TIPO              │           │
│    │  (Qué es el gasto)      │          │  (Flujo de dinero)      │           │
│    ├─────────────────────────┤          ├─────────────────────────┤           │
│    │ • Hardware              │          │ 📈 INGRESO              │           │
│    │ • Mano de Obra          │          │   • Venta de Servicio   │           │
│    │ • Transporte            │          │   • Anticipo            │           │
│    │ • Materiales            │          │   • Cuota Mensual       │           │
│    │                         │          │                         │           │
│    │   ▼ Subcategorías       │          │ 📉 EGRESO               │           │
│    │   • Sensores            │          │   • Compra Equipos      │           │
│    │   • Cables              │          │   • Pago Proveedores    │           │
│    │   • Paneles Solares     │          │   • Viáticos            │           │
│    └─────────────────────────┘          └─────────────────────────┘           │
│                                                                               │
│                         ┌─────────────────────┐                               │
│                         │    ProjectCost      │                               │
│                         │  (línea de costo)   │                               │
│                         │                     │                               │
│                         │  category ──────────┼─▶ CostCategory                │
│                         │  subcategory ───────┼─▶ CostSubCategory             │
│                         │  cost_type ─────────┼─▶ CostType (Ingreso/Egreso)   │
│                         │  cost_subtype ──────┼─▶ CostSubType                 │
│                         │  amount             │                               │
│                         │  documents ─────────┼─▶ [Document, ...]             │
│                         └─────────────────────┘                               │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Estructura de Tareas

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                              TAREAS CRM                                       │
│                                                                               │
│    ┌─────────────────────────┐          ┌─────────────────────────┐           │
│    │     CATEGORÍA           │          │       TIPO              │           │
│    │  (Área de trabajo)      │          │  (Naturaleza actividad) │           │
│    ├─────────────────────────┤          ├─────────────────────────┤           │
│    │ • Comercial             │          │ • Visita Terreno        │           │
│    │ • Técnica               │          │ • Llamada Telefónica    │           │
│    │ • Administrativa        │          │ • Instalación           │           │
│    │ • Operativa             │          │ • Mantenimiento         │           │
│    │                         │          │ • Cotización            │           │
│    │   ▼ Subcategorías       │          │                         │           │
│    │   • Captación Cliente   │          │   ▼ Subtipos            │           │
│    │   • Seguimiento         │          │   • Preventivo          │           │
│    │   • Cierre              │          │   • Correctivo          │           │
│    └─────────────────────────┘          └─────────────────────────┘           │
│                                                                               │
│                         ┌─────────────────────┐                               │
│                         │      CrmTask        │                               │
│                         │                     │                               │
│                         │  category ──────────┼─▶ TaskCategory                │
│                         │  subcategory ───────┼─▶ TaskSubCategory             │
│                         │  task_type ─────────┼─▶ TaskType                    │
│                         │  task_subtype ──────┼─▶ TaskSubType                 │
│                         │  documents ─────────┼─▶ [Document, ...]             │
│                         └─────────────────────┘                               │
│                                   │                                           │
│                                   │ 1:N                                       │
│                                   ▼                                           │
│                         ┌─────────────────────┐                               │
│                         │   TaskResponse      │                               │
│                         │                     │                               │
│                         │  content            │                               │
│                         │  responded_by       │                               │
│                         │  documents ─────────┼─▶ [Document, ...]             │
│                         └─────────────────────┘                               │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Levantamiento Técnico Dinámico

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                       LEVANTAMIENTO TÉCNICO DINÁMICO                          │
│                                                                               │
│    ┌─────────────────────────────────────────────────────────────┐            │
│    │              SurveyFieldType (Tipos de Dato)                │            │
│    ├─────────────────────────────────────────────────────────────┤            │
│    │  • TEXT      - Texto libre                                  │            │
│    │  • INTEGER   - Número entero                                │            │
│    │  • DECIMAL   - Número decimal                               │            │
│    │  • BOOLEAN   - Sí/No                                        │            │
│    │  • DATE      - Fecha                                        │            │
│    │  • DATETIME  - Fecha y hora                                 │            │
│    │  • SELECT    - Lista de opciones                            │            │
│    │  • FILE      - Archivo adjunto                              │            │
│    └─────────────────────────────────────────────────────────────┘            │
│                                   │                                           │
│                                   ▼                                           │
│    ┌─────────────────────────────────────────────────────────────┐            │
│    │            SurveyFieldDefinition (Campos)                   │            │
│    ├─────────────────────────────────────────────────────────────┤            │
│    │  name: "Diámetro Tubería"                                   │            │
│    │  code: "pipe_diameter"                                      │            │
│    │  field_type: DECIMAL                                        │            │
│    │  group: "Hidráulica"                                        │            │
│    │  is_required: true                                          │            │
│    │  min_value: 0.5, max_value: 24                              │            │
│    └─────────────────────────────────────────────────────────────┘            │
│                                   │                                           │
│                                   ▼                                           │
│    ┌─────────────────────────────────────────────────────────────┐            │
│    │                    TechnicalSurvey                          │            │
│    ├─────────────────────────────────────────────────────────────┤            │
│    │  project: FK → Project                                      │            │
│    │  name: "Pozo Norte"                                         │            │
│    │  gps_coordinates: "-33.4567, -70.1234"                      │            │
│    │  dynamic_data: {                                            │            │
│    │      "pipe_diameter": 4.5,                                  │            │
│    │      "signal_strength": -75,                                │            │
│    │      "power_source": "SOLAR",                               │            │
│    │      ...                                                    │            │
│    │  }                                                          │            │
│    │  documents: [foto_1.jpg, plano.pdf, ...]                    │            │
│    └─────────────────────────────────────────────────────────────┘            │
│                                   │                                           │
│                                   │ 1:1                                       │
│                                   ▼                                           │
│    ┌─────────────────────────────────────────────────────────────┐            │
│    │                   CatchmentPoint                            │            │
│    │               (Punto de Captación)                          │            │
│    └─────────────────────────────────────────────────────────────┘            │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. API Endpoints

| Endpoint                    | Descripción                                    |
| :-------------------------- | :--------------------------------------------- |
| `/api/crm/clients/`         | CRUD de clientes                               |
| `/api/crm/job-positions/`   | Cargos por cliente                             |
| `/api/crm/projects/`        | Proyectos                                      |
| `/api/crm/persons/`         | Contactos                                      |
| `/api/crm/cost-categories/` | Categorías de costos                           |
| `/api/crm/cost-types/`      | Tipos de costo (ingreso/egreso)                |
| `/api/crm/project-costs/`   | Líneas de costo de proyecto                    |
| `/api/crm/task-categories/` | Categorías de tareas                           |
| `/api/crm/task-types/`      | Tipos de tarea                                 |
| `/api/crm/tasks/`           | Tareas CRM                                     |
| `/api/crm/task-responses/`  | Respuestas a tareas                            |
| `/api/crm/survey-field-types/` | Tipos de campo para levantamientos          |
| `/api/crm/survey-field-definitions/` | Definiciones de campos              |
| `/api/crm/surveys/`         | Levantamientos técnicos                        |

---

## 7. Pasos Para Aplicar Cambios

```bash
# 1. Crear migraciones
docker-compose -f docker/docker-compose.dev.yml exec django_app python manage.py makemigrations crm

# 2. Aplicar migraciones
docker-compose -f docker/docker-compose.dev.yml exec django_app python manage.py migrate

# 3. Verificar en admin
# Navegar a /admin/ y verificar los nuevos modelos
```
