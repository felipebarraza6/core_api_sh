from django.db import migrations, models
import django.db.models.deletion


def _create_default_standards(apps, schema_editor):
    """Crea estándares de cumplimiento por defecto."""
    ComplianceStandard = apps.get_model("void", "ComplianceStandard")
    defaults = [
        {
            "code": "MAYOR",
            "name": "Mayor (horario)",
            "frequency_minutes": 60,
            "send_minute": 0,
            "send_hour": None,
            "send_day": None,
            "send_month": None,
        },
        {
            "code": "MEDIO",
            "name": "Medio (diario)",
            "frequency_minutes": 1440,
            "send_minute": 0,
            "send_hour": 0,
            "send_day": None,
            "send_month": None,
        },
        {
            "code": "MENOR",
            "name": "Menor (mensual)",
            "frequency_minutes": 43200,
            "send_minute": 0,
            "send_hour": 0,
            "send_day": 1,
            "send_month": None,
        },
        {
            "code": "CAUDALES_MUY_PEQUENOS",
            "name": "Caudales muy pequeños (semestral)",
            "frequency_minutes": 129600,
            "send_minute": 0,
            "send_hour": 0,
            "send_day": 1,
            "send_month": 1,
        },
        {
            "code": "SIN_ESTANDAR",
            "name": "Sin estándar (enviar siempre)",
            "frequency_minutes": 60,
            "send_minute": None,
            "send_hour": None,
            "send_day": None,
            "send_month": None,
        },
    ]
    for item in defaults:
        ComplianceStandard.objects.get_or_create(code=item["code"], defaults=item)


def _migrate_standard_to_fk(apps, schema_editor):
    """Migra el valor legacy de standard al FK de ComplianceStandard."""
    ComplianceStandard = apps.get_model("void", "ComplianceStandard")
    PointComplianceProfile = apps.get_model("void", "PointComplianceProfile")

    for profile in PointComplianceProfile.objects.all():
        legacy = (profile.standard_legacy or "").strip().upper()
        if not legacy:
            legacy = "SIN_ESTANDAR"
        try:
            standard_id = ComplianceStandard.objects.values_list("id", flat=True).get(code=legacy)
        except ComplianceStandard.DoesNotExist:
            standard_id = ComplianceStandard.objects.values_list("id", flat=True).get(code="SIN_ESTANDAR")
        # Durante la migración el campo aún es CharField; guardamos el ID como string.
        profile.standard = str(standard_id)
        profile.save(update_fields=["standard"])


class Migration(migrations.Migration):

    dependencies = [
        ("void", "0021_add_devicevariableconfig_extra_data"),
    ]

    operations = [
        migrations.CreateModel(
            name="ComplianceStandard",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True, help_text="Fecha de creación.", verbose_name="creado el")),
                ("modified", models.DateTimeField(auto_now=True, help_text="Fecha de última modificación.", verbose_name="modificado el")),
                ("code", models.CharField(db_index=True, help_text="Ej: MAYOR, MEDIO, MENOR, SIN_ESTANDAR, CUSTOM.", max_length=50, unique=True, verbose_name="Código")),
                ("name", models.CharField(max_length=200, verbose_name="Nombre")),
                ("description", models.TextField(blank=True, default="", verbose_name="Descripción")),
                ("frequency_minutes", models.PositiveIntegerField(default=60, help_text="Frecuencia teórica de envío. Se usa solo para referencia/SLA.", verbose_name="Frecuencia base (minutos)")),
                ("send_minute", models.IntegerField(blank=True, help_text="Ej: 0 para enviar en punto. Null = cualquier minuto.", null=True, verbose_name="Minuto de envío")),
                ("send_hour", models.IntegerField(blank=True, help_text="Ej: 0 para medianoche. Null = cualquier hora.", null=True, verbose_name="Hora de envío")),
                ("send_day", models.IntegerField(blank=True, help_text="Ej: 1 para primer día del mes. Null = cualquier día.", null=True, verbose_name="Día de envío")),
                ("send_month", models.IntegerField(blank=True, help_text="Ej: 1 o 7 para semestral. Null = cualquier mes.", null=True, verbose_name="Mes de envío")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="Activo")),
            ],
            options={
                "verbose_name": "Estándar de cumplimiento",
                "verbose_name_plural": "Estándares de cumplimiento",
                "ordering": ["code"],
            },
        ),
        migrations.AddField(
            model_name="pointcomplianceprofile",
            name="standard_legacy",
            field=models.CharField(blank=True, default="", help_text="Código legacy conservado para trazabilidad. Ej: MAYOR, MEDIO, MENOR.", max_length=100, verbose_name="Estándar (legacy)"),
        ),
        migrations.RunPython(_create_default_standards, migrations.RunPython.noop),
        migrations.RunPython(_migrate_standard_to_fk, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="pointcomplianceprofile",
            name="standard",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="profiles", to="void.compliancestandard", verbose_name="Estándar"),
        ),
    ]
