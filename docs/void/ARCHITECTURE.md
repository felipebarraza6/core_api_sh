# Arquitectura de `void` — Nueva generación SmartHydro

> Estado: FASE 1.6 (shadow mode para totales)  
> Última revisión: 2026-07-06

## 1. Visión

`void` es la app Django limpia donde se construirá la nueva generación de SmartHydro sin arrastrar deuda técnica legacy. El principio rector es: **los endpoints legacy nunca mueren**. `void` corre en paralelo, valida resultados contra legacy (shadow mode) y solo reemplaza componentes cuando la comparación es estable.

## 2. Estructura de carpetas

```
void/
├── __init__.py
├── admin.py                      # Registro en Django Admin
├── apps.py
├── api/
│   ├── urls.py                   # Router DRF + endpoints custom
│   ├── views.py                  # ingest, compliance custom views
│   ├── viewsets.py               # CRUD DRF puntos/devices/providers/projects/users
│   ├── serializers.py            # Serializadores DRF
│   ├── permissions.py            # Permisos por rol y por punto
│   └── auth/
│       ├── urls.py               # /void/auth/login/, /refresh/, /me/
│       └── views.py              # CurrentUser, ChangePassword
├── management/commands/
│   ├── void_compare_legacy.py    # Placeholder para comparación legacy
│   ├── void_migrate_providers.py # Migra TelemetryProvider → void.Provider
│   ├── void_mqtt_listen.py       # Listener MQTT manual
│   ├── void_shadow_report.py     # Reporte de shadow mode
│   ├── void_shadow_run.py        # Ejecución manual de shadow mode
│   └── void_sync_legacy.py       # Sync CatchmentPoint → void.Point/Device
├── migrations/
│   ├── 0001_initial.py
│   ├── 0002_provider_mqtttopicconfig...
│   └── 0003_shadowrun_shadowcomparison...
├── models/
│   ├── base.py                   # VoidModel (created/modified)
│   ├── alerts.py                 # AlertRule, AlertTrigger
│   ├── clients.py                # Client
│   ├── compliance.py             # ComplianceAuthority, Standard, Profile, Submission
│   ├── devices.py                # Device, DeviceHardware
│   ├── mqtt.py                   # MqttTopicConfig
│   ├── points.py                 # Point, PointGroup, PointPermission
│   ├── processing/
│   │   ├── schema.py             # ProcessingSchema, Step, Rule
│   │   └── sla.py                # SLAPolicy, SLAEvent
│   ├── providers.py              # Provider, ProviderEndpoint
│   ├── shadow.py                 # ShadowRun, ShadowComparison
│   ├── subscriptions.py          # Contract, Subscription, Invoice
│   ├── telemetry/
│   │   ├── processed.py          # ProcessedReading
│   │   ├── readings.py           # RawReading
│   │   ├── state.py              # DeviceVariableState
│   │   ├── totalizer.py          # CounterResetLog
│   │   └── events.py             # DeviceEvent
│   └── users.py                  # VoidUserProfile
├── services/
│   ├── __init__.py
│   ├── alerts.py                 # AlertEngine
│   ├── handlers/                 # Handlers de procesamiento
│   │   ├── base.py
│   │   ├── formula.py
│   │   ├── generic.py
│   │   ├── stateful.py           # Reglas declarativas
│   │   └── stateful_rulesets.py  # Plantillas stateful (totalizador, nivel, etc.)
│   ├── ingest.py                 # IngestService
│   ├── mqtt.py                   # MqttConsumer
│   ├── notifications.py          # AlertDispatcher
│   ├── pipeline.py               # PipelineService
│   ├── providers/
│   │   ├── base.py               # DynamicHttpProvider
│   │   ├── registry.py           # ProviderRegistry
│   │   └── tdata.py              # TdataProvider (JWT + Redis)
│   ├── shadow.py                 # ShadowService
│   └── subscriptions.py          # SubscriptionService
├── signals.py                    # post_save DeviceEvent → alertas
├── tasks.py                      # Tareas Celery
└── tests/                        # 127 tests
```

## 3. Capas

### 3.1 Infraestructura
- **Django 4.2** + **DRF** (legacy, void reutiliza settings)
- **PostgreSQL 15** para persistencia
- **Redis** para cache de tokens + broker Celery
- **Celery + Redis** para tareas asíncronas (workers/beat)
- **Docker Compose** actual; Kubernetes evaluable a futuro

### 3.2 Modelos de dominio

| Dominio | Modelos | Estado |
|---------|---------|--------|
| Identidad | `VoidUserProfile` | ✅ Base (roles, notificaciones) |
| Puntos | `Point`, `PointGroup`, `PointPermission`, `Project` | ✅ Base + Project real |
| Dispositivos | `Device`, `DeviceHardware` | ✅ Base + inventario |
| Proveedores | `Provider`, `ProviderEndpoint`, `MqttTopicConfig` | ✅ Funcional (HTTP + MQTT) |
| Telemetría | `RawReading`, `ProcessedReading` | ✅ Base |
| Procesamiento | `ProcessingSchema`, `ProcessingStep`, `ProcessingRule` | ✅ Funcional |
| Totalizador | Plantilla stateful "Totalizador stateful v1" | ✅ Paridad legacy |
| Alertas | `AlertRule`, `AlertTrigger` | ✅ Motor + dispatch async |
| Shadow mode | `ShadowRun`, `ShadowComparison` | ✅ Funcional |
| CRM | `Client` | ✅ Base |
| Suscripciones | `Contract`, `Subscription`, `Invoice` | ✅ Base |
| DGA/Compliance | `ComplianceAuthority`, `ComplianceStandard`, `PointComplianceProfile`, `ComplianceSubmission` | ✅ Funcional (auto-send bajo flag) |

### 3.3 Servicios

- `IngestService`: obtiene lecturas de proveedores y crea `RawReading`.
- `PipelineService`: aplica esquemas de procesamiento configurables.
- Plantillas stateful (`create_totalizer_schema`, `create_nivel_schema`): lógica de negocio expresada como reglas, sin handlers mágicos.
- `ShadowService`: compara `RawReading`/`ProcessedReading` contra `InteractionDetail` legacy.
  - `run_for_output_field()`: descubre variable void por campo de salida.
  - Tolerancias por campo (`total`, `flow`, `nivel`, `water_table`).
- `MqttConsumer`: consume topics MQTT y crea `RawReading`.
- `ProviderRegistry` + `DynamicHttpProvider` + `TdataProvider`: abstracción de proveedores.
- `ComplianceService`: orquesta envíos regulatorios (DGA/SMA) con schedule, retry y voucher.
- `ComplianceScheduleService`: decide si un timestamp califica para envío según `ComplianceStandard`.
- `PointService`: queryset filtrado por permisos, resumen y config de punto.
- `AlertEngine`: evalúa `DeviceEvent` contra `AlertRule` y genera `AlertTrigger`.
- `AlertDispatcher`: envía triggers por canales configurados (email/SMS/webhook/push/in-app).

### 3.4 Tareas Celery

- `void_collect_device_variable`: ingesta una variable.
- `void_collect_frequency`: enqueua ingestas para una frecuencia.
- `void_process_reading`: procesa una `RawReading`.
- `void_shadow_run`: ejecuta comparación shadow.
- `void_shadow_sample`: muestra conservadora de devices para shadow.
- `void_backfill_device`: placeholder para backfill.
- `void_run_sla_checks`: placeholder.
- `void_submit_compliance`: envía una `ComplianceSubmission` pendiente.
- `void_replicate_missing`: replica último dato válido en puntos sin lecturas.
- `void_dispatch_alerts`: envía `AlertTrigger` pendientes por canales configurados.

### 3.5 API

| Endpoint | Método | Descripción |
|---|---|---|
| `/void/auth/login/` | POST | JWT access/refresh |
| `/void/auth/refresh/` | POST | Refresh JWT |
| `/void/auth/me/` | GET | Perfil, rol y puntos accesibles |
| `/void/auth/change-password/` | POST | Cambio de password |
| `/void/users/` | CRUD | Perfiles de usuario void |
| `/void/projects/` | CRUD | Proyectos por cliente |
| `/void/points/` | CRUD | Puntos de captación |
| `/void/points/<id>/summary/` | GET | Resumen del punto + última lectura |
| `/void/points/<id>/config/` | GET | Config del punto + variables |
| `/void/points/<id>/records/` | GET | Lecturas históricas filtradas |
| `/void/points/<id>/shadow/` | POST | Shadow mode para un campo procesado |
| `/void/devices/` | CRUD | Dispositivos |
| `/void/providers/` | CRUD | Proveedores de telemetría |
| `/void/compliance/authorities/` | CRUD | Entidades regulatorias |
| `/void/compliance/standards/` | CRUD | Estándares de envío |
| `/void/compliance/profiles/` | CRUD | Perfiles de cumplimiento por punto |
| `/void/compliance/submit/` | POST | Envío manual staff |
| `/void/compliance/submissions/` | GET | Listado de submissions |
| `/void/compliance/queue/` | GET | Resumen de cola pendiente |
| `/void/alerts/rules/` | CRUD | Reglas de alerta |
| `/void/alerts/triggers/` | GET | Disparos de alerta |
| `/void/alerts/triggers/<id>/dispatch_now/` | POST | Forzar envío de trigger |
| `/void/ingest/` | POST | Ingesta push con token |
| `/void/health/` | GET | Health check |

Autenticación: **JWT (SimpleJWT)** con fallback a TokenAuthentication legacy. Permisos por rol (`admin/operator/client_admin/viewer`) y por punto via `PointPermission`.

## 4. Flujo de datos (happy path)

```
┌─────────────┐     HTTP/MQTT      ┌─────────────┐
│  Proveedor  │ ──────────────────►│  IngestService│
│  externo    │                    │  (void)       │
└─────────────┘                    └──────┬──────┘
                                          │ RawReading
                                          ▼
                                   ┌─────────────┐
                                   │ PipelineService│
                                   │  (esquema)   │
                                   └──────┬──────┘
                                          │ ProcessedReading
                                          ▼
                                   ┌─────────────┐
                                   │  ShadowService│
                                   │  vs legacy    │
                                   └─────────────┘
```

## 5. Gaps críticos detectados

### 5.1 Negocio / CRM / Suscripciones
- ✅ Modelo `Client` existe; `Point.client_fk` y `Point.project_fk` son FKs reales.
- ✅ `Project` modelo real con migración desde campos texto legacy.
- ✅ `Contract`, `Subscription`, `Invoice` existen como esqueleto funcional.
- ❌ No hay flujo de facturación recurrente, renovaciones ni estados de pago.
- ❌ No hay contactos ni relaciones comerciales.

### 5.2 Procesamiento de telemetría
- ✅ Lógica de totalizador y nivel expresada como plantillas stateful (sin handlers mágicos):
  - detección de resets de contadores,
  - monotonicidad,
  - reconexiones,
  - cálculo de caudal con factores,
  - compensación por reset,
  - diff de período y diff diaria,
  - corrección de niveles negativos con histórico,
  - cálculo de nivel freático.
- ✅ Anti-salto masivo: warning sin bloqueo (misma política que legacy).
- ✅ Shadow mode para totales: descubre variable por `output_field` y compara con tolerancia.
- ⚠️ Falta shadow mode con datos reales de proveedor (usa ingest/process).

### 5.3 Compliance / DGA
- ✅ Modelos y servicios creados (`ComplianceAuthority`, `ComplianceStandard`, `PointComplianceProfile`, `ComplianceSubmission`).
- ✅ Retry queue, voucher/tracking_id y cola de errores persistentes.
- ✅ Soporte multi-frecuencia (`ComplianceStandard`) y puntos superficiales (`type_key=SUPERFICIAL`).
- ✅ API REST de authorities/standards/profiles.
- ✅ Pipeline conectado a `ComplianceService` bajo `VOID_AUTOMATION_ENABLED`.
- ❌ Validación en sandbox con datos reales pendiente.

### 5.4 Alertas y notificaciones
- ✅ Motor de alertas basado en `DeviceEvent` + `AlertRule`/`AlertTrigger`.
- ✅ Dispatch async vía Celery.
- ✅ API REST de reglas y triggers.
- ✅ Canal email implementado (usa backend Django configurado).
- ❌ Canales SMS/webhook/push con proveedores reales.
- ❌ Alertas por umbral de variables.

### 5.5 API y autenticación
- ✅ JWT separado para void (`/void/auth/*`).
- ✅ Viewsets DRF para users, projects, points, devices, providers.
- ✅ Permisos por rol y por punto.
- ⚠️ Throttling genérico heredado de REST_FRAMEWORK; no hay throttling específico de void.
- ❌ Documentación OpenAPI específica para `/void/` (schema global incluye solo `/api/`).

### 5.6 Webhooks
- No hay modelo de webhook ni receptor genérico para proveedores push.

### 5.7 Migración de datos históricos
- `void_sync_legacy` migra puntos/devices; no migra `InteractionDetail` histórico.

### 5.8 Monitoreo y observabilidad
- No hay métricas de pipeline, latencia de ingestas, ni health de providers.
- No hay audit trail de cambios de configuración.

### 5.9 Escalabilidad
- El pipeline procesa lecturas una a una; sin sharding por punto ni batch processing.
- No hay dead-letter queue para reintentos.

## 6. Recomendaciones de prioridad

### Fase 1.1 (ya en curso)
1. Validar shadow mode en más providers (TheThings.io, Tago.io).
2. Completar tests de integración para providers HTTP/MQTT.

### Fase 1.2 ✅ (completada)
3. ✅ Modelo `Project` y migración `Point.client_fk`/`project_fk`.
4. ✅ API REST básica (users, projects, points, devices, providers) con JWT y permisos.

### Fase 1.3 ✅ (completada)
5. ✅ Conectar pipeline → `ComplianceService.submit_reading` bajo flag.
6. ✅ API REST de compliance (authorities, standards, profiles).
7. ✅ Alertas: motor basado en `DeviceEvent` + canales configurables.

### Fase 1.4 ✅ (completada)
8. ✅ API REST de alertas (`/void/alerts/rules/`, `/void/alerts/triggers/`).
9. ✅ Acción de dispatch manual de triggers.

### Fase 1.5 ✅ (completada)
10. ✅ Replicar lógica crítica de `controllers/total.py` en `PipelineService`.

### Fase 1.6 ✅ (completada)
11. ✅ Shadow mode para totales: comparar `ProcessedReading.total` vs `InteractionDetail.total`.

### Fase 2 (siguiente)
12. Shadow mode programado periódicamente + alertas ante divergencias.
13. Handler robusto de nivel (`process_nivel_variable`).
14. Caudal promedio/instantáneo legacy.
15. Implementar canales SMS/webhook/push con proveedores reales.
16. Alertas por umbral sobre `ProcessedReading`.

### Fase 3
9. Migración de datos históricos controlada.
10. Dashboards y reporting nativo en void.
11. Evaluación de Kubernetes si el volumen lo justifica.

## 7. Decisiones técnicas pendientes

- ✅ **Auth**: JWT separado para void con fallback a TokenAuthentication legacy.
- **Multi-tenancy**: ¿schema por cliente, row-level security, o simple FK?
- **Pipeline**: ¿declarativo puro (ProcessingSchema) o permitir handlers custom en código?
- **MQTT**: ¿broker propio (Mosquitto/EMQ) o seguir usando brokers de terceros?
- **Historial**: ¿migrar todo InteractionDetail o solo últimos N meses?
