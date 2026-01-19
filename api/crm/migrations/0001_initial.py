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
                    name='Client',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created', models.DateTimeField(auto_now_add=True, help_text='Fecha de creacion.', verbose_name='created at')),
                        ('modified', models.DateTimeField(auto_now=True, help_text='Fecha de modificacion.', verbose_name='modified at')),
                        ('name', models.CharField(max_length=300, verbose_name='Nombre')),
                        ('rut', models.CharField(max_length=300, verbose_name='Rut')),
                        ('address', models.CharField(max_length=300, verbose_name='Direccion')),
                        ('phone', models.CharField(max_length=300, verbose_name='Telefono')),
                        ('email', models.CharField(max_length=300, verbose_name='Correo')),
                    ],
                    options={
                        'verbose_name': 'Cliente',
                        'verbose_name_plural': 'Clientes',
                        'db_table': 'core_client',
                    },
                ),
                migrations.CreateModel(
                    name='Person',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created', models.DateTimeField(auto_now_add=True, help_text='Fecha de creacion.', verbose_name='created at')),
                        ('modified', models.DateTimeField(auto_now=True, help_text='Fecha de modificacion.', verbose_name='modified at')),
                        ('name', models.CharField(blank=True, max_length=300, null=True)),
                        ('email', models.CharField(blank=True, max_length=300, null=True)),
                        ('phone', models.CharField(blank=True, max_length=300, null=True)),
                    ],
                    options={
                        'verbose_name': 'Persona registrada',
                        'verbose_name_plural': 'Personas registradas',
                        'db_table': 'core_registerpersons',
                    },
                ),
                migrations.CreateModel(
                    name='Project',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created', models.DateTimeField(auto_now_add=True, help_text='Fecha de creacion.', verbose_name='created at')),
                        ('modified', models.DateTimeField(auto_now=True, help_text='Fecha de modificacion.', verbose_name='modified at')),
                        ('name', models.CharField(max_length=300, verbose_name='Nombre')),
                        ('code_internal', models.CharField(blank=True, max_length=300, null=True, verbose_name='Codigo interno')),
                        ('client', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='crm.client', verbose_name='Cliente')),
                    ],
                    options={
                        'verbose_name': 'Proyecto',
                        'verbose_name_plural': 'Proyectos',
                        'db_table': 'core_projectcatchments',
                    },
                ),
            ],
            database_operations=[]  # Don't create tables, they already exist
        )
    ]
