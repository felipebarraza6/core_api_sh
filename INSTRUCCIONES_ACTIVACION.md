# Instrucciones de Activación - Optimizaciones Implementadas

## ⚠️ IMPORTANTE: Leer Antes de Activar

Todas las funcionalidades están implementadas pero **desactivadas por defecto** para mantener compatibilidad. Sigue estos pasos para activarlas gradualmente.

## 1. Ejecutar Migración de Índices

**Paso crítico**: Ejecutar la migración para mejorar rendimiento de queries.

```bash
# Verificar que la migración está lista
docker-compose -f docker-compose.production.secure.yml exec django python manage.py showmigrations core | grep 0017

# Ejecutar migración
docker-compose -f docker-compose.production.secure.yml exec django python manage.py migrate core 0017
```

**Validación**: Verificar que no hay errores y que los índices se crearon correctamente.

## 2. Validar Tests de Regresión

Antes de activar cualquier feature, ejecutar tests para asegurar compatibilidad:

```bash
# Ejecutar todos los tests de regresión
docker-compose -f docker-compose.production.secure.yml exec django python manage.py test tests.regression

# Ejecutar tests específicos de DGA
docker-compose -f docker-compose.production.secure.yml exec django python manage.py test tests.dga
```

**Resultado esperado**: Todos los tests deben pasar ✅

## 3. Activar Nuevo Cálculo de Caudal para MEDIO

### Opción A: Activar por Variable de Entorno (Recomendado)

```bash
# En docker-compose.production.secure.yml, agregar en la sección django:
environment:
  - USE_NEW_CAUDAL_CALCULATION_MEDIO=True
```

### Opción B: Activar en settings.py

```python
# En api/settings.py, cambiar:
USE_NEW_CAUDAL_CALCULATION_MEDIO = True
```

### Validación Post-Activación

1. **Analizar registros históricos**:
   ```bash
   docker-compose -f docker-compose.production.secure.yml exec django python manage.py analyze_caudal_dga --standard MEDIO --output /tmp/analisis_medio.json
   ```

2. **Comparar cálculo actual vs nuevo**:
   ```bash
   docker-compose -f docker-compose.production.secure.yml exec django python manage.py analyze_caudal_dga --compare <register_id>
   ```

3. **Monitorear logs de DGA**:
   ```bash
   docker-compose -f docker-compose.production.secure.yml logs -f django | grep "NUEVO"
   ```

4. **Validar envíos a DGA**: Verificar que los datos enviados son correctos

### Estrategia de Activación Gradual

1. **Semana 1**: Activar para 1 punto de prueba
2. **Semana 2**: Activar para 1 proyecto completo
3. **Semana 3**: Activar para todos los puntos MEDIO

## 4. Usar Veracidad Histórica

**No requiere activación**: Ya está disponible como feature opcional.

### Uso en Dashboard

1. Ir a `/admin/dashboard/`
2. En el selector de "Veracidad", elegir período:
   - **Último registro** (default - comportamiento actual)
   - **Último trimestre** (90 días)
   - **Último mes** (30 días)
   - **Últimos 6 meses** (180 días)
   - **Último año** (365 días)

### Uso Programático

```python
from api.core.utils.veracidad_historica import calculate_historical_veracidad

# Calcular veracidad del último trimestre
result = calculate_historical_veracidad(
    obras_points_list=points_list,
    period_days=90
)
```

## 5. Monitorear Logging Estructurado

El logging estructurado ya está activo. Verificar que funciona:

```bash
# Ver logs de DGA
docker-compose -f docker-compose.production.secure.yml logs django | grep "cronjobs.dga"

# Ver logs de telemetría
docker-compose -f docker-compose.production.secure.yml logs django | grep "cronjobs.telemetry"
```

**Formato esperado**: `YYYY-MM-DD HH:MM:SS - logger_name - LEVEL - message`

## 6. Validar Optimizaciones de Queries

### Antes de Optimizaciones

```bash
# Activar django-debug-toolbar (si está disponible)
# O usar logging de queries en settings.py:
LOGGING = {
    'version': 1,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
```

### Después de Optimizaciones

1. Comparar número de queries en dashboard
2. Medir tiempo de respuesta
3. Verificar que resultados son idénticos

## Checklist de Activación

- [ ] Migración de índices ejecutada
- [ ] Tests de regresión pasan
- [ ] Logging estructurado funcionando
- [ ] Nuevo cálculo de caudal validado (si se activa)
- [ ] Veracidad histórica probada
- [ ] Optimizaciones de queries validadas
- [ ] Monitoreo activo durante primera semana

## Rollback (Si es Necesario)

### Desactivar Nuevo Cálculo de Caudal

```bash
# Cambiar variable de entorno a False
USE_NEW_CAUDAL_CALCULATION_MEDIO=False

# O en settings.py:
USE_NEW_CAUDAL_CALCULATION_MEDIO = False
```

**Nota**: No se requiere rollback de otras funcionalidades ya que son aditivas y no modifican comportamiento existente.

## Soporte

Si encuentras problemas:

1. Revisar logs: `docker-compose -f docker-compose.production.secure.yml logs django`
2. Ejecutar análisis: `python manage.py analyze_caudal_dga --standard MEDIO`
3. Revisar documentación: `RESUMEN_IMPLEMENTACION.md`
4. Ejecutar tests: `python manage.py test tests.regression`

## Notas Finales

- **Todas las funcionalidades son opcionales** excepto la migración de índices (recomendada)
- **El comportamiento actual se preserva** si no se activan nuevas features
- **Activación gradual recomendada** para validar en producción
- **Tests de regresión** aseguran que nada se rompió

