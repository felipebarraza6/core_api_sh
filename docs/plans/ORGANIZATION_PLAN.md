# Plan de Organización y Mejoras del Proyecto SmartHydro

Este documento detalla el estado actual del proyecto y propone un plan de reestructuración para mejorar la mantenibilidad, escalabilidad y claridad del código.

## 1. Diagnóstico Actual

### Estructura de Directorios
- **Raíz**: Contiene múltiples scripts de despliegue (`deploy.*.sh`), archivos Docker, y configuraciones dispersas.
- **api/**: Contenedor principal del código Django.
  - **core/**: "Monolito" interno. Contiene lógica de Chatbot, Reportes, Gestión, y Modelos. Se está volviendo demasiado grande.
  - **api_ik/**: Módulo pequeño, propósito no claro (posiblemente integración específica).
  - **cronjobs/**: Scripts de tareas programadas que parecen estar separados de la estructura estándar de Celery/Django.
- **monitoring/**: Configuración de Prometheus y Grafana (Correcto).

### Problemas Identificados
1.  **Sobrecarga en `api/core`**: La aplicación `core` asume demasiadas responsabilidades (Chatbot, Reportes, Modelos, Tareas). Esto viola el principio de responsabilidad única.
2.  **Dualidad de Tareas**: Existen tareas en `api/core/tasks/` (Celery) y scripts en `api/cronjobs/`. Esto crea confusión sobre dónde debe ir la lógica de segundo plano.
3.  **Configuración de Monitoreo Rota**: `prometheus.yml` tenía errores de sintaxis y referencias a contenedores inexistentes (ya corregido).
4.  **Scripts en Raíz**: Demasiados scripts en la raíz del proyecto dificultan la navegación.

## 2. Plan de Reestructuración (Propuesta)

### Fase 1: Desacoplamiento de Aplicaciones (Alta Prioridad)
Dividir `api/core` en aplicaciones Django independientes para mejorar la modularidad.

-   **`api/chatbot/`**: Mover todo el contenido de `api/core/chatbot/` a una nueva app `chatbot`.
    -   *Beneficio*: Permite mantener la lógica del LLM y conversaciones aislada del núcleo de negocio.
-   **`api/reports/`**: Mover `api/core/reports/` a una nueva app `reports`.
    -   *Beneficio*: Centraliza la lógica de generación de PDFs y Excel.
-   **`api/telemetry/`**: Si `api/core/services/telemetry_service.py` y validadores crecen, considerar una app dedicada a la ingestión de datos.

### Fase 2: Unificación de Tareas en Segundo Plano (Media Prioridad)
Eliminar la ambigüedad entre `cronjobs/` y `tasks/`.

-   **Objetivo**: Migrar scripts de `api/cronjobs/` a tareas de Celery en sus respectivas apps (ej. `api/telemetry/tasks.py`).
-   **Acción**: Si se requieren cronjobs puros (crontab del sistema), usar Management Commands de Django (`manage.py run_my_cron`) en lugar de scripts sueltos, para aprovechar el contexto de Django correctamente.

### Fase 3: Limpieza de Raíz (Baja Prioridad)
-   Mover scripts `deploy.*.sh` y `monitor.*.sh` a una carpeta `scripts/deployment/`.
-   Mantener solo `docker-compose.yml`, `manage.py`, `Dockerfile` y `README.md` en la raíz.

## 3. Acciones Inmediatas Realizadas
-   [x] **Auditoría de Prometheus**: Se corrigió el archivo `monitoring/prometheus.yml` que causaba errores al iniciar por sintaxis YAML inválida y targets inexistentes.

## 4. Próximos Pasos Recomendados
1.  Confirmar si `api_ik` es necesario o si se puede integrar en otra app.
2.  Aprobar la creación de la app `chatbot` para mover el código.
3.  Revisar los logs de Celery para asegurar que las tareas actuales funcionan correctamente.
