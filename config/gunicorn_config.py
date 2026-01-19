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
# Optimizado para mejor rendimiento en telemetría de alto volumen
workers = (multiprocessing.cpu_count() * 2) + 1  # Dinámico basado en CPU

# Threads por worker (opcional, para I/O bound operations)
threads = 4  # Habilitar Multi-threading para mejor I/O handling

# Worker class: sync (default) o gevent/eventlet para async
worker_class = "gthread"  # Cambiar sync por gthread

# Timeout optimizado para telemetría (no tan largo para evitar bloqueos)
timeout = 30  # Reducido para mejor responsiveness

# Keepalive: tiempo que el worker mantiene conexiones abiertas
keepalive = 5

# Preload app: carga la aplicación antes de forking workers
# Reduce uso de memoria y mejora startup time
preload_app = True

# Max requests per worker before restart (previene memory leaks)
max_requests = 1000
max_requests_jitter = 50

# Worker connections para mejor manejo de concurrent requests
worker_connections = 1000

# Logging
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# Procesos de gestión
max_requests = 1000  # Reiniciar worker después de N requests (previene memory leaks)
max_requests_jitter = 50  # Variación aleatoria para evitar reinicios simultáneos

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

