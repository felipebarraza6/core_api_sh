"""
Tests de regresión para locks distribuidos (puntos y cronjobs globales)
=======================================================================

Valida que acquire_point_lock, release_point_lock, acquire_cron_lock,
release_cron_lock y el decorador cron_job_lock funcionen correctamente.
"""

from django.test import TestCase
from django.core.cache import cache

from api.cronjobs.telemetry.utils.locks import (
    acquire_point_lock,
    release_point_lock,
)
from api.cronjobs.utils.locks import (
    acquire_cron_lock,
    release_cron_lock,
    cron_job_lock,
)


class LockRegressionTests(TestCase):
    """Tests para locks Redis con fallback seguro."""

    def setUp(self):
        """Limpiar locks antes de cada test."""
        cache.clear()

    def test_point_lock_acquire_and_release(self):
        """Adquirir y liberar lock de punto funciona."""
        self.assertTrue(acquire_point_lock(9999, timeout=10))
        # Segundo intento debe fallar (ya bloqueado)
        self.assertFalse(acquire_point_lock(9999, timeout=10))
        release_point_lock(9999)
        # Después de liberar, debe poder adquirirse de nuevo
        self.assertTrue(acquire_point_lock(9999, timeout=10))
        release_point_lock(9999)

    def test_cron_lock_acquire_and_release(self):
        """Adquirir y liberar lock de cronjob funciona."""
        self.assertTrue(acquire_cron_lock("test_job", timeout=10))
        self.assertFalse(acquire_cron_lock("test_job", timeout=10))
        release_cron_lock("test_job")
        self.assertTrue(acquire_cron_lock("test_job", timeout=10))
        release_cron_lock("test_job")

    def test_cron_job_lock_decorator_skips_when_locked(self):
        """El decorador salta ejecución si el job ya está bloqueado."""
        call_count = 0

        @cron_job_lock("decorated_test", timeout=10)
        def dummy_job():
            nonlocal call_count
            call_count += 1
            return {"ran": True}

        # Primera ejecución debe correr y liberar lock al terminar
        result1 = dummy_job()
        self.assertEqual(result1, {"ran": True})
        self.assertEqual(call_count, 1)

        # Simular lock tomado por otra instancia (ej. otro proceso)
        acquire_cron_lock("decorated_test", timeout=60)

        # Segunda ejecución debe saltar porque el lock está activo
        result2 = dummy_job()
        self.assertEqual(result2, {"skipped": True, "reason": "locked", "job": "decorated_test"})
        self.assertEqual(call_count, 1)  # No incrementó

        # Liberar lock y ejecutar de nuevo
        release_cron_lock("decorated_test")
        result3 = dummy_job()
        self.assertEqual(result3, {"ran": True})
        self.assertEqual(call_count, 2)

    def test_cron_job_lock_decorator_releases_on_exception(self):
        """El decorador libera el lock incluso si la función lanza excepción."""
        @cron_job_lock("exception_test", timeout=10)
        def failing_job():
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            failing_job()

        # El lock debe haberse liberado en el finally
        self.assertTrue(acquire_cron_lock("exception_test", timeout=10))
        release_cron_lock("exception_test")
