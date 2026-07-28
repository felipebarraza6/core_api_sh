"""Tareas de health check para Celery."""

import logging

from api.celery import app


logger = logging.getLogger(__name__)


@app.task(bind=True, max_retries=3, default_retry_delay=10)
def ping_celery(self):
    """
    Tarea de prueba que confirma que Celery puede recibir y ejecutar jobs.

    Returns:
        dict: {"pong": True, "task_id": <id>}
    """
    logger.info("Celery ping recibido, task_id=%s", self.request.id)
    return {"pong": True, "task_id": self.request.id}
