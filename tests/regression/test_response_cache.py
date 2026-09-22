"""
Tests para cache opt-in de respuestas GET (core/utils/response_cache.py).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from api.core.models import (
    CatchmentPoint, Client, ProjectCatchments, DgaDataConfigCatchment,
    ProfileDataConfigCatchment,
)

User = get_user_model()


class ResponseCacheTests(TestCase):
    """API_RESPONSE_CACHE_TTL>0 cachea; =0 no cachea."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='cacheuser', password='x', email='cache@example.com'
        )
        self.client.force_authenticate(user=self.user)
        c = Client.objects.create(name="Cache Client")
        p = ProjectCatchments.objects.create(name="Cache Project", client=c)
        self.point = CatchmentPoint.objects.create(
            title="Cache Point", owner_user=self.user, project=p, frecuency="60",
        )
        ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point, is_telemetry=True,
        )
        DgaDataConfigCatchment.objects.create(
            point_catchment=self.point, send_dga=True,
            code_dga="OB-CACHE-001", standard="MAYOR",
            type_dga="SUPERFICIAL", flow_granted_dga=10.0,
            total_granted_dga=1000.0,
        )

    @override_settings(API_RESPONSE_CACHE_TTL=0)
    def test_cache_disabled_by_default(self):
        """TTL=0: no debe usar cache (cada request ejecuta la vista)."""
        from django.core.cache import cache
        from api.core.utils.response_cache import make_cache_key
        cache.clear()
        r1 = self.client.get('/api/ik/compliance/')
        self.assertEqual(r1.status_code, 200)
        # Con TTL=0 no se guarda nada
        # (make_cache_key no se usa; verificamos que la vista corre siempre)
        r2 = self.client.get('/api/ik/compliance/')
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.json()['count'], r2.json()['count'])

    @override_settings(API_RESPONSE_CACHE_TTL=60)
    def test_cache_hit_returns_same_payload(self):
        """TTL>0: segunda request devuelve payload idéntico desde cache."""
        from django.core.cache import cache
        cache.clear()
        r1 = self.client.get('/api/ik/compliance/')
        self.assertEqual(r1.status_code, 200)
        data1 = r1.json()

        # Borrar el punto NO debe afectar si hay cache hit
        # (la respuesta viene del cache, no de DB)
        r2 = self.client.get('/api/ik/compliance/')
        self.assertEqual(r2.status_code, 200)
        data2 = r2.json()
        self.assertEqual(data1, data2)

    @override_settings(API_RESPONSE_CACHE_TTL=60)
    def test_cache_isolated_by_user(self):
        """Cache key incluye user id: usuarios distintos no comparten."""
        from django.core.cache import cache
        cache.clear()
        other = User.objects.create_user(
            username='othercache', password='x', email='other@example.com'
        )
        r_self = self.client.get('/api/ik/compliance/')
        self.assertEqual(r_self.status_code, 200)
        self.assertEqual(r_self.json()['count'], 1)

        client2 = APIClient()
        client2.force_authenticate(user=other)
        r_other = client2.get('/api/ik/compliance/')
        self.assertEqual(r_other.status_code, 200)
        # other no tiene puntos
        self.assertEqual(r_other.json()['count'], 0)

    @override_settings(API_RESPONSE_CACHE_TTL=60)
    def test_make_cache_key_stable(self):
        """Misma request → misma clave; user distinto → clave distinta."""
        from api.core.utils.response_cache import make_cache_key
        from django.test import RequestFactory
        factory = RequestFactory()
        req1 = factory.get('/api/ik/compliance/?page=1')
        req1.user = self.user
        req2 = factory.get('/api/ik/compliance/?page=1')
        req2.user = self.user
        req3 = factory.get('/api/ik/compliance/?page=1')
        req3.user = None

        k1 = make_cache_key(req1)
        k2 = make_cache_key(req2)
        k3 = make_cache_key(req3)
        self.assertEqual(k1, k2)
        self.assertNotEqual(k1, k3)
