# API Telemetry Reprocessor

> **Endpoint:** `POST /api/telemetry-reprocessor/`  
> **Auth:** Requiere usuario staff/admin (`IsAdminUser`)  
> **Modo por defecto:** Dry-run (`apply=false`)  

---

## Propósito

Permite al equipo técnico ejecutar auditoría, correcciones y backfill histórico de telemetría directamente desde el frontend o herramientas externas, sin necesidad de acceso al contenedor ni consola Django.

- **source=local** (default): opera sobre los datos ya guardados en `InteractionDetail`.
- **source=providers**: consulta el proveedor de telemetría configurado (TDATA/Twin o TagoIO/Novus) para recuperar datos atrasados y reprocesarlos.

Este endpoint replica la funcionalidad del comando `python manage.py telemetry_reprocessor` y del script `scripts/backfill_point_range.py`.

---

## Acciones disponibles

| Acción | Fuente | Descripción |
|--------|--------|-------------|
| `audit` | `local` | Detecta anomalías (totales caídos, diffs erróneos, flujo cero, nivel escalado, capa duplicada) |
| `fix-totals` | `local` | Recalcula `total`, `total_diff`, `total_today_diff` desde `pulses` y `factor` |
| `fix-flow` | `local` | Recalcula `flow` a partir de diferencias de `total` en el tiempo |
| `fix-nivel` | `local` | Corrige nivel escalado (÷10) e interpola ceros |
| `fix-water-table` | `local` | Recalcula `water_table = d3 - nivel` |
| `backfill` | `providers` | Recupera datos históricos del proveedor y reprocesa totales, caudal, nivel y water_table |

---

## Request

### Headers
```http
POST /api/telemetry-reprocessor/
Content-Type: application/json
Authorization: Token <tu_token>   # o sesión admin
```

### Body

```json
{
  "action": "fix-water-table",
  "source": "local",
  "point_id": 61,
  "start": "2026-05-20",
  "end": "2026-05-22",
  "apply": false
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `action` | string | ✅ | Una de: `audit`, `fix-totals`, `fix-flow`, `fix-nivel`, `fix-water-table`, `backfill` |
| `source` | string | ❌ | `local` (default) o `providers`. `backfill` requiere `providers` |
| `point_id` | int | ✅ para fix actions y backfill | ID del punto de captación |
| `start` | string (YYYY-MM-DD) | ❌ | Inicio del rango. Default: 1° enero del año actual |
| `end` | string (YYYY-MM-DD) | ❌ | Fin del rango (inclusive). Default: 31 diciembre del año actual |
| `apply` | bool | ❌ | `false` = dry-run (default). `true` = aplicar cambios en DB |

### Límites de rango

| Acción | Máximo días |
|--------|-------------|
| `audit` | 365 |
| Fix actions | 30 |
| `backfill` | 7 |

> Si el rango excede el máximo, retorna `400 Bad Request`.
>
> **Nota:** `backfill` consulta APIs externas; el límite de 7 días evita timeouts del request HTTP. Para rangos mayores usar el CLI `scripts/backfill_point_range.py`.

---

## Response

### Éxito (dry-run)
```json
{
  "success": true,
  "mode": "dry-run",
  "point_id": 61,
  "action": "fix-water-table",
  "records_affected": 3515,
  "sample": [
    {
      "id": 12345,
      "changes": { "water_table": 47.85 },
      "date": "2026-05-20T00:00:00+00:00"
    }
  ]
}
```

### Éxito (applied)
```json
{
  "success": true,
  "mode": "applied",
  "point_id": 61,
  "action": "fix-water-table",
  "records_affected": 3515,
  "sample": [...]
}
```

### Audit
```json
{
  "success": true,
  "mode": "audit",
  "points_audited": 1,
  "issues_found": 42,
  "backup_path": "/app/backups/audit_61_20260610_170348.csv",
  "sample": [
    {
      "point_id": 61,
      "point_title": "PF Planta 1 P1",
      "date_time_medition": "2026-05-20T00:01:00+00:00",
      "issue_type": "DIFF_MISMATCH",
      "severity": "HIGH",
      "field": "total_diff",
      "old_value": 150,
      "expected_value": 0,
      "suggestion": "fix-totals"
    }
  ]
}
```

### Backfill desde providers (dry-run)
```json
{
  "success": true,
  "mode": "dry-run",
  "source": "providers",
  "point_id": 61,
  "action": "backfill",
  "range": "2026-05-20T00:00:00 → 2026-05-22T00:00:00",
  "provider": "tdata",
  "records_created": 120,
  "records_updated": 45,
  "records_failed": 0,
  "processing": {},
  "fetch_errors": [],
  "sample": [...]
}
```

### Backfill desde providers (applied)
```json
{
  "success": true,
  "mode": "applied",
  "source": "providers",
  "point_id": 61,
  "action": "backfill",
  "range": "2026-05-20T00:00:00 → 2026-05-22T00:00:00",
  "provider": "tdata",
  "records_created": 120,
  "records_updated": 45,
  "records_failed": 0,
  "processing": {
    "totals_updated": 120,
    "flow_updated": 45,
    "nivel_updated": 0,
    "avg_flow_updated": 0,
    "diff_updated": 165,
    "today_diff_updated": 165
  },
  "fetch_errors": [],
  "sample": [...]
}
```

### Error
```json
{
  "error": "action inválida. Opciones: audit, fix-totals, fix-flow, fix-nivel, fix-water-table, backfill"
}
```

---

## Flujo recomendado

### Correcciones locales

1. **Auditar** primero (sin `apply`) para ver el estado:
   ```json
   { "action": "audit", "point_id": 61, "start": "2026-05-20", "end": "2026-05-22" }
   ```

2. **Descargar** el CSV de backup generado en `/app/backups/audit_*.csv`.

3. **Ejecutar fix** en dry-run para validar cambios:
   ```json
   { "action": "fix-totals", "point_id": 61, "start": "2026-05-20", "end": "2026-05-22", "apply": false }
   ```

4. **Aplicar** solo si la muestra es correcta:
   ```json
   { "action": "fix-totals", "point_id": 61, "start": "2026-05-20", "end": "2026-05-22", "apply": true }
   ```

### Recuperación histórica desde proveedores

1. **Dry-run** para ver qué datos recuperaría:
   ```json
   {
     "action": "backfill",
     "source": "providers",
     "point_id": 61,
     "start": "2026-05-20",
     "end": "2026-05-22",
     "apply": false
   }
   ```

2. **Aplicar** si la muestra es correcta:
   ```json
   {
     "action": "backfill",
     "source": "providers",
     "point_id": 61,
     "start": "2026-05-20",
     "end": "2026-05-22",
     "apply": true
   }
   ```

> **IMPORTANTE:** Siempre auditar antes de aplicar. Los cambios en DB son inmediatos y no hay undo automático.

---

## Seguridad

- Solo usuarios con flag `is_staff=True` o `is_superuser=True` pueden acceder.
- `apply=false` por defecto: nunca modifica datos a menos que se envíe explícitamente.
- Los backups CSV de auditoría se guardan en `/app/backups/` dentro del contenedor.

---

## Notas técnicas

- **Fix totals:** ignora decrementos de pulsos menores a 10 (ruido), no como reset.
- **Fix flow:** descarta flujos > 150 L/s como inválidos.
- **Fix nivel:** detecta escalamiento cuando valor está entre 100–999.99 y es entero (÷10).
- **Fix water_table:** usa `d3` del `ProfileDataConfigCatchment` del punto. Si no existe o es ≤0, retorna error.
- **Backfill providers:**
  - Detecta automáticamente el proveedor desde `TelemetryProvider.handler_name` o los booleanos legacy (`is_tdata`, `is_novus`).
  - Soporta `tdata` (TWIN) y `tago` (NOVUS).
  - Providers `thethings` y `generic_json` **no** tienen API de histórico; devuelve `400`.
  - Los datos se bucketizan según `point.frecuency` (1, 5, 10, 60 min).
  - Al aplicar (`apply=true`) se ejecuta el procesamiento en cascada completo.

---

## Ejemplos cURL

### Auditar un punto
```bash
curl -X POST https://api.smarthydro.app/api/telemetry-reprocessor/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Token $ADMIN_TOKEN" \
  -d '{
    "action": "audit",
    "point_id": 61,
    "start": "2026-05-20",
    "end": "2026-05-22"
  }'
```

### Corregir water_table (dry-run)
```bash
curl -X POST https://api.smarthydro.app/api/telemetry-reprocessor/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Token $ADMIN_TOKEN" \
  -d '{
    "action": "fix-water-table",
    "point_id": 61,
    "start": "2026-05-20",
    "end": "2026-05-22",
    "apply": false
  }'
```

### Corregir water_table (aplicar)
```bash
curl -X POST https://api.smarthydro.app/api/telemetry-reprocessor/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Token $ADMIN_TOKEN" \
  -d '{
    "action": "fix-water-table",
    "point_id": 61,
    "start": "2026-05-20",
    "end": "2026-05-22",
    "apply": true
  }'
```

### Backfill histórico desde proveedor (dry-run)
```bash
curl -X POST https://api.smarthydro.app/api/telemetry-reprocessor/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Token $ADMIN_TOKEN" \
  -d '{
    "action": "backfill",
    "source": "providers",
    "point_id": 61,
    "start": "2026-05-20",
    "end": "2026-05-22",
    "apply": false
  }'
```

### Backfill histórico desde proveedor (aplicar)
```bash
curl -X POST https://api.smarthydro.app/api/telemetry-reprocessor/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Token $ADMIN_TOKEN" \
  -d '{
    "action": "backfill",
    "source": "providers",
    "point_id": 61,
    "start": "2026-05-20",
    "end": "2026-05-22",
    "apply": true
  }'
```
