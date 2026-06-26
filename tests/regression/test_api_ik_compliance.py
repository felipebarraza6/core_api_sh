"""
Tests de regresión para el endpoint de compliance.
==================================================

GET /api/ik/compliance/
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from api.core.models import (
    CatchmentPoint, Client, ProjectCatchments,
    InteractionDetail, DgaDataConfigCatchment,
    ProfileDataConfigCatchment,
)

User = get_user_model()


class ComplianceEndpointTests(TestCase):
    """Tests para GET /api/ik/compliance/"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        self.client.force_authenticate(user=self.user)

        self.client_obj = Client.objects.create(name="Test Client")
        self.project = ProjectCatchments.objects.create(
            name="Test Project", client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title="Test Point",
            owner_user=self.user,
            project=self.project,
            frecuency="60",
            is_tdata=True,
        )
        ProfileDataConfigCatchment.objects.create(
            point_catchment=self.point,
            is_telemetry=True,
        )
        self.dga = DgaDataConfigCatchment.objects.create(
            point_catchment=self.point,
            send_dga=True,
            code_dga="OB-12345-DGA",
            standard="MAYOR",
            type_dga="SUPERFICIAL",
            flow_granted_dga=10.0,
            total_granted_dga=1000.0,
        )

    def test_compliance_structure(self):
        """Debe retornar points con flow_history y compliance_warning."""
        response = self.client.get('/api/ik/compliance/')
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn('count', data)
        self.assertIn('points', data)
        self.assertEqual(data['count'], 1)

        points = data['points']
        self.assertEqual(len(points), 1)

        first = points[0]
        self.assertIn('flow_history', first)
        self.assertIn('compliance_warning', first)
        self.assertEqual(first['point_id'], self.point.id)
        self.assertEqual(first['code'], "OB-12345-DGA")

    def test_compliance_empty_for_user_without_points(self):
        """Usuario sin puntos debe ver lista vacía."""
        empty_user = User.objects.create_user(
            username='empty', password='emptypass', email='empty@example.com'
        )
        self.client.force_authenticate(user=empty_user)

        response = self.client.get('/api/ik/compliance/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['points'], [])

    def test_compliance_type_by_code_prefix(self):
        """compliance_type se determina por prefijo del código, no por send_dga."""
        # self.point tiene code_dga='OB-12345-DGA' → DGA activo
        response = self.client.get('/api/ik/compliance/')
        data = response.json()
        point = data['points'][0]
        self.assertEqual(point['compliance_type'], ['DGA'])
        self.assertTrue(point['compliance_active'])

        # Inactivo con código OB → sigue siendo DGA pero active=false
        self.dga.send_dga = False
        self.dga.save(update_fields=['send_dga'])
        response = self.client.get('/api/ik/compliance/')
        data = response.json()
        point = data['points'][0]
        self.assertEqual(point['compliance_type'], ['DGA'])
        self.assertFalse(point['compliance_active'])

        # Código que NO empieza con OB → SMA
        self.dga.send_dga = True
        self.dga.code_dga = "7511"
        self.dga.save(update_fields=['send_dga', 'code_dga'])
        response = self.client.get('/api/ik/compliance/')
        data = response.json()
        point = data['points'][0]
        self.assertEqual(point['compliance_type'], ['SMA'])
        self.assertFalse(point['compliance_active'])

        # SMA activo vía sma_device_id
        self.dga.send_sma = True
        self.dga.sma_device_id = "12180"
        self.dga.save(update_fields=['send_sma', 'sma_device_id'])
        response = self.client.get('/api/ik/compliance/')
        data = response.json()
        point = data['points'][0]
        self.assertEqual(point['compliance_type'], ['SMA'])
        self.assertTrue(point['compliance_active'])

    def test_compliance_excludes_unauthorized_points(self):
        """No debe incluir puntos que no pertenecen al usuario."""
        other_user = User.objects.create_user(
            username='other', password='otherpass', email='other@example.com'
        )
        other_point = CatchmentPoint.objects.create(
            title="Other Point",
            owner_user=other_user,
            project=self.project,
            frecuency="60",
        )
        DgaDataConfigCatchment.objects.create(
            point_catchment=other_point,
            send_dga=True,
            code_dga="99999-DGA",
        )

        response = self.client.get('/api/ik/compliance/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Solo debe ver su propio punto
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['points'][0]['point_id'], self.point.id)


    def _create_second_point(self, title, total_granted, flow_granted, project=None):
        """Crea un segundo punto con compliance para tests de orden/filtros."""
        point = CatchmentPoint.objects.create(
            title=title,
            owner_user=self.user,
            project=project or self.project,
            frecuency="60",
        )
        ProfileDataConfigCatchment.objects.create(
            point_catchment=point,
            is_telemetry=True,
        )
        dga = DgaDataConfigCatchment.objects.create(
            point_catchment=point,
            send_dga=True,
            code_dga=f"OB-CODE-{title}",
            standard="MAYOR",
            type_dga="SUPERFICIAL",
            flow_granted_dga=flow_granted,
            total_granted_dga=total_granted,
        )
        return point, dga

    def _create_interaction(self, point, total_diff, flow, date_time=None):
        from django.utils import timezone
        from datetime import date
        if date_time is None:
            date_time = timezone.now()
        return InteractionDetail.objects.create(
            catchment_point=point,
            date_time_medition=date_time,
            total_diff=total_diff,
            flow=flow,
        )

    def test_order_by_pct_consumed_desc(self):
        """order_by=pct_consumed_desc ordena mayor % primero."""
        point2, _ = self._create_second_point("B Point", total_granted=1000, flow_granted=5.0)
        # point consumió 500/1000 = 50%, point2 200/1000 = 20%
        self._create_interaction(self.point, 500, 5.0)
        self._create_interaction(point2, 200, 2.0)

        response = self.client.get('/api/ik/compliance/?order_by=pct_consumed_desc')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 2)
        ids = [p['point_id'] for p in data['points']]
        self.assertEqual(ids[0], self.point.id)
        self.assertEqual(ids[1], point2.id)

    def test_order_by_pct_consumed_asc(self):
        """order_by=pct_consumed_asc ordena menor % primero."""
        point2, _ = self._create_second_point("B Point", total_granted=1000, flow_granted=5.0)
        self._create_interaction(self.point, 500, 5.0)
        self._create_interaction(point2, 200, 2.0)

        response = self.client.get('/api/ik/compliance/?order_by=pct_consumed_asc')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        ids = [p['point_id'] for p in data['points']]
        self.assertEqual(ids[0], point2.id)
        self.assertEqual(ids[1], self.point.id)

    def test_order_by_point_name(self):
        """order_by por nombre respeta asc/desc."""
        point2, _ = self._create_second_point("Alpha Point", total_granted=1000, flow_granted=5.0)
        self._create_interaction(self.point, 0, 0.0)
        self._create_interaction(point2, 0, 0.0)

        response = self.client.get('/api/ik/compliance/?order_by=point_name_asc')
        data = response.json()
        names = [p['point_name'] for p in data['points']]
        self.assertEqual(names, sorted(names))

        response = self.client.get('/api/ik/compliance/?order_by=point_name_desc')
        data = response.json()
        names = [p['point_name'] for p in data['points']]
        self.assertEqual(names, sorted(names, reverse=True))

    def test_invalid_order_by_returns_400(self):
        """order_by inválido retorna 400 con mensaje legible."""
        response = self.client.get('/api/ik/compliance/?order_by=invalid')
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertNotIn('<F(', data['error'])
        self.assertIn('default', data['error'])

    def test_order_default_puts_active_first(self):
        """El orden por defecto coloca activos primero, luego inactivos."""
        inactive_point = CatchmentPoint.objects.create(
            title="Z Inactive",
            owner_user=self.user,
            project=self.project,
            frecuency="60",
        )
        ProfileDataConfigCatchment.objects.create(
            point_catchment=inactive_point,
            is_telemetry=True,
        )
        DgaDataConfigCatchment.objects.create(
            point_catchment=inactive_point,
            send_dga=False,
            code_dga="OB-INACTIVE",
            standard="MAYOR",
            type_dga="SUPERFICIAL",
            flow_granted_dga=5.0,
            total_granted_dga=1000.0,
        )
        self._create_interaction(self.point, 0, 0.0)
        self._create_interaction(inactive_point, 0, 0.0)

        response = self.client.get('/api/ik/compliance/')
        data = response.json()
        ids = [p['point_id'] for p in data['points']]
        self.assertEqual(ids[0], self.point.id)
        self.assertEqual(ids[1], inactive_point.id)

    def test_order_by_exceedances_desc(self):
        """order_by=exceedances_desc ordena por excedencias de mayor a menor, activos primero."""
        from django.utils import timezone
        from datetime import date
        point2, _ = self._create_second_point("B Point", total_granted=1000, flow_granted=5.0)
        current_year = date.today().year
        dt = timezone.make_aware(timezone.datetime(current_year, 6, 15, 10, 0, 0))
        # point excede 1 vez (auth=10), point2 excede 2 veces (auth=5)
        self._create_interaction(self.point, 0, 15.0, date_time=dt)
        self._create_interaction(point2, 0, 15.0, date_time=dt)
        self._create_interaction(point2, 0, 20.0, date_time=dt + timezone.timedelta(minutes=1))

        response = self.client.get('/api/ik/compliance/?order_by=exceedances_desc')
        data = response.json()
        self.assertEqual(data['count'], 2)
        ids = [p['point_id'] for p in data['points']]
        self.assertEqual(ids[0], point2.id)
        self.assertEqual(ids[1], self.point.id)

    def test_filter_standard(self):
        """?standard filtra por estándar de la config seleccionada."""
        point2, dga2 = self._create_second_point("Other Point", total_granted=1000, flow_granted=5.0)
        dga2.standard = "MEDIO"
        dga2.save(update_fields=['standard'])
        self._create_interaction(self.point, 0, 0.0)
        self._create_interaction(point2, 0, 0.0)

        response = self.client.get('/api/ik/compliance/?standard=MEDIO')
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['points'][0]['point_id'], point2.id)

        response = self.client.get('/api/ik/compliance/?standard=MAYOR')
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['points'][0]['point_id'], self.point.id)

    def test_filter_type_dga(self):
        """?type_dga filtra por tipo SUPERFICIAL/SUBTERRANEO de la config."""
        point2, dga2 = self._create_second_point("Subterranean Point", total_granted=1000, flow_granted=5.0)
        dga2.type_dga = "SUBTERRANEO"
        dga2.save(update_fields=['type_dga'])
        self._create_interaction(self.point, 0, 0.0)
        self._create_interaction(point2, 0, 0.0)

        response = self.client.get('/api/ik/compliance/?type_dga=SUPERFICIAL')
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['points'][0]['point_id'], self.point.id)

        response = self.client.get('/api/ik/compliance/?type_dga=SUBTERRANEO')
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['points'][0]['point_id'], point2.id)

        response = self.client.get('/api/ik/compliance/?type_dga=SUPERFICIAL,SUBTERRANEO')
        data = response.json()
        self.assertEqual(data['count'], 2)

    def test_filter_project_id(self):
        """project_id filtra correctamente."""
        other_project = ProjectCatchments.objects.create(
            name="Other Project", client=self.client_obj
        )
        point2, _ = self._create_second_point(
            "Other Point", total_granted=1000, flow_granted=5.0, project=other_project
        )
        self._create_interaction(self.point, 0, 0.0)
        self._create_interaction(point2, 0, 0.0)

        response = self.client.get(f'/api/ik/compliance/?project_id={self.project.id}')
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['points'][0]['point_id'], self.point.id)

    def test_lists_inactive_points_by_default(self):
        """Por defecto se listan puntos con compliance configurado, activo o inactivo."""
        inactive_point = CatchmentPoint.objects.create(
            title="Inactive Point",
            owner_user=self.user,
            project=self.project,
            frecuency="60",
        )
        ProfileDataConfigCatchment.objects.create(
            point_catchment=inactive_point,
            is_telemetry=True,
        )
        # Compliance inactivo: tiene código DGA pero send_dga=False
        DgaDataConfigCatchment.objects.create(
            point_catchment=inactive_point,
            send_dga=False,
            code_dga="OB-INACTIVE",
            standard="MAYOR",
            type_dga="SUPERFICIAL",
            flow_granted_dga=5.0,
            total_granted_dga=1000.0,
        )
        # Punto sin compliance: no debe aparecer
        no_compliance_point = CatchmentPoint.objects.create(
            title="No Compliance Point",
            owner_user=self.user,
            project=self.project,
            frecuency="60",
        )
        ProfileDataConfigCatchment.objects.create(
            point_catchment=no_compliance_point,
            is_telemetry=True,
        )
        self._create_interaction(self.point, 0, 0.0)
        self._create_interaction(inactive_point, 0, 0.0)
        self._create_interaction(no_compliance_point, 0, 0.0)

        response = self.client.get('/api/ik/compliance/')
        data = response.json()
        self.assertEqual(data['count'], 2)
        ids = {p['point_id'] for p in data['points']}
        self.assertIn(self.point.id, ids)
        self.assertIn(inactive_point.id, ids)
        self.assertNotIn(no_compliance_point.id, ids)

        inactive_item = [p for p in data['points'] if p['point_id'] == inactive_point.id][0]
        self.assertEqual(inactive_item['compliance_active'], False)
        self.assertEqual(inactive_item['compliance_type'], ['DGA'])
        self.assertEqual(inactive_item['code'], "OB-INACTIVE")

    def test_active_only_filter(self):
        """?active_only=true excluye puntos con compliance inactivo."""
        inactive_point = CatchmentPoint.objects.create(
            title="Inactive Point",
            owner_user=self.user,
            project=self.project,
            frecuency="60",
        )
        ProfileDataConfigCatchment.objects.create(
            point_catchment=inactive_point,
            is_telemetry=True,
        )
        DgaDataConfigCatchment.objects.create(
            point_catchment=inactive_point,
            send_dga=False,
            code_dga="OB-INACTIVE",
            standard="MAYOR",
            type_dga="SUPERFICIAL",
            flow_granted_dga=5.0,
            total_granted_dga=1000.0,
        )
        self._create_interaction(self.point, 0, 0.0)
        self._create_interaction(inactive_point, 0, 0.0)

        response = self.client.get('/api/ik/compliance/?active_only=true')
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['points'][0]['point_id'], self.point.id)
        self.assertTrue(data['points'][0]['compliance_active'])

    def test_filter_search(self):
        """search filtra por nombre de punto."""
        point2, _ = self._create_second_point("Filtered Point", total_granted=1000, flow_granted=5.0)
        self._create_interaction(self.point, 0, 0.0)
        self._create_interaction(point2, 0, 0.0)

        response = self.client.get('/api/ik/compliance/?search=Filtered')
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['points'][0]['point_id'], point2.id)

    def test_filter_search_by_code(self):
        """search filtra por código DGA/SMA usando icontains."""
        point2, dga2 = self._create_second_point("Other Point", total_granted=1000, flow_granted=5.0)
        dga2.code_dga = "OB-0702-752"
        dga2.save(update_fields=['code_dga'])
        self._create_interaction(self.point, 0, 0.0)
        self._create_interaction(point2, 0, 0.0)

        # Búsqueda exacta completa
        response = self.client.get('/api/ik/compliance/?search=OB-0702-752')
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['points'][0]['point_id'], point2.id)

        # Búsqueda parcial por prefijo
        response = self.client.get('/api/ik/compliance/?search=OB-0702')
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['points'][0]['point_id'], point2.id)

        # Búsqueda parcial por número
        response = self.client.get('/api/ik/compliance/?search=0702')
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['points'][0]['point_id'], point2.id)

    def test_pagination(self):
        """page y page_size funcionan."""
        for i in range(5):
            p, _ = self._create_second_point(f"Pag Point {i}", total_granted=1000, flow_granted=5.0)
            self._create_interaction(p, 0, 0.0)

        response = self.client.get('/api/ik/compliance/?page_size=3')
        data = response.json()
        self.assertEqual(data['count'], 6)  # 1 original + 5 nuevos
        self.assertEqual(len(data['points']), 3)
        self.assertIsNotNone(data['next'])

    def test_flow_history_with_exceedance(self):
        """flow_history refleja registros que superan el caudal autorizado."""
        from django.utils import timezone
        from datetime import date
        current_year = date.today().year
        dt = timezone.make_aware(timezone.datetime(current_year, 6, 15, 10, 0, 0))
        self._create_interaction(self.point, 0, 15.0, date_time=dt)  # auth=10

        response = self.client.get('/api/ik/compliance/')
        data = response.json()
        point = data['points'][0]
        self.assertEqual(point['flow_history']['count'], 1)
        self.assertTrue(point['flow_history']['has_more'] is False)
        self.assertEqual(point['compliance_warning']['level'], 'critical')

    def test_near_limit_history(self):
        """near_limit_history refleja registros entre 90% y 100% del caudal autorizado."""
        from django.utils import timezone
        from datetime import date
        current_year = date.today().year
        dt = timezone.make_aware(timezone.datetime(current_year, 6, 15, 10, 0, 0))
        self._create_interaction(self.point, 0, 9.5, date_time=dt)  # 95% de 10

        response = self.client.get('/api/ik/compliance/')
        data = response.json()
        point = data['points'][0]
        self.assertEqual(point['near_limit_history']['count'], 1)
        self.assertEqual(point['compliance_warning']['level'], 'warning')

    def test_null_total_granted_pct_is_none(self):
        """Si total_granted_dga es nulo, pct_consumed es None."""
        self.dga.total_granted_dga = None
        self.dga.save(update_fields=['total_granted_dga'])
        self._create_interaction(self.point, 100, 1.0)

        response = self.client.get('/api/ik/compliance/')
        data = response.json()
        point = data['points'][0]
        self.assertIsNone(point['pct_consumed'])

    def test_flow_history_endpoint(self):
        """El endpoint de flow_history trae los registros que exceden el caudal."""
        from django.utils import timezone
        from datetime import date, timedelta
        current_year = date.today().year
        dt = timezone.make_aware(timezone.datetime(current_year, 6, 15, 10, 0, 0))
        self._create_interaction(self.point, 0, 15.0, date_time=dt)
        self._create_interaction(self.point, 0, 9.0, date_time=dt + timedelta(minutes=1))

        response = self.client.get(
            f'/api/ik/compliance/{self.point.id}/flow_history/'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['threshold'], 10.0)
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['results'][0]['flow'], 15.0)

    def test_near_limit_endpoint(self):
        """El endpoint de near_limit trae registros entre 90% y 100% del caudal."""
        from django.utils import timezone
        from datetime import date, timedelta
        current_year = date.today().year
        dt = timezone.make_aware(timezone.datetime(current_year, 6, 15, 10, 0, 0))
        self._create_interaction(self.point, 0, 9.5, date_time=dt)
        self._create_interaction(self.point, 0, 15.0, date_time=dt + timedelta(minutes=1))

        response = self.client.get(
            f'/api/ik/compliance/{self.point.id}/near_limit/'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['threshold'], 10.0)
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['results'][0]['flow'], 9.5)

    def test_flow_history_pagination(self):
        """flow_history respeta page y page_size."""
        from django.utils import timezone
        from datetime import date, timedelta
        current_year = date.today().year
        base_dt = timezone.make_aware(timezone.datetime(current_year, 6, 15, 10, 0, 0))
        for i in range(5):
            self._create_interaction(
                self.point, 0, 15.0,
                date_time=base_dt - timedelta(hours=i)
            )

        response = self.client.get(
            f'/api/ik/compliance/{self.point.id}/flow_history/?page_size=2'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 5)
        self.assertEqual(len(data['results']), 2)
        self.assertIsNotNone(data['next'])

    def test_flow_history_inactive_point(self):
        """El endpoint de flow_history funciona para puntos con compliance inactivo."""
        from django.utils import timezone
        from datetime import date
        self.dga.send_dga = False
        self.dga.save(update_fields=['send_dga'])
        current_year = date.today().year
        dt = timezone.make_aware(timezone.datetime(current_year, 6, 15, 10, 0, 0))
        self._create_interaction(self.point, 0, 15.0, date_time=dt)

        response = self.client.get(
            f'/api/ik/compliance/{self.point.id}/flow_history/'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['threshold'], 10.0)

    def test_flow_history_unauthorized_point(self):
        """Usuario sin acceso al punto recibe 404."""
        other_user = get_user_model().objects.create_user(
            username='other', password='otherpass', email='other@example.com'
        )
        other_point = CatchmentPoint.objects.create(
            title="Other Point",
            owner_user=other_user,
            project=self.project,
            frecuency="60",
        )
        DgaDataConfigCatchment.objects.create(
            point_catchment=other_point,
            send_dga=True,
            code_dga="OTHER-DGA",
            flow_granted_dga=10.0,
            total_granted_dga=1000.0,
        )

        response = self.client.get(
            f'/api/ik/compliance/{other_point.id}/flow_history/'
        )
        self.assertEqual(response.status_code, 404)
