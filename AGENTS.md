# SmartHydro — Guía Maestra para Agentes de Kimi

> **Última auditoría:** 2026-06-03
> **Estado:** Producción activa — CAUTELA MÁXIMA en todo cambio
>
> **Cambios recientes (2026-05-24):**
> - **Fix `variable_details` honesto:** `success=True` solo cuando el getter realmente trae datos (`date_time is not None`)
> - **Fix reconexión bypass:** `is_reconnection=True` ya no salta detección de reset. Durante reconexión, caídas de pulsos se tratan como reset real (el sensor probablemente se reinició offline)
> - **Fix DecimalField precision:** `InteractionDetail.flow/nivel/water_table` ampliados de `max_digits=5` a `10` (evita errores en valores >999.99)
> - **Índice compuesto DGA:** `['send_dga', 'is_error', 'date_time_medition']` agregado para queries de retry queue
> - **Fix crisis Redis:** `requirepass` activado, auth funcionando en todos los contenedores
> - **Fix monotonicidad total:** 1,786 registros NULL corregidos en 8 puntos TWIN + 134 registros NOVUS
> - **Fix cronjob `total.py`:** `pulses=0` nunca detecta reset falso → preserva monotonicidad
> - **Fix backfill:** `recalc_totals_for_range()` propaga último total válido cuando `pulses=0`
> - **Throttling API Ikolu:** Todos los endpoints ahora tienen rate limiting
> - **Tests Ikolu:** 10 tests nuevos cubriendo endpoints críticos del Centro de Control
> - **Auditoría telemetría:** Script `audit_telemetry_health.py` para monitoreo continuo
> - **Auditoría APIs:** Documentación de paginación y estado de Legacy vs Ikolu
> - **Documentación endpoints actualizada:** `docs/API_ENDPOINTS.md`, `docs/API_IKOLU_ENDPOINTS.md`, `API_AUDIT_AND_ROADMAP.md` actualizados con todos los endpoints actuales (tickets, backfill, chat, system events, admin dashboards, schema OpenAPI)
> - 120 tests pasando (115 regresión + 5 DGA)

---

## 🚨 MANDAMIENTO PRINCIPAL

**Este proyecto está en PRODUCCIÓN activa.** Cada cambio puede afectar:
- Monitoreo hidrológico en tiempo real
- Telemetría de dispositivos TWIN / NETTRA / NOVUS
- Envío de datos a DGA (Dirección General de Aguas — regulador)
- Alertas a clientes

**Si no estás 100% seguro de un cambio, NO LO HAGAS.** Pregunta primero.

---

## ⚡ Eficiencia Operativa (lecciones aprendidas 2026-05-31)

### Debug en contenedores
- El bind mount es **restringido** (`./api:/app/api`, no `./:/app`). Gunicorn **no recarga** automáticamente.
- Los `.pyc` pueden quedar con fecha más nueva que los `.py` → Python nunca recompila. Si hay `AttributeError` en un campo que existe en el archivo, usar `getattr()` defensivo **inmediatamente** en vez de intentar limpiar cachés.
- Ante un 500, el primer paso es siempre: `docker logs --tail 30 django_api_secure`.

### Tipos numéricos en Python 3
- `DecimalField` devuelve `Decimal`, no `float`.
- `sum([float, Decimal])` → `TypeError`. Siempre convertir a `float()` antes de sumar/promediar.
- `max(0.0, Decimal('x'))` produce tipos mixtos. Convertir ambos a `float`.

### Cambios mínimos
- Un solo propósito por edición.
- No refactorizar lo que no está roto.
- No pedirle al usuario que haga debugging que puedo hacer yo con `docker exec` / `docker logs`.

---

## 🏗️ Arquitectura

| Componente | Tecnología | Contenedor |
|------------|-----------|------------|
| API Django | Django 4.2 + DRF | `django_api_secure` |
| Base de datos | PostgreSQL 15 | `postgres_secure` |
| Reverse proxy | nginx-proxy (jwilder) | `nginx_proxy` |
| SSL/LetsEncrypt | jrcs/letsencrypt-companion | `letsencrypt` |
| Tareas cron | django-crontab | `cron_jobs_secure` |
| Cache | Redis | `redis_secure` |
| WSGI server | Gunicorn | dentro de `django_api_secure` |

### APIs
- **Legacy:** `/api/` — DefaultRouter, endpoints REST completos
- **Ikolu:** `/api/ik/` — Batch endpoints (`batch/telemetry/`, `batch/stats/`, `login/`)

### Dual Container
- `django_api_secure` sirve HTTP/HTTPS via nginx-proxy externo
- `cron_jobs_secure` comparte el mismo código pero ejecuta crontab

---

## ⚠️ REGLAS CRÍTICAS

### 1. Nunca tocar sin análisis previo
- `api/cronjobs/telemetry/controllers/total.py` — lógica de unificación de pulsos
- `api/cronjobs/telemetry/getters/tdata.py` — credenciales TDATA (¡hardcodeadas!)
- `api/core/models/catchment_points.py` — modelos principales del dominio
- `api/core/signals/notifications.py` — señales que disparan alertas
- `tests/regression/` — tests de compatibilidad que NUNCA deben romperse

### 2. Base de datos
- **NO** editar migraciones existentes
- Si se modifica un modelo → `makemigrations` + migrar en dev primero
- Las migraciones 0026-0030 son recientes; verificar estado en producción

### 3. Seguridad
- `.env` está en `.gitignore` pero fue trackeado en el pasado → **credenciales en historial git**
- `credentials/google_service_account_key.json` existe físicamente
- NUNCA agregar credenciales al código (ver hallazgos de auditoría abajo)

### 4. Docker/Producción
- **NO** hacer `docker-compose down` sin confirmación del usuario
- El bind mount `./:/app` expone el código fuente al contenedor
- `cron_jobs_secure` usa `cron-entrypoint.sh` — modificaciones requieren copia al contenedor y reinicio

### 5. Tests obligatorios
Antes de considerar cualquier tarea terminada:
```bash
source .venv/bin/activate
python manage.py test tests.regression
python manage.py test tests.dga
```

---

## 🔴 HALLAZGOS DE AUDITORÍA (2026-05-14)

### CRÍTICOS — Requieren atención inmediata

| # | Problema | Ubicación | Riesgo |
|---|----------|-----------|--------|
| 1 | **Credenciales TDATA hardcodeadas** | `getters/tdata.py:12-13` | Usuario/password expuestos en git |
| 2 | **Tokens impresos en logs stdout** | `getters/tdata.py:38`, `thingsio.py:18` | Fuga de credenciales en logs Docker |
| 3 | **Race condition en totales** | `controllers/total.py:160-162` | Pérdida de pulsos si dos cron corren simultáneo |
| 4 | **Cookies sin Secure flag** | `settings.py` (antes del fix) | Robo de sesión vía MITM |
| 5 | **Sin SECURE_SSL_REDIRECT** | `settings.py` (antes del fix) | Downgrade HTTP posible |
| 6 | **Redis sin autenticación** | `docker-compose.yml` | Acceso libre desde red interna |
| 7 | **Bind mount `./:/app`** | `docker-compose.yml` | Inmutabilidad rota, `.git/` expuesto |

### ALTOS — Deuda técnica grave

| # | Problema | Ubicación |
|---|----------|-----------|
| 8 | **N+1 Query severo** | `views/management.py:155-188` — 1 query por punto + 1 por perfil |
| 9 | **Endpoints sin paginación** | `catchment_points.py` — `all()` sin límite |
| 10 | **DecimalField con `max_length`** | ~~`models/catchment_points.py:475`~~ ✅ Corregido |
| 11 | **Modelos sin índices DB** | Parcialmente resuelto: FKs recientes tienen `db_index=True`; índice compuesto `send_dga+is_error+date_time_medition` agregado |
| 12 | **100+ prints de debug** | Todo `api/cronjobs/` |
| 13 | **X_FRAME_OPTIONS = SAMEORIGIN** | `settings.py:462` — anula DENY en producción |
| 14 | **CORS permite localhost en prod** | `settings.py:249-257` |
| 15 | **Redis sin password** | `docker-compose.yml` |
| 16 | **Imágenes Docker con `latest`** | `nginx-proxy`, `letsencrypt` |

### MEDIOS — Mejoras de calidad

| # | Problema | Ubicación |
|---|----------|-----------|
| 17 | Imports no usados | `management.py`, `catchment_points.py`, `reports.py`, `users.py` |
| 18 | `hasattr` innecesario | `controllers/total.py:103-105` |
| 19 | Código comentado muerto | `nettra_f5.py`, `novus.py`, `twin*.py` |
| 20 | Excepciones silenciadas | `reports.py`, `interaction_detail.py` |
| 21 | `rotate-cron-logs.sh` vacío | raíz del proyecto |
| 22 | `init-db-secure.sql/` es directorio vacío | raíz del proyecto |

---

## 🔧 FIXES YA APLICADOS (2026-05-14)

✅ **Seguridad settings.py:**
- `SESSION_COOKIE_SECURE = True`
- `CSRF_COOKIE_SECURE = True`
- `SECURE_SSL_REDIRECT = True`

✅ **Eliminación de logs de tokens:**
- `getters/tdata.py` — removidos `print(token)` y `print(str_variable)`
- `getters/thingsio.py` — removidos `print(token)` y prints de debug

✅ **Limpieza de imports no usados:**
- `management.py`, `catchment_points.py`, `reports.py`, `users.py`

✅ **Crontab duplicados:**
- Limpieza completa de crontab (tenía 61+ líneas, ahora 16)
- `cron-entrypoint.sh` corregido para evitar acumulación en reinicios

---

## 📋 PLAN DE MEJORAS TÉCNICAS (NO APLICAR SIN PLAN DETALLADO)

### Fase 1: Performance DB (parcialmente completada)
- ✅ Agregar `db_index=True` a FKs frecuentemente filtrados (migraciones 0032+)
- ✅ Corregir `DecimalField(max_length=1200)` → usar `max_digits` + `decimal_places`
- ✅ Corregir `IntegerField(default=0.0)` → `default=0`
- ✅ Ampliar `DecimalField(max_digits=5→10)` en `InteractionDetail.flow/nivel/water_table`
- ✅ Índice compuesto `['send_dga', 'is_error', 'date_time_medition']` agregado
- Pendiente: `ResponseNotificationsCatchment.notification`, `user` (baja frecuencia)

### Fase 2: Optimización API
- Resolver N+1 en `management.py:points_status` con `prefetch_related`
- Agregar paginación a ViewSets que usan `.all()`
- Cachear consultas de perfil frecuentes con Redis

### Fase 3: Seguridad Docker
- Agregar `requirepass` a Redis
- Eliminar bind mount `./:/app` o restringir a solo código necesario
- Pin versiones de imágenes (`nginx-proxy:1.x` en vez de `latest`)
- Revisar si `DAC_OVERRIDE` es realmente necesario

### Fase 4: Lógica crítica (parcialmente completada)
- ✅ Fix race condition en `controllers/total.py` usando `select_for_update()` + `F()` expressions
- ✅ Fix reconexión bypass: reset detection ya no se salta en `is_reconnection=True`
- ✅ Fix `variable_details` honesto: `success` refleja estado real del getter
- Revisar truncamiento `int(amount_to_add)` en cálculo de totales
- Mover credenciales TDATA a variables de entorno

---

## 🛠️ COMANDOS DE EMERGENCIA

### Verificar estado de contenedores
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.State}}"
```

### Health check rápido
```bash
# Interno (Django directo)
docker exec django_api_secure wget -qO- http://localhost:8000/health/

# Externo vía nginx-proxy
curl -s -L -H "Host: api.smarthydro.app" -o /dev/null -w "%{http_code}" http://localhost/health/
```

### Reiniciar servicios individuales
```bash
# NUNCA hacer down en toda la stack sin confirmación
docker restart nginx_proxy
docker restart django_api_secure
docker restart cron_jobs_secure
```

### Ver logs de errores
```bash
docker logs --tail 50 django_api_secure 2>&1 | grep -i error
docker logs --tail 50 cron_jobs_secure 2>&1 | grep -i error
docker logs --tail 20 nginx_proxy 2>&1
```

### Crontab (dentro de contenedor cron)
```bash
docker exec cron_jobs_secure crontab -l
docker exec cron_jobs_secure cat /app/.cron_env.sh
```

---

## 📝 ESTILO DE CÓDIGO

- PEP 8
- Type hints cuando sea posible
- Docstrings en español
- Variables de negocio en español
- Imports: stdlib → Django → terceros → locales
- **NO dejar prints de debug** — usar `logging` si es necesario

---

## ✅ CHECKLIST ANTES DE CUALQUIER CAMBIO EN PRODUCCIÓN

- [ ] ¿El cambio modifica lógica de negocio? → Requiere test + validación manual
- [ ] ¿El cambio toca modelos? → Requiere migración + backup de DB
- [ ] ¿El cambio toca cronjobs/telemetría? → Requiere revisar `controllers/total.py`
- [ ] ¿Hay credenciales hardcodeadas en el código nuevo? → RECHAZAR
- [ ] ¿Los tests de regresión pasan? (`python manage.py test tests.regression`)
- [ ] ¿Sintaxis válida? (`python -m py_compile` en archivos modificados)
- [ ] ¿No hay prints de debug?
- [ ] ¿Se actualizó la documentación si cambia la API?
