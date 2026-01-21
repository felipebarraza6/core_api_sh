# 🔍 Análisis Crítico: Arquitectura MQTT y Cumplimiento DGA

**Fecha:** 2026-01-20
**Analista:** Sistema de revisión de arquitectura

---

## 🎯 Problemas Identificados

### 1. ❌ Duplicación de Servicios MQTT

**Problema:** Hay TRES sistemas MQTT diferentes que hacen cosas similares:

```
api/core/services/mqtt_service.py          # Servicio legacy del core
api/telemetry/providers/mqtt_handler.py    # Handler dinámico (cliente)
api/telemetry/providers/mqtt_subscriber_service.py  # Subscriber (servidor) ✨ NUEVO
```

**Análisis:**

| Archivo | Propósito | Estado | Recomendación |
|---------|-----------|--------|---------------|
| `mqtt_service.py` | Servicio legacy con infraestructura | 🔄 Activo | ⚠️ Migrar a sistema dinámico |
| `mqtt_handler.py` | Cliente MQTT (conecta a externos) | ✅ Bueno | ✅ Mantener |
| `mqtt_subscriber_service.py` | Servidor MQTT (escucha local) | ✨ Nuevo | ✅ Mantener |

**Solución:** Deprecar `mqtt_service.py` y migrar su funcionalidad al sistema de providers dinámicos.

---

### 2. ❌ DGA No Está Completamente Separado

**Problema Actual:**

```python
# En TelemetryRecord
class TelemetryRecord:
    send_dga = models.BooleanField(default=False)  # ❌ Hardcoded en telemetría
```

**Lo que DEBERÍA ser:**

```python
# Modelo independiente de compliance
class PointComplianceConfig:
    point = FK(CatchmentPoint)
    provider = FK(ComplianceProvider)  # provider.name = 'dga'
    config_data = JSONField()  # Configuración específica DGA
    send_compliance = BooleanField()  # ✅ Dinámico
```

**Tu razón es 100% correcta:**
> "El cumplimiento DGA debería estar aparte donde se relaciona con el punto y proveedor de cumplimiento, y en ese modelo se definen los alcances de cumplimiento."

---

### 3. ⚠️ Configuración Aún No Es 100% Dinámica

**Problemas encontrados:**

#### A. En `catchment_points.py`:
```python
# ❌ Campos DGA hardcoded
dga_estandar = models.CharField(...)  # Debería estar en PointComplianceConfig
dga_data_config = FK(DgaDataConfigCatchment)  # ❌ Modelo específico DGA
```

#### B. En `unified_processing.py`:
```python
# ❌ Lógica DGA hardcoded
def determine_dga_send(point_catchment, chile_tz) -> bool:
    # Esto debería ser dinámico según ComplianceProvider.submission_frequency
```

#### C. En múltiples archivos:
- `api/core/tasks/dga.py` - ❌ Tarea específica DGA
- `api/core/tasks/compliance.py` - ✅ Tarea genérica (buena)
- Hardcoding de "DGA" en 43 archivos

---

## ✅ Lo Que SÍ Está Bien Implementado

### 1. Sistema de Compliance Providers ✅

**Archivo:** `api/telemetry/providers/compliance_models.py`

```python
class ComplianceProvider:  # ✅ Excelente diseño
    name = "dga" | "sma" | "indh"  # Dinámico
    service_type = "water_rights" | "environmental"
    auth_method = "bearer" | "oauth2" | ...
    payload_template = JSONField()  # ✅ Dinámico
    submission_frequency = "hourly" | "daily"

class PointComplianceConfig:  # ✅ Perfecto
    point = FK(CatchmentPoint)
    provider = FK(ComplianceProvider)
    config_data = JSONField()  # ✅ Configuración específica del punto
    send_compliance = BooleanField()  # ✅ Control por punto
```

**Esto es EXACTAMENTE lo que describiste.**

---

### 2. Sistema de Providers Dinámicos ✅

```python
# api/telemetry/providers/
TelemetryProvider → Proveedores de datos (MQTT, API, etc.)
ComplianceProvider → Proveedores de cumplimiento (DGA, SMA, etc.)
```

Separación clara y correcta.

---

## 🔧 Plan de Mejora Propuesto

### Fase 1: Unificar MQTT (1-2 días)

#### Opción A: Merger Completo
```python
# Unificar en un solo MQTTManager
class MQTTManager:
    """
    Manager unificado para MQTT que maneja:
    1. Conexiones salientes (cliente) → mqtt_handler.py
    2. Subscripciones entrantes (servidor) → mqtt_subscriber_service.py
    3. Infraestructura → mqtt_service.py (deprecar)
    """
```

#### Opción B: Deprecación Gradual (RECOMENDADO)
```python
# 1. Marcar mqtt_service.py como LEGACY
# 2. Migrar funcionalidad a mqtt_subscriber_service.py
# 3. Actualizar referencias en infrastructure/models.py
# 4. Eliminar cuando todo esté migrado
```

---

### Fase 2: Separar DGA Completamente (2-3 días)

#### Paso 1: Crear Migración

```python
# Nueva migración
from api.telemetry.providers.compliance_models import ComplianceProvider, PointComplianceConfig

def migrate_dga_to_compliance(apps, schema_editor):
    """
    Migrar configuración DGA existente a sistema de compliance dinámico.
    """
    CatchmentPoint = apps.get_model('telemetry', 'CatchmentPoint')

    # 1. Crear ComplianceProvider para DGA
    dga_provider, _ = ComplianceProvider.objects.get_or_create(
        name='dga',
        defaults={
            'display_name': 'DGA - Dirección General de Aguas',
            'service_type': 'water_rights',
            'base_url': 'https://dga.mop.gob.cl/api',  # Ajustar URL real
            'auth_method': 'oauth2',
            'data_endpoint_template': '/ufs/{uf_id}/procesos/{process_id}/registros',
            'submission_frequency': 'hourly',
            'payload_template': {
                'codigo_obra': '{config.codigo_obra}',
                'caudal': '{record.data.flow}',
                'fecha': '{record.timestamp}'
            },
            'required_fields': [
                {'name': 'codigo_obra', 'type': 'string', 'label': 'Código de Obra'},
                {'name': 'rut_informante', 'type': 'string', 'label': 'RUT Informante'},
            ]
        }
    )

    # 2. Migrar puntos existentes
    for point in CatchmentPoint.objects.filter(dga_data_config__isnull=False):
        # Crear PointComplianceConfig
        config_data = {
            'codigo_obra': point.dga_data_config.codigo_obra,
            'rut_informante': point.dga_data_config.rut_informante,
            # ... otros campos DGA
        }

        PointComplianceConfig.objects.create(
            point=point,
            provider=dga_provider,
            config_data=config_data,
            send_compliance=point.send_dga,  # Migrar flag
            data_source='telemetry'
        )
```

#### Paso 2: Actualizar Modelos

```python
# api/telemetry/models/catchment_points.py

class CatchmentPoint(ModelApi):
    # ❌ DEPRECAR estos campos (mantener temporalmente)
    # dga_estandar = models.CharField(...)  # → PointComplianceConfig.config_data['estandar']
    # dga_data_config = FK(...)  # → PointComplianceConfig
    # send_dga = BooleanField()  # → PointComplianceConfig.send_compliance

    # ✅ Nuevo método helper
    def get_compliance_configs(self, provider_name=None):
        """Obtener configuraciones de cumplimiento del punto."""
        configs = self.compliance_configs.filter(is_active=True)
        if provider_name:
            configs = configs.filter(provider__name=provider_name)
        return configs

    def should_send_compliance(self, provider_name='dga'):
        """Verificar si debe enviar a un proveedor de cumplimiento."""
        config = self.compliance_configs.filter(
            provider__name=provider_name,
            is_active=True,
            send_compliance=True
        ).first()
        return config is not None
```

#### Paso 3: Actualizar Procesamiento

```python
# api/telemetry/ingestion/controllers/unified_processing.py

def save_telemetry_data(point_id, created_register, processed_variables=None):
    """Guardar telemetría y procesar compliance dinámicamente."""

    # Guardar telemetría
    record = TelemetryRecord.objects.create(...)

    # ✅ Procesar compliance dinámicamente (reemplaza determine_dga_send)
    point = CatchmentPoint.objects.get(id=point_id)

    # Obtener todos los proveedores de compliance activos para este punto
    compliance_configs = point.compliance_configs.filter(
        is_active=True,
        send_compliance=True
    ).select_related('provider')

    for config in compliance_configs:
        # Verificar frecuencia de envío
        if should_submit_now(config, record.timestamp):
            # Encolar tarea de envío
            from api.core.tasks.compliance import send_compliance_data
            send_compliance_data.delay(
                record_id=record.id,
                compliance_config_id=config.id
            )

    return record


def should_submit_now(config: PointComplianceConfig, timestamp: datetime) -> bool:
    """
    Determinar si debe enviar ahora según frecuencia del proveedor.
    Reemplaza determine_dga_send() con lógica dinámica.
    """
    frequency = config.provider.submission_frequency

    if frequency == 'on_record':
        return True

    elif frequency == 'hourly':
        # Enviar solo si el minuto es 00
        return timestamp.minute == 0

    elif frequency == 'daily':
        # Enviar solo a medianoche
        return timestamp.hour == 0 and timestamp.minute == 0

    elif frequency == 'weekly':
        # Enviar los lunes a medianoche
        return timestamp.weekday() == 0 and timestamp.hour == 0

    elif frequency == 'monthly':
        # Enviar el día 1 de cada mes
        return timestamp.day == 1 and timestamp.hour == 0

    return False
```

#### Paso 4: Actualizar Tarea de Compliance

```python
# api/core/tasks/compliance.py (UNIFICAR con dga.py)

from celery import shared_task
from api.telemetry.providers.compliance_models import PointComplianceConfig, ComplianceProvider
import requests
import json

@shared_task(bind=True, max_retries=3)
def send_compliance_data(self, record_id: int, compliance_config_id: int):
    """
    Enviar datos de cumplimiento de forma dinámica.
    Reemplaza send_data_to_dga_task con versión genérica.
    """
    try:
        # Cargar configuración y registro
        config = PointComplianceConfig.objects.select_related(
            'provider', 'point'
        ).get(id=compliance_config_id)

        record = TelemetryRecord.objects.get(id=record_id)

        # Construir payload dinámicamente desde template
        payload = build_payload_from_template(
            config.provider.payload_template,
            config=config.config_data,
            record=record
        )

        # Construir URL desde template
        endpoint = build_endpoint_from_template(
            config.provider.data_endpoint_template,
            config=config.config_data
        )

        url = f"{config.provider.base_url}{endpoint}"

        # Obtener credenciales efectivas
        credentials = config.get_effective_credentials()

        # Autenticar según método del proveedor
        headers = get_auth_headers(config.provider, credentials)

        # Enviar request
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=config.provider.timeout_seconds
        )

        response.raise_for_status()

        # Parsear respuesta según mapping
        response_data = response.json()
        voucher = extract_voucher_from_response(
            response_data,
            config.provider.response_mapping
        )

        # Registrar éxito
        config.record_success()

        # Actualizar registro de telemetría
        record.compliance_status[config.provider.name] = {
            'sent': True,
            'voucher': voucher,
            'sent_at': timezone.now().isoformat()
        }
        record.save(update_fields=['compliance_status'])

        logger.info(
            f"Compliance data sent successfully: "
            f"{config.point} → {config.provider.display_name} "
            f"(voucher: {voucher})"
        )

    except Exception as exc:
        # Registrar error
        error_msg = str(exc)
        config.record_error(error_msg)

        # Retry con backoff
        raise self.retry(
            exc=exc,
            countdown=config.provider.retry_delay_seconds * (2 ** self.request.retries)
        )


def build_payload_from_template(template: dict, config: dict, record) -> dict:
    """
    Construir payload desde template con variables.

    Soporta:
    - {config.key} → config_data del punto
    - {record.data.field} → datos del registro
    - {record.timestamp} → timestamp del registro
    """
    import re

    def replace_vars(value):
        if not isinstance(value, str):
            return value

        # Reemplazar {config.*}
        value = re.sub(
            r'\{config\.(\w+)\}',
            lambda m: str(config.get(m.group(1), '')),
            value
        )

        # Reemplazar {record.data.*}
        value = re.sub(
            r'\{record\.data\.(\w+)\}',
            lambda m: str(record.data.get(m.group(1), '')),
            value
        )

        # Reemplazar {record.timestamp}
        value = value.replace(
            '{record.timestamp}',
            record.timestamp.isoformat()
        )

        return value

    # Aplicar recursivamente a todo el template
    return {
        key: replace_vars(value)
        for key, value in template.items()
    }
```

---

### Fase 3: Admin Mejorado (1 día)

```python
# api/telemetry/admin_configuration.py (AGREGAR)

@admin.register(ComplianceProvider)
class ComplianceProviderAdmin(admin.ModelAdmin):
    list_display = [
        'display_name', 'name', 'service_type',
        'submission_frequency', 'is_active'
    ]
    list_filter = ['service_type', 'is_active', 'submission_frequency']
    search_fields = ['name', 'display_name']

    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'display_name', 'description', 'service_type')
        }),
        ('Conexión', {
            'fields': ('base_url', 'auth_endpoint', 'data_endpoint_template', 'timeout_seconds')
        }),
        ('Autenticación', {
            'fields': ('auth_method', 'auth_config'),
            'classes': ('collapse',)
        }),
        ('Payload y Respuesta', {
            'fields': ('payload_template', 'response_mapping'),
            'classes': ('collapse',)
        }),
        ('Configuración Requerida', {
            'fields': ('required_fields', 'data_variables', 'validation_rules'),
            'classes': ('collapse',)
        }),
        ('Frecuencia y Reintentos', {
            'fields': ('submission_frequency', 'max_retries', 'retry_delay_seconds')
        }),
        ('Estado', {
            'fields': ('is_active', 'documentation_url')
        }),
    )


@admin.register(PointComplianceConfig)
class PointComplianceConfigAdmin(admin.ModelAdmin):
    list_display = [
        'point', 'provider', 'data_source',
        'send_compliance', 'is_active', 'success_rate',
        'last_submission', 'error_count'
    ]
    list_filter = [
        'provider', 'data_source', 'send_compliance',
        'is_active', 'point__client'
    ]
    search_fields = ['point__title', 'point__point_code', 'provider__name']

    readonly_fields = [
        'last_submission', 'last_success', 'last_error',
        'error_count', 'total_submissions', 'successful_submissions',
        'success_rate'
    ]

    fieldsets = (
        ('Relaciones', {
            'fields': ('point', 'provider')
        }),
        ('Configuración del Punto', {
            'fields': ('config_data', 'credentials_override'),
            'description': 'Datos específicos para este punto según required_fields del proveedor'
        }),
        ('Origen de Datos', {
            'fields': ('data_source', 'is_active', 'send_compliance')
        }),
        ('Estadísticas', {
            'fields': (
                'last_submission', 'last_success', 'last_error',
                'error_count', 'total_submissions', 'successful_submissions',
                'success_rate'
            ),
            'classes': ('collapse',)
        }),
    )

    def success_rate(self, obj):
        if obj.total_submissions == 0:
            return "N/A"
        rate = (obj.successful_submissions / obj.total_submissions) * 100
        color = 'green' if rate >= 90 else 'orange' if rate >= 70 else 'red'
        return format_html(
            '<span style="color: {}">{:.1f}%</span>',
            color, rate
        )
    success_rate.short_description = 'Tasa de Éxito'


# Agregar inline a CatchmentPointAdmin
class ComplianceConfigInline(admin.TabularInline):
    model = PointComplianceConfig
    extra = 0
    fields = [
        'provider', 'data_source', 'send_compliance',
        'is_active', 'last_success', 'error_count'
    ]
    readonly_fields = ['last_success', 'error_count']
```

---

## 📋 Flujo en Django Admin (MEJORADO)

### Configurar DGA para un Punto (Nuevo Flujo)

#### 1. Crear/Verificar Proveedor DGA (Una Sola Vez)

```
Admin → Compliance Providers → Add ComplianceProvider

Nombre: dga
Nombre para Mostrar: DGA - Dirección General de Aguas
Tipo de Servicio: Derechos de Agua

Conexión:
  Base URL: https://dga.mop.gob.cl/api
  Data Endpoint Template: /ufs/{uf_id}/procesos/{process_id}/registros

Autenticación:
  Método: OAuth2
  Config: {"username": "default_user", "password": "default_pass"}

Payload Template:
{
  "codigo_obra": "{config.codigo_obra}",
  "caudal": "{record.data.flow}",
  "fecha": "{record.timestamp}",
  "rut_informante": "{config.rut_informante}"
}

Campos Requeridos:
[
  {"name": "codigo_obra", "type": "string", "label": "Código de Obra"},
  {"name": "rut_informante", "type": "string", "label": "RUT Informante"},
  {"name": "uf_id", "type": "string", "label": "UF ID"},
  {"name": "process_id", "type": "string", "label": "ID Proceso"}
]

Frecuencia: Cada hora
```

#### 2. Configurar Punto para DGA

```
Admin → Catchment Points → [Tu Punto] → Edit

Scroll to bottom → Compliance Configurations (Inline)

Click "Add another Point Compliance Config"

Proveedor: DGA - Dirección General de Aguas
Origen de Datos: Telemetría Automática

Config Data:
{
  "codigo_obra": "ND-0401-1234",
  "rut_informante": "12345678-9",
  "nombre_informante": "Juan Pérez",
  "caudal_otorgado": 10.5,
  "uf_id": "13",
  "process_id": "ABC123"
}

Credentials Override: (dejar vacío para usar credenciales del proveedor)

☑️ Is Active
☑️ Send Compliance  ← Este es el nuevo "send_dga"

Save
```

#### 3. Agregar SMA (Ejemplo Multi-Compliance)

```
Same Catchment Point → Add another Compliance Config

Proveedor: SMA - Superintendencia del Medio Ambiente
Config Data:
{
  "res_id": "RES-2024-001",
  "empresa_rut": "98765432-1",
  ...
}

☑️ Is Active
☑️ Send Compliance

Save
```

**Ahora el punto envía automáticamente a DGA Y SMA según sus frecuencias configuradas.**

---

## ✅ Ventajas del Nuevo Sistema

| Característica | Antes (Hardcoded) | Después (Dinámico) |
|----------------|-------------------|-------------------|
| **Agregar nuevo proveedor** | Modificar código, migración, deploy | Admin → Add Provider (5 min) |
| **Cambiar frecuencia DGA** | Modificar `determine_dga_send()` | Admin → Edit frequency field |
| **Credenciales por punto** | Imposible | `credentials_override` field |
| **Múltiples compliance** | Solo DGA hardcoded | Todos los que quieras |
| **Testing** | Difícil, requiere BD real | Fácil, mock de provider |
| **Payload personalizado** | Hardcoded en task | `payload_template` dinámico |
| **Logs y estadísticas** | Dispersos | Centralizados en model |

---

## 🎯 Recomendaciones Finales

### Prioridad ALTA (Hacer Ya)

1. **Migrar DGA a ComplianceProvider** (2-3 días)
   - Crear migración de datos
   - Deprecar campos DGA en CatchmentPoint
   - Actualizar `unified_processing.py`

2. **Unificar sistema MQTT** (1-2 días)
   - Deprecar `mqtt_service.py`
   - Documentar cuándo usar cada handler

### Prioridad MEDIA (Próximas 2 semanas)

3. **Mejorar Admin de Compliance** (1 día)
   - Agregar inlines
   - Dashboards de estadísticas
   - Validaciones en el form

4. **Testing exhaustivo** (2 días)
   - Unit tests de `build_payload_from_template`
   - Integration tests de compliance flow
   - Mock de APIs externas

### Prioridad BAJA (Backlog)

5. **Documentación**
   - Guía de creación de nuevos providers
   - Ejemplos de payloads comunes
   - Troubleshooting

---

## 📝 Resumen Ejecutivo

**Tu análisis fue 100% correcto:**

✅ **DGA debe estar separado** → Ya tienes `ComplianceProvider`, solo falta migrar
✅ **Configuración debe ser dinámica** → Ya tienes `config_data` JSONField
✅ **MQTT tiene duplicación** → Necesita unificación

**Siguiente paso recomendado:**
Migrar DGA a `ComplianceProvider` en 2-3 días de trabajo, con ventajas inmediatas:
- Soporte multi-compliance (DGA + SMA + otros)
- Configuración 100% desde Admin
- Código más limpio y mantenible
- Escalable sin modificar código

¿Quieres que genere el código de migración completo?
