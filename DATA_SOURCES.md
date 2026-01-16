# Inventario de Fuentes de Datos y Respaldos

## 1. Volúmenes de Datos Activos (Docker)
Estos son los datos "vivos" que usa la aplicación actualmente.
- **`postgres_data`**: Volumen principal de la base de datos de producción (`smarthydro_prod`).
- **`core_api_sh_postgres_data`**: Volumen del contenedor de base de datos segura.

## 2. Respaldos Locales (Archivos)
Todos los respaldos encontrados en el servidor datan del **13 de Agosto de 2025**. No se encontraron archivos más recientes.

### A. Respaldo Binario (Formato Custom)
- **Ubicación**: `/root/core_api_sh/backups/`
- **Archivo**: `backup_20250813_195330.dump` (30MB)
- **Fecha**: 13 Agosto 2025, 19:53 UTC.
- **Contenido**: Base de datos completa en formato binario de PostgreSQL.

### B. Respaldo SQL Plano
- **Ubicación**: `/root/core_api_sh/backup_local/`
- **Archivo**: `backup_complete_20250813_130655.sql` (147MB)
- **Fecha**: 13 Agosto 2025, 13:06 UTC.
- **Contenido**: Dump completo en texto plano SQL.

### C. Respaldos Granulares (Por Tabla)
- **Ubicación**: `/root/core_api_sh/maintenance/backup_cluster_20250813_023409/`
- **Fecha**: 13 Agosto 2025, 02:34 UTC.
- **Archivos Clave**:
    - `core_interactiondetail_backup.sql` (162MB) - Telemetría antigua.
    - `django_admin_log_backup.sql` (4.8MB) - Logs de auditoría hasta esa fecha.
    - `core_catchmentpoint_backup.sql` (17KB) - Puntos de captación existentes en Agosto.

## Resumen
Actualmente **NO existen respaldos locales posteriores a Agosto 2025**.
Toda la información generada entre Septiembre 2025 y Enero 2026 residía exclusivamente en el **Cluster Remoto** hasta que fue recuperada hoy mediante el script de sincronización.
