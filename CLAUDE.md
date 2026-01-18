# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SmartHydro** is a hydrological monitoring and telemetry system with ultra-secure configuration, built with Django REST Framework and PostgreSQL. It continuously monitors water catchment points, integrates with external services (DGA, SMA), generates alerts, and produces PDF/Excel reports.

### Key Characteristics

- **REST API**: Django REST Framework with token authentication
  - Legacy API: `/api/` - Full REST endpoints via DefaultRouter
  - Optimized API: `/api/ik/` - Batch endpoints (`batch/telemetry/`, `batch/stats/`, `login/`)
- **Telemetry Engine**: Multiple concurrent data ingestion pipelines (TData TWIN, NETTRA, NOVUS) with unified processing controllers
- **Dual Container Architecture**: Separate containers for Django API and Cron jobs, both sharing the same codebase
- **Scheduled Tasks**: Django-crontab for automated data processing and transmission (runs in dedicated cron container)
- **Data Integrations**: DGA (Chilean water authority) and SMA (water quality service) with voucher tracking
- **Reporting**: PDF and Excel generation with complex filtering and calculations
- **Admin Dashboard**: Django admin with Jazzmin UI and custom telemetry monitoring views
- **Monitoring System**: Prometheus + Grafana for real-time metrics, alerts, and dashboards

## Development Commands

### Local Development Setup

```bash
# Install dependencies
pip install -r api/requirements.txt

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run development server
python manage.py runserver 0.0.0.0:8000
```

### Building and Deployment

```bash
# ========================================
# REBUILD SOLO API (lo más común)
# ========================================
# Usar cuando: cambios en código Python, templates, serializers, views, etc.
# NO afecta: postgres, nginx_proxy, letsencrypt, redis, cron

docker-compose -f docker-compose.production.secure.yml build django && \
docker-compose -f docker-compose.production.secure.yml up -d --no-deps django && \
docker logs django_api_secure --tail=30

# ========================================
# REBUILD SOLO CRON (cambios en cronjobs)
# ========================================
# Usar cuando: cambios en api/cronjobs/*, telemetry, DGA, SMA, alerts

docker-compose -f docker-compose.production.secure.yml build cron && \
docker-compose -f docker-compose.production.secure.yml up -d --no-deps cron && \
docker logs cron_jobs_secure --tail=30

# ========================================
# REBUILD API + CRON (cambios compartidos)
# ========================================
# Usar cuando: cambios en models, settings, o código usado por ambos

docker-compose -f docker-compose.production.secure.yml build django cron && \
docker-compose -f docker-compose.production.secure.yml up -d --no-deps django && \
docker-compose -f docker-compose.production.secure.yml up -d --no-deps cron && \
docker-compose -f docker-compose.production.secure.yml ps

# ========================================
# REINICIO RÁPIDO (sin rebuild, solo restart)
# ========================================
# Usar cuando: el código no cambió, solo quieres reiniciar el servicio

# Solo API
docker-compose -f docker-compose.production.secure.yml restart django

# Solo Cron
docker-compose -f docker-compose.production.secure.yml restart cron

# Ambos
docker-compose -f docker-compose.production.secure.yml restart django cron

# ========================================
# VER ESTADO Y LOGS
# ========================================
docker-compose -f docker-compose.production.secure.yml ps
docker logs django_api_secure --tail=50
docker logs cron_jobs_secure --tail=50
docker logs -f django_api_secure                                    # Logs en tiempo real
docker exec cron_jobs_secure tail -f /tmp/smarthydro/dga.log        # Logs DGA

# ========================================
# COMANDOS DE EMERGENCIA
# ========================================

# Si django no arranca
docker logs django_api_secure 2>&1 | tail -100

# Si cron no funciona, reinstalar cronjobs
docker exec cron_jobs_secure python manage.py crontab remove
docker exec cron_jobs_secure python manage.py crontab add
docker exec cron_jobs_secure crontab -l

# ========================================
# DEPLOY COMPLETO (solo primera vez o cambios mayores)
# ========================================
sudo mkdir -p /opt/smarthydro/{postgres_data,postgres_logs,django_static,django_media,django_logs,cron_logs}
sudo chown -R 1000:1000 /opt/smarthydro/django_*
sudo chown -R 999:999 /opt/smarthydro/postgres_*
docker-compose -f docker-compose.production.secure.yml build
docker-compose -f docker-compose.production.secure.yml up -d
```

**NUNCA hacer:**
- `docker-compose down` - para y borra contenedores (innecesario para deploy)
- `docker-compose up -d --force-recreate` - recrea TODOS los contenedores
- `docker-compose down --volumes` - BORRA TODOS LOS DATOS
- Rebuild de `postgres` sin backup previo

### Monitoring System (Prometheus + Grafana)

```bash
# ========================================
# INICIO RÁPIDO
# ========================================
./start_monitoring.sh

# El script automáticamente:
# - Crea la red Docker si no existe
# - Conecta Django a la red de monitoreo
# - Levanta Prometheus, Grafana, Alertmanager, Node Exporter
# - Verifica que el endpoint /metrics/ funcione

# ========================================
# ACCESO A DASHBOARDS
# ========================================
# Grafana: http://localhost:3000
#   Usuario: admin
#   Password: smarthydro2026
#
# Prometheus: http://localhost:9090
# Alertmanager: http://localhost:9093

# ========================================
# COMANDOS ÚTILES
# ========================================
# Ver estado de servicios
docker-compose -f docker-compose.monitoring.yml ps

# Ver logs
docker logs -f smarthydro_prometheus
docker logs -f smarthydro_grafana

# Detener monitoreo
docker-compose -f docker-compose.monitoring.yml down

# Documentación completa
cat monitoring/README.md
```

**Dashboards Incluidos:**
- **Telemetría General**: Caudal, totales, consumo diario por punto
- **Monitoreo DGA**: Registros pendientes, transmisiones, errores
- **Infraestructura**: CPU, memoria, disco, red, I/O

**Alertas Configuradas:**
- Puntos offline (>2h, >24h)
- Errores de ingestión
- Registros DGA acumulados
- Alta carga del sistema
- Django caído

### Management Commands

```bash
# Django management commands (custom)
python manage.py recalc_totals --points=123,456     # Recalculate totals for specific points
python manage.py recalc_totals --points=123 --dry-run  # Preview changes without saving
python manage.py recalc_totals --points=123 --from-datetime=2025-01-01 --to-datetime=2025-01-31
python manage.py analyze_caudal_dga                 # Analyze flow data against DGA standards
python manage.py inspect_point --point=123          # Debug data for specific point
python manage.py inspect_point --point=123 --limit=20  # Show more records
python manage.py find_points                        # Search points by criteria

# Cron job management
python manage.py crontab add              # Install scheduled jobs
python manage.py crontab show             # List installed cron jobs
python manage.py crontab remove           # Remove all cron jobs
```

### Running Tests

```bash
# Run all tests
python manage.py test tests/

# Run specific test module
python manage.py test tests.dga.test_caudal_calculations       # DGA calculation tests
python manage.py test tests.regression.test_dga_send           # DGA sending tests
python manage.py test tests.regression.test_cronjobs_unchanged # Cronjob regression tests

# Run single test class or method
python manage.py test tests.dga.test_caudal_calculations.CaudalCalculationsTests
python manage.py test tests.dga.test_caudal_calculations.CaudalCalculationsTests.test_calculate_daily_average_flow_medio

# Run with verbose output
python manage.py test tests/ -v 2
```

## Architecture Overview

### Directory Structure

```
api/
├── core/              # Main Django app
│   ├── models/        # Database models (CatchmentPoint, InteractionDetail, etc.)
│   ├── views/         # API viewsets (REST endpoints)
│   ├── serializers/   # Data serializers for API requests/responses
│   ├── admin.py       # Django admin customizations
│   ├── admin_views.py # Custom admin dashboard and telemetry views
│   ├── reports/       # PDF/Excel report generation
│   ├── utils/         # Utility functions and validators
│   ├── signals/       # Django signals for data consistency
│   └── management/    # Custom management commands
│
├── cronjobs/          # Scheduled task workers
│   ├── telemetry/     # Real-time data ingestion
│   │   ├── twin.py           # TWIN 60-min ingestion (hourly at :00)
│   │   ├── twin_f1.py        # TWIN 1-min ingestion (every minute)
│   │   ├── twin_f5.py        # TWIN 5-min ingestion (every 5 mins)
│   │   ├── nettra.py         # NETTRA data ingestion
│   │   ├── novus.py          # NOVUS data ingestion
│   │   └── controllers/      # Unified telemetry processing
│   │       ├── flow.py       # Caudal/flow calculations
│   │       ├── total.py      # Daily total aggregations
│   │       └── unified_processing.py # Main pipeline orchestrator
│   │
│   ├── dga/           # DGA integration (Chilean water authority)
│   │   ├── cron_dga.py        # Scheduled DGA data transmission
│   │   ├── send_data_dga.py   # DGA API client
│   │   └── caudal_calculations.py # DGA-specific calculations
│   │
│   ├── sma/           # SMA integration (water quality service)
│   │   └── cron_sma.py        # Scheduled SMA data transmission
│   │
│   └── alerts/        # Email alert system
│
├── settings.py        # Django configuration
├── urls.py           # URL routing configuration
├── wsgi.py           # WSGI entry point for Gunicorn
├── asgi.py           # ASGI entry point (async)
└── requirements.txt  # Python dependencies

docker-compose.production.secure.yml  # Production deployment config
docker-entrypoint.sh                  # Container startup script
Dockerfile                            # App container build
gunicorn_config.py                    # Gunicorn WSGI server config
manage.py                             # Django CLI
```

### Key Models

- **CatchmentPoint**: Water catchment measurement points with metadata
- **InteractionDetail**: Individual telemetry records with flow/level measurements
- **DgaDataConfigCatchment**: DGA transmission configuration per point
- **ProfileIkoluCatchment**: User access profiles and permissions

### Data Flow

1. **Ingestion**: External services (TWIN, NETTRA, NOVUS) push data to REST API
2. **Processing**: Telemetry controllers calculate flow, totals, and quality metrics
3. **Storage**: Data stored in PostgreSQL with timestamps for auditing
4. **Transmission**: Scheduled DGA/SMA exports with voucher tracking
5. **Reporting**: PDF/Excel generation on-demand with filtered data

### Scheduled Jobs (Django-Crontab)

Defined in `api/settings.py` CRONJOBS list:

- **twin.run()** - Every hour at :00 (60-min data)
- **twin_f1.run()** - Every minute (1-min data)
- **twin_f5.run()** - Every 5 minutes (5-min data)
- **twin_f10.run()** - Every 10 minutes (10-min data)
- **nettra.run()** / **nettra_f5.run()** - NETTRA hourly and 5-min ingestion
- **novus.run()** - NOVUS hourly ingestion
- **cron_dga.run()** - Every 3 minutes (DGA transmission queue)
- **cron_sma.run()** - Every 5 minutes (SMA transmission queue)
- **cron_alerts.run()** - Every 10 minutes (email alerts)
- **cluster_backup_complete_final.run()** - Every hour (cluster backup/sync)

Each cronjob writes logs to `/tmp/smarthydro/*.log`

## Important Configuration

### Environment Variables (Required for Production)

```env
# Security
DJANGO_SECRET_KEY=<your-secret-key>
DJANGO_DEBUG=False

# Database
LOCAL_DB_PASSWORD=<postgres-password>
CLUSTER_DB_HOST=<cluster-postgres-host>
CLUSTER_DB_PASSWORD=<cluster-password>

# Domain
VIRTUAL_HOST=api.smarthydro.app
LETSENCRYPT_EMAIL=admin@smarthydro.app

# Email (for alerts)
EMAIL_HOST=<smtp-server>
EMAIL_PORT=465
EMAIL_HOST_USER=notify@smarthydro.app
EMAIL_HOST_PASSWORD=<smtp-password>

# Feature flags
USE_NEW_CAUDAL_CALCULATION_MEDIO=True  # Control flow calculation method (default: True)
```

### Critical Files

- **api/settings.py** - Django config, CRONJOBS, email, security settings
- **docker-compose.production.secure.yml** - Network isolation, volumes, health checks
- **docker-entrypoint.sh** - Container startup orchestration for Django and Cron
- **api/core/admin_views.py** - Admin dashboard with telemetry monitoring (70KB file)

## Development Patterns

### Adding New REST Endpoints

1. Create view in `api/core/views/` extending `ViewSet`
2. Register in `api/core/router.py` with DefaultRouter (URL prefix is auto-generated from basename)
3. Define serializer in `api/core/serializers/`
4. Add filtering/permissions as needed

Legacy API endpoints are mounted under `/api/` (see `api/urls.py` and `api/core/router.py`).
Optimized batch endpoints are under `/api/ik/` (see `api/api_ik/routes.py`).

### Adding New Cronjob

1. Create function or class in `api/cronjobs/telemetry/` or subdirectory
2. Implement `run()` function that can be called by cron
3. Add to CRONJOBS in `api/settings.py` with schedule expression
4. Write logs to `/tmp/smarthydro/` directory
5. Handle errors gracefully (exceptions logged, process continues)

### Processing Telemetry Data

Use unified_processing.py controller which orchestrates:
1. Data validation and cleaning
2. Flow calculations (caudal)
3. Total aggregations (daily sums)
4. Quality checks and alerts
5. DGA/SMA format compliance

### Report Generation

- **PDF Reports**: `api/reports/pdf_generator.py` with ReportLab
- **Excel Reports**: `api/reports/excel_generator.py` with openpyxl
- Filters applied in serializers before export

## Common Tasks

### Debugging Telemetry Issues

```bash
# Check specific point's recent data
python manage.py inspect_point --point=123

# View cron job logs
tail -f /tmp/smarthydro/twin_60.log
tail -f /tmp/smarthydro/dga.log

# Check Django application logs
docker logs <container-id>
```

### Manually Recalculating Data

```bash
# Recalculate totals for specific points
python manage.py recalc_totals --points=123 --dry-run  # Preview first
python manage.py recalc_totals --points=123,456        # Apply changes

# Recalculate for date range
python manage.py recalc_totals --points=123 --from-datetime=2025-01-01 --to-datetime=2025-01-31
```

### Database Access

```bash
# PostgreSQL is running in Docker, NOT directly exposed
# Access via Docker exec or through Django ORM
docker exec postgres_container psql -U postgres -d smarthydro -c "SELECT * FROM core_catchmentpoint LIMIT 5;"
```

## Important Notes

### DGA Integration Complexity

DGA transmission has complex business logic around:
- **Standard types** (MAYOR, MEDIO, MENOR, CAUDALES_MUY_PEQUENOS, SIN_ESTANDAR)
- **Frequency requirements** (hourly, daily, monthly, biannual)
- **Voucher tracking** - Confirms successful transmission to Chilean authority
- **Data validation** - Must pass DGA format requirements before transmission

When modifying DGA logic, verify against standards in `caudal_calculations.py`.

### Admin Dashboard

The custom admin dashboard (`admin_views.py`) provides real-time telemetry monitoring with:
- Live point status and last data received
- Recent records table filtered by DGA standard
- Alert status and email notifications

The admin uses **django-jazzmin** for enhanced UI styling. Jazzmin must be listed BEFORE `django.contrib.admin` in `INSTALLED_APPS` (see `api/settings.py`). Custom admin routes are defined in `api/urls.py` and must appear BEFORE `admin.site.urls`.

### Security

- PostgreSQL runs in isolated Docker network (not exposed)
- SSL/TLS handled by Let's Encrypt nginx-proxy companion
- Token authentication for API endpoints
- Django security headers enforced (HSTS, CSP, etc.)
- Minimal user permissions model in place

### Performance Considerations

- Gunicorn runs with `(2 * CPU_COUNT) + 1` workers
- Static files served by Nginx with WhiteNoise fallback
- Django-crontab runs in separate container/process
- Large Excel reports may timeout - adjust settings.py request timeout if needed
- Batch operations on InteractionDetail (millions of records) can be slow

## Testing Strategy

Test suites are organized under `tests/`:
- **tests/dga/**: DGA calculation and formatting validation (`test_caudal_calculations.py`)
- **tests/regression/**: Prevent breaking changes
  - `test_cronjobs_unchanged.py` - Cronjob configuration regression
  - `test_endpoints_unchanged.py` - API endpoint regression
  - `test_dga_send.py` - DGA transmission logic
  - `test_dga_error_mapping.py` - DGA error code handling
  - `test_fpc_block.py` - FPC blocking logic

All tests use Django's test database and do not touch production data.
