from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('void', '0020_add_compute_flow'),
    ]

    operations = [
        migrations.AddField(
            model_name='devicevariableconfig',
            name='extra_data',
            field=models.JSONField(blank=True, default=dict, help_text='Configuración adicional específica de la variable (ej: calculate_nivel).', verbose_name='Datos extra'),
        ),
    ]
