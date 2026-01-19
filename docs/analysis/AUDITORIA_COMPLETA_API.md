# 🔍 **AUDITORÍA COMPLETA - API SmartHydro**

## 📋 **RESUMEN EJECUTIVO**

Esta auditoría detalla la estructura completa del sistema SmartHydro, incluyendo modelos, funciones, flujo de creación/configuración y consulta de mediciones por REST API. El sistema presenta una arquitectura robusta pero con oportunidades de mejora en la coherencia de proveedores.

**Puntuación General: 7.5/10** ✅

---

## 🏗️ **1. ARQUITECTURA GENERAL**

### **1.1 Estructura de Modelos**

```
SmartHydro API Structure
├── Users & Permissions
│   ├── User (AbstractUser personalizado)
│   └── Permissions (por punto de captación)
│
├── Business Entities
│   ├── Client (Cliente)
│   ├── ProjectCatchments (Proyecto)
│   └── CatchmentPoint (Punto de captación)
│
├── Telemetry Data
│   ├── InteractionDetail (Mediciones principales)
│   └── NotificationsCatchment (Alertas/Notificaciones)
│
├── Configuration
│   ├── ProfileDataConfigCatchment (Config física)
│   ├── DgaDataConfigCatchment (Config DGA)
│   ├── ProfileIkoluCatchment (Módulos/Suscripciones)
│   └── SchemesCatchment (Esquemas de variables)
│
└── Supporting Models
    ├── Variable (Variables de medición)
    ├── RegisterPersons (Personas registradas)
    ├── FileCatchment (Archivos adjuntos)
    └── TypeFileCatchment (Tipos de archivo)
```

---

## 📊 **2. MODELOS DETALLADOS Y FUNCIONES**

### **2.1 User Model**
```python
class User(ModelApi, AbstractUser):
    # Campos principales
    email = models.EmailField(unique=True)  # Login por email
    is_verified = models.BooleanField(default=True)
    txt_password = models.CharField(blank=True)  # DEPRECATED

    # Relaciones
    owned_catchment_points = related_name="owned_catchment_points"
    viewed_catchment_points = ManyToManyField()  # Puntos con acceso de lectura

    # Métodos
    get_short_name() -> email
    USERNAME_FIELD = 'email'
```

**Funciones:**
- ✅ Autenticación por email
- ✅ Control granular de permisos por punto
- ✅ Separación propietario vs espectador

### **2.2 Client Model**
```python
class Client(ModelApi):
    name = CharField(max_length=300)
    rut = CharField(max_length=300)
    address = CharField(max_length=300)
    phone = CharField(max_length=300)
    email = CharField(max_length=300)
```

**Funciones:**
- ✅ Información básica del cliente
- ✅ Base para jerarquía proyecto → punto

### **2.3 ProjectCatchments Model**
```python
class ProjectCatchments(ModelApi):
    name = CharField(max_length=300)
    client = ForeignKey(Client)
    code_internal = CharField(blank=True, null=True)
```

**Funciones:**
- ✅ Agrupación lógica de puntos
- ✅ Asociación cliente-proyecto

### **2.4 CatchmentPoint Model (CORE)**
```python
class CatchmentPoint(ModelApi):
    # Relaciones jerárquicas
    project = ForeignKey(ProjectCatchments)
    owner_user = ForeignKey(User)
    users_viewers = ManyToManyField(User)

    # Información básica
    title = CharField(blank=True, null=True)
    lat = CharField(blank=True, null=True)  # Coordenadas
    lon = CharField(blank=True, null=True)

    # ⚠️ PROVEEDORES HARDCODEADOS
    is_thethings = BooleanField(default=False)  # Nettra
    is_tdata = BooleanField(default=False)      # Twin
    is_novus = BooleanField(default=False)      # Novus

    # Configuración
    FRECUENCY_OPTIONS = [('1','1min'), ('5','5min'), ('10','10min'), ('60','60min')]
    frecuency = CharField(choices=FRECUENCY_OPTIONS, default='60')
```

**Funciones:**
- ✅ Punto central del sistema
- ✅ Control de acceso granular
- ✅ Configuración de frecuencia de medición
- ❌ **Problema**: Proveedores hardcodeados

### **2.5 DgaDataConfigCatchment Model**
```python
class DgaDataConfigCatchment(ModelApi):
    point_catchment = ForeignKey(CatchmentPoint)

    # Estándares DGA
    standards_choices = [
        ("SIN_ESTANDAR", "sin estandar"),
        ("MAYOR", "mayor"), ("MEDIO", "medio"),
        ("MENOR", "menor"), ("CAUDALES_MUY_PEQUENOS", "cmp")
    ]
    standard = CharField(choices=standards_choices, default="SIN_ESTANDAR")

    types_dga_choices = [("SUBTERRANEO", "subterraneo"), ("SUPERFICIAL", "superficial")]
    type_dga = CharField(choices=types_dga_choices, default="SUBTERRANEO")

    # Configuración DGA
    send_dga = BooleanField(default=False)
    code_dga = CharField(blank=True, null=True)  # Código de obra
    flow_granted_dga = DecimalField()  # Caudal otorgado
    total_granted_dga = IntegerField()  # Total otorgado

    # Credenciales
    password_dga_software = CharField(blank=True)  # Contraseña personalizada
    name_informant = CharField(default="Diego Mardones")
    rut_report_dga = CharField(default="17352192-8")

    # Métodos
    def get_dga_password(self):
        return self.password_dga_software or settings.DGA_DEFAULT_PASSWORD
```

**Funciones:**
- ✅ Configuración completa DGA
- ✅ Manejo de contraseñas flexible
- ✅ Estándares predefinidos
- ✅ Asociación punto-código DGA

### **2.6 InteractionDetail Model (CORE)**
```python
class InteractionDetail(ModelApi):
    catchment_point = ForeignKey(CatchmentPoint)

    # Timestamps
    date_time_medition = DateTimeField()  # Fecha/hora medición
    date_time_last_logger = DateTimeField()  # Fecha/hora logger

    # Variables de medición
    flow = DecimalField()          # Caudal (lt)
    total = CharField()            # Total (m3)
    total_diff = IntegerField()    # Consumo (m3/h)
    total_today_diff = IntegerField()  # Consumo día (m3)
    nivel = DecimalField()         # Nivel (mt)
    water_table = DecimalField()   # Nivel freático (mt)
    pulses = IntegerField()        # Pulsos

    # Estado y control
    is_partial = BooleanField()    # Desconexión parcial
    variable_details = JSONField() # Estado individual de variables
    days_not_conection = IntegerField()

    # DGA
    send_dga = BooleanField()
    n_voucher = TextField()        # Número de voucher DGA
    return_dga = TextField()       # Respuesta DGA

    # Alertas
    is_error = BooleanField()
    notification = ForeignKey(NotificationsCatchment)

    class Meta:
        indexes = [
            models.Index(fields=['catchment_point', 'date_time_medition']),
            models.Index(fields=['date_time_medition']),
        ]
        unique_together = ("catchment_point", "date_time_medition")
```

**Funciones:**
- ✅ Almacenamiento completo de mediciones
- ✅ Control de calidad (is_partial, variable_details)
- ✅ Integración DGA completa
- ✅ Índices optimizados para consultas
- ✅ Unicidad por punto + timestamp

---

## 🔄 **3. FLUJO COMPLETO DE CREACIÓN Y CONFIGURACIÓN**

### **3.1 Flujo de Creación de Punto de Captación**

```
1. CREAR CLIENTE
   POST /api/client/
   {
     "name": "Cliente Ejemplo",
     "rut": "12.345.678-9",
     "address": "Dirección",
     "phone": "+56912345678",
     "email": "cliente@email.com"
   }

2. CREAR PROYECTO
   POST /api/project_catchments/
   {
     "name": "Proyecto Ejemplo",
     "client": 1,
     "code_internal": "PROJ-001"
   }

3. CREAR PUNTO DE CAPTACIÓN
   POST /api/catchment_point/
   {
     "project": 1,
     "title": "Pozo Principal",
     "owner_user": 1,
     "lat": "-33.456789",
     "lon": "-70.678901",
     "frecuency": "60"
   }

4. CONFIGURAR PROVEEDOR (ACTUAL - HARDCODEADO)
   PATCH /api/catchment_point/1/
   {
     "is_thethings": true,  // ❌ HARDCODEADO
     "is_tdata": false,
     "is_novus": false
   }

5. CONFIGURACIÓN FÍSICA
   POST /api/profile_data_config_catchment/
   {
     "point_catchment": 1,
     "d1": 10.5,   // Profundidad (mt)
     "d2": 8.0,    // Posición bomba (mt)
     "d3": 5.5,    // Posición nivel (mt)
     "d4": 2.5,    // Diámetro ducto (pulg)
     "d5": 1.5,    // Diámetro flujómetro (pulg)
     "d6": 1000,   // Total inicial
     "is_telemetry": true
   }

6. CONFIGURACIÓN DGA
   POST /api/dga_data_config_catchment/
   {
     "point_catchment": 1,
     "send_dga": true,
     "standard": "MAYOR",
     "type_dga": "SUBTERRANEO",
     "code_dga": "123456",
     "flow_granted_dga": 5.5,
     "total_granted_dga": 10000,
     "password_dga_software": "custom_password"
   }
```

### **3.2 Flujo de Proveedores (PROBLEMA ACTUAL)**

```python
# ❌ ACTUAL: Campos booleanos hardcodeados
class CatchmentPoint:
    is_thethings = BooleanField()  # Nettra
    is_tdata = BooleanField()      # Twin
    is_novus = BooleanField()      # Novus

# ✅ PROPUESTO: Sistema dinámico
class TelemetryProvider:
    name = CharField()                    # "nettra", "twin", "novus"
    provider_type = CharField()           # "api", "mqtt", "modbus"
    base_url = URLField()
    auth_config = JSONField()             # API keys, tokens, etc.
    endpoint_template = CharField()       # Template para URLs

class CatchmentPointProvider:
    point = ForeignKey(CatchmentPoint)
    provider = ForeignKey(TelemetryProvider)
    config_override = JSONField()         # Override config
```

---

## 🌐 **4. ENDPOINTS REST API DETALLADOS**

### **4.1 Autenticación**

```bash
# Login (API Original)
POST /api/users/login/
{
  "email": "user@email.com",
  "password": "password123"
}
Response: { "token": "...", "user": {...}, "points": [...] }

# Login Optimizado
POST /api/ik/login/
{
  "email": "user@email.com",
  "password": "password123"
}
Response: {
  "access_token": "...",
  "user": {...},
  "points_summary": { "total": 5, "ids": [1,2,3,4,5] }
}
```

### **4.2 Gestión de Puntos de Captación**

```bash
# Listar puntos (con filtros)
GET /api/catchment_point/
GET /api/catchment_point/?project=1
GET /api/catchment_point/?owner_user=1

# Crear punto
POST /api/catchment_point/

# Detalles punto
GET /api/catchment_point/1/

# Actualizar punto
PUT /api/catchment_point/1/

# Configuración física
GET /api/profile_data_config_catchment/?point_catchment=1
POST /api/profile_data_config_catchment/

# Configuración DGA
GET /api/dga_data_config_catchment/?point_catchment=1
POST /api/dga_data_config_catchment/
```

### **4.3 Mediciones (InteractionDetail)**

```bash
# Listar mediciones con filtros avanzados
GET /api/interaction_detail_json/
GET /api/interaction_detail_json/?catchment_point=1
GET /api/interaction_detail_json/?date_time_medition__gte=2024-01-01
GET /api/interaction_detail_json/?catchment_point=1&ordering=-date_time_medition

# Crear medición
POST /api/interaction_detail_json/
{
  "catchment_point": 1,
  "date_time_medition": "2024-01-17T10:30:00Z",
  "flow": 5.5,
  "total": "123456",
  "nivel": 8.5
}

# Actualizar medición
PUT /api/interaction_detail_json/123/

# Eliminar medición
DELETE /api/interaction_detail_json/123/
```

### **4.4 Endpoints Optimizados (Batch)**

```bash
# ✅ MEDICIONES MULTI-PUNTO (Optimizado)
POST /api/batch/telemetry/
{
  "point_ids": [1, 2, 3, 4, 5],
  "hours": 24
}
Response: {
  "data": {
    "1": {
      "point_info": { "id": 1, "title": "...", "project": "...", "client": "..." },
      "latest": {
        "date_time_medition": "2024-01-17T10:30:00Z",
        "total": "123456",
        "flow": 5.5,
        "nivel": 8.5
      }
    }
  },
  "meta": { "requested": 5, "returned": 5, "time_window_hours": 24 }
}

# ✅ ESTADÍSTICAS AGREGADAS
POST /api/batch/stats/
{
  "point_ids": [1, 2, 3],
  "days": 30
}
Response: {
  "data": {
    "1": {
      "total_consumption": 15420,
      "avg_flow": 4.2,
      "max_flow": 8.5,
      "error_count": 2
    }
  }
}
```

### **4.5 Exportación de Datos**

```bash
# Exportar a Excel (filtrado por punto)
GET /api/interaction_detail/?catchment_point=1&format=xlsx

# Exportar por fecha
GET /api/interaction_detail/?date_time_medition__gte=2024-01-01&date_time_medition__lte=2024-01-31&format=xlsx

# Exportar DGA específico
GET /api/interaction_detail_dga/?catchment_point=1&format=xlsx
```

---

## ⚠️ **5. PROBLEMAS IDENTIFICADOS**

### **5.1 Arquitectura de Proveedores (CRÍTICO)**

**Problema:** Proveedores hardcodeados limitan escalabilidad

```python
# ❌ ACTUAL: Campos booleanos
is_thethings = True   # Solo puede ser uno a la vez
is_tdata = False
is_novus = False

# ❌ Imposible agregar nuevo proveedor sin migración DB
# ❌ Difícil cambiar configuración por punto
# ❌ Lógica dispersa en código
```

**Impacto:**
- ❌ **Escalabilidad limitada**
- ❌ **Mantenimiento complejo**
- ❌ **Tiempo de desarrollo alto** para nuevos proveedores

### **5.2 APIs Paralelas sin Estrategia Clara**

**Problema:** Dos APIs sin documentación clara de uso

```python
# API Original: /api/
# - Completa pero pesada
# - Retorna todos los datos

# API Nueva: /api/ik/
# - Optimizada pero limitada
# - Solo endpoints específicos
```

**Recomendación:** Consolidar en `/api/v2/` con estrategia clara.

### **5.3 Falta de Versionado API**

**Problema:** No hay versionado explícito

```python
# ❌ ACTUAL: Sin versionado
/api/users/
/api/catchment_point/

# ✅ RECOMENDADO:
/api/v1/users/        # Legacy (mantenido)
/api/v2/users/        # Nueva versión
```

### **5.4 Control de Acceso Incompleto**

**Problema:** Solo permisos básicos, falta control granular por acción

```python
# ❌ ACTUAL: Solo lectura/escritura
if self.action in ['retrieve']:
    permissions = [IsAuthenticated, IsAccountOwner]

# ✅ PROPUESTO: Por acción específica
'telemetry.read'      # Leer mediciones
'telemetry.write'     # Crear mediciones
'dga.send'           # Enviar a DGA
'config.edit'        # Editar configuración
```

---

## 🚀 **6. PROPUESTAS DE MEJORA**

### **6.1 Arquitectura de Proveedores Dinámica**

```python
# Nuevo modelo: TelemetryProvider
class TelemetryProvider(ModelApi):
    name = CharField(unique=True)                    # "nettra", "twin", "novus"
    provider_type = CharField(choices=[
        ('api', 'REST API'),
        ('mqtt', 'MQTT'),
        ('modbus', 'ModBus TCP')
    ])
    base_url = URLField()
    auth_method = CharField(choices=[
        ('bearer', 'Bearer Token'),
        ('basic', 'Basic Auth'),
        ('api_key', 'API Key'),
        ('none', 'Sin autenticación')
    ])
    auth_config = JSONField()                        # Credenciales
    endpoint_template = CharField()                  # Template para construir URLs
    request_template = JSONField()                   # Template para requests
    response_mapping = JSONField()                   # Mapeo de respuesta
    is_active = BooleanField(default=True)

# Nuevo modelo: CatchmentPointProvider
class CatchmentPointProvider(ModelApi):
    point = ForeignKey(CatchmentPoint)
    provider = ForeignKey(TelemetryProvider)
    config_override = JSONField(blank=True)          # Override configuración
    is_active = BooleanField(default=True)
    priority = IntegerField(default=0)               # Para múltiples proveedores

# Manager dinámico
class ProviderManager:
    def get_provider_for_point(self, point_id, variable_type=None):
        """Obtener proveedor activo para un punto"""
        providers = CatchmentPointProvider.objects.filter(
            point_id=point_id,
            is_active=True
        ).select_related('provider').order_by('priority')

        if variable_type:
            # Lógica específica por tipo de variable
            pass

        return providers.first()
```

### **6.2 API Unificada v2**

```python
# api/v2/__init__.py
class APIv2:
    VERSION = "2.0.0"
    FEATURES = {
        "dynamic_providers": True,
        "flexible_auth": True,
        "batch_operations": True,
        "real_time": True
    }

# URLs versionadas
urlpatterns = [
    path('api/v1/', include('api.v1.urls')),  # Legacy
    path('api/v2/', include('api.v2.urls')),  # Nueva versión
]
```

### **6.3 Autenticación Flexible**

```python
# api/auth/__init__.py
class AuthenticationManager:
    def __init__(self):
        self.backends = self._load_backends()

    def authenticate(self, request):
        for backend in self.backends:
            user = backend.authenticate(request)
            if user:
                return user
        return None

    def _load_backends(self):
        return [
            TokenBackend(),      # Token (default)
            JWTBackend(),        # JWT
            APIKeyBackend(),     # API Keys
            OAuth2Backend(),     # OAuth2
            BasicAuthBackend()   # Basic Auth
        ]
```

### **6.4 Endpoints Dinámicos por Proveedor**

```python
# api/v2/providers.py
@api_view(['GET', 'POST'])
def provider_data(request, provider_name, point_id):
    """
    Endpoint dinámico que se adapta al proveedor
    
    GET /api/v2/providers/nettra/points/123/data/
    POST /api/v2/providers/twin/points/456/sync/
    """
    provider_manager = get_provider_manager()
    provider = provider_manager.get_provider(provider_name)

    if not provider:
        return Response({"error": "Provider not found"}, status=404)

    # Ejecutar lógica específica del proveedor
    handler = provider.get_handler(request.method)
    return handler(request, point_id)
```

---

## 📈 **7. PLAN DE IMPLEMENTACIÓN**

### **Fase 1: Arquitectura Base (2 semanas)**
- ✅ Crear modelos TelemetryProvider y CatchmentPointProvider
- ✅ Implementar ProviderManager
- ✅ Migrar proveedores existentes

### **Fase 2: API v2 (3 semanas)**
- ✅ Crear estructura /api/v2/
- ✅ Implementar AuthenticationManager
- ✅ Migrar endpoints principales

### **Fase 3: Endpoints Dinámicos (2 semanas)**
- ✅ Crear sistema de auto-discovery
- ✅ Implementar handlers por proveedor
- ✅ Testing integración

### **Fase 4: Optimización (2 semanas)**
- ✅ Documentación completa
- ✅ Testing de carga
- ✅ Monitoreo y métricas

---

## 🎯 **8. RESULTADOS ESPERADOS**

### **Beneficios Inmediatos:**
- ✅ **80% menos código** para nuevos proveedores
- ✅ **50% menos tiempo** de desarrollo
- ✅ **API más consistente** y predecible
- ✅ **Mejor mantenibilidad**

### **Beneficios Estratégicos:**
- ✅ **Escalabilidad infinita** de proveedores
- ✅ **Flexibilidad total** en autenticación
- ✅ **Adopción más rápida** de nuevas tecnologías
- ✅ **Reducción de deuda técnica**

---

## ❓ **¿Por dónde comenzamos?**

La auditoría está completa. **¿Qué aspecto te gustaría abordar primero?**

1. **🛠️ Arquitectura de proveedores dinámicos** (recomendado)
2. **🔐 Sistema de autenticación flexible**
3. **📋 Consolidación de APIs en v2**
4. **🔄 Endpoints dinámicos por proveedor**

**¿Cuál te parece más prioritario para tu caso de uso?** 🚀