# Análisis del Funcionamiento General de la API de Telemetría

## 📋 Resumen Ejecutivo

Esta API es un sistema de telemetría para monitoreo hidrológico que:
- **Recibe datos de loggers** (Twin, Nettra, Novus) mediante cronjobs
- **Almacena datos** en PostgreSQL (nivel, caudal, totalizado, pulsos)
- **Procesa y calcula** valores derivados (caudal promedio, consumo, etc.)
- **Envía datos a servicios externos** (DGA, SMA) para cumplimiento normativo
- **Genera alertas** automáticas por email
- **Expone datos** para visualización en plataforma web

---

## 🏗️ Arquitectura del Sistema

### Componentes Principales

1. **API REST (Django REST Framework)**
   - Endpoints para CRUD de entidades
   - Autenticación por Token
   - Exportación a Excel

2. **Cronjobs de Telemetría**
   - Frecuencias: 1 min, 5 min, 60 min
   - Proveedores: Twin (TData), Nettra (ThingsIO), Novus (Tago)
   - Procesamiento unificado de variables

3. **Sistema de Alertas**
   - Notificaciones por email
   - Alertas por umbrales (nivel, caudal, totalizado)
   - Respuestas de usuarios

4. **Integraciones Externas**
   - DGA: Envío de datos de cumplimiento normativo
   - SMA: Envío de datos ambientales

---

## 📊 Modelos de Datos Principales

### 1. **CatchmentPoint** (Punto de Captación)
- Punto físico donde se monitorea el agua
- Configuración de frecuencia (1, 5, 60 minutos)
- Proveedor de datos (Twin, Nettra, Novus)
- Propietario y usuarios con acceso

### 2. **InteractionDetail** (Registro de Telemetría)
- **Datos de medición:**
  - `date_time_medition`: Fecha/hora de la medición
  - `date_time_last_logger`: Última conexión del logger
  - `days_not_conection`: Días sin conexión
  
- **Variables medidas:**
  - `nivel`: Nivel de agua (metros)
  - `water_table`: Nivel freático (metros)
  - `flow`: Caudal instantáneo (litros/segundo)
  - `pulses`: Pulsos del contador
  - `total`: Total acumulado (m³)
  - `total_diff`: Consumo por hora (m³/h)
  - `total_today_diff`: Consumo del día (m³)

- **Control de envío:**
  - `send_dga`: Flag para cola de envío DGA
  - `return_dga`: Respuesta del servicio DGA
  - `n_voucher`: Número de comprobante DGA
  - `is_error`: Indica si hay error en el registro

### 3. **ProfileDataConfigCatchment** (Configuración de Datos)
- Parámetros físicos del pozo (profundidad, diámetros)
- Token del servicio de telemetría
- Fechas de inicio de telemetría
- Activa/desactiva telemetría

### 4. **DgaDataConfigCatchment** (Configuración DGA)
- Código de obra DGA
- Caudal otorgado
- Totalizado otorgado
- Estándar (mayor, medio, menor, CMP)
- Tipo (subterráneo, superficial)

### 5. **NotificationsCatchment** (Notificaciones)
- Alertas por umbrales de variables
- Tipos: INFO, WARNING, ALERT, CRITICAL, SUPPORT
- Variables monitoreadas: NIVEL, CAUDAL, CAUDAL_PROMEDIO, TOTALIZADO
- Estados: activo, leído, respuesta, espera, finalizado

### 6. **Client / ProjectCatchments** (Estructura Organizacional)
- Clientes → Proyectos → Puntos de Captación

---

## 🔄 Flujo de Datos

### 1. **Recolección de Datos (Cronjobs)**

```
Cronjob (1min/5min/60min)
    ↓
Filtra puntos por frecuencia y proveedor
    ↓
Obtiene variables del esquema configurado
    ↓
Llama a API del proveedor (Twin/Nettra/Novus)
    ↓
Procesa variables según tipo:
    - NIVEL → calcula nivel_mt, water_table
    - CAUDAL → calcula flow (instantáneo/promedio)
    - TOTALIZADO → calcula total, total_diff, total_today_diff
    ↓
Crea registro InteractionDetail
    ↓
Valida alertas configuradas
    ↓
Marca para envío DGA si corresponde
```

### 2. **Procesamiento de Variables**

**NIVEL:**
- `nivel_mt = (base_calculo - valor_raw) / base_calculo`
- `water_table = d1 - nivel_mt` (d1 = profundidad del pozo)

**CAUDAL:**
- Instantáneo: `flow = valor_raw * factor_conversion`
- Promedio: `caudal_promedio = (diff/3600) * 1000`

**TOTALIZADO:**
- `total = ((pulsos * pulses_factor) / 1000) + addition`
- `total_diff = diferencia entre registros consecutivos`
- `total_today_diff = suma de consumos del día`

### 3. **Envío a DGA (Cronjob cada 3 minutos)**

```
Cronjob DGA
    ↓
Filtra InteractionDetail con send_dga=True
    ↓
Agrupa por punto de captación
    ↓
Formatea datos según estándar DGA
    ↓
Envía a API DGA
    ↓
Actualiza return_dga y n_voucher
    ↓
Marca send_dga=False
```

### 4. **Sistema de Alertas (Cronjob cada 10 minutos)**

```
Cronjob Alertas
    ↓
Filtra notificaciones activas
    ↓
Obtiene último registro de cada punto
    ↓
Evalúa condiciones de alerta:
    - MAX: valor > umbral
    - MIN: valor < umbral
    - EQUALS: valor == umbral
    ↓
Si se cumple condición:
    - Crea/actualiza notificación
    - Envía email si corresponde
    - Vincula notificación al registro
```

---

## 🌐 Endpoints Existentes

### **Autenticación y Usuarios**
- `POST /api/users/login/` - Iniciar sesión
- `POST /api/users/signup/` - Registro de usuario
- `GET /api/users/` - Listar usuarios
- `GET /api/users/{username}/` - Detalle de usuario
- `PUT /api/users/{username}/` - Actualizar usuario

### **Clientes y Proyectos**
- `GET /api/client/` - Listar clientes
- `POST /api/client/` - Crear cliente
- `GET /api/project_catchments/` - Listar proyectos
- `POST /api/project_catchments/` - Crear proyecto

### **Puntos de Captación**
- `GET /api/catchment_point/` - Listar puntos
- `POST /api/catchment_point/` - Crear punto
- `GET /api/catchment_point/{id}/` - Detalle completo (con esquema)
- `PUT /api/catchment_point/{id}/` - Actualizar punto

### **Configuraciones**
- `GET /api/profile_data_config_catchment/` - Configuraciones de datos
- `GET /api/dga_data_config_catchment/` - Configuraciones DGA
- `GET /api/profile_ikolu_catchment/` - Perfiles Ikolu (módulos)

### **Telemetría (Datos)**
- `GET /api/interaction_detail_json/` - Listar registros (JSON, paginado)
- `GET /api/interaction_detail_override/` - Listar registros (sin paginación)
- `GET /api/interaction_detail_override_month/` - Registros diarios (uno por día)
- `GET /api/interaction_detail/` - Exportar a Excel
- `GET /api/interaction_detail_override_month_xlsx/` - Exportar mensual a Excel
- `GET /api/interaction_detail_dga/` - Exportar formato DGA a Excel

**Filtros disponibles:**
- `catchment_point` - ID del punto
- `date_time_medition__gte` - Desde fecha
- `date_time_medition__lte` - Hasta fecha
- `date_time_medition__date__range` - Rango de fechas
- `send_dga` - Filtrar por envío DGA

### **Notificaciones**
- `GET /api/notifications_catchment/` - Listar notificaciones
- `POST /api/notifications_catchment/` - Crear notificación
- `GET /api/response_notifications_catchment/` - Respuestas a notificaciones

### **Archivos y Documentos**
- `GET /api/file_catchment/` - Archivos asociados a puntos
- `GET /api/type_file_catchment/` - Tipos de archivo

### **Esquemas y Variables**
- `GET /api/schemes_catchment/` - Esquemas de variables
- `GET /api/variable/` - Variables configuradas

---

## ⚠️ Endpoints de Gestión Faltantes

### **Estadísticas y Monitoreo**
- ❌ Estado general del sistema
- ❌ Estadísticas de puntos activos/inactivos
- ❌ Métricas de telemetría (últimas 24h, 7d, 30d)
- ❌ Puntos con problemas de conexión
- ❌ Estado de cronjobs

### **Administración de Servicio**
- ❌ Activar/desactivar telemetría de un punto
- ❌ Reprocesar datos históricos
- ❌ Forzar ejecución de cronjob
- ❌ Limpiar cola DGA
- ❌ Reenviar datos fallidos a DGA

### **Configuración Avanzada**
- ❌ Cambiar frecuencia de un punto
- ❌ Actualizar tokens de servicios
- ❌ Gestionar esquemas de variables
- ❌ Configurar alertas masivamente

### **Logs y Auditoría**
- ❌ Ver logs de cronjobs
- ❌ Historial de cambios
- ❌ Errores recientes

---

## 🔧 Mejoras Recomendadas

1. **Endpoints de Gestión:**
   - Crear módulo `/api/management/` para operaciones administrativas
   - Endpoints para estadísticas, monitoreo y control

2. **Limpieza de Código:**
   - Eliminar archivos `.bak`, `.backup`
   - Eliminar directorio `telemetry_backup_20250819_0234/`
   - Consolidar código duplicado

3. **Documentación:**
   - Agregar docstrings a todos los endpoints
   - Crear documentación OpenAPI/Swagger

4. **Validaciones:**
   - Validar permisos en endpoints de gestión
   - Agregar validaciones de datos de entrada

5. **Optimización:**
   - Índices en campos de búsqueda frecuente
   - Cache para consultas repetitivas

---

## 📝 Notas Técnicas

- **Base de datos:** PostgreSQL 15
- **Framework:** Django 3.x + Django REST Framework
- **Autenticación:** Token Authentication
- **Timezone:** America/Santiago
- **Formato de fechas:** ISO 8601 con timezone

---

*Documento generado para análisis y mejora del sistema de telemetría*

