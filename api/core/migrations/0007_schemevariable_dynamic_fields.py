# Generated manually - Add dynamic processing fields to SchemeVariable

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_alter_profiledataconfigcatchment_extra_config"),
    ]

    operations = [
        # Add operation field
        migrations.AddField(
            model_name="schemevariable",
            name="operation",
            field=models.CharField(
                choices=[
                    ("PHYSICAL", "Dato Físico (Sensor)"),
                    ("SUM", "Suma"),
                    ("DIFF", "Resta (A - B)"),
                    ("MUL", "Multiplicación"),
                    ("AVG", "Promedio"),
                    ("FORMULA", "Fórmula Personalizada"),
                ],
                default="PHYSICAL",
                max_length=20,
                verbose_name="Tipo de Operación",
            ),
        ),
        # Add formula field
        migrations.AddField(
            model_name="schemevariable",
            name="formula",
            field=models.CharField(
                blank=True,
                help_text="Ej: ({var1} + {var2}) * 0.5. Use los internal_codes entre llaves.",
                max_length=500,
                null=True,
                verbose_name="Fórmula",
            ),
        ),
        # Add sources field
        migrations.AddField(
            model_name="schemevariable",
            name="sources",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Lista de internal_codes de origen para operaciones",
                verbose_name="Variables de Origen",
            ),
        ),
        # Add priority field
        migrations.AddField(
            model_name="schemevariable",
            name="priority",
            field=models.IntegerField(
                default=0,
                help_text="Menor valor se calcula antes.",
                verbose_name="Prioridad de Cálculo",
            ),
        ),
        # Add is_virtual field
        migrations.AddField(
            model_name="schemevariable",
            name="is_virtual",
            field=models.BooleanField(
                default=False,
                help_text="Indica si la variable es calculada internamente.",
                verbose_name="Es Virtual",
            ),
        ),
        # Add min_value field
        migrations.AddField(
            model_name="schemevariable",
            name="min_value",
            field=models.FloatField(
                blank=True,
                help_text="Si el dato es menor a este valor, se ignorará.",
                null=True,
                verbose_name="Valor Mínimo",
            ),
        ),
        # Add max_value field
        migrations.AddField(
            model_name="schemevariable",
            name="max_value",
            field=models.FloatField(
                blank=True,
                help_text="Si el dato es mayor a este valor, se ignorará.",
                null=True,
                verbose_name="Valor Máximo",
            ),
        ),
    ]
