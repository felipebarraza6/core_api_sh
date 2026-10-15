# Corrección de días sin conexión y fecha del logger (auditoría 30-09-2026)

## 1. Qué estaba mal

| # | Bug | Efecto visible | Puntos detectados |
|---|-----|----------------|-------------------|
| 1 | Los días sin conexión se calculaban solo con la fecha del **TOTALIZADO**. Caudal y nivel después pisaban la fecha del logger con la suya. | Punto conectado marcado como desconectado cuando solo se cae el totalizador. El registro muestra fecha de hoy y "160 días" a la vez. | CPP Pozo 4 (211), CPP Pozo 2 (209), Essbio Sondaje 1547 (35), Sondaje 6607 (39) |
| 2 | Si el TOTALIZADO llegaba **sin fecha**, se usaba la hora de la medición como fecha del logger. | Punto sin datos aparece con 0 días sin conexión, pulsos 0 y totalizado alterado (Pichilemu 15.634.640 a 12.005.610 y de vuelta). | Todos los Nettra el 28-09 21:00 a 29-09 10:00; Venecia 1 el 30-09 15:00 |
| 3 | TheThings.io (Nettra) entrega la fecha en **UTC** y se guardaba como hora de Chile. | Fecha del logger 3 h adelantada (4 h en invierno). | Todos los puntos Nettra, desde siempre |

## 2. Cambio de código (rama `fix/telemetria-dias-sin-conexion`)

- `api/cronjobs/telemetry/utils/connection.py` (nuevo, sin Django): parseo de fechas, fecha más fresca, días, UTC a Chile y variables atrasadas.
- `telemetry_unified._process_point`:
  - la fecha del logger es la **más fresca entre todas las variables** que trajeron fecha real;
  - los días sin conexión se calculan **una vez**, con esa fecha;
  - si ninguna variable trajo fecha, se arrastra la última fecha real guardada (excluye registros falsos);
  - cada variable guarda su fecha en `variable_details[].date_time` y se marca `stale: true` si quedó más de 24 h atrás de la más fresca (log WARNING). Esto deja visible "logger conectado, totalizador caído".
- `unified_processing.process_totalizado_variable`: elimina el fallback que usaba la hora de medición como fecha del logger.
- `getters/thingsio.py`: convierte la fecha UTC a hora de Chile.
- Réplica legacy (`replicate_on_missing`): mismo comportamiento que antes (no se activa en puntos con TOTALIZADO); los días ya no quedan en 9999, se calculan con la última fecha real.

Pruebas: `tests/regression/test_connection_days.py` y `tests/regression/test_connection_runner.py`.

**Efecto esperado al desplegar:** 209, 211, 35 y 39 pasan a 0 días (sus alertas de desconexión se resuelven solas); los Nettra muestran la hora real del logger; deja de haber "reconexiones" falsas.

## 3. Plan de corrección retroactiva en producción

Comando: `python manage.py fix_connection_history` (por defecto **simula**, no escribe).

- **Fase B, hora Nettra:** reinterpreta como UTC la fecha del logger de puntos Nettra en registros anteriores al despliegue.
- **Fase A, conexión falsa:** registros con fecha del logger = hora de medición y totalizado fallido. Arrastra fecha, pulsos y total del último registro válido, `total_diff = 0`, `is_error = True`; recalcula `total_diff` del primer registro real posterior y `total_today_diff` de los días afectados.
- **Fase C, días sin conexión:** recalcula con la fecha guardada **solo si baja** (nunca sube días).
- Nunca toca registros con `n_voucher` (ya enviados a la DGA): quedan en el CSV como `omitido_enviado_dga`.

### Pasos

1. **Desplegar** la rama (flujo normal con gate de CI) y anotar la hora exacta del despliegue, idealmente entre corridas horarias (ej. HH:20). Esa hora es `--until`.
2. **Verificar en vivo** (siguiente hora): 211 y 209 con `days_not_connection = 0`; un Nettra con fecha del logger ≤ hora actual; log `logger conectado pero variables sin actualizar` para 209/211.
3. **Respaldo** del rango a corregir:
   ```sql
   CREATE TABLE core_interactiondetail_bkp_20261001 AS
   SELECT * FROM core_interactiondetail
   WHERE date_time_medition >= '2026-06-01';
   ```
4. **Piloto en simulación** con los 5 puntos auditados:
   ```bash
   python manage.py fix_connection_history --since 2026-09-01 --until "<despliegue>" \
     --points 209,211,47,35,39,25 --csv /tmp/fix_conn_piloto.csv
   ```
   Revisar el CSV (antes/después) contra lo auditado.
5. **Aplicar piloto** (mismo comando + `--apply`) y revisar en la API `/api/ik/point/<id>/records/`.
6. **Simulación completa** (todos los puntos, desde la fecha acordada, ej. 2026-06-01, cuando el runner unificado pasó a producción): revisar totales por fase y los `omitido_enviado_dga`.
7. **Aplicar completo** fuera de horario (no coincidir con el cron DGA). Se guarda por punto dentro de una transacción.
8. **Verificación posterior:**
   - sin registros con `date_time_last_logger = date_time_medition` y totalizado fallido en el rango;
   - ningún Nettra con fecha del logger en el futuro respecto a la medición;
   - informe de desconectados vuelve a calzar con la realidad (37 reales de 41).
9. **DGA:** para los registros `omitido_enviado_dga` de la fase A, decidir con operaciones si se reenvía o corrige en la DGA (el totalizado enviado fue el del registro falso).
10. **Tickets:** reclasificar #14480 (209) y #6604 (211) como falla de caudalímetro/totalizador; #14495 y #14496 (35/39) como configuración (solo nivel: revisar si deben tener TOTALIZADO en su esquema).

### Reversa

- Código: revertir el merge y redesplegar.
- Datos: restaurar desde `core_interactiondetail_bkp_20261001` los ids listados en el CSV:
  ```sql
  UPDATE core_interactiondetail d SET
    date_time_last_logger = b.date_time_last_logger, pulses = b.pulses, total = b.total,
    total_diff = b.total_diff, total_today_diff = b.total_today_diff,
    days_not_conection = b.days_not_conection, is_error = b.is_error
  FROM core_interactiondetail_bkp_20261001 b
  WHERE d.id = b.id AND d.id IN (<ids del CSV>);
  ```

### Límites conocidos

- La fase C no puede reconstruir días de registros donde la fecha guardada vino de una variable muerta (ej. nivel de Pichilemu con fecha 2023): esos se dejan como están.
- El histórico no guardaba la fecha por variable; desde el despliegue sí (`variable_details[].date_time`).
