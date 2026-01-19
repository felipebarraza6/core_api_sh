import django.core.validators
import django.db.models.deletion
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0001_initial'),
        ('infrastructure', '0001_initial'),
        ('support', '0002_remove_supportticket_support_sup_ticket__4a7d4b_idx_and_more'),
        ('telemetry', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='alertrule',
            name='target_client',
        ),
        migrations.RemoveField(
            model_name='alertrule',
            name='target_device',
        ),
        migrations.RemoveField(
            model_name='alertrule',
            name='target_point',
        ),
        migrations.RemoveField(
            model_name='alertrule',
            name='target_project',
        ),
        migrations.RemoveField(
            model_name='projectcatchments',
            name='client',
        ),
        migrations.RemoveField(
            model_name='datacorrectionlog',
            name='corrected_by',
        ),
        migrations.RemoveField(
            model_name='datacorrectionlog',
            name='original_record',
        ),
        migrations.RemoveField(
            model_name='dataqualitymetric',
            name='data_point',
        ),
        migrations.RemoveField(
            model_name='devicemaintenanceschedule',
            name='assigned_technician',
        ),
        migrations.RemoveField(
            model_name='devicemaintenanceschedule',
            name='device',
        ),
        migrations.AlterUniqueTogether(
            name='equipmentmodel',
            unique_together=None,
        ),
        migrations.RemoveField(
            model_name='equipmentmodel',
            name='provider',
        ),
        migrations.RemoveField(
            model_name='iotdevice',
            name='equipment_model',
        ),
        migrations.RemoveField(
            model_name='mqttconnection',
            name='provider',
        ),
        migrations.RemoveField(
            model_name='providerdatasync',
            name='provider',
        ),
        migrations.RemoveField(
            model_name='filecatchment',
            name='point_catchment',
        ),
        migrations.RemoveField(
            model_name='filecatchment',
            name='type_file',
        ),
        migrations.RemoveField(
            model_name='iotdevice',
            name='catchment_point',
        ),
        migrations.RemoveField(
            model_name='mqttmessagelog',
            name='device',
        ),
        migrations.AlterField(
            model_name='constantdefinition',
            name='device',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='constants', to='infrastructure.device'),
        ),
        migrations.AlterField(
            model_name='datapoint',
            name='device',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='granular_data_points', to='infrastructure.device'),
        ),
        migrations.AlterField(
            model_name='datastream',
            name='device',
            field=models.ForeignKey(help_text='Dispositivo que genera este stream', on_delete=django.db.models.deletion.CASCADE, related_name='data_streams', to='infrastructure.device'),
        ),
        migrations.RemoveField(
            model_name='mqttmessagelog',
            name='connection',
        ),
        migrations.RemoveField(
            model_name='notificationscatchment',
            name='point_catchment',
        ),
        migrations.RemoveField(
            model_name='responsenotificationscatchment',
            name='notification',
        ),
        migrations.AlterField(
            model_name='catchmentpoint',
            name='project',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='catchment_points', to='crm.project', verbose_name='Proyecto'),
        ),
        migrations.RemoveField(
            model_name='registerpersons',
            name='profile',
        ),
        migrations.RemoveField(
            model_name='responsenotificationscatchment',
            name='user',
        ),
        migrations.AlterModelOptions(
            name='constantapplication',
            options={'verbose_name': 'Aplicación de Constante', 'verbose_name_plural': 'Aplicaciones de Constantes'},
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name='AlertRule'),
                migrations.DeleteModel(name='Client'),
                migrations.DeleteModel(name='DataCorrectionLog'),
                migrations.DeleteModel(name='DataQualityMetric'),
                migrations.DeleteModel(name='DeviceMaintenanceSchedule'),
                migrations.DeleteModel(name='EquipmentModel'),
                migrations.DeleteModel(name='EquipmentProvider'),
                migrations.DeleteModel(name='ProviderDataSync'),
                migrations.DeleteModel(name='FileCatchment'),
                migrations.DeleteModel(name='TypeFileCatchment'),
                migrations.DeleteModel(name='IoTDevice'),
                migrations.DeleteModel(name='MQTTConnection'),
                migrations.DeleteModel(name='MQTTMessageLog'),
                migrations.DeleteModel(name='NotificationsCatchment'),
                migrations.DeleteModel(name='ProjectCatchments'),
                migrations.DeleteModel(name='RegisterPersons'),
                migrations.DeleteModel(name='ResponseNotificationsCatchment'),
                migrations.DeleteModel(name='SystemMetrics'),
            ],
            database_operations=[]
        ),
    ]
