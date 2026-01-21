# Estructura del Proyecto SmartHydro

## Directorio Raíz

```
core_api_sh/
├── api/                    # Aplicaciones Django del proyecto
├── backups/               # Backups del sistema
├── conf/                  # Configuraciones de servicios (nginx, mosquitto, etc.)
├── config/                # Archivos de configuración del proyecto
├── dev_data/              # Bases de datos y datos de desarrollo (gitignored)
├── docker/                # Archivos Docker (Dockerfiles y docker-compose)
├── docs/                  # Documentación del proyecto
├── logs/                  # Logs del sistema
├── media/                 # Archivos media de Django
├── monitoring/            # Configuraciones de monitoreo (Prometheus, Grafana, etc.)
├── scripts/               # Scripts organizados por categoría
├── ssl/                   # Certificados SSL
├── static/                # Archivos estáticos de Django
├── staticfiles/           # Archivos estáticos compilados
├── templates/             # Templates de Django
├── tests/                 # Tests de integración del proyecto
├── manage.py              # Comando principal de Django
├── .env                   # Variables de entorno (gitignored)
└── README.md              # Documentación principal
```

## Aplicaciones Django (`api/`)

- **api_ik/** - API IK
- **chatbot/** - Sistema de chatbot
- **core/** - Funcionalidades core del sistema
- **cronjobs/** - Tareas programadas
- **reports/** - Sistema de reportes
- **support/** - Sistema de tickets de soporte
- **telemetry/** - Sistema de telemetría y sensores

## Scripts (`scripts/`)

### `scripts/deploy/`
Scripts de deployment y monitoreo de producción:
- `deploy.dev.sh` - Deploy desarrollo
- `deploy.production.sh` - Deploy producción
- `monitor.production.sh` - Monitoreo de producción

### `scripts/dev/`
Scripts para desarrollo local:
- `run_dev_simple.sh` - Servidor de desarrollo
- `create_dev_sqlite.py` - Crear BD SQLite local

### `scripts/maintenance/`
Scripts de mantenimiento y backup:
- `backup_cluster.py` - Backup del cluster PostgreSQL
- `sync_cluster_to_local.py` - Sincronizar cluster a local
- `analyze_cluster.py` - Análisis del cluster

### `scripts/migration/`
Scripts de migración de datos:
- `migrate_novus_points.py` - Migrar puntos Novus
- `migrate_twin_points.py` - Migrar puntos Twin
- `cleanup_old_getters.py` - Limpieza de código legacy

### `scripts/setup/`
Scripts de configuración inicial:
- `create_superuser.py` - Crear superusuario
- `create_sample_providers.py` - Crear proveedores de prueba

### `scripts/testing/`
Scripts de testing y validación:
- `test_compatibility_providers.py` - Test de compatibilidad
- `test_novus_dynamic.py` - Test sistema Novus
- `test_twin_dynamic.py` - Test sistema Twin
- Otros tests...

## Docker (`docker/`)

- `Dockerfile` - Imagen principal
- `Dockerfile.production` - Imagen de producción
- `Dockerfile.mqtt` - Imagen MQTT broker
- `docker-compose.dev.yml` - Compose para desarrollo
- `docker-compose.production.yml` - Compose para producción
- `docker-compose.monitoring.yml` - Compose para monitoreo
- `docker-compose.celery.yml` - Compose para Celery

## Documentación (`docs/`)

### `docs/analysis/`
Análisis y auditorías:
- `AUDITORIA_COMPLETA_API.md`
- `COMPATIBILIDAD_PROVEEDORES_ANALYSIS.md`
- `GEMINI.md`

### Otras secciones
- `guides/` - Guías de uso
- `migration/` - Documentación de migraciones
- `plans/` - Planes de implementación

## Configuración (`config/`)

- `gunicorn_config.py` - Configuración Gunicorn
- `nginx.production.conf` - Configuración Nginx
- `mosquitto.conf` - Configuración MQTT
- `dev_config.sh` - Variables de desarrollo
- Otros archivos de configuración...

## Monitoreo (`monitoring/`)

- `prometheus/` - Configuración de Prometheus
- `grafana/` - Dashboards y provisioning de Grafana
- `alertmanager/` - Configuración de alertas

## Notas Importantes

1. **dev_data/** está en `.gitignore` - No se sube al repositorio
2. Las apps de Django están en `api/`, NO en la raíz
3. Todos los scripts están organizados en `scripts/` por categoría
4. Los archivos Docker están en `docker/` para mantener orden
5. La documentación está centralizada en `docs/`
