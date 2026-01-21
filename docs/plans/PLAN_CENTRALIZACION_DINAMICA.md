# Plan de Centralización: Eliminación de Hardcoding

**Fecha:** 2026-01-21  
**Objetivo:** Centralizar todas las opciones hardcodeadas en modelos dinámicos administrables desde el panel de Django Admin.

---

## 1. Inventario de Elementos Hardcodeados

### 1.1 Resumen por Archivo

| Archivo | Elemento Hardcodeado | Línea | Prioridad |
|:--------|:---------------------|:------|:----------|
| `telemetry.py` | `VARIABLE_TYPES` | 33 | 🔴 Alta |
| `telemetry.py` | `OPERATIONS` x3 | 54, 134, 226 | 🔴 Alta |
| `catchment_points.py` | `FRECUENCY_OPTIONS` | 69 | 🟢 Migrado (SamplingFrequency) |
| `catchment_points.py` | `SUBSCRIPTIONS_CHOICES` | 157 | 🔴 Alta |
| `configuration.py` | `DATA_TYPES` | 98 | 🟡 Media |
| `granular_telemetry.py` | `STREAM_TYPES` | 36 | 🟡 Media |
| `granular_telemetry.py` | `DATA_QUALITY_CHOICES` | 95 | 🟡 Media |
| `compliance_models.py` | `AUTH_METHODS` | 79 | 🟡 Media |
| `compliance_models.py` | `FREQUENCY_CHOICES` | 169 | 🟡 Media |
| `compliance_models.py` | `DATA_SOURCE_CHOICES` | 281 | 🟡 Media |
| `compliance_models.py` | `STATUS_CHOICES` | 428 | 🟢 Baja (estados fijos) |
| `compliance_standard.py` | `FREQUENCY_CHOICES` | 22 | 🟡 Media |
| `models.py` (providers) | `AUTH_METHODS` | 65 | 🟡 Media (duplicado) |

---

## 2. Modelos Dinámicos Propuestos

### 2.1 Catálogo Central de Opciones

Crear un modelo genérico para manejar todas las opciones que no requieren lógica adicional:

```python
# api/core/models/catalog.py

class OptionCatalog(ModelApi):
    """
    Catálogo centralizado de opciones dinámicas.
    Reemplaza todos los CHOICES hardcodeados.
    """
    
    CATALOG_TYPES = [
        ("SUBSCRIPTION_TYPE", "Tipo de Suscripción"),
        ("DATA_QUALITY", "Calidad de Datos"),
        ("STREAM_TYPE", "Tipo de Stream"),
        ("DATA_TYPE", "Tipo de Dato"),
        ("AUTH_METHOD", "Método de Autenticación"),
        ("COMPLIANCE_FREQUENCY", "Frecuencia de Cumplimiento"),
        ("DATA_SOURCE", "Fuente de Datos"),
    ]
    
    catalog_type = models.CharField(
        max_length=50,
        choices=CATALOG_TYPES,
        verbose_name="Tipo de Catálogo"
    )
    code = models.CharField(
        max_length=50,
        verbose_name="Código",
        help_text="Identificador único dentro del catálogo"
    )
    name = models.CharField(
        max_length=200,
        verbose_name="Nombre para Mostrar"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Descripción"
    )
    
    # Configuración adicional
    extra_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Configuración Extra"
    )
    
    order = models.IntegerField(default=0, verbose_name="Orden")
    is_active = models.BooleanField(default=True, verbose_name="Activo")
    
    class Meta:
        unique_together = ('catalog_type', 'code')
        ordering = ['catalog_type', 'order', 'name']
        verbose_name = "Opción de Catálogo"
        verbose_name_plural = "Opciones de Catálogo"
    
    def __str__(self):
        return f"[{self.catalog_type}] {self.name}"
```

---

### 2.2 Modelos Específicos con Lógica

Para opciones que requieren campos adicionales o lógica especial, crear modelos dedicados:

#### 2.2.1 OperationType (Reemplaza OPERATIONS)

```python
# api/telemetry/models/constants_dynamic.py

class OperationType(ModelApi):
    """
    Tipos de operaciones para variables.
    Reemplaza OPERATIONS hardcodeado en SchemeVariable, VirtualVariable, CoreVariable.
    """
    
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Código",
        help_text="PHYSICAL, SUM, DIFF, MUL, AVG, FORMULA"
    )
    name = models.CharField(
        max_length=200,
        verbose_name="Nombre"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Descripción"
    )
    
    # Indica si requiere fórmula
    requires_formula = models.BooleanField(
        default=False,
        verbose_name="Requiere Fórmula"
    )
    
    # Indica si requiere sources
    requires_sources = models.BooleanField(
        default=False,
        verbose_name="Requiere Variables de Origen"
    )
    
    # Número mínimo de sources
    min_sources = models.IntegerField(
        default=0,
        verbose_name="Mínimo de Orígenes"
    )
    
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Tipo de Operación"
        verbose_name_plural = "Tipos de Operación"
    
    def __str__(self):
        return f"{self.name} ({self.code})"
```

#### 2.2.2 SubscriptionPlan (Reemplaza SUBSCRIPTIONS_CHOICES)

```python
class SubscriptionPlan(ModelApi):
    """
    Planes de suscripción para módulos.
    Reemplaza SUBSCRIPTIONS_CHOICES en ProfileIkoluCatchment.
    """
    
    code = models.CharField(max_length=50, unique=True, verbose_name="Código")
    name = models.CharField(max_length=200, verbose_name="Nombre")
    
    duration_months = models.IntegerField(
        verbose_name="Duración (meses)",
        help_text="1=Mensual, 3=Trimestral, 6=Semestral, 12=Anual"
    )
    
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Precio Base"
    )
    
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Plan de Suscripción"
        verbose_name_plural = "Planes de Suscripción"
        ordering = ['duration_months']
    
    def __str__(self):
        return self.name
```

#### 2.2.3 IkoluModule (Reemplaza m1-m7 hardcodeados)

```python
class IkoluModule(ModelApi):
    """
    Módulos disponibles en la plataforma.
    Reemplaza los campos m1-m7 hardcodeados en ProfileIkoluCatchment.
    """
    
    code = models.CharField(max_length=50, unique=True, verbose_name="Código")
    name = models.CharField(max_length=200, verbose_name="Nombre")
    description = models.TextField(blank=True)
    
    # Icono para UI
    icon = models.CharField(max_length=50, blank=True, verbose_name="Icono")
    
    # Precio mensual base
    base_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Precio Mensual Base"
    )
    
    # Indica si es un módulo core (siempre activo)
    is_core = models.BooleanField(
        default=False,
        verbose_name="Módulo Core",
        help_text="Los módulos core están siempre activos"
    )
    
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Módulo Ikolu"
        verbose_name_plural = "Módulos Ikolu"
        ordering = ['order']
    
    def __str__(self):
        return self.name


class PointModuleSubscription(ModelApi):
    """
    Suscripción de un punto a un módulo.
    Reemplaza los campos m1-m7 + fechas en ProfileIkoluCatchment.
    """
    
    point = models.ForeignKey(
        'telemetry.CatchmentPoint',
        on_delete=models.CASCADE,
        related_name='module_subscriptions'
    )
    module = models.ForeignKey(
        IkoluModule,
        on_delete=models.CASCADE,
        related_name='subscriptions'
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subscriptions'
    )
    
    start_date = models.DateField(verbose_name="Fecha Inicio")
    end_date = models.DateField(null=True, blank=True, verbose_name="Fecha Fin")
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Suscripción a Módulo"
        verbose_name_plural = "Suscripciones a Módulos"
        unique_together = ('point', 'module')
    
    def __str__(self):
        return f"{self.point.title} - {self.module.name}"
```

---

## 3. Plan de Migración

### Fase 1: Modelos Base (Semana 1)

| Paso | Acción | Impacto |
|:-----|:-------|:--------|
| 1.1 | Crear `OptionCatalog` en `api/core/models/` | Bajo |
| 1.2 | Crear `OperationType` en `api/telemetry/models/` | Bajo |
| 1.3 | Crear `SubscriptionPlan` | Bajo |
| 1.4 | Crear `IkoluModule` y `PointModuleSubscription` | Bajo |
| 1.5 | Registrar todos en Admin | Bajo |
| 1.6 | Crear fixtures con datos iniciales | Bajo |

### Fase 2: Migración de OPERATIONS (Semana 2)

| Paso | Acción | Impacto |
|:-----|:-------|:--------|
| 2.1 | Agregar `operation_type = FK(OperationType)` a `SchemeVariable` | Medio |
| 2.2 | Agregar `operation_type = FK(OperationType)` a `VirtualVariable` | Medio |
| 2.3 | Agregar `operation_type = FK(OperationType)` a `CoreVariable` | Medio |
| 2.4 | Script de migración de datos | Medio |
| 2.5 | Marcar `operation` (CharField) como `[DEP]` | Bajo |

### Fase 3: Migración de Tipos de Variable (Semana 3)

| Paso | Acción | Impacto |
|:-----|:-------|:--------|
| 3.1 | Ya existe `VariableType` - verificar uso | Bajo |
| 3.2 | Agregar `type_definition = FK(VariableType)` donde falte | Medio |
| 3.3 | Migrar datos de `type_variable` (CharField) | Medio |
| 3.4 | Marcar `VARIABLE_TYPES` como `[DEP]` | Bajo |

### Fase 4: Migración de Módulos Ikolu (Semana 4)

| Paso | Acción | Impacto |
|:-----|:-------|:--------|
| 4.1 | Crear registros en `IkoluModule` (m1-m7) | Bajo |
| 4.2 | Script para migrar datos de `ProfileIkoluCatchment` a `PointModuleSubscription` | Alto |
| 4.3 | Actualizar vistas y serializers | Alto |
| 4.4 | Marcar `ProfileIkoluCatchment` como `[DEP]` | Medio |

### Fase 5: Migración de Opciones Restantes (Semana 5)

| Paso | Acción | Impacto |
|:-----|:-------|:--------|
| 5.1 | Poblar `OptionCatalog` con todas las opciones | Bajo |
| 5.2 | Crear helpers para obtener opciones: `get_catalog_choices('DATA_QUALITY')` | Bajo |
| 5.3 | Migrar campos uno por uno usando FK a `OptionCatalog` | Medio |

---

## 4. Fixtures Iniciales

### 4.1 operation_types.json

```json
[
    {"code": "PHYSICAL", "name": "Dato Físico (Sensor)", "requires_formula": false, "requires_sources": false},
    {"code": "SUM", "name": "Suma", "requires_formula": false, "requires_sources": true, "min_sources": 2},
    {"code": "DIFF", "name": "Resta (A - B)", "requires_formula": false, "requires_sources": true, "min_sources": 2},
    {"code": "MUL", "name": "Multiplicación", "requires_formula": false, "requires_sources": true, "min_sources": 2},
    {"code": "AVG", "name": "Promedio", "requires_formula": false, "requires_sources": true, "min_sources": 2},
    {"code": "FORMULA", "name": "Fórmula Personalizada", "requires_formula": true, "requires_sources": false}
]
```

### 4.2 variable_types.json

```json
[
    {"code": "TOTALIZADO", "name": "Totalizado (Pulsos)", "default_unit": "m3"},
    {"code": "NIVEL", "name": "Nivel Freático", "default_unit": "mt"},
    {"code": "CAUDAL", "name": "Caudal Instantáneo", "default_unit": "L/s"},
    {"code": "CAUDAL_PROMEDIO", "name": "Caudal Promedio", "default_unit": "L/s"},
    {"code": "GENERIC", "name": "Genérico / Directo", "default_unit": ""}
]
```

### 4.3 ikolu_modules.json

```json
[
    {"code": "m1", "name": "Mi Pozo", "is_core": true, "order": 1},
    {"code": "m2", "name": "DGA", "is_core": false, "order": 2},
    {"code": "m3", "name": "Datos y Reportes", "is_core": false, "order": 3},
    {"code": "m4", "name": "Gráficos", "is_core": false, "order": 4},
    {"code": "m5", "name": "Indicadores", "is_core": false, "order": 5},
    {"code": "m6", "name": "Alarmas", "is_core": false, "order": 6},
    {"code": "m7", "name": "Documentos", "is_core": false, "order": 7}
]
```

### 4.4 subscription_plans.json

```json
[
    {"code": "MENSUAL", "name": "Mensual", "duration_months": 1},
    {"code": "TRIMESTRAL", "name": "Trimestral", "duration_months": 3},
    {"code": "SEMESTRAL", "name": "Semestral", "duration_months": 6},
    {"code": "ANUAL", "name": "Anual", "duration_months": 12}
]
```

---

## 5. Helpers Centralizados

```python
# api/core/utils/catalog.py

from django.core.cache import cache
from api.core.models.catalog import OptionCatalog


def get_catalog_choices(catalog_type: str, include_inactive: bool = False) -> list:
    """
    Obtiene las opciones de un catálogo como lista de tuplas para usar en CharField.choices.
    
    Uso:
        status = models.CharField(choices=get_catalog_choices('DATA_QUALITY'))
    """
    cache_key = f"catalog_choices_{catalog_type}_{include_inactive}"
    choices = cache.get(cache_key)
    
    if choices is None:
        qs = OptionCatalog.objects.filter(catalog_type=catalog_type)
        if not include_inactive:
            qs = qs.filter(is_active=True)
        
        choices = list(qs.order_by('order', 'name').values_list('code', 'name'))
        cache.set(cache_key, choices, timeout=300)  # 5 min cache
    
    return choices


def get_catalog_option(catalog_type: str, code: str) -> OptionCatalog:
    """
    Obtiene una opción específica del catálogo.
    """
    return OptionCatalog.objects.get(catalog_type=catalog_type, code=code)


def invalidate_catalog_cache(catalog_type: str = None):
    """
    Invalida el cache del catálogo cuando se modifican opciones.
    Llamar desde OptionCatalogAdmin.save_model().
    """
    if catalog_type:
        cache.delete_many([
            f"catalog_choices_{catalog_type}_True",
            f"catalog_choices_{catalog_type}_False",
        ])
    else:
        # Invalidar todos los catálogos
        for ct, _ in OptionCatalog.CATALOG_TYPES:
            invalidate_catalog_cache(ct)
```

---

## 6. Diagrama de Arquitectura Final

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           CATÁLOGOS CENTRALES                                 │
│                                                                               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐               │
│  │  VariableType   │  │  OperationType  │  │ OptionCatalog   │               │
│  │  (dinámico ✅)  │  │  (nuevo)        │  │ (genérico)      │               │
│  │                 │  │                 │  │                 │               │
│  │ • TOTALIZADO    │  │ • PHYSICAL      │  │ • DATA_QUALITY  │               │
│  │ • NIVEL         │  │ • SUM           │  │ • STREAM_TYPE   │               │
│  │ • CAUDAL        │  │ • DIFF          │  │ • AUTH_METHOD   │               │
│  │ • GENERIC       │  │ • FORMULA       │  │ • ...           │               │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘               │
│                                                                               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐               │
│  │  IkoluModule    │  │SubscriptionPlan │  │ SamplingFreq    │               │
│  │  (nuevo)        │  │ (nuevo)         │  │ (dinámico ✅)   │               │
│  │                 │  │                 │  │                 │               │
│  │ • Mi Pozo       │  │ • MENSUAL       │  │ • 1 minuto      │               │
│  │ • DGA           │  │ • TRIMESTRAL    │  │ • 5 minutos     │               │
│  │ • Reportes      │  │ • SEMESTRAL     │  │ • 60 minutos    │               │
│  │ • Gráficos      │  │ • ANUAL         │  │                 │               │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘               │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                           MODELOS DE NEGOCIO                                  │
│                                                                               │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │                         CatchmentPoint                                 │   │
│  │                                                                        │   │
│  │  FK → SamplingFrequency ✅ (ya migrado)                                │   │
│  │  FK → ConfigurationScheme ✅                                           │   │
│  │  FK → TelemetryScheme ✅                                               │   │
│  │                                                                        │   │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐     │   │
│  │  │   CoreVariable   │  │   TelemetryRecord│  │PointModuleSubs   │     │   │
│  │  │                  │  │                  │  │ (NUEVO)          │     │   │
│  │  │ FK→VariableType ✅│  │ data: JSON ✅    │  │                  │     │   │
│  │  │ FK→OperationType │  │                  │  │ FK→IkoluModule   │     │   │
│  │  │ (NUEVO)          │  │                  │  │ FK→SubsPlan      │     │   │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────┘     │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Beneficios de la Centralización

| Aspecto | Antes (Hardcodeado) | Después (Dinámico) |
|:--------|:--------------------|:-------------------|
| **Agregar opción** | Editar código + migración + deploy | Admin panel |
| **Desactivar opción** | Editar código + migración + deploy | Admin panel |
| **Traducción** | Hardcodeado en código | Campo `name` editable |
| **Configuración extra** | Nuevo campo en modelo | `extra_config` JSON |
| **Auditoría** | No hay | `created`, `modified` de ModelApi |
| **Permisos** | Ninguno | Django permissions |

---

## 8. Checklist de Implementación

### Fase 1: Modelos Base
- [ ] Crear `api/core/models/catalog.py`
- [ ] Crear `api/telemetry/models/constants_dynamic.py`
- [ ] Registrar modelos en Admin
- [ ] Crear fixtures JSON
- [ ] Cargar fixtures iniciales
- [ ] Ejecutar migraciones

### Fase 2: OPERATIONS
- [ ] Agregar FK `operation_type` a SchemeVariable
- [ ] Agregar FK `operation_type` a VirtualVariable
- [ ] Agregar FK `operation_type` a CoreVariable
- [ ] Script de migración de datos
- [ ] Actualizar Admin forms
- [ ] Marcar `operation` (CharField) como deprecated

### Fase 3: VARIABLE_TYPES
- [ ] Verificar uso de VariableType existente
- [ ] Migrar SchemeVariable.type_variable a FK
- [ ] Script de migración de datos
- [ ] Marcar VARIABLE_TYPES como deprecated

### Fase 4: IKOLU MODULES
- [ ] Crear IkoluModule y PointModuleSubscription
- [ ] Script para migrar ProfileIkoluCatchment
- [ ] Actualizar API/serializers
- [ ] Actualizar frontend (si aplica)
- [ ] Marcar ProfileIkoluCatchment como deprecated

### Fase 5: OPTIONS RESTANTES
- [ ] Poblar OptionCatalog
- [ ] Crear helpers get_catalog_choices()
- [ ] Migrar DATA_QUALITY_CHOICES
- [ ] Migrar STREAM_TYPES
- [ ] Migrar AUTH_METHODS
- [ ] Migrar FREQUENCY_CHOICES

---

## 9. Estimación de Esfuerzo

| Fase | Duración | Riesgo | Dependencias |
|:-----|:---------|:-------|:-------------|
| Fase 1 | 2-3 días | Bajo | Ninguna |
| Fase 2 | 3-4 días | Medio | Fase 1 |
| Fase 3 | 2-3 días | Bajo | Fase 1 |
| Fase 4 | 4-5 días | Alto | Fases 1-3, Frontend |
| Fase 5 | 3-4 días | Bajo | Fase 1 |

**Total estimado:** 2-3 semanas
