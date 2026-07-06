from django.db import migrations


def _migrate_project_data(apps, schema_editor):
    """Crea Client/Project a partir de los campos texto legacy y los asigna."""
    Point = apps.get_model("void", "Point")
    Client = apps.get_model("void", "Client")
    Project = apps.get_model("void", "Project")

    for point in Point.objects.all():
        client_name = (point.client or "").strip()
        project_name = (point.project or "").strip()

        client = point.client_fk
        if client is None and client_name:
            client, _ = Client.objects.get_or_create(
                name=client_name,
                defaults={
                    "status": "active",
                    "tax_id": "",
                    "contact_email": "",
                },
            )
            point.client_fk = client

        if client is not None and project_name:
            project, _ = Project.objects.get_or_create(
                name=project_name,
                client=client,
                defaults={
                    "code_internal": project_name,
                    "is_active": True,
                },
            )
            point.project_fk = project

        if client is not None or project_name:
            point.save(update_fields=["client_fk", "project_fk"])


class Migration(migrations.Migration):

    dependencies = [
        ("void", "0024_add_project_and_point_project_fk"),
    ]

    operations = [
        migrations.RunPython(_migrate_project_data, migrations.RunPython.noop),
    ]
