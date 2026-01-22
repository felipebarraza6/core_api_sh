# Generated migration - Add Variable FK to CatchmentPointProvider

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('telemetry', '0003_catchmentpoint_device'),
        ('telemetry_providers', '0001_initial'),
    ]

    operations = [
        # First remove the old unique_together constraint
        migrations.AlterUniqueTogether(
            name='catchmentpointprovider',
            unique_together=set(),
        ),
        # Add the variable FK (nullable initially for existing data)
        migrations.AddField(
            model_name='catchmentpointprovider',
            name='variable',
            field=models.ForeignKey(
                help_text='Variable del punto que recibe datos de este proveedor',
                null=True,  # Temporarily nullable
                on_delete=django.db.models.deletion.CASCADE,
                related_name='provider_configs',
                to='telemetry.corevariable',
                verbose_name='Variable',
            ),
        ),
        # Add new unique_together with variable
        migrations.AlterUniqueTogether(
            name='catchmentpointprovider',
            unique_together={('point', 'provider', 'variable')},
        ),
    ]
