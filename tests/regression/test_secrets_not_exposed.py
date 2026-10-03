"""
Tests de seguridad: la API no debe exponer credenciales/tokens en claro.

Serializers públicos ocultan token_service, auth_password, auth_token,
password_dga_software y txt_password. Los writes legítimos siguen funcionando.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from api.core.models import (
    CatchmentPoint,
    Client,
    DgaDataConfigCatchment,
    ProfileDataConfigCatchment,
    ProjectCatchments,
    SchemesCatchment,
    Variable,
)
from api.core.models.compliance_providers import ComplianceProvider
from api.core.models.telemetry_providers import TelemetryProvider
from api.core.serializers.catchment_points import (
    CatchmentPointSerializerDetailCron,
    TelemetryProviderInternalSerializer,
    VariableConfigSerializer,
)

User = get_user_model()

SECRET_TOKEN = 'SECRET_DEVICE_TOKEN_SHOULD_NOT_LEAK'
SECRET_PASSWORD = 'SECRET_PROVIDER_PASSWORD_SHOULD_NOT_LEAK'
SECRET_AUTH_TOKEN = 'SECRET_AUTH_TOKEN_SHOULD_NOT_LEAK'
SECRET_DGA_PASSWORD = 'SECRET_DGA_PASSWORD_SHOULD_NOT_LEAK'


class SecretsNotExposedAPITests(TestCase):
    """GET de endpoints públicos no debe devolver secretos en claro."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='secuser',
            password='testpass123',
            email='secuser@example.com',
            is_staff=True,
        )
        # txt_password legacy (nunca debe salir en JSON)
        self.user.txt_password = 'LEGACY_PLAINTEXT_PASSWORD'
        self.user.save(update_fields=['txt_password'])

        self.client_obj = Client.objects.create(name='Sec Client')
        self.project = ProjectCatchments.objects.create(
            name='Sec Project', client=self.client_obj
        )
        self.point = CatchmentPoint.objects.create(
            title='Sec Point',
            owner_user=self.user,
            project=self.project,
            frecuency='60',
            is_tdata=True,
        )

        self.profile = ProfileDataConfigCatchment.objects.get(point_catchment=self.point)
        self.profile.token_service = SECRET_TOKEN
        self.profile.is_telemetry = True
        self.profile.save()

        self.dga = DgaDataConfigCatchment.objects.get(point_catchment=self.point)
        self.dga.password_dga_software = SECRET_DGA_PASSWORD
        self.dga.send_dga = True
        self.dga.save()

        self.provider = TelemetryProvider.objects.create(
            name='Tago Test',
            handler_name='tago',
            protocol='HTTP_REST',
            base_url='https://api.tago.io',
            auth_type='API_KEY_HEADER',
            auth_username='tago-user',
            auth_password=SECRET_PASSWORD,
            auth_token=SECRET_AUTH_TOKEN,
            is_active=True,
        )
        self.compliance = ComplianceProvider.objects.create(
            code='dga-test',
            name='DGA Test',
            protocol='HTTP_REST',
            base_url='https://example.com',
            auth_type='BASIC',
            auth_username='dga-user',
            auth_password=SECRET_PASSWORD,
            auth_token=SECRET_AUTH_TOKEN,
            is_active=True,
        )

        self.scheme = SchemesCatchment.objects.create(
            name='Scheme Sec', description='test'
        )
        self.scheme.points_catchment.add(self.point)
        self.variable = Variable.objects.create(
            scheme_catchment=self.scheme,
            str_variable='pulsos',
            label='Pulsos',
            type_variable='TOTALIZADO',
            token_service=SECRET_TOKEN,
            provider=self.provider,
            service='TWIN',
        )

        self.client.force_authenticate(user=self.user)

    def _assert_no_secret_values(self, payload):
        blob = str(payload)
        for secret in (
            SECRET_TOKEN,
            SECRET_PASSWORD,
            SECRET_AUTH_TOKEN,
            SECRET_DGA_PASSWORD,
            'LEGACY_PLAINTEXT_PASSWORD',
        ):
            self.assertNotIn(secret, blob, f'Secreto filtrado en respuesta: {secret[:12]}...')

    def test_telemetry_providers_hide_credentials(self):
        response = self.client.get('/api/telemetry_providers/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        self.assertTrue(len(results) >= 1)
        item = next(r for r in results if r['id'] == self.provider.id)
        self.assertNotIn('auth_password', item)
        self.assertNotIn('auth_token', item)
        self.assertTrue(item.get('has_auth_password'))
        self.assertTrue(item.get('has_auth_token'))
        self._assert_no_secret_values(data)

    def test_compliance_providers_hide_credentials(self):
        response = self.client.get('/api/compliance_providers/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        item = next(r for r in results if r['id'] == self.compliance.id)
        self.assertNotIn('auth_password', item)
        self.assertNotIn('auth_token', item)
        self.assertTrue(item.get('has_auth_password'))
        self.assertTrue(item.get('has_auth_token'))
        self._assert_no_secret_values(data)

    def test_variable_get_hides_token_but_patch_can_set(self):
        response = self.client.get(f'/api/variable/{self.variable.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn('token_service', data)
        self._assert_no_secret_values(data)

        new_token = 'NEW_WRITE_ONLY_TOKEN_VALUE'
        patch = self.client.patch(
            f'/api/variable/{self.variable.id}/',
            data={'token_service': new_token},
            format='json',
        )
        self.assertEqual(patch.status_code, 200)
        self.assertNotIn('token_service', patch.json())
        self.variable.refresh_from_db()
        self.assertEqual(self.variable.token_service, new_token)

    def test_profile_data_config_hides_token_but_patch_can_set(self):
        response = self.client.get(f'/api/profile_data_config_catchment/{self.profile.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn('token_service', data)
        self._assert_no_secret_values(data)

        new_token = 'NEW_PROFILE_TOKEN_VALUE'
        patch = self.client.patch(
            f'/api/profile_data_config_catchment/{self.profile.id}/',
            data={'token_service': new_token},
            format='json',
        )
        self.assertEqual(patch.status_code, 200)
        self.assertNotIn('token_service', patch.json())
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.token_service, new_token)

    def test_dga_config_hides_password_but_patch_can_set(self):
        response = self.client.get(f'/api/dga_data_config_catchment/{self.dga.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn('password_dga_software', data)
        self._assert_no_secret_values(data)

        new_pwd = 'NEW_DGA_PASSWORD_VALUE'
        patch = self.client.patch(
            f'/api/dga_data_config_catchment/{self.dga.id}/',
            data={'password_dga_software': new_pwd},
            format='json',
        )
        self.assertEqual(patch.status_code, 200)
        self.assertNotIn('password_dga_software', patch.json())
        self.dga.refresh_from_db()
        self.assertEqual(self.dga.password_dga_software, new_pwd)

    def test_user_model_hides_plaintext_password_fields(self):
        response = self.client.get(f'/api/users/{self.user.username}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn('password', data)
        self.assertNotIn('txt_password', data)
        self._assert_no_secret_values(data)

    def test_ikolu_nested_variables_hide_token(self):
        """CatchmentPointIkolu / VariableConfigSerializer no debe devolver token_service."""
        response = self.client.get(f'/api/catchment_point/{self.point.id}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self._assert_no_secret_values(data)
        # Buscar variables anidadas si existen
        config = data.get('config_data') or {}
        variables = config.get('variables') or []
        for var in variables:
            self.assertNotIn('token_service', var)
            if var.get('id') == self.variable.id:
                self.assertTrue(var.get('has_token_service'))

    def test_variable_config_serializer_uses_has_token_flag(self):
        data = VariableConfigSerializer(self.variable).data
        self.assertNotIn('token_service', data)
        self.assertTrue(data['has_token_service'])

    def test_cron_internal_serializer_still_includes_secrets(self):
        """Los cronjobs internos DEBEN seguir recibiendo tokens/credenciales."""
        cron_data = CatchmentPointSerializerDetailCron(self.point).data
        profile = cron_data['profile_data_config']
        self.assertEqual(profile['token_service'], SECRET_TOKEN)
        variables = profile['scheme']['variables']
        self.assertTrue(any(v.get('token_service') == SECRET_TOKEN for v in variables))
        provider = next(v['provider'] for v in variables if v.get('provider'))
        self.assertEqual(provider['auth_password'], SECRET_PASSWORD)
        self.assertEqual(provider['auth_token'], SECRET_AUTH_TOKEN)

        internal = TelemetryProviderInternalSerializer(self.provider).data
        self.assertEqual(internal['auth_password'], SECRET_PASSWORD)
        self.assertEqual(internal['auth_token'], SECRET_AUTH_TOKEN)
