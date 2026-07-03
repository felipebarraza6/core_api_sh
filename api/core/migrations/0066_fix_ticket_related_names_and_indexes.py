# Manual migration: fix related_names for TicketCategory FKs and ensure
# SupportTicket composite indexes exist without failing on missing legacy indexes.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0065_ticketcategory_and_more"),
    ]

    operations = [
        # Drop the legacy point_catchment index if it still exists (test DB only).
        migrations.RunSQL(
            sql="DROP INDEX IF EXISTS core_suppor_point_c_6f251b_idx;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Drop the old single-field category index if it still exists (test DB only).
        migrations.RunSQL(
            sql="DROP INDEX IF EXISTS core_suppor_categor_db22f1_idx;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Create the composite index on category+status+is_active if missing.
        migrations.RunSQL(
            sql=(
                "CREATE INDEX IF NOT EXISTS core_suppor_categor_093f61_idx "
                "ON core_supportticket (category_id, status, is_active);"
            ),
            reverse_sql="DROP INDEX IF EXISTS core_suppor_categor_093f61_idx;",
        ),
        # Align related_names with the current model definitions.
        migrations.AlterField(
            model_name="slaconfig",
            name="category",
            field=models.ForeignKey(
                blank=True,
                help_text="Si se deja vacío, aplica a todas las categorías.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="sla_configs",
                to="core.ticketcategory",
                verbose_name="Categoría",
            ),
        ),
        migrations.AlterField(
            model_name="supportticket",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="tickets",
                to="core.ticketcategory",
                verbose_name="Categoría",
            ),
        ),
    ]
