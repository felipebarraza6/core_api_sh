# 🌊 SmartHydro

Sistema de monitoreo hidrológico y telemetría para la gestión inteligente de recursos hídricos.

## Descripción

SmartHydro es una plataforma integral para:

- **Monitoreo en tiempo real** de puntos de captación de agua
- **Telemetría automatizada** desde dispositivos TWIN, NETTRA y NOVUS
- **Integración regulatoria** con DGA (Dirección General de Aguas) y SMA
- **Alertas inteligentes** basadas en umbrales configurables
- **Reportes automatizados** en PDF y Excel
- **Panel administrativo** moderno con django-unfold

## 🚀 Tecnologías

- **Backend**: Django 4.2, Django REST Framework
- **Base de Datos**: PostgreSQL
- **Servidor**: Gunicorn + Nginx
- **Contenedores**: Docker + Docker Compose
- **Tareas Programadas**: django-crontab (contenedor dedicado)
- **Telemetría**: APIs REST propias + integración con dispositivos IoT

## 📦 Instalación Local

```bash
# Clonar repositorio
git clone <repo-url>
cd core_api_sh

# Crear y activar entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r api/requirements.txt

# Configurar variables de entorno
cp .env.example .env  # Editar con tus valores

# Crear la base de datos y cargar el dump de desarrollo
# (esquema completo + configuración + mediciones del último mes)
createdb smarthydro_dev
gunzip -c dev_database.sql.gz | psql -d smarthydro_dev

# (Alternativa) Si prefieres migrar desde cero:
python manage.py migrate

# Crear superusuario
python manage.py createsuperuser

# Iniciar servidor
python manage.py runserver
```

### 🗄️ Base de Datos de Desarrollo

El repositorio incluye `dev_database.sql.gz`, un dump listo para clonar
y levantar un entorno de desarrollo al instante:

- **Esquema completo** de la base de datos (tablas, índices, FKs, migraciones)
- **Configuración completa** (clientes, puntos de captación, usuarios, tickets, catálogos)
- **Mediciones del último mes** de `core_interactiondetail` y `django_admin_log`

```bash
# Restaurar el dump en una base PostgreSQL local
createdb smarthydro_dev
gunzip -c dev_database.sql.gz | psql -d smarthydro_dev

# Configurar el .env apuntando a esa base
LOCAL_DB_NAME=smarthydro_dev

# Regenerar el dump desde producción cuando quieras datos frescos
source .env  # o exporta LOCAL_DB_HOST, LOCAL_DB_USER, LOCAL_DB_PASSWORD
python scripts/generate_dev_dump.py
```

## 🧪 Tests

```bash
# Ejecutar todos los tests
python manage.py test

# Tests de regresión (validan compatibilidad API)
python manage.py test tests.regression

# Tests específicos DGA
python manage.py test tests.dga
```

## 🐳 Docker (Producción)

```bash
# Levantar toda la stack
docker-compose -f docker-compose.production.secure.yml up -d

# Ver estado
docker-compose -f docker-compose.production.secure.yml ps

# Logs
docker logs -f smarthydro_api_secure
docker logs -f cron_jobs_secure
```

## 📚 Documentación

- [Guía Frontend - Login](docs/GUIA_FRONTEND_LOGIN.md)
- [Guía Frontend - Alertas](docs/GUIA_FRONTEND_ALERTAS.md)
- [Guía Frontend - Reportes](docs/GUIA_FRONTEND_REPORTES.md)
- [Análisis del Sistema Completo](docs/FULL_SYSTEM_ANALYSIS.md)
- [Migración Cloudflare](docs/CLOUDFLARE_MIGRATION.md)

## 🔒 Seguridad

- Nunca subir el archivo `.env` al repositorio
- Las credenciales se gestionan mediante variables de entorno
- CSP, CORS y headers de seguridad configurados para producción

## 📄 Licencia

Ver archivo [LICENSE](LICENSE)
