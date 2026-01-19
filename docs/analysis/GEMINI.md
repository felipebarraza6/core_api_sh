# GEMINI.md: Project Overview

This document provides a comprehensive overview of the SmartHydro project, intended for developers and future interactions with the Gemini CLI.

## Project Overview

SmartHydro is a full-featured, security-focused hydrological monitoring system. It's a Django-based application designed for real-time telemetry, automatic alerts, and data integration with external services like DGA and SMA. The system is architected to be "ultra-secure," with a strong emphasis on preventing ransomware and unauthorized access.

The project is heavily containerized using Docker and Docker Compose, with separate configurations for development and production environments. It includes a complete suite of services for web serving, background task processing, messaging, and monitoring.

## Core Technologies

- **Backend:** Django, Django REST Framework
- **Database:** PostgreSQL 15
- **Task Queue:** Celery with Celery Beat for scheduled tasks
- **Cache & Message Broker:** Redis
- **Web Server:** Gunicorn (application server) proxied by Nginx (web server)
- **Real-time Communication:** MQTT Broker (Mosquitto)
- **Frontend:** Django templates with `django-jazzmin` for an enhanced admin interface.
- **Monitoring:** Prometheus and Grafana

## Project Structure Highlights

- `api/`: The main Django project directory.
  - `core/`: The core application with models, views, and business logic.
  - `telemetry/`: Handles data ingestion and processing.
  - `reports/`: Logic for generating reports (Excel, PDF).
  - `settings.py`: Main Django settings file.
  - `requirements.txt`: Python dependencies.
- `docker-compose.*.yml`: Docker Compose files for different environments (development, production, celery).
- `Dockerfile.*`: Dockerfiles for building the application containers.
- `conf/`: Configuration files for services like Nginx and Mosquitto.
- `scripts_utils/`: Utility scripts for deployment and development.
- `monitoring/`: Configuration for Prometheus and Grafana.

## Building and Running the Project

The project is designed to be run with Docker.

### Production

The primary method for deploying the application in a production environment is by using the provided shell script:

```bash
./deploy_production.sh
```

This script likely handles the setup of environment variables and runs `docker-compose` with the appropriate production configuration (`docker-compose.production.yml` and `docker-compose.production.secure.yml`).

### Development

A development environment can be started using `docker-compose.dev.yml`:

```bash
docker-compose -f docker-compose.dev.yml up
```

## Development Conventions

- **Security Focus:** The project emphasizes security, with isolated networks and an "ultra-secure" setup. Any changes should be made with security in mind.
- **Containerization:** All services are containerized. Development and testing should be done within the Docker environment to ensure consistency.
- **Environment Variables:** Configuration is managed through environment variables (e.g., via a `.env` file). See `env.production.example` for required variables.
- **Migrations:** Database schema changes are managed through Django migrations.
- **Static Files:** Static files are collected and served by Whitenoise in production.

## Key Commands

- **Run tests:**
  ```bash
  # TODO: Test command not explicitly found. A likely command is:
  docker-compose -f docker-compose.dev.yml exec django_app python manage.py test
  ```
- **Run database migrations:**
  ```bash
  docker-compose -f docker-compose.dev.yml exec django_app python manage.py migrate
  ```
- **Create a superuser:**
  ```bash
  docker-compose -f docker-compose.dev.yml exec django_app python manage.py createsuperuser
  ```
- **Deploy production changes:**
  ```bash
  ./deploy_production.sh
  ```
