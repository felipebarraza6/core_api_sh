# Generated migration - Add Device FK to CatchmentPoint

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('infrastructure', '0007_add_use_internal_mqtt'),
        ('telemetry', '0002_catchmentpoint_project'),
    ]

    operations = [
        migrations.AddField(
            model_name='catchmentpoint',
            name='device',
            field=models.ForeignKey(
                blank=True,
                help_text='Dispositivo físico (logger/datalogger) instalado en este punto. Puede estar vacío si el punto no tiene equipo asignado.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='catchment_points',
                to='infrastructure.device',
                verbose_name='Dispositivo IoT',
            ),
        ),
    ]
