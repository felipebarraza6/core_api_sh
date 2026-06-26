# Generated manually for performance optimization
# Date: 2025-01-XX

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_catchmentpoint_lat_catchmentpoint_lon'),
    ]

    operations = [
        # Índice para date_time_medition (usado frecuentemente en filtros y ordenamiento)
        migrations.AddIndex(
            model_name='interactiondetail',
            index=models.Index(
                fields=['date_time_medition'],
                name='core_interactiondetail_date_time_medition_idx'
            ),
        ),
        # Índice compuesto para catchment_point + date_time_medition (query muy común)
        migrations.AddIndex(
            model_name='interactiondetail',
            index=models.Index(
                fields=['catchment_point', 'date_time_medition'],
                name='core_interactiondetail_point_date_idx'
            ),
        ),
        # Índice compuesto para send_dga + created (usado en cron_dga.py)
        migrations.AddIndex(
            model_name='interactiondetail',
            index=models.Index(
                fields=['send_dga', 'created'],
                name='core_interactiondetail_send_dga_created_idx'
            ),
        ),
        # Índice para date_time_last_logger (usado en cálculos de caudal promedio)
        migrations.AddIndex(
            model_name='interactiondetail',
            index=models.Index(
                fields=['date_time_last_logger'],
                name='core_interactiondetail_date_time_last_logger_idx'
            ),
        ),
    ]

