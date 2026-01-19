import django.db.models.deletion
from django.db import migrations, models

class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ('telemetry', '0001_initial'),
    ]
    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='DocumentType',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created', models.DateTimeField(auto_now_add=True, help_text='Fecha de creacion.', verbose_name='created at')),
                        ('modified', models.DateTimeField(auto_now=True, help_text='Fecha de modificacion.', verbose_name='modified at')),
                        ('name', models.CharField(max_length=300, verbose_name='Nombre')),
                        ('internal', models.BooleanField(default=False, verbose_name='Interno')),
                    ],
                    options={
                        'verbose_name': 'Tipo de archivo',
                        'verbose_name_plural': 'Tipos de archivos',
                        'db_table': 'core_typefilecatchment',
                    },
                ),
                migrations.CreateModel(
                    name='Document',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created', models.DateTimeField(auto_now_add=True, help_text='Fecha de creacion.', verbose_name='created at')),
                        ('modified', models.DateTimeField(auto_now=True, help_text='Fecha de modificacion.', verbose_name='modified at')),
                        ('name', models.CharField(max_length=300, verbose_name='Nombre')),
                        ('file', models.FileField(upload_to='files_catchment', verbose_name='Archivo')),
                        ('description', models.CharField(blank=True, max_length=300, null=True, verbose_name='Descripción')),
                        ('is_active', models.BooleanField(default=True, verbose_name='Activo')),
                        ('point_catchment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='telemetry.catchmentpoint', verbose_name='Punto de captacion')),
                        ('document_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='documents.documenttype', verbose_name='Tipo de archivo')),
                    ],
                    options={
                        'verbose_name': 'Archivo',
                        'verbose_name_plural': 'Archivos',
                        'db_table': 'core_filecatchment',
                    },
                ),
            ],
            database_operations=[]
        )
    ]
