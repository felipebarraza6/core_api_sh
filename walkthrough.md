# Recuperación de Telemetría 2025-2026

## Resumen Ejecutivo
Se ha completado exitosamente la recuperación de datos históricos desde el Cluster Remoto.
Se restauraron **162 Puntos de Captación** y aproximadamente **1.5 millones de registros de telemetría**.

## Estado de los Datos
| Mes | Estado | Registros Recuperados |
| :--- | :--- | :--- |
| **Ene 2025** | ✅ Completo | 2,166 |
| **Feb 2025** | ✅ Completo | 87,882 |
| **Mar 2025** | ✅ Completo | 148,011 |
| **Abr 2025** | ✅ Completo | 140,632 |
| **May 2025** | ✅ Completo | 146,972 |
| **Jun 2025** | ✅ Completo | 144,387 |
| **Jul 2025** | ✅ Completo | 147,168 |
| **Ago 2025** | ✅ Completo | 119,833 |
| **Sep 2025** | ✅ Completo | 164,383 |
| **Oct 2025** | ✅ Completo | 173,131 |
| **Nov 2025** | ✅ Completo | 166,622 |
| **Dic 2025** | ✅ Completo | 175,179 |
| **Ene 2026** | ⏳ En Progreso | 6,277+ |

## Investigación de "Huerto La Higuera" y Fantasmas
- **Total de IDs Huérfanos**: Se detectaron **9 Puntos Fantasma** (sin ficha) en el servidor remoto.
- **Lista Completa**:
  | ID | Registros | Rango de Fechas |
  | :--- | :--- | :--- |
  | **186** | 816 | 12 Dic - Presente |
  | **187** | 2,667 | 19 Dic - Presente |
  | **188** | 2,753 | 19 Dic - Presente |
  | **189** | 2,754 | 19 Dic - Presente |
  | **190** | 725 | 16 Dic - Presente |
  | **191** | 725 | 16 Dic - Presente |
  | **192** | 816 | 12 Dic - Presente |
  | **193** | 816 | 12 Dic - Presente |
  | **202** | 182 | 08 Ene - Presente |

- **Análisis de Logs**: Se verificó que la base de datos remota (`data_store_telemetry`) **no contiene tablas de auditoría** (`django_admin_log` o similares), por lo que es técnicamente imposible rastrear el nombre original de estos IDs.

## Acciones Realizadas
1. **Sincronización de Metadata**: Corrección de esquema y carga de Clients, Users, Projects, CatchmentPoints, Variables y Configs.
2. **Recuperación de Datos (V6)**: Script robusto que:
    - Maneja discrepancias de esquema (`modified`, `total_today_diff`).
    - Filtra registros huérfanos (IDs inexistentes) para evitar fallos.
    - Utiliza commit fila-por-fila para maximizar la cantidad de datos recuperados en secciones críticas.
