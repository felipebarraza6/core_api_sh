import django.core.validators
import django.db.models.deletion
from django.db import migrations, models

class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ('telemetry', '0001_initial'),
    ]
    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='Manufacturer',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created', models.DateTimeField(auto_now_add=True, help_text='Fecha de creacion.', verbose_name='created at')),
                        ('modified', models.DateTimeField(auto_now=True, help_text='Fecha de modificacion.', verbose_name='modified at')),
                        ('name', models.CharField(help_text='Nombre del proveedor/fabricante', max_length=100, unique=True)),
                        ('code', models.CharField(help_text='Código único del proveedor', max_length=20, unique=True)),
                        ('description', models.TextField(blank=True, help_text='Descripción del proveedor')),
                        ('website', models.URLField(blank=True, help_text='Sitio web del proveedor')),
                        ('contact_email', models.EmailField(blank=True, help_text='Email de contacto', max_length=254)),
                        ('contact_phone', models.CharField(blank=True, help_text='Teléfono de contacto', max_length=20)),
                        ('mqtt_broker_host', models.CharField(blank=True, help_text='Host del broker MQTT del proveedor', max_length=255)),
                        ('mqtt_broker_port', models.PositiveIntegerField(default=1883, help_text='Puerto del broker MQTT', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(65535)])),
                        ('mqtt_username', models.CharField(blank=True, help_text='Usuario MQTT', max_length=100)),
                        ('mqtt_password', models.CharField(blank=True, help_text='Contraseña MQTT', max_length=255)),
                        ('mqtt_use_tls', models.BooleanField(default=False, help_text='Usar TLS para MQTT')),
                        ('is_active', models.BooleanField(default=True, help_text='Proveedor activo')),
                        ('integration_status', models.CharField(choices=[('NOT_STARTED', 'No iniciado'), ('IN_PROGRESS', 'En progreso'), ('TESTING', 'En pruebas'), ('PRODUCTION', 'En producción'), ('DEPRECATED', 'Obsoleto')], default='NOT_STARTED', help_text='Estado de integración', max_length=20)),
                    ],
                    options={
                        'verbose_name': 'Proveedor de Equipos',
                        'verbose_name_plural': 'Proveedores de Equipos',
                        'db_table': 'core_equipmentprovider',
                    },
                ),
                migrations.CreateModel(
                    name='DeviceModel',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created', models.DateTimeField(auto_now_add=True, help_text='Fecha de creacion.', verbose_name='created at')),
                        ('modified', models.DateTimeField(auto_now=True, help_text='Fecha de modificacion.', verbose_name='modified at')),
                        ('model_name', models.CharField(help_text='Nombre del modelo', max_length=100)),
                        ('model_code', models.CharField(help_text='Código del modelo', max_length=50)),
                        ('description', models.TextField(blank=True, help_text='Descripción del modelo')),
                        ('is_active', models.BooleanField(default=True, help_text='Modelo activo')),
                        ('manufacturer', models.ForeignKey(help_text='Proveedor del equipo', on_delete=django.db.models.deletion.CASCADE, related_name='models', to='infrastructure.manufacturer')),
                    ],
                    options={
                        'verbose_name': 'Modelo de Equipo',
                        'verbose_name_plural': 'Modelos de Equipos',
                        'db_table': 'core_equipmentmodel',
                        'unique_together': {('manufacturer', 'model_code')},
                    },
                ),
                migrations.CreateModel(
                    name='Device',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created', models.DateTimeField(auto_now_add=True, help_text='Fecha de creacion.', verbose_name='created at')),
                        ('modified', models.DateTimeField(auto_now=True, help_text='Fecha de modificacion.', verbose_name='modified at')),
                        ('device_id', models.CharField(help_text='ID único del dispositivo (MAC, Serial, etc.)', max_length=100, unique=True)),
                        ('name', models.CharField(help_text='Nombre descriptivo del dispositivo', max_length=100)),
                        ('status', models.CharField(choices=[('OFFLINE', 'Offline'), ('ONLINE', 'Online'), ('ERROR', 'Error'), ('MAINTENANCE', 'Mantenimiento'), ('BATTERY_LOW', 'Batería baja')], default='OFFLINE', help_text='Estado actual del dispositivo', max_length=20)),
                        ('last_seen', models.DateTimeField(blank=True, null=True)),
                        ('battery_level', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                        ('catchment_point', models.ForeignKey(help_text='Punto de captación al que pertenece', on_delete=django.db.models.deletion.CASCADE, related_name='devices', to='telemetry.catchmentpoint')),
                        ('device_model', models.ForeignKey(help_text='Modelo del equipo', on_delete=django.db.models.deletion.PROTECT, related_name='devices', to='infrastructure.devicemodel')),
                    ],
                    options={
                        'verbose_name': 'Dispositivo IoT',
                        'verbose_name_plural': 'Dispositivos IoT',
                        'db_table': 'core_iotdevice',
                    },
                ),
                migrations.CreateModel(
                    name='Connection',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created', models.DateTimeField(auto_now_add=True, help_text='Fecha de creacion.', verbose_name='created at')),
                        ('modified', models.DateTimeField(auto_now=True, help_text='Fecha de modificacion.', verbose_name='modified at')),
                        ('connection_name', models.CharField(max_length=100)),
                        ('broker_host', models.CharField(max_length=255)),
                        ('broker_port', models.PositiveIntegerField(default=1883)),
                        ('username', models.CharField(blank=True, max_length=100)),
                        ('password', models.CharField(blank=True, max_length=255)),
                        ('client_id', models.CharField(max_length=100, unique=True)),
                        ('status', models.CharField(choices=[('DISCONNECTED', 'Desconectado'), ('CONNECTING', 'Conectando'), ('CONNECTED', 'Conectado'), ('ERROR', 'Error')], default='DISCONNECTED', max_length=15)),
                        ('is_active', models.BooleanField(default=True)),
                        ('manufacturer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='connections', to='infrastructure.manufacturer')),
                    ],
                    options={
                        'verbose_name': 'Conexión MQTT',
                        'verbose_name_plural': 'Conexiones MQTT',
                        'db_table': 'core_mqttconnection',
                    },
                ),
            ],
            database_operations=[]
        )
    ]
