# Auditoría de Paginación — API Legacy (Corregida)

> **Fecha:** 2026-05-22
> **Scope:** API Legacy (`/api/`)
> **Nota:** Esta es una corrección del análisis inicial. Se descubrió que Django REST Framework tiene paginación global configurada.

## Configuración Global de Paginación

En `api/settings.py`:
```python
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
}
```

Esto significa que **todos los viewsets que heredan de GenericViewSet o ModelViewSet**
usan paginación automática de 10 ítems por página, **a menos que** anulen explícitamente
`pagination_class`.

---

## Estado Real de Paginación por ViewSet

### ✅ Paginados automáticamente (gracias a configuración global)

| ViewSet | Archivo | Paginación |
|---------|---------|------------|
| `ClientViewSet` | catchment_points.py | ✅ Global (10/page) |
| `ProjectCatchmentsViewSet` | catchment_points.py | ✅ Global (10/page) |
| `CatchmentPointViewSet` | catchment_points.py | ✅ Global (10/page) |
| `ProfileIkoluCatchmentViewSet` | catchment_points.py | ✅ Global (10/page) |
| `NotificationsCatchmentViewSet` | catchment_points.py | ✅ Global (10/page) |
| `ResponseNotificationsCatchmentViewSet` | catchment_points.py | ✅ Global (10/page) |
| `TypeFileCatchmentViewSet` | catchment_points.py | ✅ Global (10/page) |
| `FileCatchmentViewSet` | catchment_points.py | ✅ Global (10/page) |
| `ProfileDataConfigCatchmentViewSet` | catchment_points.py | ✅ Global (10/page) |
| `DgaDataConfigCatchmentViewSet` | catchment_points.py | ✅ Global (10/page) |
| `SchemesCatchmentViewSet` | catchment_points.py | ✅ Global (10/page) |
| `VariableViewSet` | catchment_points.py | ✅ Global (10/page) |
| `RegisterPersonsViewSet` | catchment_points.py | ✅ Global (10/page) |
| `InteractionDetailViewSet` | interaction_detail.py | ✅ CustomPagination (10/page) |
| `InteractionXLS` | interaction_detail.py | ✅ CustomPagination (sin paginar para XLSX) |
| `InteractionXLSDga` | interaction_detail.py | ✅ CustomPagination (sin paginar para XLSX) |
| `InteractionXLSMonth` | interaction_detail.py | ✅ CustomPagination (sin paginar para XLSX) |
| `AlertRuleViewSet` | alerts.py | ✅ Global (10/page) |
| `AlertChannelViewSet` | alerts.py | ✅ Global (10/page) |
| `AlertTriggerViewSet` | alerts.py | ✅ Global (10/page) |
| `SystemEventViewSet` | alerts.py | ✅ Global (10/page) |
| `UserViewSet` | users.py | ✅ Global (10/page) |

### ❌ SIN paginación (anulada explícitamente)

| ViewSet | Archivo | Razón | Riesgo |
|---------|---------|-------|--------|
| `InteractionDetailOverrideViewSet` | interaction_detail.py | `NoPagination` — diseñado para arrays planos | **Alto** — puede traer miles de registros |
| `InteractionDetailOverrideMonthViewSet` | interaction_detail.py | `NoPagination` — diseñado para arrays planos | **Alto** — puede traer miles de registros |

### ⚠️ Acciones personalizadas SIN paginación

| Acción | ViewSet | URL | Riesgo |
|--------|---------|-----|--------|
| `all` | `CatchmentPointViewSet` | `GET /api/catchment_point/all/` | **Medio** — retorna 191 puntos con prefetch anidado |
| `points_status` | `ManagementViewSet` | `GET /api/management/points_status/` | **Medio** — retorna 191 puntos con última interacción |
| `metrics` | `ManagementViewSet` | `GET /api/management/metrics/` | Bajo — retorna agregados |
| `daily_records` | `ManagementViewSet` | `GET /api/management/daily_records/` | Bajo — retorna agregados por día |
| `hourly_records` | `ManagementViewSet` | `GET /api/management/hourly_records/` | Bajo — retorna agregados por hora |
| `by_project` | `ReportsGenerationViewSet` | `GET /api/reports/by-project/` | Bajo — genera archivo Excel |
| `by_point` | `ReportsGenerationViewSet` | `GET /api/reports/by-point/` | Bajo — genera archivo Excel |

---

## Problemas Reales Identificados

### 1. `InteractionDetailOverrideViewSet` — `NoPagination`

**Endpoint:** `GET /api/interaction_detail_override/`

Retorna array plano de overrides. Con 2.5M registros en interactiondetail, los overrides pueden ser miles.

**Mitigación actual:** Frontend probablemente filtra por punto y fecha.
**Riesgo:** Si alguien llama sin filtros, trae todo.

### 2. `InteractionDetailOverrideMonthViewSet` — `NoPagination`

**Endpoint:** `GET /api/interaction_detail_override_month/`

Similar al anterior, agrupado por mes.

### 3. `CatchmentPointViewSet.all()` — Acción personalizada

**Endpoint:** `GET /api/catchment_point/all/`

Retorna TODOS los puntos con `prefetch_related` anidado (perfiles, esquemas, variables).
Con 191 puntos, el payload JSON puede ser grande (~1-2MB).

**Nota:** Esta acción está diseñada para dropdowns/selects que necesitan todos los puntos.
**Riesgo:** Medio. 191 puntos no es masivo, pero con prefetch anidado el payload crece.

### 4. `ManagementViewSet.points_status()` — Acción personalizada

**Endpoint:** `GET /api/management/points_status/`

Retorna lista de puntos con última interacción, perfil de telemetría, etc.

**Nota:** Ya está optimizado con `select_related` y `prefetch_related`. El payload es manejable.
**Riesgo:** Medio.

---

## Recomendaciones Corregidas

### Prioridad Alta

1. **Agregar límite a `InteractionDetailOverrideViewSet`**
   - Máximo 1000 registros por request sin filtros.
   - Si el usuario no pasa `point_id` ni rango de fecha, retornar error 400.

2. **Agregar límite a `InteractionDetailOverrideMonthViewSet`**
   - Similar al anterior.

### Prioridad Media

3. **Agregar parámetro `?limit=` a `CatchmentPointViewSet.all()`**
   - Default: 500 (cubre todos los puntos actuales)
   - Máximo: 1000
   - Esto previene problemas futuros si el sistema crece a 1000+ puntos.

### Prioridad Baja

4. **Documentar que `ManagementViewSet.points_status()` no está paginado**
   - El payload actual (~191 puntos) es manejable.
   - Si crece a 1000+ puntos, reevaluar.

---

## Verificación Rápida

Para confirmar que un endpoint está paginado:
```bash
curl -s -H "Authorization: Token <token>" \
  "https://api.smarthydro.app/api/catchment_point/" | jq 'keys'
# Debe retornar: ["count", "next", "previous", "results"]
```

Para confirmar que NO está paginado:
```bash
curl -s -H "Authorization: Token <token>" \
  "https://api.smarthydro.app/api/interaction_detail_override/" | jq 'type'
# Debe retornar: "array"
```
