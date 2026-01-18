# Manual de Operaciones y Control de Tareas

## 1. Control de Tareas (Activar/Desactivar)

Ahora que hemos migrado a **Celery + Redis**, tienes control total sobre las tareas programadas desde el panel de administración de Django.

### Pasos para gestionar tareas:
1.  Ingresa al Admin: `https://api.smarthydro.app/admin/`
2.  Busca la sección **"Periodic Tasks"** (o "Tareas Periódicas").
3.  Aquí verás la lista de todas las tareas (Telemetría, DGA, Reportes, etc.).
4.  Para **desactivar** una tarea:
    *   Haz clic en la tarea (ej: `collect-telemetry-1min`).
    *   Desmarca la casilla **"Enabled"**.
    *   Guarda. La tarea dejará de ejecutarse inmediatamente.
5.  Para **cambiar la frecuencia**:
    *   Edita el "Interval Schedule" o "Crontab Schedule" asociado.

## 2. Monitoreo y Métricas (Prometheus) 📊

Hemos integrado **Prometheus** para monitorear la salud de la API en tiempo real.

### Acceso a Métricas
*   **Endpoint de Métricas:** `https://api.smarthydro.app/metrics`
*   **Prometheus Dashboard:** `http://localhost:9090` (Si tienes acceso al puerto)
*   **Formato:** Texto plano compatible con Prometheus Scraper.

### Qué se monitorea:
*   **Latencia de Requests:** Tiempo de respuesta por endpoint.
*   **Conteo de Requests:** Total de peticiones HTTP (200, 400, 500).
*   **Base de Datos:** Tiempos de consulta SQL.
*   **Sistema:** Uso de memoria y CPU del contenedor (si está configurado el exporter de nodo).

Para visualizar estos datos, asegúrate de que tu instancia de **Grafana** esté apuntando a este endpoint como un *Data Source*.

## 3. Dónde ver los Logs

Ya no existen los archivos dispersos en `/tmp/smarthydro/*.log`. Ahora todo está centralizado.

### Opciones para ver logs:

**Opción A: Logs del Servidor (Docker)**
Si tienes acceso a la terminal del servidor:
```bash
# Ver logs de ejecución de tareas en tiempo real
docker logs -f smarthydro_celery_1

# Ver logs de la API web
docker logs -f smarthydro_api_1
```

**Opción B: Archivo de Logs Centralizado**
El sistema escribe todos los eventos importantes en un solo archivo rotativo:
*   **Ruta:** `/app/logs/django.log` (dentro del contenedor)
*   **Contenido:** Errores de tareas, confirmaciones de envío DGA, alertas generadas, etc.

Para verlo desde fuera (si el volumen está montado):
```bash
tail -f logs/django.log
```

## 4. Verificación de Estado

Para saber si el sistema está "sano":

1.  **Cola de Tareas:**
    En el Admin, si instalas una herramienta como `django-celery-results`, podrás ver el historial de ejecuciones (Éxito/Fallo).

2.  **Redis (Broker):**
    Asegúrate que el contenedor de Redis esté corriendo (`docker ps`).

## 5. Resumen de Tareas Migradas

| Tarea Antigua (Crontab) | Nueva Tarea (Celery) | Función |
|-------------------------|----------------------|---------|
| `twin_*.py` (T-Data) | `collect-telemetry` | Recolección de datos de sensores |
| `cron_dga.py` | `process-dga-queue` | Envío de datos a la DGA |
| `cron_sma.py` | `process-sma-queue` | Envío de datos a la SMA |
| `daily_bulletin.py` | `generate-daily-bulletin` | Generación de boletín PDF |
| `cluster_backup...` | `cluster-sync` | Sincronización de respaldo DB |

---
**Nota:** Al usar `DatabaseScheduler`, la configuración en `settings.py` sirve como base, pero la "verdad" está en la base de datos. Si cambias algo en el código, asegúrate de reflejarlo en el Admin si es necesario.
