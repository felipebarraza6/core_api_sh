# Bug de zona horaria en DashboardStatsView

> **Detectado:** 2026-07-04 durante la verificación de baseline de tests.
> **Archivo afectado:** `api/api_ik/views.py` (`DashboardStatsView.get`)
> **Fix aplicado:** cambiar `today = date.today()` por `today = timezone.now().date()`.

---

## Síntoma

El test `test_dashboard_stats_daily_consumption_sums_diffs` fallaba intermitentemente con:

```
AssertionError: unexpectedly None
```

en la línea:

```python
today_day = next((d for d in point_data['days'] if d['date'] == today_str), None)
self.assertIsNotNone(today_day)
```

## Causa raíz

- El servidor Docker corre en UTC.
- `TIME_ZONE = 'America/Santiago'` en `settings.py`.
- `USE_TZ = True`.
- El test crea registros de telemetría con `timezone.now()` (aware UTC).
- La vista usaba `date.today()` para determinar "hoy", que devuelve la fecha según la configuración local del sistema operativo.

En el momento del fallo:
- `timezone.now()` = `2026-07-05 00:13 UTC`
- `date.today()` = `2026-07-04` (zona horaria del sistema = America/Santiago)

Resultado: los registros se creaban para el 2026-07-05, pero la vista buscaba datos del 2026-07-04.

## Fix

En `api/api_ik/views.py`, línea 622:

```python
# Antes
today = date.today()

# Después
today = timezone.now().date()
```

Esto alinea la fecha usada por la vista con la zona horaria UTC en la que se almacenan los registros (`date_time_medition`).

## Verificación

```bash
docker exec django_api_secure python manage.py test tests.regression.test_api_ik_core --verbosity=2 --noinput --keepdb
```

Resultado: 20 tests OK.

## Nota importante

Este mismo patrón (`date.today()` vs `timezone.now().date()`) aparece en otras vistas de Ikolu:

- `api/api_ik/views_control_center.py` (líneas 74 y 161)
- `api/api_ik/views.py` (líneas 985, 1096, 1408)
- `api/api_ik/views_compliance.py` (línea 106)

**No se modificaron** en esta pasada porque sus tests actuales asumen el comportamiento con `date.today()` y un cambio global requiere un análisis más profundo de la semántica de "hoy" para usuarios en Chile vs UTC.

## Recomendación futura

Definir una política clara de manejo de fechas:

1. ¿Los dashboards usan fecha UTC o fecha local del usuario?
2. ¿Se debe detectar la zona horaria del cliente (frontend) para agrupar por día?
3. Estandarizar el uso de `timezone.localdate()` o `timezone.now().date()` en todas las vistas.

Esto debería abordarse en una fase posterior dedicada a consistencia de zona horaria, con tests que cubran el cambio de día en UTC vs hora local.
