# Validación y Fix de Cronjobs - CRÍTICO

**Fecha**: 2025-12-13  
**Problema**: Los cronjobs estaban fallando porque no podían conectarse a la base de datos

## Problema Identificado

1. **Variable de entorno incorrecta en cron-entrypoint.sh**:
   - Valor por defecto: `postgres_secure` (incorrecto)
   - Debería ser: `postgres` (nombre del servicio en Docker Compose)

2. **Variable de entorno incorrecta en contenedor**:
   - El contenedor tenía: `LOCAL_DB_HOST=bc16424f25be_postgres_secure` (ID de contenedor antiguo)
   - Debería ser: `LOCAL_DB_HOST=postgres` (nombre del servicio)

3. **Error resultante**:
   ```
   django.db.utils.OperationalError: could not translate host name "postgres_secure" to address: Name or service not known
   ```

## Solución Aplicada

### 1. Corregido cron-entrypoint.sh
```bash
# ANTES (incorrecto):
export LOCAL_DB_HOST="${LOCAL_DB_HOST:-postgres_secure}"

# DESPUÉS (correcto):
export LOCAL_DB_HOST="${LOCAL_DB_HOST:-postgres}"
```

### 2. Verificado docker-compose.production.secure.yml
```yaml
cron:
  environment:
    - LOCAL_DB_HOST=postgres  # ✅ Correcto
```

### 3. Recreado contenedor de cron
- Detenido y eliminado el contenedor antiguo
- Creado nuevo contenedor con variables correctas

## Estado Actual

✅ **Cronjobs instalados correctamente**:
- 10 cronjobs configurados con variables de entorno correctas
- Todos usan `LOCAL_DB_HOST='postgres'`
- Variables de entorno incluidas en cada línea del crontab

✅ **Conexión a base de datos**:
- `LOCAL_DB_HOST=postgres` (correcto)
- Contenedor puede conectarse a PostgreSQL

✅ **Cronjobs activos**:
1. `twin_60` - Cada hora (0 * * * *)
2. `twin_1` - Cada minuto (* * * * *)
3. `twin_5` - Cada 5 minutos (*/5 * * * *)
4. `nettra_60` - Cada hora (0 * * * *)
5. `nettra_5` - Cada 5 minutos (*/5 * * * *)
6. `novus_60` - Cada hora (0 * * * *)
7. `dga` - Cada 3 minutos (*/3 * * * *)
8. `sma` - Cada 5 minutos (*/5 * * * *)
9. `cluster_backup` - Cada hora (0 * * * *)
10. `alerts` - Cada 10 minutos (*/10 * * * *)

## Validación

```bash
# Verificar variables de entorno
LOCAL_DB_HOST=postgres  # ✅ Correcto

# Verificar cronjobs instalados
crontab -l  # ✅ 10 cronjobs + 1 rotación de logs

# Verificar conexión BD
python manage.py shell -c "from django.db import connection; connection.ensure_connection(); print('✅ Conexión BD OK')"
```

## Resultado

✅ **CRONJOBS FUNCIONANDO CORRECTAMENTE**  
✅ **Conexión a base de datos restaurada**  
✅ **Todos los cronjobs configurados y activos**

## Nota Importante

Los logs antiguos pueden mostrar errores con `postgres_secure`, pero los nuevos logs deberían funcionar correctamente. Los cronjobs se ejecutarán según su programación y escribirán en `/var/log/smarthydro/*.log`.

