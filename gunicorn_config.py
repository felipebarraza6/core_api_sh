"""
Configuración de Gunicorn para producción
Optimizado para mejor rendimiento y auto-detección de workers
"""
import multiprocessing
import os

# Directorio base de la aplicación
# Nota: El puerto se especifica en el CMD del Dockerfile (8000)
# Nginx hace proxy desde puerto 80 a este puerto
bind = "0.0.0.0:8000"

# Workers auto-detectados: (2 * CPU_COUNT) + 1
# Limitado a 3 workers para no exceder el límite de memoria del contenedor (3G).
# Con gthread: 3 workers * 3 threads = 9 requests concurrentes.
workers = 3

# Threads por worker (opcional, para I/O bound operations)
threads = 3  # Habilitar Multi-threading para mejor I/O handling

# Worker class: sync (default) o gevent/eventlet para async
worker_class = "gthread"  # Cambiar sync por gthread

# Timeout para requests largos (dashboard, reportes grandes)
timeout = 120

# Keepalive: tiempo que el worker mantiene conexiones abiertas
keepalive = 5

# Preload app: carga la aplicación antes de forking workers
# Desactivado para evitar que todos los workers hereden el mismo estado
# en memoria y facilitar el reciclaje por max_requests.
preload_app = False

# Logging
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# Procesos de gestión
# Reiniciar worker después de N requests (previene memory leaks)
# Valor bajo para reciclar workers antes de que crezcan en memoria.
max_requests = 1000
max_requests_jitter = 200  # Variación aleatoria para evitar reinicios simultáneos

# Graceful timeout: tiempo para terminar workers gracefully
graceful_timeout = 30

# Worker connections (solo para async workers)
# worker_connections = 1000

# Statsd (opcional, para monitoreo)
# statsd_host = "localhost:8125"

# User/Group (opcional, para seguridad)
# user = "www-data"
# group = "www-data"

# PID file
pidfile = "/tmp/gunicorn.pid"

# Daemon mode (desactivado, Docker maneja esto)
daemon = False

# SSL (si se necesita en el futuro)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"

