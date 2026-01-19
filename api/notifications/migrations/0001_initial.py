import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ('telemetry', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='Notification',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created', models.DateTimeField(auto_now_add=True, help_text='Fecha de creacion.', verbose_name='created at')),
                        ('modified', models.DateTimeField(auto_now=True, help_text='Fecha de modificacion.', verbose_name='modified at')),
                        ('title', models.CharField(max_length=300, verbose_name='Titulo')),
                        ('message', models.CharField(max_length=1300, verbose_name='Mensaje')),
                        ('type_variable', models.CharField(blank=True, choices=[('NIVEL', 'nivel'), ('CAUDAL', 'caudal'), ('CAUDAL PROMEDIO', 'caudal_promedio((diff/3600)*1000)'), ('TOTALIZADO', 'totalizado'), ('TODOS', 'todos')], max_length=300, null=True, verbose_name='Tipo variable')),
                        ('value', models.IntegerField(default=0, verbose_name='Valor')),
                        ('type_alert', models.CharField(blank=True, choices=[('MAX', 'mas'), ('MIN', 'menos'), ('EQUALS', 'igual')], max_length=300, null=True, verbose_name='Tipo de alerta')),
                        ('type_notification', models.CharField(choices=[('INFO', 'Informativo'), ('WARNING', 'Advertencia'), ('ALERT', 'Alerta'), ('CRITICAL', 'Crítico'), ('SUPPORT', 'Soporte')], max_length=50, verbose_name='Tipo de notificación')),
                        ('start_date', models.DateField(blank=True, null=True, verbose_name='Fecha inicio')),
                        ('end_date', models.DateField(blank=True, null=True, verbose_name='Fecha fin')),
                        ('is_periodic', models.BooleanField(default=False, verbose_name='Cada registro')),
                        ('is_active', models.BooleanField(default=True, verbose_name='Activo')),
                        ('is_read', models.BooleanField(default=False, verbose_name='Leido')),
                        ('is_response', models.BooleanField(default=False, verbose_name='Respuesta')),
                        ('is_wait', models.BooleanField(default=False, verbose_name='Espera')),
                        ('is_finish', models.BooleanField(default=False, verbose_name='Finalizado')),
                        ('point_catchment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications_list', to='telemetry.catchmentpoint', verbose_name='Punto de captacion')),
                    ],
                    options={
                        'verbose_name': 'Notificación',
                        'verbose_name_plural': 'Notificaciones',
                        'db_table': 'core_notificationscatchment',
                    },
                ),
                migrations.CreateModel(
                    name='NotificationResponse',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created', models.DateTimeField(auto_now_add=True, help_text='Fecha de creacion.', verbose_name='created at')),
                        ('modified', models.DateTimeField(auto_now=True, help_text='Fecha de modificacion.', verbose_name='modified at')),
                        ('response', models.CharField(max_length=1300, verbose_name='Respuesta')),
                        ('notification', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='responses_list', to='notifications.notification', verbose_name='Notificación')),
                        ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='responses_list', to=settings.AUTH_USER_MODEL, verbose_name='Usuario')),
                    ],
                    options={
                        'verbose_name': 'Respuesta de notificación',
                        'verbose_name_plural': 'Respuestas de notificaciones',
                        'db_table': 'core_responsenotificationscatchment',
                    },
                ),
            ],
            database_operations=[]
        )
    ]
