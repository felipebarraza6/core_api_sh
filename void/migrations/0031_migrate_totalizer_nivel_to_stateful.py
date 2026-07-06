# Generated manually: convierte processing_type totalizer/nivel a stateful.

from django.db import migrations


def forward(apps, schema_editor):
    DeviceVariableConfig = apps.get_model("void", "DeviceVariableConfig")
    ProcessingSchema = apps.get_model("void", "ProcessingSchema")

    totalizer_schema, _ = ProcessingSchema.objects.get_or_create(
        name="Totalizador stateful v1",
        is_template=True,
        defaults={
            "version": "1.5",
            "description": "Totalizador monotónico con detección de resets, reconexiones y caudal derivado.",
            "is_active": True,
        },
    )
    nivel_schema, _ = ProcessingSchema.objects.get_or_create(
        name="Nivel stateful v1",
        is_template=True,
        defaults={
            "version": "1.1",
            "description": "Nivel con corrección de lecturas negativas usando histórico y cálculo de nivel freático.",
            "is_active": True,
        },
    )

    DeviceVariableConfig.objects.filter(processing_type="totalizer").update(
        processing_type="stateful",
        custom_schema=totalizer_schema,
    )
    DeviceVariableConfig.objects.filter(processing_type="nivel").update(
        processing_type="stateful",
        custom_schema=nivel_schema,
    )


def backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("void", "0030_alter_devicevariableconfig_processing_type_and_more"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
