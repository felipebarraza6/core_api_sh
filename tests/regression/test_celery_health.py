"""
Tests de regresión para el health check de Celery.

No requieren un worker real: se mockea la tarea ping_celery.
"""
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


User = get_user_model()


@override_settings(CACHES={
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
})
class CeleryHealthRegressionTests(TestCase):
    """Validar endpoint /health/celery/."""

    def setUp(self):
        self.client = APIClient()

    def test_celery_health_ok(self):
        """Si Celery responde, el endpoint retorna 200."""
        fake_result = MagicMock()
        fake_result.get.return_value = {"pong": True, "task_id": "task-123"}

        with patch("api.core.views.health.ping_celery.delay", return_value=fake_result):
            response = self.client.get("/health/celery/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["celery"], "ok")
        self.assertTrue(data["result"])
        self.assertEqual(data["task_id"], "task-123")

    def test_celery_health_unavailable(self):
        """Si Celery no responde, el endpoint retorna 503 con estructura clara."""
        with patch(
            "api.core.views.health.ping_celery.delay",
            side_effect=Exception("broker unreachable")
        ):
            response = self.client.get("/health/celery/")

        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["celery"], "unavailable")
        self.assertIn("broker unreachable", data["error"])

    def test_basic_health_still_works(self):
        """El health check básico sigue funcionando."""
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "SmartHydro API")
