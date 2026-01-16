# 📊 Análisis del Dashboard de Django Admin

## 🔧 Error de Llave Corregido

### Problema Identificado
El dashboard tenía un error de llave (KeyError) que ocurría cuando se intentaba acceder a campos que no estaban definidos en algunos diccionarios:

1. **Campo `horario` faltante**: En los errores de nivel, no se estaba agregando el campo `horario`, pero el template intentaba acceder a él.
2. **Campo `variables` podría ser None**: Aunque se inicializaba como lista, se agregó validación para asegurar que siempre sea una lista.
3. **Campos de caudal faltantes en errores de nivel**: Se agregaron campos `caudal_medido`, `caudal_real` y `caudal_probable` con valor `None` para mantener consistencia.

### Correcciones Aplicadas
- ✅ Agregado campo `horario` en errores de nivel y errores de caudal imposible
- ✅ Asegurado que `variables` siempre sea una lista (inicializada como `[]` si está vacía)
- ✅ Agregados campos faltantes para mantener consistencia en todos los tipos de errores
- ✅ Agregado campo `tipo_error` en la lista de veracidad para compatibilidad

## 📋 Organización de los Indicadores y Cards

### 1. **Métricas Principales (Cards Superiores)**

El dashboard muestra **8 cards de métricas** organizadas en un grid responsive:

#### Card 1: Número de Obras
- **Tipo**: Info (azul)
- **Valor**: `num_obras`
- **Descripción**: Puntos con código de obra
- **Cálculo**: Puntos únicos con `code_dga` no nulo y no vacío

#### Card 2: % Conectados
- **Tipo**: Success/Warning/Danger (según porcentaje)
  - Verde (success): ≥ 80%
  - Amarillo (warning): ≥ 50%
  - Rojo (danger): < 50%
- **Valor**: `pct_conectados` (%)
- **Detalle**: `pct_conectados_count` de `pct_conectados_total` puntos con telemetría activa
- **Cálculo**: De los puntos con código de obra, cuántos tienen telemetría activa (`is_telemetry=True`)

#### Card 3: % DGA
- **Tipo**: Info (azul)
- **Valor**: `pct_dga` (%)
- **Detalle**: `pct_dga_count` de `pct_dga_total` puntos con cumplimiento activo
- **Cálculo**: De los puntos con código de obra, cuántos tienen `send_dga=True` (cumplimiento activo)

#### Card 4: % Veracidad
- **Tipo**: Success/Warning/Danger (según porcentaje)
  - Verde (success): ≥ 70%
  - Amarillo (warning): ≥ 50%
  - Rojo (danger): < 50%
- **Valor**: `pct_veracidad` (%)
- **Detalle**:
  - `pct_veracidad_total`: Puntos con código de obra, telemetría activa y CAUDAL/CAUDAL_PROMEDIO
  - `pct_veracidad_con_d5`: De esos, cuántos tienen diámetro flujómetro (d5)
  - `pct_veracidad_count`: Puntos que NO superan el caudal probable
  - `pct_veracidad_pasan_probable`: Puntos que SÍ pasan el caudal probable (⚠️)
- **Cálculo**: % de puntos con d5 que NO superan el caudal probable (usando velocidad razonable de 2.5 m/s)

#### Card 5: Con Desconexión
- **Tipo**: Warning/Success (según cantidad)
  - Amarillo (warning): > 0
  - Verde (success): 0
- **Valor**: `stats_caudal_probable.con_desconexion`
- **Descripción**: Puntos con código de obra y DGA activo que están desconectados
- **Cálculo**: Puntos con código de obra y DGA activo que:
  - No tienen telemetría activa, O
  - No tienen registros recientes, O
  - Tienen `days_not_conection > 0`

#### Card 6: Registro Errores
- **Tipo**: Danger/Success (según cantidad)
  - Rojo (danger): > 0
  - Verde (success): 0
- **Valor**: `registro_errores`
- **Descripción**: Registros con errores (caudales y niveles imposibles)
- **Cálculo**: Puntos con código de obra que tienen:
  - Caudal imposible (supera máximo teórico según diámetro)
  - Nivel imposible (supera límites físicos)

#### Card 7: % Cola DGA
- **Tipo**: Warning/Info (según porcentaje)
  - Amarillo (warning): > 10%
  - Azul (info): ≤ 10%
- **Valor**: `pct_cola_dga` (%)
- **Detalle**: `pct_cola_dga_count` de `pct_cola_dga_total` últimos registros
- **Cálculo**: % de los últimos 1000 registros que tienen `send_dga=True`

#### Card 8: Notificaciones Pendientes
- **Tipo**: Warning/Success (según cantidad)
  - Amarillo (warning): > 0
  - Verde (success): 0
- **Valor**: `notificaciones_pendientes`
- **Descripción**: Errores sin incidencias (notificaciones sin respuesta)
- **Cálculo**: Notificaciones relacionadas con mediciones con errores que NO tengan incidencias (responses)

### 2. **Tabla de Registros con Errores y Excesos de Caudal**

**Ubicación**: Después de las cards de métricas

**Contenido**: Lista combinada de:
- Errores de caudal imposible
- Errores de nivel imposible
- Excesos de caudal (puntos que superan el caudal probable)

**Ordenamiento**: Por prioridad descendente:
1. Caudal Imposible (prioridad 3)
2. Exceso Caudal (prioridad 2)
3. Nivel Imposible (prioridad 1)

**Columnas**:
- **Punto**: Nombre del punto de captación
- **Proyecto**: Nombre del proyecto
- **Código Obra**: Código DGA del punto
- **Variables**: Tipos de variables configuradas (CAUDAL, CAUDAL_PROMEDIO, NIVEL, etc.)
- **Medición**: 
  - Horario de captura
  - Pulsos
  - Nivel (si aplica)
  - Caudal medido y probable
- **Exceso**: Exceso de caudal sobre el probable (L/s y %)
- **Tipo**: Tipo de error (Caudal Imposible, Exceso Caudal, Nivel Imposible)

### 3. **Tabla de Registros Recientes**

**Ubicación**: Al final del dashboard

**Contenido**: Último registro de cada punto con código de obra (últimas 24 horas o más reciente disponible)

**Ordenamiento**: 
1. Primero: Puntos desconectados (`days_not_conection > 0`)
2. Luego: Por fecha descendente (más reciente primero)

**Columnas**:
- **Información**: 
  - Nombre del punto (enlace al admin)
  - Nombre del proyecto
  - Código de obra y estándar DGA
- **Variables**: Tipos de variables configuradas (badges de colores)
- **Fechas**: 
  - Fecha/hora de medición
  - Fecha/hora del logger
  - Estado de conexión (badge)
- **Pulsos**: Cantidad de pulsos
- **Total (m³)**: Total acumulado
- **Consumo (m³)**: Diferencia de consumo
- **Nivel**: 
  - Nivel medido (m)
  - Posicionamiento (d3) si aplica
  - Nivel freático (water_table)
- **Caudal**: 
  - Caudal autorizado DGA (si aplica)
  - Caudal medido (L/s)
  - Porcentaje usado del autorizado (si aplica)
- **Voucher DGA**: Número de voucher si existe

## 🎨 Estilos y Colores

### Colores de Cards
- **Info (Azul)**: `#569cd6` - Métricas informativas
- **Success (Verde)**: `#4ec9b0` - Valores buenos
- **Warning (Amarillo)**: `#dcdcaa` - Advertencias
- **Danger (Rojo)**: `#f48771` - Errores críticos

### Colores de Variables (Badges)
- **CAUDAL / CAUDAL_PROMEDIO**: Verde (`#4ec9b0`)
- **NIVEL**: Azul (`#569cd6`)
- **TOTALIZADO**: Amarillo (`#dcdcaa`)
- **Otros**: Gris (`#858585`)

### Tema
- **Fondo**: Oscuro tipo Grafana (`#1e1e1e`)
- **Cards**: Fondo oscuro (`#252526`) con bordes (`#3c3c3c`)
- **Texto**: Gris claro (`#d4d4d4`) y blanco (`#ffffff`)

## 🔄 Auto-refresh

El dashboard se actualiza automáticamente cada **60 segundos** mediante JavaScript.

## 📍 Filtros

El dashboard incluye filtros por:
- **Proyecto**: Selector dropdown de todos los proyectos
- **Punto**: Selector dropdown de puntos del proyecto seleccionado (solo visible si hay proyecto seleccionado)

Los filtros se aplican a:
- Todas las métricas
- Tabla de errores y excesos
- Tabla de registros recientes

## 📝 Notas Técnicas

1. **Filtrado por código de obra**: Todos los cálculos y visualizaciones se basan en puntos que tienen código de obra (`code_dga` no nulo y no vacío).

2. **Cálculo de caudal probable**: Se usa la función `calculate_probable_flow_by_velocity()` con una velocidad razonable de 2.5 m/s y el diámetro del flujómetro (d5).

3. **Cálculo dinámico de flow**: Para puntos con variable `CAUDAL_PROMEDIO` y diámetro d6 configurado, se calcula el flow dinámicamente usando el serializer `InteractionDetailModelSerializer`.

4. **Evitar duplicados**: Se usa un diccionario con `point.id` como clave para evitar mostrar el mismo punto múltiples veces en las listas de errores.

5. **Priorización de errores**: Los errores se priorizan para mostrar primero los más críticos (Caudal Imposible > Exceso Caudal > Nivel Imposible).

