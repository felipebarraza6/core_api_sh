# Plan de Particionamiento / Archivado — `core_interactiondetail`

> **Fecha:** 2026-05-22
> **Tabla:** `core_interactiondetail`
> **Registros actuales:** 2,523,925
> **Tamaño actual:** 2.2 GB
> **Filas muertas:** 116,105 (~4.6%)
> **Crecimiento:** ~150K-200K registros/mes

---

## Análisis de Datos

### Distribución por antigüedad

| Rango | Registros | % del total |
|-------|-----------|-------------|
| Total | 2,523,925 | 100% |
| > 12 meses | ~1,397,245 | 55% |
| > 6 meses | ~1,397,245 | 55% |
| > 3 meses | ~1,959,207 | 78% |
| Último mes | ~125,126 | 5% |

### Distribución mensual (últimos 12 meses)

| Mes | Registros | Tamaño estimado |
|-----|-----------|-----------------|
| 2026-05 | 125,126 | 113 MB |
| 2026-04 | 197,197 | 178 MB |
| 2026-03 | 204,070 | 184 MB |
| 2026-02 | 182,172 | 164 MB |
| 2026-01 | 188,513 | 170 MB |
| 2025-12 | 185,717 | 168 MB |
| 2025-11 | 166,794 | 151 MB |
| 2025-10 | 173,307 | 156 MB |
| 2025-09 | 164,697 | 149 MB |
| 2025-08 | 119,117 | 108 MB |
| 2025-07 | 147,992 | 134 MB |
| 2025-06 | 144,351 | 130 MB |

**Proyección de crecimiento:**
- Año 1 (2027-05): ~4.5M registros, ~4 GB
- Año 2 (2028-05): ~7.5M registros, ~7 GB
- Año 3 (2029-05): ~10M registros, ~10 GB

---

## Patrones de Consulta

### Frecuencia de filtros por `date_time_medition`

| Filtro | Frecuencia en código | Uso típico |
|--------|---------------------|------------|
| `__gte` | 81 | Dashboard, últimos N días |
| `__lte` | 37 | Rango de fechas |
| `__date` | 14 | Reportes diarios |
| `__lt` | 10 | Exclusiones |
| `__year` | 4 | Reportes anuales |
| `__range` | 3 | Reportes personalizados |

**Conclusión:** La gran mayoría de las consultas filtran por rango de fecha. Particionar por `date_time_medition` optimizaría estas queries significativamente.

### Constraints e integridad referencial

| Constraint | Tipo | Impacto en particionamiento |
|------------|------|----------------------------|
| `id` (PK) | SERIAL | Fácil de migrar |
| `(catchment_point_id, date_time_medition)` | UNIQUE | Debe replicarse en cada partición |
| `FK → core_catchmentpoint` | Referencia hacia afuera | Compatible con particionamiento |
| `FK ← core_alerttrigger.interaction_detail_id` | Referencia hacia adentro | **NO compatible** con PostgreSQL 15 |

**Problema crítico:** `core_alerttrigger` tiene una FK hacia `core_interactiondetail(id)`. PostgreSQL 15 no permite FKs desde tablas no-particionadas hacia tablas particionadas.

**Soluciones posibles:**
1. Eliminar la FK y convertir el campo a `IntegerField` (Django maneja la integridad)
2. Particionar `core_alerttrigger` también (overkill)
3. Usar archivado en lugar de particionamiento

---

## Opciones Evaluadas

### Opción A: Archivado periódico (RECOMENDADA para corto plazo)

**Estrategia:** Mantener la tabla principal con los últimos 12 meses. Mover datos antiguos a una tabla `core_interactiondetail_archive` mensualmente.

**Pros:**
- ✅ No requiere cambiar la estructura de la tabla principal
- ✅ Compatible con FKs existentes
- ✅ Reversible (se pueden mover datos de vuelta)
- ✅ Queries del sistema principal no se ven afectadas
- ✅ Puede hacerse incrementalmente (mes a mes)
- ✅ No requiere ventana de mantenimiento larga

**Contras:**
- ❌ Reportes que requieren > 12 meses necesitan UNION con archive
- ❌ Dos tablas que mantener
- ❌ No es particionamiento "real" (no hay optimización de queries por rango)

**Implementación:**
1. Crear tabla `core_interactiondetail_archive` (misma estructura, sin constraints)
2. Crear cronjob mensual que mueva datos de > 12 meses a archive
3. Modificar reportes anuales para hacer UNION si es necesario

### Opción B: Particionamiento declarativo por mes (RECOMENDADA para mediano plazo)

**Estrategia:** Convertir `core_interactiondetail` en tabla particionada por rango de `date_time_medition`, con una partición por mes.

**Pros:**
- ✅ PostgreSQL optimiza automáticamente queries por rango de fecha (pruning de particiones)
- ✅ Queries de dashboard y reportes recientes son mucho más rápidas
- ✅ Mantenimiento (VACUUM, REINDEX) se hace por partición
- ✅ Puede eliminar particiones antiguas fácilmente (DROP PARTITION)

**Contras:**
- ❌ Requiere eliminar FK desde `core_alerttrigger` (cambio de modelo)
- ❌ Requiere ventana de mantenimiento (migración de 2.2GB)
- ❌ Migración compleja (recrear índices, constraints, secuencias)
- ❌ Django ORM tiene soporte limitado para tablas particionadas

**Implementación:**
1. Crear migración Django para eliminar FK de `AlertTrigger`
2. Crear tabla particionada con `PARTITION BY RANGE (date_time_medition)`
3. Crear particiones mensuales desde 2025-01 hasta actual
4. Migrar datos en batches de 50K registros
5. Renombrar tablas y recrear índices
6. Actualizar secuencia de `id`

### Opción C: Particionamiento declarativo por año (COMPROMISO)

Igual que Opción B, pero con particiones anuales en lugar de mensuales.

**Pros:** Menos particiones que administrar (~5 particiones vs ~17)
**Contras:** Menor granularidad para pruning (las queries de un solo mes escanean todo el año)

---

## Recomendación Final

### Fase 1: Inmediata (esta semana) — Limpieza
1. Ejecutar `VACUUM FULL ANALYZE core_interactiondetail`
   - Elimina 116K filas muertas
   - Recupera espacio (~100-200 MB estimado)
   - Actualiza estadísticas del planner
   - **Tiempo estimado:** 10-20 minutos
   - **Impacto:** Bloquea la tabla durante la operación

### Fase 2: Corto plazo (próximos 3 meses) — Archivado
1. Crear tabla `core_interactiondetail_archive`
2. Implementar cronjob mensual de archivado
3. Monitorear tamaño mensualmente

### Fase 3: Mediano plazo (cuando tabla llegue a 5M+ registros) — Particionamiento
1. Evaluar si el crecimiento justifica el esfuerzo
2. Implementar particionamiento mensual
3. Este punto probablemente sea en ~2027 Q2

---

## Script de Limpieza Inmediata

```sql
-- Ejecutar durante ventana de bajo tráfico (ej: domingo 3 AM)

-- 1. VACUUM FULL (bloquea la tabla)
VACUUM FULL ANALYZE core_interactiondetail;

-- 2. REINDEX (reconstruye índices corruptos/fragmentados)
REINDEX TABLE CONCURRENTLY core_interactiondetail;

-- 3. Actualizar estadísticas
ANALYZE core_interactiondetail;
```

**Nota:** `VACUUM FULL` requiere el doble de espacio en disco (4.4GB libres). Como tenemos 47GB libres, es seguro.

---

## Script de Archivado (para implementar en cronjob)

```sql
-- Mover datos de > 12 meses a archive
INSERT INTO core_interactiondetail_archive
SELECT * FROM core_interactiondetail
WHERE date_time_medition < NOW() - INTERVAL '12 months';

-- Eliminar de tabla principal
DELETE FROM core_interactiondetail
WHERE date_time_medition < NOW() - INTERVAL '12 months';

-- VACUUM para liberar espacio
VACUUM core_interactiondetail;
```

---

## Script de Particionamiento (para ejecutar en ventana de mantenimiento futura)

Ver: `scripts/migrate_interactiondetail_partitioning.py`
