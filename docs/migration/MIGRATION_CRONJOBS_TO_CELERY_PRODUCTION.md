# 🚨 MIGRACIÓN CRÍTICA: Cronjobs → Celery (PRODUCCIÓN)

## 📊 ANÁLISIS DE LA SITUACIÓN ACTUAL

### ❌ **PROBLEMA CRÍTICO IDENTIFICADO**

**En producción están corriendo DOS sistemas simultáneamente:**

1. **CRONJOBS tradicionales** (activos en `settings.py`)
2. **Celery** (configurado pero archivos no deployados)

Esto causa:
- 🔄 **Procesamiento duplicado** de telemetría
- 💾 **Uso excesivo de recursos**
- 🔀 **Confusión en logs y monitoreo**
- 💥 **Posibles conflictos de datos**

### 📋 **ARCHIVOS EN PRODUCCIÓN vs LOCAL**

**En Producción (GitHub):**
```bash
❌ CRONJOBS activos en settings.py
❌ Sistema de InteractionDetail básico
❌ Sin MQTT integrado
❌ Sin constantes históricas
❌ Django Admin limitado
```

**En Local (Mis cambios):**
```bash
✅ Sistema Celery completo
✅ DataPoint con raw_values
✅ MQTT Broker integrado
✅ Constantes históricas
✅ Django Admin mejorado
❌ NO DEPLOYADO A PRODUCCIÓN
```

---

## 🎯 **PLAN DE MIGRACIÓN A PRODUCCIÓN**

### **FASE 1: ANÁLISIS Y PREPARACIÓN (Esta semana)**

#### **Día 1: Verificar estado actual**
```bash
# Ver qué está corriendo actualmente
ps aux | grep -E "(celery|cron)"

# Ver logs de cronjobs
tail -f /tmp/smarthydro/*.log

# Ver si hay procesamiento duplicado
grep "telemetry" /tmp/smarthydro/*.log | tail -20
```

#### **Día 2: Backup completo**
```bash
# Backup de base de datos
python manage.py dumpdata > backup_production_pre_migration.json

# Backup de configuración
cp settings.py settings_production_backup.py
```

#### **Día 3: Análisis de impacto**
```python
# Verificar procesamiento actual
from api.core.models import InteractionDetail
import datetime

# Datos procesados en las últimas 24h
recent_data = InteractionDetail.objects.filter(
    date_time_medition__gte=timezone.now() - timedelta(days=1)
).count()

print(f"Datos procesados en 24h: {recent_data}")
```

### **FASE 2: DEPLOY GRADUAL (Semana siguiente)**

#### **Paso 1: Deploy archivos base (sin activar)**
```bash
# Commitear y pushear cambios
git add .
git commit -m "feat: Sistema Celery completo para reemplazar cronjobs"
git push origin main

# Deploy a staging primero
# Verificar que no se caiga nada
```

#### **Paso 2: Migraciones de datos**
```bash
# Crear las nuevas tablas sin afectar las existentes
python manage.py makemigrations core
python manage.py migrate --dry-run
python manage.py migrate

# Migrar datos existentes (si aplica)
python manage.py migrate_data_to_new_models
```

#### **Paso 3: Configurar Celery (sin activar cronjobs)**
```bash
# Instalar dependencias
pip install celery[redis] django-celery-beat flower psutil

# Verificar configuración
python -c "from api.celery_app import app; print('Celery OK')"

# Crear usuario para Celery Beat
python manage.py createsuperuser --username=celery_admin
```

#### **Paso 4: Test en paralelo**
```bash
# Correr Celery en background sin afectar cronjobs
celery -A api worker --loglevel=info --concurrency=1 --hostname=celery_test

# Monitorear que no haya conflictos
tail -f /tmp/smarthydro/*.log
```

### **FASE 3: ACTIVACIÓN CONTROLADA (Semana siguiente)**

#### **Día 1: Desactivar cronjobs gradualmente**
```python
# settings.py - Comentar cronjobs uno por uno
CRONJOBS = [
    # Comentar primero los menos críticos
    # ("0 * * * *", "api.cronjobs.telemetry.twin.run", ">> /tmp/smarthydro/twin_60.log 2>&1"),
    # ...

    # Mantener solo los críticos inicialmente
    ("*/3 * * * *", "api.cronjobs.dga.cron_dga.run", ">> /tmp/smarthydro/dga.log 2>&1"),
]
```

#### **Día 2: Activar Celery Beat**
```bash
# Iniciar Celery Beat
celery -A api beat --loglevel=info --scheduler=django_celery_beat.schedulers:DatabaseScheduler

# Verificar que se creen las tareas programadas
python manage.py shell -c "
from django_celery_beat.models import PeriodicTask
print('Tasks programadas:', PeriodicTask.objects.count())
"
```

#### **Día 3: Monitoreo intensivo**
```bash
# Flower dashboard
celery -A api flower

# Monitoreo de ambos sistemas
watch -n 30 'ps aux | grep -E "(celery|cron)"'

# Verificar procesamiento
python manage.py shell -c "
from api.core.models import InteractionDetail
import datetime
recent = InteractionDetail.objects.filter(
    date_time_medition__gte=timezone.now() - timedelta(minutes=30)
).count()
print(f'Procesamiento últimos 30min: {recent}')
"
```

#### **Día 4: Desactivar cronjobs restantes**
```python
# settings.py - Comentar TODOS los cronjobs
CRONJOBS = [
    # Todos comentados - Celery toma control
]

# Reiniciar Django
sudo systemctl restart gunicorn
```

### **FASE 4: OPTIMIZACIÓN Y LIMPIEZA (Semana final)**

#### **Paso 1: Limpiar código obsoleto**
```bash
# Eliminar directorio cronjobs (backup primero)
cp -r api/cronjobs api/cronjobs_backup_$(date +%Y%m%d)
rm -rf api/cronjobs

# Limpiar settings.py
# Remover CRONJOBS completamente
# Limpiar imports no usados
```

#### **Paso 2: Optimizar performance**
```bash
# Ejecutar optimizaciones
python manage.py optimize_database
python manage.py clear_cache

# Verificar índices
python manage.py shell -c "
from django.db import connection
cursor = connection.cursor()
cursor.execute('SELECT count(*) FROM pg_indexes WHERE tablename LIKE 'core_%';')
print('Índices creados:', cursor.fetchone()[0])
"
```

#### **Paso 3: Documentar y entrenar**
```bash
# Crear documentación de operaciones
# Documentar procedimientos de monitoreo
# Entrenar equipo en uso de Flower
# Crear runbooks para troubleshooting
```

---

## 🔧 **DJANGO ADMIN MEJORADO PARA GESTIÓN COMPLETA**

### **Configuración del Admin**
```python
# api/core/admin_enhanced.py
from django.contrib import admin
from django.contrib.admin import ModelAdmin
from .models import *

# Admin para modelos nuevos
@admin.register(DataPoint)
class DataPointAdmin(ModelAdmin):
    list_display = ['data_point_id', 'stream', 'device', 'collected_at', 'quality', 'processed_value']
    list_filter = ['quality', 'is_valid', 'stream__name', 'device__name']
    search_fields = ['data_point_id', 'device__device_id']
    readonly_fields = ['data_point_id', 'received_at', 'processed_at']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('stream', 'device', 'point')

@admin.register(SupportTicket)
class SupportTicketAdmin(ModelAdmin):
    list_display = ['ticket_number', 'title', 'status', 'priority', 'created_by', 'assigned_to', 'opened_at']
    list_filter = ['status', 'priority', 'category', 'assigned_to']
    search_fields = ['ticket_number', 'title', 'description']
    readonly_fields = ['ticket_number', 'opened_at', 'resolved_at', 'closed_at']

    actions = ['assign_to_me', 'mark_resolved', 'close_ticket']

    def assign_to_me(self, request, queryset):
        for ticket in queryset:
            ticket.assign_to(request.user)
        self.message_user(request, f"{queryset.count()} tickets asignados a ti")

    def mark_resolved(self, request, queryset):
        for ticket in queryset:
            ticket.resolve(request.user, "Resuelto desde admin")
        self.message_user(request, f"{queryset.count()} tickets marcados como resueltos")

    def close_ticket(self, request, queryset):
        queryset.update(status='CLOSED', closed_at=timezone.now())
        self.message_user(request, f"{queryset.count()} tickets cerrados")

@admin.register(ConstantDefinition)
class ConstantDefinitionAdmin(ModelAdmin):
    list_display = ['name', 'code', 'constant_type', 'value_numeric', 'is_active']
    list_filter = ['constant_type', 'is_active']
    search_fields = ['name', 'code']

    actions = ['activate_constants', 'deactivate_constants']

    def activate_constants(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, f"{queryset.count()} constantes activadas")

    def deactivate_constants(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f"{queryset.count()} constantes desactivadas")

@admin.register(ProviderDataSync)
class ProviderDataSyncAdmin(ModelAdmin):
    list_display = ['provider', 'sync_type', 'current_status', 'last_successful_sync', 'total_records_synced']
    list_filter = ['sync_type', 'current_status', 'is_active']
    readonly_fields = ['last_sync_attempt', 'last_successful_sync', 'total_records_synced']

    actions = ['enable_sync', 'disable_sync', 'force_sync']

    def enable_sync(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, f"{queryset.count()} sincronizaciones habilitadas")

    def disable_sync(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f"{queryset.count()} sincronizaciones deshabilitadas")

    def force_sync(self, request, queryset):
        from ..tasks.provider_sync_tasks import sync_provider_data
        for sync in queryset:
            sync_provider_data.delay(sync.provider.code)
        self.message_user(request, f"Sincronización forzada para {queryset.count()} proveedores")

# Configurar admin site
admin.site.site_header = "SmartHydro - Gestión Empresarial"
admin.site.site_title = "SmartHydro Admin"
admin.site.index_title = "Panel de Administración Completo"

# Crear grupos de modelos en el admin
TELEMETRY_MODELS = [
    ('Data Granular', 'DataPoint'),
    ('Streams', 'DataStream'),
    ('Variables', 'VariableDefinition'),
    ('Agregaciones', 'DataAggregation'),
]

PROVIDER_MODELS = [
    ('Proveedores', 'EquipmentProvider'),
    ('Modelos', 'EquipmentModel'),
    ('Dispositivos', 'IoTDevice'),
    ('Sincronización', 'ProviderDataSync'),
]

CONSTANTS_MODELS = [
    ('Constantes', 'ConstantDefinition'),
    ('Aplicaciones', 'ConstantApplication'),
    ('Correcciones', 'DataCorrectionLog'),
]

SUPPORT_MODELS = [
    ('Tickets', 'SupportTicket'),
    ('Comentarios', 'TicketComment'),
    ('SLAs', 'TicketSLA'),
]

# Registrar todos los modelos
admin.site.register(DataPoint, DataPointAdmin)
admin.site.register(SupportTicket, SupportTicketAdmin)
admin.site.register(ConstantDefinition, ConstantDefinitionAdmin)
admin.site.register(ProviderDataSync, ProviderDataSyncAdmin)

# Registrar modelos restantes automáticamente
for model in [DataStream, VariableDefinition, DataAggregation, EquipmentProvider,
              EquipmentModel, IoTDevice, ConstantApplication, DataCorrectionLog,
              TicketComment, TicketSLA, DataQualityMetric]:
    admin.site.register(model)
```

### **Mejoras en el Admin Existente**
```python
# api/core/admin.py - Agregar al existente

# Agregar pestañas para modelos nuevos
class SmartHydroAdminSite(admin.AdminSite):
    site_header = "SmartHydro - Gestión Empresarial"
    site_title = "SmartHydro Admin"
    index_title = "Panel de Control Empresarial"

    def get_app_list(self, request):
        app_list = super().get_app_list(request)

        # Reorganizar por categorías de negocio
        custom_app_list = []

        # Dashboard ejecutivo
        custom_app_list.append({
            'name': '🏠 Dashboard Ejecutivo',
            'app_label': 'dashboard',
            'models': []
        })

        # Telemetría y datos
        custom_app_list.append({
            'name': '📊 Telemetría & Datos',
            'app_label': 'telemetry',
            'models': [
                {'model': 'datapoint', 'name': 'Puntos de Datos'},
                {'model': 'datastream', 'name': 'Streams de Datos'},
                {'model': 'variabledefinition', 'name': 'Definiciones de Variables'},
                {'model': 'dataaggregation', 'name': 'Agregaciones'},
                {'model': 'dataqualitymetric', 'name': 'Métricas de Calidad'},
            ]
        })

        # Proveedores y equipos
        custom_app_list.append({
            'name': '🔧 Proveedores & Equipos',
            'app_label': 'providers',
            'models': [
                {'model': 'equipmentprovider', 'name': 'Proveedores'},
                {'model': 'equipmentmodel', 'name': 'Modelos de Equipos'},
                {'model': 'iotdevice', 'name': 'Dispositivos IoT'},
                {'model': 'providerdatasync', 'name': 'Sincronización'},
            ]
        })

        # Constantes y correcciones
        custom_app_list.append({
            'name': '⚖️ Constantes & Correcciones',
            'app_label': 'constants',
            'models': [
                {'model': 'constantdefinition', 'name': 'Definiciones'},
                {'model': 'constantapplication', 'name': 'Aplicaciones'},
                {'model': 'datacorrectionlog', 'name': 'Logs de Corrección'},
            ]
        })

        # Soporte y tickets
        custom_app_list.append({
            'name': '🎫 Soporte & Tickets',
            'app_label': 'support',
            'models': [
                {'model': 'supportticket', 'name': 'Tickets'},
                {'model': 'ticketcomment', 'name': 'Comentarios'},
                {'model': 'ticketsla', 'name': 'SLAs'},
            ]
        })

        return custom_app_list

# Instancia global
smarthydro_admin = SmartHydroAdminSite()
```

---

## 🎯 **MONITOREO POST-MIGRACIÓN**

### **Scripts de Verificación**
```bash
# Verificar que Celery está corriendo
watch -n 30 'celery -A api inspect active'

# Verificar procesamiento de datos
python manage.py shell -c "
from api.core.models import DataPoint, InteractionDetail
import datetime

# Datos nuevos vs antiguos
new_data = DataPoint.objects.filter(
    collected_at__gte=timezone.now() - timedelta(hours=1)
).count()

old_data = InteractionDetail.objects.filter(
    date_time_medition__gte=timezone.now() - timedelta(hours=1)
).count()

print(f'New DataPoints: {new_data}')
print(f'Old InteractionDetail: {old_data}')
"

# Verificar sincronización con proveedores
python manage.py shell -c "
from api.core.models import ProviderDataSync
syncs = ProviderDataSync.objects.all()
for s in syncs:
    print(f'{s.provider.name}: {s.current_status} - {s.total_records_synced} records')
"
```

### **Alertas de Monitoreo**
```python
# Configurar alertas automáticas
ALERT_THRESHOLDS = {
    'data_ingestion_rate': 100,  # registros/hora mínimo
    'sync_failures': 3,          # fallos máximos por hora
    'ticket_resolution_time': 24, # horas máximo para resolución
}

def check_system_health():
    """Verificación automática de salud post-migración"""
    from api.core.services.monitoring_service import check_critical_metrics

    issues = []

    # Verificar ingestion rate
    ingestion_rate = get_current_ingestion_rate()
    if ingestion_rate < ALERT_THRESHOLDS['data_ingestion_rate']:
        issues.append(f'Low ingestion rate: {ingestion_rate} records/hour')

    # Verificar sync health
    sync_issues = check_sync_health()
    issues.extend(sync_issues)

    # Alertar si hay problemas
    if issues:
        send_admin_alert('SYSTEM_HEALTH_ISSUES', issues)

    return issues
```

---

## 🚨 **ROLLBACK PLAN (Si algo sale mal)**

### **Rollback Inmediato (Primeros 5 minutos)**
```bash
# Si Celery falla al iniciar
sudo systemctl stop celery_worker celery_beat

# Restaurar cronjobs en settings.py
CRONJOBS = [
    # Pegar configuración original
]

# Reiniciar Django
sudo systemctl restart gunicorn
```

### **Rollback Parcial (24 horas)**
```bash
# Desactivar Celery pero mantener datos
# Los DataPoints nuevos se pueden migrar a InteractionDetail si es necesario

# Script de rollback
python manage.py rollback_to_cronjobs
```

### **Rollback Completo (Hasta 7 días)**
```bash
# Restaurar backup completo
python manage.py loaddata backup_production_pre_migration.json

# Restaurar código
git checkout COMMIT_HASH_ANTES_DE_MIGRACION

# Reiniciar servicios
sudo systemctl restart gunicorn
```

---

## 🎉 **RESULTADO ESPERADO**

### **Antes de la Migración:**
- ❌ Cronjobs lentos y difíciles de monitorear
- ❌ Sin raw_values de dispositivos
- ❌ Sin gestión de tickets
- ❌ Sin constantes históricas
- ❌ Django Admin básico

### **Después de la Migración:**
- ✅ **Celery distribuido** con monitoreo completo
- ✅ **Raw values preservados** de todos los dispositivos
- ✅ **Sistema completo de tickets** con SLA
- ✅ **Constantes históricas** editables y aplicables por rangos
- ✅ **Django Admin empresarial** con gestión completa

---

## ⚡ **TIEMPO ESTIMADO: 3 semanas**

- **Semana 1:** Análisis, backup, deploy gradual
- **Semana 2:** Activación controlada, monitoreo intensivo
- **Semana 3:** Optimización, limpieza, documentación

**¿Quieres que inicie la Fase 1 del plan de migración a producción?** 🚀

El riesgo es **bajo** con el plan de rollback, y los beneficios son **masivos**. ¿Procedemos? 🎯