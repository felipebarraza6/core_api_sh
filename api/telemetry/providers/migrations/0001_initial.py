# Generated manually for providers app

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0001_initial'),  # Dependencia de la app core
    ]

    operations = [
        migrations.CreateModel(
            name='TelemetryProvider',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Creado')),
                ('modified', models.DateTimeField(auto_now=True, verbose_name='Modificado')),
                ('name', models.CharField(help_text='Nombre único del proveedor', max_length=100, unique=True, verbose_name='Nombre')),
                ('display_name', models.CharField(help_text='Nombre para mostrar en la interfaz', max_length=200, verbose_name='Nombre para mostrar')),
                ('description', models.TextField(blank=True, help_text='Descripción del proveedor', verbose_name='Descripción')),
                ('base_url', models.URLField(help_text='URL base del proveedor', verbose_name='URL Base')),
                ('endpoint_template', models.CharField(default='/api/v1/data', help_text='Template para construir endpoints', max_length=500, verbose_name='Template de Endpoint')),
                ('auth_type', models.CharField(choices=[('none', 'Sin autenticación'), ('basic', 'Basic Auth'), ('bearer', 'Bearer Token'), ('api_key', 'API Key'), ('custom', 'Personalizado')], default='none', help_text='Tipo de autenticación', max_length=20, verbose_name='Tipo de Autenticación')),
                ('auth_config', models.JSONField(blank=True, default=dict, help_text='Configuración de autenticación', verbose_name='Configuración de Auth')),
                ('headers', models.JSONField(blank=True, default=dict, help_text='Headers adicionales para requests', verbose_name='Headers')),
                ('timeout', models.PositiveIntegerField(default=30, help_text='Timeout en segundos', verbose_name='Timeout')),
                ('retry_count', models.PositiveIntegerField(default=3, help_text='Número de reintentos', verbose_name='Reintentos')),
                ('retry_delay', models.PositiveIntegerField(default=2, help_text='Delay entre reintentos (segundos)', verbose_name='Delay de Reintento')),
                ('is_active', models.BooleanField(default=True, help_text='Proveedor activo', verbose_name='Activo')),
                ('health_check_url', models.URLField(blank=True, help_text='URL para health checks', null=True, verbose_name='URL de Health Check')),
                ('supported_protocols', models.JSONField(blank=True, default=list, help_text='Protocolos soportados', verbose_name='Protocolos Soportados')),
                ('config_schema', models.JSONField(blank=True, default=dict, help_text='Esquema de configuración', verbose_name='Esquema de Config')),
                ('rate_limit', models.PositiveIntegerField(default=100, help_text='Límite de requests por minuto', verbose_name='Rate Limit')),
            ],
            options={
                'verbose_name': 'Proveedor de Telemetría',
                'verbose_name_plural': 'Proveedores de Telemetría',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='CatchmentPointProvider',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Creado')),
                ('modified', models.DateTimeField(auto_now=True, verbose_name='Modificado')),
                ('point_code', models.CharField(help_text='Código del punto en el proveedor', max_length=200, verbose_name='Código del Punto')),
                ('config_override', models.JSONField(blank=True, default=dict, help_text='Configuración específica para este punto', verbose_name='Config Override')),
                ('device_config', models.JSONField(blank=True, default=dict, help_text='Configuración del dispositivo', verbose_name='Config del Dispositivo')),
                ('priority', models.PositiveIntegerField(default=1, help_text='Prioridad del proveedor (menor número = mayor prioridad)', verbose_name='Prioridad')),
                ('is_active', models.BooleanField(default=True, help_text='Configuración activa', verbose_name='Activa')),
                ('last_success', models.DateTimeField(blank=True, help_text='Última vez que funcionó correctamente', null=True, verbose_name='Último Éxito')),
                ('last_error', models.DateTimeField(blank=True, help_text='Última vez que falló', null=True, verbose_name='Último Error')),
                ('error_message', models.TextField(blank=True, help_text='Mensaje del último error', verbose_name='Mensaje de Error')),
                ('consecutive_successes', models.PositiveIntegerField(default=0, help_text='Éxitos consecutivos', verbose_name='Éxitos Consecutivos')),
                ('error_count', models.PositiveIntegerField(default=0, help_text='Número de errores', verbose_name='Conteo de Errores')),
                ('point', models.ForeignKey(help_text='Punto de captación', on_delete=django.db.models.deletion.CASCADE, related_name='provider_configs', to='core.catchmentpoint', verbose_name='Punto de Captación')),
                ('provider', models.ForeignKey(help_text='Proveedor de telemetría', on_delete=django.db.models.deletion.CASCADE, related_name='point_configs', to='providers.telemetryprovider', verbose_name='Proveedor')),
            ],
            options={
                'verbose_name': 'Configuración de Punto-Proveedor',
                'verbose_name_plural': 'Configuraciones de Punto-Proveedor',
                'ordering': ['point', 'priority'],
                'unique_together': {('point', 'provider')},
            },
        ),
    ]