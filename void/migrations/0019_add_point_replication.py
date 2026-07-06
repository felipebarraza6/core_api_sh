from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('void', '0018_shadow_output_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='point',
            name='max_replication_hours',
            field=models.PositiveIntegerField(default=24, help_text='Ventana máxima hacia atrás para buscar el último dato válido a replicar.', verbose_name='Máximas horas de replicación'),
        ),
        migrations.AddField(
            model_name='point',
            name='replicate_on_missing',
            field=models.BooleanField(default=False, help_text='Si no llegan datos del proveedor, replica el último ProcessedReading válido en los slots de tiempo esperados (similar a legacy Nettra).', verbose_name='Replicar último dato si no hay lecturas'),
        ),
    ]
