# 🧠 Análisis Profundo: API Core

**Fecha**: 24 Enero 2026

## 1. Diagnóstico Actual
`api/core` sufre de **Sobrecarga de Responsabilidades**. Originalmente diseñado como el núcleo del sistema, terminó absorbiendo lógica de presentación (Dashboards), lógica de negocio (Stats) y orquestación (Tasks).

### Estructura de "Core" hoy:
*   ✅ **Identidad**: `models/users.py`, `permissions.py`. (Correcto)
*   ✅ **Utilidades**: `models/utils.py`. (Correcto)
*   ❌ **Interfaz de Usuario**: `views/dashboard.py`. Contiene lógica compleja de agregación para el frontend. Debería estar en `api.unified`.
*   ❌ **Infraestructura**: `mqtt_broker.py` (Legacy/Proxy).
*   ❌ **Estadísticas**: `services/stats_service.py`. Calcula promedios de telemetría. Debería estar en `api.telemetry` o `api.analytics`.

## 2. Puntos Críticos (Hotspots)

### A. El "Dashboard Monolítico" (`views/dashboard.py`)
Este archivo importa modelos de **5 aplicaciones distintas** (Telemetry, Compliance, Infrastructure, CRM, Notifications).
*   **Riesgo**: Genera un acoplamiento cíclico. Si `api.telemetry` intenta importar algo de `api.core` (ej: `User`), y `core` importa `Telemetry`, tenemos un ciclo.
*   **Solución**: Mover a `api.unified`, que por definición es la capa superior que "conoce a todos".

### B. Action Service (`services/action_service.py`)
Implementa un sistema de permisos dinámicos (`user_can_perform_action`).
*   **Evaluación**: Es un buen patrón (RBAC dinámico), pero si las acciones son específicas de negocio (ej: `DGA_SEND`), quizás debería ser un servicio base que otras apps extienden, en lugar de tener `if action == 'DGA_SEND'` hardcodeado en Core.

## 3. Plan de Mejora (Roadmap Core)

### Fase 1: Migración de Dashboard (Inmediata)
Mover `DashboardSummaryView` y `RealtimeDashboardView` a la nueva app `api.unified`.
*   **Beneficio**: `api.core` deja de depender de `api.telemetry`. Rompemos el ciclo principal.

### Fase 2: Extracción de Analytics (Mediano Plazo)
Mover `metrics.py` y `stats_service.py` a una nueva app `api.analytics` o integrarlo en `api.telemetry.analysis`.
*   **Beneficio**: Core se queda solo con "Usuarios y Permisos".

### Fase 3: Limpieza Final
Eliminar los proxies de `mqtt_broker` una vez que se confirme que ningún script externo los llama.

## 4. Estructura Ideal de Core
```
api/core/
├── models/
│   ├── users.py      # Usuarios y Perfiles
│   └── utils.py      # Modelos Base (TimeStampedModel)
├── services/
│   ├── auth.py       # Lógica de Login/JWT
│   └── permissions.py # RBAC Genérico
├── middleware/       # Middlewares globales (audit, request_id)
└── constants.py      # Constantes globales del sistema
```
Cualquier otra cosa (Vistas de negocio, Procesamiento de datos, Dashboards) **DEBE SALIR**.
