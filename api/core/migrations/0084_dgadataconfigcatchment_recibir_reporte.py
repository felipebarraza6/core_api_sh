from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0083_supportticket_sla_paused_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='dgadataconfigcatchment',
            name='recibir_reporte',
            field=models.BooleanField(
                default=False,
                help_text='Si está activo, el owner de este punto recibirá el reporte semanal automáticamente.',
                verbose_name='Recibir reporte semanal',
            ),
        ),
        migrations.AddField(
            model_name='dgadataconfigcatchment',
            name='reporte_cc_emails',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Emails adicionales (separados por coma) que recibirán copia del reporte semanal.',
                verbose_name='CC reporte semanal',
            ),
        ),
    ]
