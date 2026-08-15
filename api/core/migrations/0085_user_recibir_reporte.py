from django.db import migrations, models


def transfer_recibir_reporte_to_user(apps, schema_editor):
    """Transferir el flag recibir_reporte de DgaDataConfigCatchment al owner del punto.

    Si al menos un punto de un usuario tiene recibir_reporte activo,
    se activa el flag en el usuario (el reporte incluye todos sus puntos).
    """
    User = apps.get_model('core', 'User')
    CatchmentPoint = apps.get_model('core', 'CatchmentPoint')
    DgaConfig = apps.get_model('core', 'DgaDataConfigCatchment')

    flagged_dgas = DgaConfig.objects.filter(recibir_reporte=True).values_list(
        'point_catchment__owner_user_id', flat=True)
    user_ids = set(u for u in flagged_dgas if u is not None)
    if user_ids:
        User.objects.filter(id__in=user_ids).update(recibir_reporte=True)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0084_dgadataconfigcatchment_recibir_reporte'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='recibir_reporte',
            field=models.BooleanField(
                default=False,
                help_text='Si está activo, el usuario (owner) recibe el reporte semanal automáticamente con todos sus puntos.',
                verbose_name='Recibir reporte semanal',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='reporte_cc_emails',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Emails adicionales (separados por coma) que reciben copia del reporte semanal.',
                verbose_name='CC reporte semanal',
            ),
        ),
        migrations.RunPython(transfer_recibir_reporte_to_user, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='dgadataconfigcatchment',
            name='recibir_reporte',
        ),
        migrations.RemoveField(
            model_name='dgadataconfigcatchment',
            name='reporte_cc_emails',
        ),
    ]
