# Generated manually 2026-05-19

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0056_alter_counterresetlog_reset_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="alertrule",
            name="legacy_notification_id",
            field=models.IntegerField(
                blank=True,
                db_index=True,
                null=True,
                unique=True,
                verbose_name="ID de notificación legacy vinculada",
                help_text="Si esta regla fue creada desde una NotificationsCatchment legacy, "
                          "guarda el ID original para poder sincronizar endpoints legacy.",
            ),
        ),
    ]
