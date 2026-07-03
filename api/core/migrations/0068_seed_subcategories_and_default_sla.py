# Manual migration: seed obvious subcategories per ticket type and global
# fallback SLA configs so every ticket gets deadlines calculated.

from django.db import migrations


def seed_subcategories_and_sla(apps, schema_editor):
    TicketCategory = apps.get_model("core", "TicketCategory")
    SLAConfig = apps.get_model("core", "SLAConfig")

    # Map each parent category (type, name) to a list of subcategory names.
    subcategories = {
        ("SOFTWARE", "Software"): [
            "Bug / Error",
            "Mejora",
            "Soporte",
            "Integración",
        ],
        ("HARDWARE", "Hardware"): [
            "Sensor",
            "PLC / Logger",
            "Comunicaciones",
            "Energía",
        ],
        ("HARDWARE", "Conectividad"): [
            "Sin señal",
            "Intermitencia",
            "Reconexión",
        ],
        ("HARDWARE", "Telemetría"): [
            "Datos erróneos",
            "Salto de pulsos",
            "Reset de contador",
        ],
        ("COMPLIANCE", "Cumplimiento DGA"): [
            "Envío de datos",
            "Retraso",
            "Error DGA",
            "Exceso de caudal",
        ],
        ("WORK_ORDER", "Orden de Trabajo"): [
            "Mantenimiento preventivo",
            "Mantenimiento correctivo",
            "Instalación",
            "Visita técnica",
        ],
    }

    for (cat_type, parent_name), sub_names in subcategories.items():
        try:
            parent = TicketCategory.objects.get(
                category_type=cat_type, name=parent_name, parent=None
            )
        except TicketCategory.DoesNotExist:
            continue
        for sub_name in sub_names:
            TicketCategory.objects.get_or_create(
                category_type=cat_type,
                name=sub_name,
                parent=parent,
                defaults={"is_active": True},
            )

    # Global fallback SLAs by priority so every ticket gets a deadline.
    global_sla = [
        ("CRITICA", 1, 4),
        ("ALTA", 4, 24),
        ("MEDIA", 8, 48),
        ("BAJA", 24, 120),
    ]
    for priority, response_hours, resolution_hours in global_sla:
        SLAConfig.objects.get_or_create(
            client=None,
            project=None,
            category=None,
            priority=priority,
            defaults={
                "response_time_hours": response_hours,
                "resolution_time_hours": resolution_hours,
                "business_hours_only": False,
                "is_active": True,
            },
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0067_align_supportticket_indexes_state"),
    ]

    operations = [
        migrations.RunPython(seed_subcategories_and_sla, noop),
    ]
