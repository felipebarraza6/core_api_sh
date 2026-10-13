# Totalizador Modbus de dos registros (`TOTALIZADO_MODBUS_*`)

Tipo de procesamiento reutilizable para totalizadores Modbus cuyo acumulado
está partido en dos registros (ticket soporte **#14458**).

No cambia el envío a DGA: solo afecta cómo se calcula `pulses` / `total` /
`total_diff` en la ingesta de telemetría.

## Fórmula

| Registro | Rol | Ejemplo |
|----------|-----|---------|
| LO | Contador 16-bit (wrap a 0) | variable / key `5001` |
| HI | Multiplicador (veces que wrapeó LO) | variable / key `5002` |

```
acumulado_bruto = HI * 65536 + LO
total_m³        = (acumulado_bruto * pulses_factor) / 1000 + addition
consumo         = total_actual - total_anterior   (clamp ≥ 0)
```

- El wrap se maneja tanto en **65535→0** (uint16) como si el equipo reporta
  **LO = 65536** (se normaliza a LO=0 y +1 a HI).
- Mid-rollover solo se corrige con patrón inequívoco:
  - **LO-ahead:** LO previo cerca del tope (≥90%) y LO nuevo cerca de 0 (≤10%),
    mismo HI. Una regresión chica (ej. LO 5→3) **se sostiene**, no se suma 65534.
  - **HI-ahead:** HI +1 y LO sigue en zona alta. Huecos largos con HI/LO
    coherentes (avance >65536) **se aceptan** sin restar el módulo.
- **Reset (0,0):** re-baseline absorbiendo pulses previos en `addition`
  (no congela el punto).
- **Migración desde TOTALIZADO:** la primera lectura Modbus no usa pulses del
  TOTALIZADO clásico como baseline de mid-rollover; absorbe el delta en
  `addition` para continuidad de `total` (ej. punto 152).

## Tipos de variable (`Variable.type_variable`)

| `type_variable` | Obligatorio | Qué hace |
|-----------------|-------------|----------|
| `TOTALIZADO_MODBUS_HI` | Sí | Stash del multiplicador (no escribe total solo) |
| `TOTALIZADO_MODBUS_LO` | Sí (o alias) | Contador LO; lleva `pulses_factor` |
| `TOTALIZADO_MODBUS` | Alias del LO | Equivalente a `TOTALIZADO_MODBUS_LO` |

Ambos registros deben pertenecer al **mismo esquema** del punto. El cron
unificado (`telemetry_unified`) los pide por `str_variable` al proveedor
(Tago, TheThings, TData, etc.) igual que cualquier otra variable.

**No** uses `TOTALIZADO` clásico en el mismo esquema como acumulado principal
si ya configuraste el par Modbus (evitarían pisarse en `pulses`/`total`).

## Configurar un punto (genérico / Colbún)

1. Admin → esquema del punto → Variables.
2. Crear (o editar) dos variables:

| Campo | HI | LO |
|-------|----|----|
| `str_variable` | Key del proveedor para el registro multiplicador (ej. `5002`) | Key del contador 16-bit (ej. `5001`) |
| `type_variable` | `TOTALIZADO_MODBUS_HI` | `TOTALIZADO_MODBUS_LO` |
| `pulses_factor` | (ignorado) | Factor de unidad, igual que TOTALIZADO: `(pulsos × factor) / 1000` |
| `display_key` | opcional / vacío | `total` (recomendado para frontend) |
| `token_service` / `provider` | Igual que el resto del punto | Igual |

3. Quitar o desactivar la variable `TOTALIZADO` antigua del esquema si
   reemplazaba el mismo acumulado.
4. Verificar en la siguiente corrida del cron:
   - `InteractionDetail.pulses` ≈ `HI*65536 + LO`
   - `total` coherente con el factor
   - `total_diff` sin negativos ni saltos de ~65536 en el wrap
5. `CAUDAL_PROMEDIO` sigue funcionando: el par Modbus escribe `total` como
   el TOTALIZADO clásico.

## Punto 152 — IANSA Chillán P2 (no aplicar en este PR)

Estado actual (referencia soporte):

- Punto id **152**, fuente **Tago**
- Una variable TOTALIZADO id **174** (`Acumulado`) con `pulses_factor = 1000`

Pasos recomendados en admin (manual, fuera de este cambio de código):

1. Confirmar en TagoIO los nombres/keys reales de los dos registros Modbus
   (LO ≈ 5001, HI ≈ 5002). Pueden no llamarse literalmente `5001`/`5002`
   en Tago; usar la key que expone el dispositivo.
2. Variable 174: cambiar `type_variable` de `TOTALIZADO` →
   `TOTALIZADO_MODBUS_LO`, y `str_variable` a la key del registro LO.
   Mantener `pulses_factor = 1000` salvo que soporte indique otro factor.
3. Crear variable hermana en el mismo esquema:
   - `type_variable = TOTALIZADO_MODBUS_HI`
   - `str_variable` = key del registro HI
   - mismo token/provider que 174
4. No tocar `DgaDataConfigCatchment` ni flags de envío DGA.
5. Monitorear 1–2 ciclos de cron y un wrap de LO si es posible (o
   validar con backfill/dry-run si hay histórico de ambos registros).

Este repositorio **no** aplica esa config a producción; solo deja el
procesador listo.

## Código de referencia

| Pieza | Ruta |
|-------|------|
| Aritmética + mid-rollover | `api/cronjobs/telemetry/controllers/modbus_totalizer.py` |
| Dispatch / stash HI+LO | `process_modbus_totalizer_variable` en `unified_processing.py` |
| Pipeline total/diff | Reutiliza `process_totalizado_variable` → `total_m3` / `total_hour` / `total_day` |
| Tests | `tests/regression/test_modbus_totalizer.py` |
