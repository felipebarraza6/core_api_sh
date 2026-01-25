# Generated manually for Device configuration_scheme

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('telemetry', '0007_remove_corevariable_formula_and_more'),
        ('infrastructure', '0007_add_use_internal_mqtt'),
    ]

    operations = [
        # Agregar configuration_scheme a Device
        migrations.AddField(
            model_name='device',
            name='configuration_scheme',
            field=models.ForeignKey(
                blank=True,
                help_text='Plantilla de configuración dinámica para este dispositivo',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='devices',
                to='telemetry.configurationscheme',
                verbose_name='Esquema de Configuración',
            ),
        ),
        # Crear modelo DeviceConfigurationValue
        migrations.CreateModel(
            name='DeviceConfigurationValue',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, help_text='Fecha de creacion.', verbose_name='created at')),
                ('modified', models.DateTimeField(auto_now=True, help_text='Fecha de modificacion.', verbose_name='modified at')),
                ('value', models.JSONField(help_text='Valor de la configuración según el tipo de dato del campo', verbose_name='Valor')),
                ('device', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='configuration_values',
                    to='infrastructure.device',
                    verbose_name='Dispositivo',
                )),
                ('field', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to='telemetry.configurationschemefield',
                    verbose_name='Campo de Configuración',
                )),
            ],
            options={
                'verbose_name': 'Valor de Configuración de Dispositivo',
                'verbose_name_plural': 'Valores de Configuración de Dispositivo',
                'db_table': 'infrastructure_deviceconfigurationvalue',
                'unique_together': {('device', 'field')},
            },
        ),
    ]
