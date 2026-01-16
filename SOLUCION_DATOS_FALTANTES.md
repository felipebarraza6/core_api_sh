# Solución: Garantizar Registros Cada Hora (Sin Vacíos)

## Problema Detectado

Los puntos JCE (ID 21, 22, 23) tienen vacíos en sus datos:
- ✅ 00:00-16:00: Datos OK
- ❌ 16:00-19:00: SIN DATOS (vacío)
- ✅ 19:00: Datos OK

**Causa Raíz**: Cuando ThingsIO no devuelve datos O devuelve valores que el sistema considera "glitch", el código NO está creando registros, dejando huecos.

## Solución

Modificar `api/cronjobs/telemetry/nettra.py` para **SIEMPRE crear un registro cada hora**, incluso cuando:
- ThingsIO no tiene datos nuevos
- Los valores son 0 o sospechosos de glitch
- No hay conexión temporal

**Estrategia**: Replicar el último dato válido y marcar el registro como "dato replicado" (no nuevo).

## Cambios Necesarios

### 1. Modificar `get_data_nettra()` en `nettra.py`

Después del loop de variables, **ANTES** de la línea que chequea `if best_date_time_last_logger or variable_details:`, agregar:

```python
# ✅ GARANTIZAR REGISTRO CADA HORA: Si no hay datos nuevos, replicar último válido
if not best_date_time_last_logger and not variable_details:
    # No hay datos de ninguna variable - buscar último registro válido
    last_valid = InteractionDetail.objects.filter(
        catchment_point_id=point_catchment["id"]
    ).exclude(
        date_time_last_logger__isnull=True
    ).order_by("-created").first()

    if last_valid:
        # Replicar valores del último registro válido
        created_register["flow"] = last_valid.flow
        created_register["total"] = last_valid.total
        created_register["total_diff"] = 0  # Sin consumo nuevo
        created_register["total_today_diff"] = 0
        created_register["nivel"] = last_valid.nivel
        created_register["water_table"] = last_valid.water_table
        created_register["pulses"] = last_valid.pulses
        created_register["date_time_last_logger"] = last_valid.date_time_last_logger.strftime("%Y-%m-%dT%H:%M:%S")
        created_register["days_not_conection"] = 9999  # Marcar como desconectado
        created_register["is_partial"] = False
        created_register["variable_details"] = []  # Sin detalles de variables

        print(f"⚠️ Punto {point_catchment['id']}: Sin datos nuevos. Replicando último válido.")
    else:
        # No hay registro previo - crear con valores 0
        created_register.setdefault("flow", 0.00)
        created_register.setdefault("total", "0")
        created_register.setdefault("total_diff", 0)
        created_register.setdefault("total_today_diff", 0)
        created_register.setdefault("nivel", 0.00)
        created_register.setdefault("water_table", 0.00)
        created_register.setdefault("pulses", 0)
        created_register.setdefault("date_time_last_logger", None)
        created_register["days_not_conection"] = 9999
        created_register["is_partial"] = False
        created_register["variable_details"] = []

        print(f"⚠️ Punto {point_catchment['id']}: Sin datos y sin historial. Creando registro con valores 0.")
```

### 2. Asegurar que `update_or_create` SIEMPRE se ejecute

El bloque `update_or_create` **NO debe estar dentro de ningún `if`**. Debe ejecutarse SIEMPRE al final de `get_data_nettra()`.

Verificar que las líneas 409-413 NO estén dentro de un bloque condicional.

## Beneficios

1. ✅ **Sin vacíos**: Siempre hay un registro cada hora
2. ✅ **Visibilidad**: El cliente puede ver el último valor conocido
3. ✅ **Diagnóstico**: days_not_conection=9999 indica problema de conectividad
4. ✅ **Continuidad**: Gráficos y reportes no se rompen

## Implementación

1. Hacer backup del archivo actual:
   ```bash
   cp api/cronjobs/telemetry/nettra.py api/cronjobs/telemetry/nettra.py.backup
   ```

2. Aplicar cambios al archivo

3. Rebuild del contenedor cron:
   ```bash
   docker-compose -f docker-compose.production.secure.yml build cron
   docker-compose -f docker-compose.production.secure.yml up -d --no-deps cron
   ```

4. Verificar logs:
   ```bash
   docker logs cron_jobs_secure --tail=50 -f
   tail -f /tmp/smarthydro/nettra_60.log
   ```

## Alternativa: Replicar Automáticamente en Controller

En lugar de modificar cada cronjob (nettra, twin, novus), se podría agregar un post-procesador que:
1. Verifica qué puntos NO tienen registro en la hora actual
2. Replica automáticamente el último válido
3. Corre cada hora después de todos los cronjobs

Esta sería una solución más genérica y menos invasiva.
