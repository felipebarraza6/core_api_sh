# Análisis de Volúmenes Docker

## Resumen
Se revisaron todos los volúmenes de almacenamiento del servidor para buscar datos "ocultos" o respaldos automáticos previos a la recuperación.

## 1. Volúmenes de Base de Datos (PostgreSQL)
Solo existen dos volúmenes con datos de base de datos:

### A. `core_api_sh_postgres_data` (ACTIVO)
- **Estado**: Montado en el contenedor `postgres_secure`.
- **Contenido**: Es la base de datos de producción actual.
- **Datos**: Contiene toda la información histórica recuperada hoy (Ene 2025 - Ene 2026) + la info antigua.

### B. `postgres_data` (INACTIVO / ANTIGUO)
- **Estado**: Desconectado (No usado por el sistema actual).
- **Última Modificación**: **13 de Agosto de 2025**.
- **Contenido**: Copia antigua de la base de datos.
- **Conclusión**: No sirve para recuperar datos de "Huerto La Higuera" porque es muy antiguo (igual que el respaldo SQL).

## 2. Volúmenes "Dangling" (Huérfanos)
Se encontraron 6 volúmenes con nombres de hash (ej: `5f495...`).
- **Inspección**: Se revisó el contenido de CADA UNO.
- **Resultado**: Todos contienen archivos `dump.rdb`.
- **Significado**: Son volcados de memoria de **Redis** (sistema de caché y colas), no de la base de datos.
- **Relevancia**: **Nula**. No contienen información de puntos ni mediciones históricas.

## Conclusión Final
**No existen volúmenes de respaldo con datos de Septiembre-Diciembre 2025.**
El sistema no "pisó" datos recientes, porque lo único que había localmente era información de Agosto. La única fuente de datos real de ese periodo era el Cluster Remoto, que ya fue totalmente migrada a su servidor.
