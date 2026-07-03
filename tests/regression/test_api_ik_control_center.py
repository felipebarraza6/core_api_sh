import json
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from api.core.models import (
    CatchmentPoint, Client, ProjectCatchments,
    InteractionDetail, ProfileDataConfigCatchment,
    DgaDataConfigCatchment, SystemEvent,
    SchemesCatchment, Variable,
)

User = get_user_model()


@override_settings(CACHES={
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
})
class ControlCenterGeneralStatsTests(TestCase):
    """Tests para GET /api/ik/control_center/general_stats/"""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

        self.client = APIClient()

        # Superuser
        self.admin = User.objects.create_superuser(
            username='admin',
            password='admin123',
            email='admin@test.cl',
        )

        # Usuario normal
        self.user = User.objects.create_user(
            username='regular',
            password='pass123',
            email='regular@test.cl',
        )

        # Clientes y proyectos
        self.client_a = Client.objects.create(name="Cliente A")
        self.client_b = Client.objects.create(name="Cliente B")

        self.project_a = ProjectCatchments.objects.create(
            name="Proyecto Alpha", client=self.client_a
        )
        self.project_b = ProjectCatchments.objects.create(
            name="Proyecto Beta", client=self.client_b
        )
        self.project_c = ProjectCatchments.objects.create(
            name="Proyecto Gamma", client=None
        )

        # Puntos: user es owner de project_a, viewer de project_b, sin acceso a project_c
        self.point_a1 = CatchmentPoint.objects.create(
            title="Punto A1",
            owner_user=self.user,
            project=self.project_a,
            frecuency="60",
        )
        self.point_a2 = CatchmentPoint.objects.create(
            title="Punto A2",
            owner_user=self.user,
            project=self.project_a,
            frecuency="60",
        )
        self.point_b1 = CatchmentPoint.objects.create(
            title="Punto B1",
            owner_user=User.objects.create_user(username='other', password='x', email='other@test.cl'),
            project=self.project_b,
            frecuency="60",
        )
        self.point_b1.users_viewers.add(self.user)

        # Punto al que user NO tiene acceso (solo admin lo ve)
        self.point_c1 = CatchmentPoint.objects.create(
            title="Punto C1",
            owner_user=User.objects.create_user(username='other2', password='x', email='other2@test.cl'),
            project=self.project_c,
            frecuency="60",
        )

        # Telemetría en A1
        ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point_a1,
            is_telemetry=True,
        )
        # A2 sin telemetría
        # B1 con telemetría
        ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point_b1,
            is_telemetry=True,
        )

    def test_structure_admin(self):
        """Admin recibe todas las claves esperadas y NO last_7."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/ik/control_center/general_stats/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('points', data)
        self.assertIn('status_today', data)
        self.assertIn('projects', data)
        self.assertIn('chat_quota', data)
        self.assertNotIn('last_7', data)
        self.assertNotIn('count', data)
        self.assertNotIn('next', data)
        self.assertNotIn('previous', data)

        # Admin ve todos los puntos del sistema (a1, a2, b1, c1 = 4)
        self.assertEqual(data['points']['total'], 4)
        self.assertEqual(data['points']['with_telemetry'], 2)

    def test_structure_regular_user(self):
        """Usuario normal recibe solo sus puntos."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/ik/control_center/general_stats/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('points', data)
        self.assertIn('status_today', data)
        self.assertIn('projects', data)
        self.assertIn('chat_quota', data)
        self.assertNotIn('last_7', data)

        # User ve 3 puntos (A1 owner, A2 owner, B1 viewer)
        # project_c (C1) no tiene acceso
        # A1 con telemetría, A2 sin telemetría, B1 con telemetría
        self.assertEqual(data['points']['total'], 3)
        self.assertEqual(data['points']['with_telemetry'], 2)

    def test_projects_admin_sees_client_name(self):
        """Admin: projects incluye 'Proyecto - Cliente'."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/ik/control_center/general_stats/')
        data = response.json()

        project_names = {p['name'] for p in data['projects']}
        self.assertIn('Proyecto Alpha - Cliente A', project_names)
        self.assertIn('Proyecto Beta - Cliente B', project_names)
        # project_c no tiene cliente, solo nombre
        self.assertIn('Proyecto Gamma', project_names)

    def test_projects_regular_user_name_only(self):
        """Usuario normal: projects solo nombre, sin cliente."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/ik/control_center/general_stats/')
        data = response.json()

        project_names = {p['name'] for p in data['projects']}
        self.assertIn('Proyecto Alpha', project_names)
        self.assertIn('Proyecto Beta', project_names)
        # project_c no debe aparecer (user no tiene acceso)
        self.assertNotIn('Proyecto Gamma', project_names)
        # Sin sufijo - Cliente
        self.assertNotIn(' - ', ' '.join(project_names))

    def test_projects_list_shape(self):
        """projects es una lista de {id, name}."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/ik/control_center/general_stats/')
        data = response.json()

        self.assertIsInstance(data['projects'], list)
        for p in data['projects']:
            self.assertIn('id', p)
            self.assertIn('name', p)
            self.assertIsInstance(p['id'], int)
            self.assertIsInstance(p['name'], str)

    def test_status_today_structure(self):
        """status_today tiene connected y disconnected."""
        from datetime import date

        self.client.force_authenticate(user=self.user)

        # Crear telemetría hoy para A1
        from django.utils import timezone
        InteractionDetail.objects.create(
            catchment_point=self.point_a1,
            date_time_medition=timezone.now(),
            total="100",
        )

        response = self.client.get('/api/ik/control_center/general_stats/')
        data = response.json()

        status = data['status_today']
        self.assertIn('connected', status)
        self.assertIn('disconnected', status)

        # A1 connected, B1 disconnected (sin telemetría hoy)
        # with_telemetry = 2 (A1 + B1)
        self.assertEqual(status['connected'], 1)
        self.assertEqual(status['disconnected'], 1)

    def test_empty_user(self):
        """Usuario sin puntos ve todo en 0."""
        empty = User.objects.create_user(
            username='empty', password='x', email='empty@test.cl'
        )
        self.client.force_authenticate(user=empty)
        response = self.client.get('/api/ik/control_center/general_stats/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data['points']['total'], 0)
        self.assertEqual(data['points']['with_telemetry'], 0)
        self.assertEqual(data['points']['warnings'], 0)
        self.assertEqual(data['points']['with_compliance'], 0)
        self.assertEqual(data['status_today']['connected'], 0)
        self.assertEqual(data['status_today']['disconnected'], 0)
        self.assertEqual(data['projects'], [])
        self.assertIn('chat_quota', data)

    def test_warnings_count(self):
        """warnings refleja SystemEvent para los puntos del usuario."""
        from django.utils import timezone
        from datetime import timedelta

        SystemEvent.objects.create(
            point_catchment=self.point_a1,
            event_type="DISCONNECTION",
            severity="WARNING",
            title="Desconexión A1",
        )
        SystemEvent.objects.create(
            point_catchment=self.point_a2,
            event_type="RECONNECTION",
            severity="INFO",
            title="Reconexión A2",
        )
        # Punto fuera del alcance del user (no debe contarse)
        SystemEvent.objects.create(
            point_catchment=self.point_c1,
            event_type="COUNTER_RESET",
            severity="CRITICAL",
            title="Reset C1",
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/ik/control_center/general_stats/')
        data = response.json()

        # user ve 3 puntos (A1, A2, B1), solo A1 y A2 tienen eventos = 2
        self.assertEqual(data['points']['warnings'], 2)

    def test_unauthenticated_returns_401(self):
        """Sin token retorna 401."""
        response = self.client.get('/api/ik/control_center/general_stats/')
        self.assertEqual(response.status_code, 401)


@override_settings(CACHES={
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
})
class ControlCenterProjectPointsTests(TestCase):
    """Tests para GET /api/ik/control_center/project_points/"""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

        self.client = APIClient()

        self.admin = User.objects.create_superuser(
            username='admin3', password='admin123', email='admin3@test.cl',
        )
        self.user = User.objects.create_user(
            username='regular3', password='pass123', email='regular3@test.cl',
        )

        self.client_a = Client.objects.create(name="Cliente A")
        self.project_a = ProjectCatchments.objects.create(
            name="Proyecto Alpha", client=self.client_a
        )
        self.project_b = ProjectCatchments.objects.create(
            name="Proyecto Beta", client=self.client_a
        )

        self.point_a1 = CatchmentPoint.objects.create(
            title="Punto A1", owner_user=self.user, project=self.project_a, frecuency="60",
        )
        self.point_a2 = CatchmentPoint.objects.create(
            title="Punto A2", owner_user=self.user, project=self.project_a, frecuency="60",
        )
        self.point_b1 = CatchmentPoint.objects.create(
            title="Punto B1",
            owner_user=User.objects.create_user(username='other4', password='x', email='other4@test.cl'),
            project=self.project_b, frecuency="60",
        )
        self.point_b1.users_viewers.add(self.user)

        # DGA config con code_dga para point_a1
        DgaDataConfigCatchment.objects.create(
            point_catchment=self.point_a1,
            send_dga=True,
            code_dga="OB-0101-999",
        )

        # DGA config SIN code_dga para point_a2
        DgaDataConfigCatchment.objects.create(
            point_catchment=self.point_a2,
            send_dga=True,
            code_dga=None,
        )

    def _url(self, **params):
        qs = '&'.join(f'{k}={v}' for k, v in params.items()) if params else ''
        return f'/api/ik/control_center/project_points/?{qs}' if qs else '/api/ik/control_center/project_points/'

    def test_requires_project_id(self):
        """Sin project_id retorna 400."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/ik/control_center/project_points/')
        self.assertEqual(response.status_code, 400)

    def test_structure_admin(self):
        """Admin ve puntos del proyecto correctamente."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self._url(project_id=str(self.project_a.id)))
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('points', data)
        self.assertIsInstance(data['points'], list)

        # project_a tiene 2 puntos admin visibles (a1, a2)
        # project_b no
        self.assertEqual(len(data['points']), 2)

    def test_structure_regular_user(self):
        """Usuario normal ve solo sus puntos del proyecto."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self._url(project_id=str(self.project_a.id)))
        self.assertEqual(response.status_code, 200)

        data = response.json()
        # a1 owner, a2 owner
        self.assertEqual(len(data['points']), 2)

    def test_name_with_code_obra(self):
        """Punto con code_dga muestra 'nombre (codigo)'."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self._url(project_id=str(self.project_a.id)))
        data = response.json()

        # A1 tiene code_dga = OB-0101-999
        a1 = [p for p in data['points'] if p['id'] == self.point_a1.id][0]
        self.assertEqual(a1['name'], 'Punto A1 (OB-0101-999)')

    def test_name_without_code_obra(self):
        """Punto sin code_dga muestra solo nombre."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self._url(project_id=str(self.project_a.id)))
        data = response.json()

        # A2 tiene code_dga = None
        a2 = [p for p in data['points'] if p['id'] == self.point_a2.id][0]
        self.assertEqual(a2['name'], 'Punto A2')

    def test_empty_project_returns_empty_list(self):
        """Proyecto sin puntos visibles retorna lista vacía."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self._url(project_id='99999'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['points'], [])

    def test_unauthenticated_returns_401(self):
        """Sin token retorna 401."""
        response = self.client.get('/api/ik/control_center/project_points/?project_id=1')
        self.assertEqual(response.status_code, 401)


@override_settings(CACHES={
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
})
class ControlCenterListTests(TestCase):
    """Tests para GET /api/ik/control_center/list/"""

    URL = '/api/ik/control_center/list/'

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

        self.client = APIClient()

        self.admin = User.objects.create_superuser(
            username='admin_list', password='admin123', email='admin_list@test.cl',
        )
        self.user = User.objects.create_user(
            username='regular_list', password='pass123', email='regular_list@test.cl',
        )

        self.client_a = Client.objects.create(name="Cliente List")
        self.project_a = ProjectCatchments.objects.create(
            name="Proyecto List A", client=self.client_a
        )
        self.project_b = ProjectCatchments.objects.create(
            name="Proyecto List B", client=self.client_a
        )

        self.point_a1 = CatchmentPoint.objects.create(
            title="Alfa", owner_user=self.user, project=self.project_a, frecuency="60",
        )
        self.point_a2 = CatchmentPoint.objects.create(
            title="Beta", owner_user=self.user, project=self.project_a, frecuency="60",
        )
        self.point_b1 = CatchmentPoint.objects.create(
            title="Gamma",
            owner_user=User.objects.create_user(
                username='other_list', password='x', email='other_list@test.cl'
            ),
            project=self.project_b, frecuency="60",
        )
        self.point_b1.users_viewers.add(self.user)

        # Punto fuera del alcance del user
        self.point_hidden = CatchmentPoint.objects.create(
            title="Hidden",
            owner_user=User.objects.create_user(
                username='other_list2', password='x', email='other_list2@test.cl'
            ),
            project=self.project_b, frecuency="60",
        )

        # Telemetría en a1
        ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point_a1,
            is_telemetry=True,
        )

        self.test_date = '2026-01-15'

    def _add_telemetry(self, point, date_str, total_diff, flow=5.0, nivel=3.0, water_table=2.0, count=3):
        """Crea N registros de InteractionDetail para el punto en la fecha dada."""
        from django.utils.timezone import make_aware
        from datetime import datetime, timedelta
        base = datetime.fromisoformat(f"{date_str}T08:00:00")
        for i in range(count):
            dt = make_aware(base + timedelta(hours=i))
            InteractionDetail.objects.create(
                catchment_point=point,
                date_time_medition=dt,
                total_diff=total_diff,
                flow=flow,
                nivel=nivel,
                water_table=water_table,
            )

    def test_date_required(self):
        """Sin date retorna 400."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    def test_date_invalid_format(self):
        """Date con formato incorrecto retorna 400."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'{self.URL}?date=15-01-2026')
        self.assertEqual(response.status_code, 400)

    def test_unauthenticated_returns_401(self):
        """Sin token retorna 401."""
        response = self.client.get(f'{self.URL}?date={self.test_date}')
        self.assertEqual(response.status_code, 401)

    def test_structure_admin(self):
        """Admin recibe estructura correcta y ve todos los puntos."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'{self.URL}?date={self.test_date}')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('count', data)
        self.assertIn('next', data)
        self.assertIn('previous', data)
        self.assertIn('results', data)

        # Admin ve los 4 puntos
        self.assertEqual(data['count'], 4)

        # Validar campos del primer resultado
        r = data['results'][0]
        for field in ('point_id', 'point_name', 'project_id', 'project_name',
                      'is_telemetry', 'is_form', 'status', 'measurements_count',
                      'consumption', 'avg_flow', 'avg_level', 'water_table',
                      'variables', 'warnings_count'):
            self.assertIn(field, r, f"Campo '{field}' faltante en results[0]")

    def test_structure_regular_user(self):
        """Usuario normal ve solo sus puntos accesibles."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f'{self.URL}?date={self.test_date}')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        # a1 (owner), a2 (owner), b1 (viewer) = 3 puntos. hidden = fuera de alcance
        self.assertEqual(data['count'], 3)
        ids = {r['point_id'] for r in data['results']}
        self.assertIn(self.point_a1.id, ids)
        self.assertIn(self.point_a2.id, ids)
        self.assertIn(self.point_b1.id, ids)
        self.assertNotIn(self.point_hidden.id, ids)

    def test_filter_project_id(self):
        """project_id filtra correctamente."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            f'{self.URL}?date={self.test_date}&project_id={self.project_a.id}'
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data['count'], 2)
        ids = {r['point_id'] for r in data['results']}
        self.assertIn(self.point_a1.id, ids)
        self.assertIn(self.point_a2.id, ids)
        self.assertNotIn(self.point_b1.id, ids)

    def test_telemetry_and_status(self):
        """is_telemetry y status reflejan datos reales."""
        self._add_telemetry(self.point_a1, self.test_date, total_diff=100)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(f'{self.URL}?date={self.test_date}')
        data = response.json()

        a1 = next(r for r in data['results'] if r['point_id'] == self.point_a1.id)
        a2 = next(r for r in data['results'] if r['point_id'] == self.point_a2.id)

        self.assertTrue(a1['is_telemetry'])
        self.assertEqual(a1['status'], 'connected')
        self.assertEqual(a1['measurements_count'], 3)
        self.assertGreater(a1['consumption'], 0)

        self.assertFalse(a2['is_telemetry'])
        self.assertEqual(a2['status'], 'disconnected')
        self.assertEqual(a2['measurements_count'], 0)
        self.assertEqual(a2['consumption'], 0.0)

    def test_order_by_consumption_desc(self):
        """order_by=consumption ordena mayor a menor."""
        self._add_telemetry(self.point_a1, self.test_date, total_diff=50, count=1)
        self._add_telemetry(self.point_a2, self.test_date, total_diff=200, count=1)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            f'{self.URL}?date={self.test_date}&project_id={self.project_a.id}&order_by=consumption'
        )
        data = response.json()
        consumptions = [r['consumption'] for r in data['results']]
        self.assertGreaterEqual(consumptions[0], consumptions[-1])

    def test_order_by_consumption_asc(self):
        """order_by=-consumption ordena menor a mayor."""
        self._add_telemetry(self.point_a1, self.test_date, total_diff=50, count=1)
        self._add_telemetry(self.point_a2, self.test_date, total_diff=200, count=1)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            f'{self.URL}?date={self.test_date}&project_id={self.project_a.id}&order_by=-consumption'
        )
        data = response.json()
        consumptions = [r['consumption'] for r in data['results']]
        self.assertLessEqual(consumptions[0], consumptions[-1])

    def test_pagination(self):
        """page_size y count funcionan correctamente."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'{self.URL}?date={self.test_date}&page_size=2&page=1')
        data = response.json()

        self.assertEqual(data['count'], 4)
        self.assertEqual(len(data['results']), 2)
        self.assertIsNotNone(data['next'])
        self.assertIsNone(data['previous'])

        # Página 2
        response2 = self.client.get(f'{self.URL}?date={self.test_date}&page_size=2&page=2')
        data2 = response2.json()
        self.assertEqual(len(data2['results']), 2)
        self.assertIsNone(data2['next'])
        self.assertIsNotNone(data2['previous'])

    def test_warnings_count(self):
        """warnings_count refleja SystemEvent del punto para ese día."""
        from django.utils import timezone
        import datetime

        # created usa auto_now_add → usamos la fecha de hoy
        today_str = datetime.date.today().isoformat()

        e1 = SystemEvent.objects.create(
            point_catchment=self.point_a1,
            event_type="DISCONNECTION",
            severity="WARNING",
            title="Test",
        )
        e2 = SystemEvent.objects.create(
            point_catchment=self.point_a1,
            event_type="RECONNECTION",
            severity="INFO",
            title="Test2",
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(f'{self.URL}?date={today_str}')
        data = response.json()

        a1 = next((r for r in data['results'] if r['point_id'] == self.point_a1.id), None)
        a2 = next((r for r in data['results'] if r['point_id'] == self.point_a2.id), None)

        self.assertIsNotNone(a1)
        self.assertEqual(a1['warnings_count'], 2)
        if a2:
            self.assertEqual(a2['warnings_count'], 0)

    def _add_warning_events(self):
        """Crea 2 SystemEvent para point_a1 (hoy) y 0 para point_a2."""
        SystemEvent.objects.create(
            point_catchment=self.point_a1,
            event_type="DISCONNECTION",
            severity="WARNING",
            title="E1",
            message="M1",
        )
        SystemEvent.objects.create(
            point_catchment=self.point_a1,
            event_type="RECONNECTION",
            severity="INFO",
            title="E2",
            message="M2",
        )

    def test_order_by_warnings_count_desc(self):
        """order_by=warnings_count_desc pone primero los puntos con más eventos."""
        import datetime
        today_str = datetime.date.today().isoformat()
        self._add_warning_events()

        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            f'{self.URL}?date={today_str}&project_id={self.project_a.id}&order_by=warnings_count_desc'
        )
        data = response.json()
        ids = [r['point_id'] for r in data['results']]
        self.assertEqual(ids[0], self.point_a1.id)
        self.assertEqual(ids[1], self.point_a2.id)

    def test_order_by_warnings_count_asc(self):
        """order_by=warnings_count_asc pone primero los puntos con menos eventos."""
        import datetime
        today_str = datetime.date.today().isoformat()
        self._add_warning_events()

        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            f'{self.URL}?date={today_str}&project_id={self.project_a.id}&order_by=warnings_count_asc'
        )
        data = response.json()
        ids = [r['point_id'] for r in data['results']]
        self.assertEqual(ids[0], self.point_a2.id)
        self.assertEqual(ids[1], self.point_a1.id)

    def test_invalid_order_by_uses_default(self):
        """order_by inválido no da error, usa orden default."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'{self.URL}?date={self.test_date}&order_by=nonsense')
        self.assertEqual(response.status_code, 200)

    def test_empty_result_no_points(self):
        """Usuario sin puntos retorna count=0 results=[]."""
        empty = User.objects.create_user(
            username='empty_list', password='x', email='empty_list@test.cl'
        )
        self.client.force_authenticate(user=empty)
        response = self.client.get(f'{self.URL}?date={self.test_date}')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['results'], [])

    def _assign_variable(self, point, type_variable):
        scheme, _ = SchemesCatchment.objects.get_or_create(
            name=f"Scheme {type_variable}",
            defaults={'description': 'Test scheme'},
        )
        scheme.points_catchment.add(point)
        Variable.objects.create(
            scheme_catchment=scheme,
            str_variable=type_variable,
            label=type_variable,
            type_variable=type_variable,
        )

    def test_order_by_avg_flow_desc(self):
        """order_by=avg_flow ordena promedio de caudal descendente."""
        self._assign_variable(self.point_a1, 'CAUDAL')
        self._assign_variable(self.point_a2, 'CAUDAL')
        self._add_telemetry(self.point_a1, self.test_date, total_diff=50, flow=5.0, count=1)
        self._add_telemetry(self.point_a2, self.test_date, total_diff=50, flow=15.0, count=1)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            f'{self.URL}?date={self.test_date}&project_id={self.project_a.id}&order_by=avg_flow'
        )
        data = response.json()
        flows = [r['avg_flow'] for r in data['results']]
        self.assertIsNotNone(flows[0])
        self.assertIsNotNone(flows[-1])
        self.assertGreaterEqual(flows[0], flows[-1])

    def test_order_by_avg_level_asc(self):
        """order_by=-avg_level ordena promedio de nivel ascendente."""
        self._assign_variable(self.point_a1, 'NIVEL')
        self._assign_variable(self.point_a2, 'NIVEL')
        self._add_telemetry(self.point_a1, self.test_date, total_diff=50, nivel=5.0, count=1)
        self._add_telemetry(self.point_a2, self.test_date, total_diff=50, nivel=1.0, count=1)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            f'{self.URL}?date={self.test_date}&project_id={self.project_a.id}&order_by=-avg_level'
        )
        data = response.json()
        levels = [r['avg_level'] for r in data['results']]
        self.assertIsNotNone(levels[0])
        self.assertIsNotNone(levels[-1])
        self.assertLessEqual(levels[0], levels[-1])



@override_settings(CACHES={
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
})
class ControlCenterDailySummaryTests(TestCase):
    """Tests para GET /api/ik/control_center/daily_summary/"""

    URL = '/api/ik/control_center/daily_summary/'

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

        self.client = APIClient()

        self.admin = User.objects.create_superuser(
            username='admin_daily', password='admin123', email='admin_daily@test.cl',
        )
        self.user = User.objects.create_user(
            username='regular_daily', password='pass123', email='regular_daily@test.cl',
        )

        self.client_a = Client.objects.create(name="Cliente Daily")
        self.project_a = ProjectCatchments.objects.create(
            name="Proyecto Daily A", client=self.client_a
        )
        self.project_b = ProjectCatchments.objects.create(
            name="Proyecto Daily B", client=self.client_a
        )

        self.point_a1 = CatchmentPoint.objects.create(
            title="Alfa Daily", owner_user=self.user, project=self.project_a, frecuency="60",
        )
        self.point_a2 = CatchmentPoint.objects.create(
            title="Beta Daily", owner_user=self.user, project=self.project_a, frecuency="60",
        )
        self.point_b1 = CatchmentPoint.objects.create(
            title="Gamma Daily",
            owner_user=User.objects.create_user(
                username='other_daily', password='x', email='other_daily@test.cl'
            ),
            project=self.project_b, frecuency="60",
        )
        self.point_b1.users_viewers.add(self.user)

        self.test_date = '2026-01-15'

    def _add_telemetry(self, point, date_str, total_diff):
        from django.utils.timezone import make_aware
        from datetime import datetime
        dt = make_aware(datetime.fromisoformat(f"{date_str}T08:00:00"))
        InteractionDetail.objects.create(
            catchment_point=point,
            date_time_medition=dt,
            total_diff=total_diff,
            flow=5.0,
        )

    def test_date_required(self):
        """Sin date retorna estructura con rango default (últimos 7 días)."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('date_range', data)
        self.assertIn('days', data)
        self.assertIn('projects', data)
        self.assertIn('points', data)

    def test_invalid_date_format(self):
        """Date con formato incorrecto retorna 400."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'{self.URL}?start_date=15-01-2026')
        self.assertEqual(response.status_code, 400)

    def test_max_range(self):
        """Rango mayor a 92 días retorna 400."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(
            f'{self.URL}?start_date=2026-01-01&end_date=2026-04-15'
        )
        self.assertEqual(response.status_code, 400)

    def test_filter_project_id(self):
        """project_id filtra puntos y proyectos."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            f'{self.URL}?date={self.test_date}&project_id={self.project_a.id}'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        point_ids = {p['id'] for p in data['points']}
        self.assertEqual(point_ids, {self.point_a1.id, self.point_a2.id})
        project_ids = {p['id'] for p in data['projects']}
        self.assertEqual(project_ids, {self.project_a.id})

    def test_filter_point_id(self):
        """point_id filtra a un solo punto."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            f'{self.URL}?date={self.test_date}&point_id={self.point_a1.id}'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['points']), 1)
        self.assertEqual(data['points'][0]['id'], self.point_a1.id)

    def test_daily_consumption(self):
        """El consumo diario se acumula correctamente."""
        from datetime import timedelta
        from django.utils.timezone import make_aware
        from datetime import datetime

        base = make_aware(datetime.fromisoformat(f"{self.test_date}T08:00:00"))
        for i in range(3):
            InteractionDetail.objects.create(
                catchment_point=self.point_a1,
                date_time_medition=base + timedelta(hours=i),
                total_diff=100,
                flow=5.0,
            )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            f'{self.URL}?date={self.test_date}&start_date={self.test_date}&end_date={self.test_date}'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['days'][self.test_date]['total_consumption'], 300.0)

    def test_empty_user(self):
        """Usuario sin puntos retorna listas vacías."""
        empty = User.objects.create_user(
            username='empty_daily', password='x', email='empty_daily@test.cl'
        )
        self.client.force_authenticate(user=empty)
        response = self.client.get(f'{self.URL}?date={self.test_date}')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['points'], [])
        self.assertEqual(data['projects'], [])

    def test_projects_for_regular_user(self):
        """Usuario regular ve solo proyectos de sus puntos."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f'{self.URL}?date={self.test_date}')
        data = response.json()
        project_names = {p['name'] for p in data['projects']}
        self.assertIn('Proyecto Daily A', project_names)
        self.assertIn('Proyecto Daily B', project_names)
        self.assertNotIn('Proyecto No Acceso', project_names)



class ControlCenterSystemEventsTests(TestCase):
    """Tests para GET /api/ik/control_center/system_events/"""

    URL = '/api/ik/control_center/system_events/'

    def setUp(self):
        self.client = APIClient()

        self.admin = User.objects.create_superuser(
            username='events_admin',
            password='admin123',
            email='events_admin@test.cl',
        )
        self.user = User.objects.create_user(
            username='events_user',
            password='pass123',
            email='events_user@test.cl',
        )
        self.other = User.objects.create_user(
            username='events_other',
            password='pass123',
            email='events_other@test.cl',
        )

        self.client_obj = Client.objects.create(name="Events Client")
        self.project = ProjectCatchments.objects.create(
            name="Events Project", client=self.client_obj
        )

        self.user_point = CatchmentPoint.objects.create(
            title="User Point",
            owner_user=self.user,
            project=self.project,
            frecuency="60",
        )
        self.other_point = CatchmentPoint.objects.create(
            title="Other Point",
            owner_user=self.other,
            project=self.project,
            frecuency="60",
        )

        from django.utils import timezone
        from datetime import datetime
        self.now = timezone.make_aware(datetime(2026, 6, 26, 12, 0, 0))

        self.event_user = SystemEvent.objects.create(
            point_catchment=self.user_point,
            event_type='DISCONNECTION',
            severity='WARNING',
            title='Desconexión detectada',
            message='Punto desconectado por 2 horas',
            created=self.now,
        )
        self.event_other = SystemEvent.objects.create(
            point_catchment=self.other_point,
            event_type='COUNTER_RESET',
            severity='CRITICAL',
            title='Reinicio de contador',
            message='Posible reinicio de contador detectado',
            created=self.now,
        )

    def test_user_sees_only_own_events(self):
        """Usuario normal ve solo eventos de sus puntos."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['id'], self.event_user.id)

    def test_admin_sees_all_events(self):
        """Admin ve eventos de todos los puntos."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 2)

    def test_filter_by_point_id(self):
        """Filtrar por point_id funciona y valida acceso."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f'{self.URL}?point_id={self.user_point.id}')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['point']['id'], self.user_point.id)

    def test_filter_by_forbidden_point_id(self):
        """No se puede filtrar por un punto al que no se tiene acceso."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f'{self.URL}?point_id={self.other_point.id}')
        self.assertEqual(response.status_code, 404)

    def test_filter_by_event_type(self):
        """Filtrar por event_type."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'{self.URL}?event_type=DISCONNECTION')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['event_type'], 'DISCONNECTION')

    def test_filter_by_severity(self):
        """Filtrar por severity."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'{self.URL}?severity=CRITICAL')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['severity'], 'CRITICAL')

    def test_filter_by_date_range(self):
        """Filtrar por rango de fechas."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(
            f'{self.URL}?start=2026-06-26T00:00:00&end=2026-06-26T23:59:59'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 2)

    def test_search_message(self):
        """Buscar en título o mensaje."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'{self.URL}?search=desconectado')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['id'], self.event_user.id)

    def test_invalid_event_type(self):
        """event_type inválido devuelve 400."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'{self.URL}?event_type=INVALID')
        self.assertEqual(response.status_code, 400)

    def test_pagination(self):
        """Paginación funciona."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'{self.URL}?page_size=1')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['results']), 1)
        self.assertIsNotNone(data['next'])


class ControlCenterSystemEventsPointDetailTests(TestCase):
    """Tests para GET /api/ik/control_center/system_events/<point_id>/"""

    URL_TMPL = '/api/ik/control_center/system_events/{point_id}/'

    def setUp(self):
        self.client = APIClient()

        self.admin = User.objects.create_superuser(
            username='detail_admin',
            password='admin123',
            email='detail_admin@test.cl',
        )
        self.user = User.objects.create_user(
            username='detail_user',
            password='pass123',
            email='detail_user@test.cl',
        )
        self.other = User.objects.create_user(
            username='detail_other',
            password='pass123',
            email='detail_other@test.cl',
        )

        self.client_obj = Client.objects.create(name="Detail Client")
        self.project = ProjectCatchments.objects.create(
            name="Detail Project", client=self.client_obj
        )

        self.user_point = CatchmentPoint.objects.create(
            title="Detail User Point",
            owner_user=self.user,
            project=self.project,
            frecuency="60",
        )
        self.other_point = CatchmentPoint.objects.create(
            title="Detail Other Point",
            owner_user=self.other,
            project=self.project,
            frecuency="60",
        )

        from django.utils import timezone
        from datetime import datetime
        self.now = timezone.make_aware(datetime(2026, 6, 26, 12, 0, 0))

        self.event_1 = SystemEvent.objects.create(
            point_catchment=self.user_point,
            event_type='DISCONNECTION',
            severity='WARNING',
            title='Desconexión',
            message='Punto desconectado',
            created=self.now,
        )
        self.event_2 = SystemEvent.objects.create(
            point_catchment=self.user_point,
            event_type='RECONNECTION',
            severity='INFO',
            title='Reconexión',
            message='Punto reconectado',
            created=self.now,
        )

    def _url(self, point_id):
        return self.URL_TMPL.format(point_id=point_id)

    def test_owner_sees_point_events(self):
        """Owner ve todos los eventos de su punto."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self._url(self.user_point.id))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 2)
        self.assertNotIn('point', data)
        self.assertEqual(data['results'][0]['point']['id'], self.user_point.id)
        self.assertIn('display_name', data['results'][0]['point'])

    def test_unauthorized_point_returns_404(self):
        """Usuario sin acceso al punto recibe 404."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self._url(self.other_point.id))
        self.assertEqual(response.status_code, 404)

    def test_admin_can_view_any_point_events(self):
        """Admin puede ver eventos de cualquier punto."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self._url(self.other_point.id))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 0)

    def test_detail_filters_by_event_type(self):
        """Filtros funcionan en la vista detallada."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(
            f'{self._url(self.user_point.id)}?event_type=DISCONNECTION'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['event_type'], 'DISCONNECTION')

    def test_detail_pagination(self):
        """Paginación funciona en la vista detallada."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f'{self._url(self.user_point.id)}?page_size=1')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['results']), 1)
        self.assertIsNotNone(data['next'])

    def test_point_display_name_omits_redundant_client(self):
        """display_name incluye cliente solo si proyecto != cliente."""
        # Caso proyecto distinto a cliente
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self._url(self.user_point.id))
        data = response.json()
        display = data['results'][0]['point']['display_name']
        self.assertIn(self.user_point.title, display)
        self.assertIn(self.project.name, display)
        self.assertIn(self.client_obj.name, display)

        # Caso proyecto igual a cliente
        same_client = Client.objects.create(name="SameName")
        same_project = ProjectCatchments.objects.create(
            name="SameName", client=same_client
        )
        same_point = CatchmentPoint.objects.create(
            title="Same Point",
            owner_user=self.user,
            project=same_project,
            frecuency="60",
        )
        SystemEvent.objects.create(
            point_catchment=same_point,
            event_type='DISCONNECTION',
            severity='WARNING',
            title='E',
            message='M',
            created=self.now,
        )
        response = self.client.get(self._url(same_point.id))
        data = response.json()
        display = data['results'][0]['point']['display_name']
        self.assertIn(same_point.title, display)
        self.assertIn(same_project.name, display)
        # Cliente no debe repetirse: no debe aparecer "SameName (SameName)"
        self.assertNotIn('SameName (SameName)', display)
