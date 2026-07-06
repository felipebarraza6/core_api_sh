from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('void', '0019_add_point_replication'),
    ]

    operations = [
        migrations.AddField(
            model_name='devicevariableconfig',
            name='compute_flow',
            field=models.BooleanField(default=False, help_text='Solo para totalizadores stateful: calcula caudal promedio (L/s) como derivada del total.', verbose_name='Calcular caudal derivado'),
        ),
    ]
