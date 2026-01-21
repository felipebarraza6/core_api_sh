# Propuesta de Reorganización Arquitectónica

**Fecha:** 2026-01-21  
**Estado:** Propuesta para discusión

---

## 1. Situación Actual

```
api/
├── core/           # Usuarios, permisos, utilidades
├── crm/            # Clientes, proyectos, tareas, costos, levantamientos
├── telemetry/      # TODO MEZCLADO:
│   ├── Puntos de captación
│   ├── Variables y registros
│   ├── Proveedores de datos
│   ├── Cumplimiento (DGA, SMA)
│   ├── MQTT
│   └── Perfiles Ikolu (⚠️ lógica de negocio/suscripciones)
├── documents/      # Gestión de archivos
├── infrastructure/ # Dispositivos
├── notifications/  # Alertas
├── reports/        # Reportes
├── support/        # Soporte técnico
└── chatbot/        # IA
```

### Problemas Identificados:

1. **`telemetry/`** tiene demasiadas responsabilidades mezcladas
2. **ProfileIkoluCatchment** es lógica de negocio/suscripciones, no telemetría
3. **Cumplimiento** (DGA/SMA) tiene su propia complejidad y podría crecer
4. **Proveedores** tienen modelos en `telemetry/providers/` que son casi una app

---

## 2. Propuesta de Reorganización

### Arquitectura Propuesta

```
api/
├── core/               # Usuarios, permisos, catálogos centrales
│
├── crm/                # Gestión comercial del cliente
│   ├── clients/        # Clientes
│   ├── projects/       # Proyectos
│   ├── tasks/          # Tareas CRM
│   ├── costs/          # Costos
│   └── surveys/        # Levantamientos técnicos
│
├── subscriptions/      # 🆕 APP: Planes y suscripciones
│   ├── plans/          # SubscriptionPlan
│   ├── modules/        # IkoluModule (catálogo)
│   └── point_access/   # PointModuleSubscription
│
├── telemetry/          # SOLO datos operacionales
│   ├── points/         # CatchmentPoint (sin ProfileIkolu)
│   ├── variables/      # CoreVariable, VariableType
│   ├── records/        # TelemetryRecord
│   ├── schemes/        # TelemetryScheme, ConfigurationScheme
│   └── ingestion/      # Parsers, handlers de datos
│
├── providers/          # 🆕 APP: Proveedores de telemetría
│   ├── api/            # TelemetryProvider, CatchmentPointProvider
│   ├── mqtt/           # MQTTProviderConfig, PayloadParsingRule
│   └── manager/        # Lógica de conexión y failover
│
├── compliance/         # 🆕 APP: Cumplimiento normativo
│   ├── providers/      # ComplianceProvider (DGA, SMA, INDH)
│   ├── config/         # PointComplianceConfig
│   ├── records/        # ManualComplianceRecord
│   ├── standards/      # ComplianceStandard
│   └── submission/     # Lógica de envío
│
├── documents/          # Gestión de archivos
├── infrastructure/     # Dispositivos IoT
├── notifications/      # Alertas y notificaciones
├── reports/            # Generación de reportes
├── support/            # Soporte técnico
└── chatbot/            # Asistente IA
```

---

## 3. Responsabilidades por App

### 3.1 `crm/` - Gestión Comercial

| Responsabilidad | Modelos |
|:----------------|:--------|
| Clientes y prospectos | `Client`, `JobPosition` |
| Proyectos (ciclo de vida) | `Project` |
| Contactos | `Person` |
| Tareas comerciales/técnicas | `CrmTask`, `TaskResponse`, `TaskCategory`, `TaskType` |
| Costos y presupuestos | `ProjectCost`, `CostCategory`, `CostType` |
| Levantamientos técnicos | `TechnicalSurvey`, `SurveyFieldDefinition` |

**NO incluye:** Puntos de captación, telemetría, suscripciones

---

### 3.2 `subscriptions/` - Gestión de Acceso (🆕)

| Responsabilidad | Modelos |
|:----------------|:--------|
| Catálogo de módulos | `IkoluModule` |
| Planes de pago | `SubscriptionPlan` |
| Acceso por punto | `PointModuleSubscription` |
| Permisos de API/Frontend | Integración con `core.permissions` |

**Beneficios:**
- Endpoints específicos para el frontend Ikolu
- Permisos granulares por módulo
- Facturación y métricas de uso
- Separación clara de lógica comercial vs operacional

```python
# subscriptions/models.py

class IkoluModule(ModelApi):
    """Módulos disponibles en la plataforma Ikolu."""
    code = models.CharField(max_length=50, unique=True)  # 'mi_pozo', 'dga', etc.
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Configuración de acceso
    api_permission_codename = models.CharField(max_length=100, blank=True)
    frontend_route = models.CharField(max_length=200, blank=True)
    
    # Precio
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_core = models.BooleanField(default=False)
    
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)


class SubscriptionPlan(ModelApi):
    """Planes de suscripción."""
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    duration_months = models.IntegerField()
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)


class PointModuleAccess(ModelApi):
    """Acceso de un punto a un módulo."""
    point = models.ForeignKey('telemetry.CatchmentPoint', on_delete=models.CASCADE)
    module = models.ForeignKey(IkoluModule, on_delete=models.CASCADE)
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True)
    
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ('point', 'module')
```

---

### 3.3 `telemetry/` - Datos Operacionales (Limpia)

| Responsabilidad | Modelos |
|:----------------|:--------|
| Puntos de captación | `CatchmentPoint` (sin ProfileIkolu) |
| Configuración técnica | `ProfileDataConfigCatchment`, `ConfigurationScheme` |
| Variables | `CoreVariable`, `VariableType`, `OperationType` |
| Registros de datos | `TelemetryRecord`, `DataPoint` |
| Esquemas de procesamiento | `TelemetryScheme`, `SchemeVariable` |
| Frecuencias | `SamplingFrequency` |

**NO incluye:** Proveedores externos, cumplimiento, suscripciones

---

### 3.4 `providers/` - Proveedores de Telemetría (🆕)

| Responsabilidad | Modelos |
|:----------------|:--------|
| Proveedores API | `TelemetryProvider` |
| Configuración por punto | `CatchmentPointProvider` |
| MQTT | `MQTTProviderConfig`, `PayloadParsingRule`, `CatchmentPointMQTT` |
| Lógica de conexión | `ProviderManager`, handlers |

**Beneficios:**
- Aislamiento de integraciones externas
- Fácil agregar nuevos proveedores
- Testing independiente
- Configuración de failover centralizada

---

### 3.5 `compliance/` - Cumplimiento Normativo (🆕)

| Responsabilidad | Modelos |
|:----------------|:--------|
| Proveedores regulatorios | `ComplianceProvider` |
| Estándares | `ComplianceStandard` |
| Configuración por punto | `PointComplianceConfig` |
| Registros manuales | `ManualComplianceRecord` |
| Lógica de envío | Celery tasks, handlers |

**Beneficios:**
- Cumplimiento DGA es complejo y tiene reglas propias
- Fácil agregar SMA, INDH, otros reguladores
- Auditoría separada
- Endpoints específicos para reportes regulatorios

---

## 4. Diagrama de Dependencias

```
                              ┌─────────────┐
                              │    core     │
                              │  (base)     │
                              └──────┬──────┘
                                     │
           ┌─────────────────────────┼─────────────────────────┐
           │                         │                         │
           ▼                         ▼                         ▼
    ┌─────────────┐           ┌─────────────┐           ┌─────────────┐
    │     crm     │           │  documents  │           │notifications│
    │             │           │             │           │             │
    └──────┬──────┘           └─────────────┘           └─────────────┘
           │
           │ TechnicalSurvey
           ▼
    ┌─────────────┐
    │  telemetry  │◄──────────────────────────────────────────────┐
    │  (datos)    │                                                │
    └──────┬──────┘                                                │
           │                                                       │
           │ CatchmentPoint                                        │
           ├───────────────────────┬───────────────────────────────┤
           │                       │                               │
           ▼                       ▼                               ▼
    ┌─────────────┐         ┌─────────────┐                 ┌─────────────┐
    │ providers   │         │ compliance  │                 │subscriptions│
    │ (ingestion) │         │ (DGA/SMA)   │                 │ (acceso)    │
    └─────────────┘         └─────────────┘                 └─────────────┘
```

---

## 5. Plan de Migración

### Fase 1: Crear Apps Nuevas (Sin migrar datos)

```bash
# Crear estructura de apps
python manage.py startapp subscriptions
python manage.py startapp providers
python manage.py startapp compliance
```

```python
# api/settings.py
INSTALLED_APPS = [
    ...
    'api.subscriptions',
    'api.providers', 
    'api.compliance',
]
```

### Fase 2: Mover Modelos Gradualmente

| Modelo | De | A | Prioridad |
|:-------|:---|:--|:----------|
| `ProfileIkoluCatchment` | telemetry | subscriptions (refactor a nuevos modelos) | Alta |
| `TelemetryProvider` | telemetry/providers | providers | Media |
| `CatchmentPointProvider` | telemetry/providers | providers | Media |
| `MQTTProviderConfig` | telemetry/providers | providers | Media |
| `ComplianceProvider` | telemetry/providers | compliance | Media |
| `PointComplianceConfig` | telemetry/providers | compliance | Media |
| `ComplianceStandard` | telemetry/providers | compliance | Media |

### Fase 3: Actualizar Imports y Relaciones

```python
# Usar strings para evitar circular imports
point = models.ForeignKey('telemetry.CatchmentPoint', ...)

# O crear proxy models si es necesario
```

### Fase 4: Crear URLs y Permisos

```python
# api/urls.py
urlpatterns = [
    path('crm/', include('api.crm.urls')),
    path('telemetry/', include('api.telemetry.urls')),
    path('subscriptions/', include('api.subscriptions.urls')),  # 🆕
    path('providers/', include('api.providers.urls')),          # 🆕
    path('compliance/', include('api.compliance.urls')),        # 🆕
]
```

---

## 6. Resumen de Decisión

### Recomendación Final

| Concepto | App | Justificación |
|:---------|:----|:--------------|
| **Ikolu Modules** | `subscriptions` | Lógica de negocio/acceso, no telemetría |
| **Planes** | `subscriptions` | Comercial, no operacional |
| **Permisos frontend** | `subscriptions` + `core` | Integración con sistema de permisos |
| **Telemetría** | `telemetry` (limpia) | Solo datos operacionales |
| **DGA/SMA** | `compliance` | Complejidad propia, auditoría separada |
| **Proveedores** | `providers` | Integraciones externas aisladas |

### Beneficios Clave

1. **Separación de Responsabilidades** - Cada app hace UNA cosa bien
2. **Testing Aislado** - Puedes testear compliance sin telemetría
3. **Escalabilidad** - Nuevos reguladores en `compliance`, nuevos módulos en `subscriptions`
4. **Permisos Granulares** - Endpoints específicos por app
5. **Mantenibilidad** - Cambios en DGA no afectan telemetría

---

## 7. Próximos Pasos

1. **¿Confirmas esta arquitectura?**
2. Si sí, creo las apps nuevas con estructura básica
3. Migración gradual de modelos (sin romper producción)
4. Actualizar imports y tests
