# ✅ Implementación: Análisis de Telemetría y Monitoreo en Tiempo Real

## 📋 Resumen

Se ha implementado un sistema completo de análisis de telemetría y monitoreo en tiempo real para validar la coherencia de los datos y detectar valores imposibles según parámetros estáticos.

---

## 🎯 Funcionalidades Implementadas

### 1. **Generación de PDF "Análisis de Telemetría"**

#### **Acción Masiva por Puntos de Captación**
- **Ubicación**: Django Admin → Puntos de Captación
- **Acción**: `📄 Generar Análisis de Telemetría (PDF)`
- **Funcionalidad**: 
  - Selecciona uno o más puntos
  - Genera un PDF con análisis de coherencia de datos
  - Incluye estadísticas, incidencias y validaciones

#### **Acción Masiva por Proyecto**
- **Ubicación**: Django Admin → Proyectos
- **Acción**: `📄 Generar Análisis de Telemetría por Proyecto (PDF)`
- **Funcionalidad**:
  - Selecciona uno o más proyectos
  - Genera PDF para **todos los puntos** de los proyectos seleccionados
  - Análisis individual por cada punto

#### **Contenido del PDF**
- ✅ Información del punto (nombre, proyecto, período analizado)
- ✅ Variables configuradas (Totalizado, Caudal Instantáneo, Caudal Promedio, Nivel)
- ✅ Estadísticas (mínimo, máximo, promedio, variación)
- ✅ **Incidencias detectadas**:
  - **Críticas**: Valores imposibles, totalizado sin caudal, etc.
  - **Advertencias**: Valores constantes, desconexiones, etc.
  - **Informativas**: Tipo de caudal configurado

---

### 2. **Monitoreo en Tiempo Real**

#### **Vista de Monitoreo**
- **URL**: `/admin/telemetry-monitoring/`
- **Acceso**: Solo personal autorizado (staff)
- **Funcionalidad**:
  - Muestra todos los puntos con telemetría activa
  - **Validación automática** de valores imposibles:
    - **Caudal imposible**: Según diámetro del flujómetro (d5)
    - **Nivel imposible**: Según profundidad (d1) y posicionamiento (d3)
  - Alertas visuales por criticidad
  - Auto-refresh cada 60 segundos

#### **API de Monitoreo**
- **URL**: `/admin/telemetry-monitoring/api/`
- **Formato**: JSON
- **Uso**: Para actualizaciones AJAX en tiempo real

---

## 🔍 Análisis de Coherencia Implementado

### **Validaciones de Valores Imposibles**

#### **1. Caudal Imposible**
```python
# Fórmula: Q_max (L/s) = π * (d/2)² * v_max * 1000 * 1.2
# Donde:
# - d = diámetro en metros (pulgadas * 0.0254)
# - v_max = 2.5 m/s (velocidad máxima razonable)
# - 1.2 = margen de seguridad (20%)
```
- ✅ Detecta si el caudal excede el máximo teórico según d5
- ✅ Marca como **incidencia crítica** si es imposible

#### **2. Nivel Imposible**
- ✅ Detecta si el nivel excede la profundidad total (d1)
- ✅ Detecta si el nivel es negativo
- ✅ Detecta si el nivel está muy por encima del sensor (d3)
- ✅ Marca como **incidencia crítica** si es imposible

### **Análisis de Coherencia de Datos**

#### **1. Totalizado**
- ✅ Detecta si el totalizado no cambia (incidencia crítica)
- ✅ Calcula variación y estadísticas

#### **2. Caudal**
- ✅ Detecta si el caudal siempre es cero pero el total aumenta (incidencia crítica)
- ✅ Detecta si el caudal es constante (incidencia de advertencia)
- ✅ Cuenta registros con caudal=0

#### **3. Nivel**
- ✅ Detecta si el nivel es constante (incidencia de advertencia)
- ✅ Calcula variación y estadísticas

#### **4. Desviaciones**
- ✅ Detecta consumo sin caudal registrado (más del 50% de registros)
- ✅ Marca como **incidencia crítica**

#### **5. Tipo de Caudal**
- ✅ Identifica si es instantáneo o promedio
- ✅ Marca como **informativo** si es promedio (se calcula dinámicamente)

---

## 📁 Archivos Creados/Modificados

### **Nuevos Archivos**
1. `api/core/validators/telemetry_validator.py`
   - Funciones de validación de valores imposibles
   - Función de análisis de coherencia de datos

2. `api/core/reports/pdf_generator.py`
   - Generador de PDFs con análisis de telemetría

3. `api/core/admin_views.py`
   - Vista de monitoreo en tiempo real
   - API endpoint para monitoreo

4. `templates/admin/telemetry_monitoring.html`
   - Template HTML para la vista de monitoreo

### **Archivos Modificados**
1. `api/requirements.txt`
   - ✅ Agregado: `reportlab>=4.0.0,<5.0.0`

2. `api/core/admin.py`
   - ✅ Agregadas acciones masivas:
     - `generar_analisis_telemetria_pdf` (para puntos)
     - `generar_analisis_telemetria_proyecto_pdf` (para proyectos)
   - ✅ Agregado enlace a monitoreo en `CatchmentPointAdmin` y `ProjectCatchmentsAdmin`

3. `api/urls.py`
   - ✅ Agregadas rutas:
     - `/admin/telemetry-monitoring/` (vista)
     - `/admin/telemetry-monitoring/api/` (API)

---

## 🚀 Cómo Usar

### **Generar PDF de Análisis**

#### **Por Puntos:**
1. Ir a Django Admin → **Puntos de Captación**
2. Seleccionar uno o más puntos
3. En el menú "Acción", elegir: **📄 Generar Análisis de Telemetría (PDF)**
4. Click en "Ir"
5. Se descargará el PDF con el análisis

#### **Por Proyecto:**
1. Ir a Django Admin → **Proyectos**
2. Seleccionar uno o más proyectos
3. En el menú "Acción", elegir: **📄 Generar Análisis de Telemetría por Proyecto (PDF)**
4. Click en "Ir"
5. Se descargará el PDF con el análisis de **todos los puntos** del proyecto

### **Monitoreo en Tiempo Real**
1. Ir a Django Admin
2. Navegar a: `/admin/telemetry-monitoring/`
   - O usar el enlace desde la lista de puntos/proyectos
3. Ver alertas y advertencias en tiempo real
4. La página se actualiza automáticamente cada 60 segundos

---

## 📊 Ejemplo de Incidencias Detectadas

### **Críticas:**
- ❌ **Caudal imposible**: `Caudal 150.50 L/s excede máximo teórico 120.00 L/s (d5=4")`
- ❌ **Nivel imposible**: `Nivel 25.50 m excede profundidad total 20.00 m`
- ❌ **Totalizado sin caudal**: `Total aumenta pero caudal siempre es 0`
- ❌ **Totalizado constante**: `Total constante: 1500 m³ en todo el período`

### **Advertencias:**
- ⚠️ **Caudal constante**: `Caudal constante: 5.50 L/s`
- ⚠️ **Nivel constante**: `Nivel constante: 10.25 m`
- ⚠️ **Desconexión**: `Punto desconectado hace 3 día(s)`

### **Informativas:**
- ℹ️ **Caudal promedio**: `El caudal se calcula dinámicamente (no se almacena)`

---

## 🔧 Configuración Técnica

### **Parámetros Estáticos Usados:**
- **d5**: Diámetro del flujómetro (pulgadas) → Para validar caudal máximo
- **d1**: Profundidad total (metros) → Para validar nivel máximo
- **d3**: Posicionamiento del sensor de nivel (metros) → Para validar nivel

### **Período de Análisis:**
- Por defecto: **30 días** hacia atrás
- Configurable en `analyze_data_coherence(points, days_back=30)`

---

## ✅ Próximos Pasos (Opcional)

1. **Agregar más validaciones**:
   - Validar rangos de valores según tipo de pozo
   - Validar coherencia temporal (valores que cambian muy rápido)

2. **Mejoras en el PDF**:
   - Gráficos de tendencias
   - Comparación con períodos anteriores

3. **Notificaciones automáticas**:
   - Enviar alertas por email cuando se detecten incidencias críticas

---

## 🛡️ Seguridad

- ✅ Solo personal autorizado puede acceder (decorador `@staff_member_required`)
- ✅ Validaciones robustas para evitar errores
- ✅ Manejo de excepciones en todas las funciones

---

## 📝 Notas Importantes

- **El análisis de caudal promedio** se marca como informativo porque se calcula dinámicamente (no se almacena)
- **Los valores imposibles** se detectan según parámetros estáticos configurados en `ProfileDataConfigCatchment`
- **El monitoreo en tiempo real** solo muestra puntos con telemetría activa (`is_telemetry=True`)

---

**✅ Implementación completada y lista para usar en producción**


