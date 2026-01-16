# Documentación de Excel Generados
## Análisis de Telemetría - Core API

---

## 📊 Resumen de Excel Generados

Este documento describe todos los tipos de Excel que se generan en el sistema, sus características, contenido y uso.

---

## 1. Excel por Proyecto
**Función:** `generate_excel_by_project()`

### Descripción
Genera un Excel con análisis de telemetría para múltiples puntos de captación de un proyecto.

### Estructura del Excel

#### Hoja 1: "Resumen Completo"
- **Contenido:** Tabla resumen con todos los puntos del proyecto
- **Columnas:**
  - Punto de Captación
  - Total Mediciones
  - Total Actual (m³)
  - Primer Registro Año (m³)
  - Caudal Min (L/s)
  - Caudal Max (L/s)
  - Caudal Promedio (L/s)
  - Nivel Min (m)
  - Nivel Max (m)
  - Nivel Promedio (m)
  - Variación Caudal %
  - Variación Nivel %
  - Incidencias Críticas
  - Incidencias Advertencia
  - Consumo Día (m³)

#### Hojas Adicionales: Una por cada Punto
- **Título:** Nombre del punto (limitado a 31 caracteres)
- **Contenido:**
  - Información Básica del Punto
  - Indicadores Principales (tabla con indicadores)
  - Últimas Mediciones (Top 20 registros)
    - **Columnas:** ID, Fecha Medición, Fecha Logger, Total (m³), Caudal (L/s), Nivel (m), Consumo (m³/h), Pulsos, Voucher DGA

### Características
- ✅ Incluye ID de registro en tabla de detalle
- ✅ Máximo 20 registros en tabla de últimas mediciones
- ✅ Indicadores calculados con análisis de coherencia

---

## 2. Excel por Punto (Detallado por Mes)
**Función:** `generate_excel_by_point()`

### Descripción
Genera un Excel detallado para un punto específico, con una hoja por cada mes del año (o mes específico si se filtra).

### Parámetros
- `point`: Punto de captación
- `year`: Año a filtrar (opcional)
- `month`: Mes a filtrar (opcional, 1-12)

### Estructura del Excel

#### Hoja 1: "Resumen Anual"
- **Contenido:**
  - Datos Estáticos del Pozo (tabla)
  - Información General DGA (tabla)
  - Indicadores Anuales (tabla)
    - Total registros
    - Consumo total año
    - Caudal promedio/máximo/mínimo año
    - Nivel promedio/máximo/mínimo año

#### Hojas Adicionales: Una por cada Mes con Datos
- **Título:** "{Mes} {Año}" (ej: "Enero 2024")
- **Contenido:**
  1. **Indicadores del Mes** (tabla)
     - Total registros
     - Consumo total mes
     - Caudal promedio/máximo/mínimo mes
     - Nivel promedio/máximo/mínimo mes
  
  2. **Últimos 5 Registros Enviados a DGA** (tabla)
     - **Columnas:** ID, Fecha Medición, Fecha Logger, Total (m³), Caudal (L/s), Nivel (m), Voucher DGA
  
  3. **Detalle del Mes** (tabla)
     - **Columnas:** ID, Fecha Medición, Fecha Logger, Total (m³), Caudal (L/s), Nivel (m), Consumo (m³/h), Pulsos, Nivel Freático (m), Voucher DGA
     - **⚠️ Límite:** Máximo 744 registros (uno por hora: 24h × 31 días)
     - **Filtro:** Solo registros con hora exacta (:00:00) en `date_time_medition`
  
  4. **Gráficos** (3 gráficos de línea)
     - Gráfico de Caudal (L/s)
     - Gráfico de Nivel (m)
     - Gráfico de Total (m³)
     - **⚠️ Límite:** Máximo 744 puntos de datos por gráfico

### Características
- ✅ Incluye ID de registro en todas las tablas de detalle
- ✅ Filtrado por hora exacta (00:00, 01:00, 02:00, etc.)
- ✅ Máximo 744 registros por mes (uno por hora)
- ✅ Gráficos optimizados (máximo 744 puntos)
- ✅ Cálculo optimizado de flow para CAUDAL_PROMEDIO

---

## 3. Excel Último Mes Completo (por Puntos)
**Función:** `generate_excel_last_month_by_points()`

### Descripción
Genera un Excel del último mes completo para varios puntos. Cada punto tiene su propia hoja y hay un resumen combinado.

### Estructura del Excel

#### Hoja 1: "Resumen Combinado"
- **Contenido:** Tabla resumen con todos los puntos del último mes
- **Columnas:**
  - Punto
  - Total Registros
  - Total Mín (m³)
  - Total Máx (m³)
  - Nivel Min (m)
  - Nivel Max (m)
  - Nivel Prom (m)
  - Caudal Min (L/s)
  - Caudal Max (L/s)
  - Caudal Prom (L/s)
  - Consumo Mes (m³)

- **Sección de Análisis:**
  - Advertencias DGA (si hay límites excedidos)
  - Resumen de Incidencias por Punto

#### Hojas Adicionales: Una por cada Punto
- **Título:** Nombre del punto (limitado a 31 caracteres)
- **Contenido:**
  1. **Datos Estáticos del Pozo** (tabla)
  2. **Información DGA** (tabla)
  3. **Indicadores del Mes** (tabla)
     - Total registros
     - Consumo total mes
     - Caudal promedio/máximo/mínimo mes
     - Nivel promedio/máximo/mínimo mes
     - Total Actual (m³) - si tiene totalizado
  
  4. **Detalle del Mes** (tabla)
     - **Columnas:** ID, Fecha Medición, Fecha Logger, Total (m³), Caudal (L/s), Nivel (m), Consumo (m³/h), Pulsos, Nivel Freático (m), Voucher DGA
     - **⚠️ Límite:** Máximo 744 registros (uno por hora: 24h × 31 días)
     - **Filtro:** Solo registros con hora exacta (:00:00) en `date_time_medition`
  
  5. **Gráficos** (3 gráficos de línea)
     - Gráfico de Caudal (L/s)
     - Gráfico de Nivel (m)
     - Gráfico de Total (m³)
     - **⚠️ Límite:** Máximo 744 puntos de datos por gráfico

### Características
- ✅ Incluye ID de registro en todas las tablas de detalle
- ✅ Filtrado por hora exacta (00:00, 01:00, 02:00, etc.)
- ✅ Máximo 744 registros por mes (uno por hora)
- ✅ Gráficos optimizados (máximo 744 puntos)
- ✅ Análisis de límites DGA

---

## 📋 Resumen de Columnas Comunes

### Tabla de Detalle (Registros)
Todas las tablas de detalle incluyen:
1. **ID** - ID del registro en la base de datos (para referencia/corrección)
2. **Fecha Medición** - Fecha y hora de medición
3. **Fecha Logger** - Fecha y hora del logger
4. **Total (m³)** - Total acumulado
5. **Caudal (L/s)** - Caudal (calculado dinámicamente si es CAUDAL_PROMEDIO)
6. **Nivel (m)** - Nivel de agua
7. **Consumo (m³/h)** - Consumo por hora (total_diff)
8. **Pulsos** - Número de pulsos
9. **Nivel Freático (m)** - Nivel freático (water_table)
10. **Voucher DGA** - Voucher DGA (si aplica)

### Tabla de Registros DGA
1. **ID** - ID del registro
2. **Fecha Medición** - Fecha y hora de medición
3. **Fecha Logger** - Fecha y hora del logger
4. **Total (m³)** - Total acumulado
5. **Caudal (L/s)** - Caudal
6. **Nivel (m)** - Nivel de agua
7. **Voucher DGA** - Voucher DGA

---

## ⚙️ Optimizaciones Implementadas

### 1. Filtrado por Hora Exacta
- **Aplicado a:** Todas las tablas de detalle mensual
- **Filtro:** Solo registros con `date_time_medition` con hora exacta (:00:00)
- **Razón:** Reducir datos a uno por hora (máximo 744 registros/mes)

### 2. Límite de Registros
- **Máximo:** 744 registros por mes (24 horas × 31 días)
- **Aplicado a:** Tablas de detalle mensual
- **Razón:** Evitar archivos pesados y timeouts

### 3. Límite de Puntos en Gráficos
- **Máximo:** 744 puntos de datos por gráfico
- **Aplicado a:** Todos los gráficos (Caudal, Nivel, Total)
- **Razón:** Reducir tamaño del archivo Excel y mejorar rendimiento

### 4. Cálculo Optimizado de Flow
- **Para CAUDAL_PROMEDIO:** Cálculo dinámico optimizado (sin N+1 queries)
- **Para CAUDAL instantáneo:** Usa flow guardado en BD
- **Razón:** Evitar timeout en puntos con muchos registros

### 5. ID de Registro
- **Incluido en:** Todas las tablas de detalle
- **Razón:** Permitir referencia y corrección de datos específicos

---

## 📝 Notas Importantes

1. **Filtrado por Hora:** Los registros se filtran por hora exacta en `date_time_medition` (NO en `date_time_last_logger`)
2. **Límite 744:** Este límite corresponde a 24 horas/día × 31 días máximo = 744 registros
3. **ID de Registro:** Siempre presente en la primera columna de todas las tablas de detalle
4. **Gráficos:** Se posicionan a la derecha de las tablas de datos
5. **Optimizaciones:** Todas las optimizaciones están documentadas con comentarios ⚠️ en el código

---

## 🔧 Funciones de Generación

| Función | Ubicación | Uso |
|---------|-----------|-----|
| `generate_excel_by_project()` | `api/core/reports/excel_generator.py` | Admin: "Generar Excel por Proyecto" |
| `generate_excel_by_point()` | `api/core/reports/excel_generator.py` | Admin: "Generar Excel Detallado por Mes (con filtro)" |
| `generate_excel_last_month_by_points()` | `api/core/reports/excel_generator.py` | Admin: "Generar Excel Último Mes Completo" |

---

## 📅 Fecha de Actualización
Última actualización: 2025-11-21

