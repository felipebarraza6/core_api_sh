# Manual migration: align Django's project state with the actual database
# indexes created by 0066, without re-running the SQL.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0066_fix_ticket_related_names_and_indexes"),
    ]

    operations = [
        # Tell Django's state that the legacy point_catchment index is gone.
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="DROP INDEX IF EXISTS core_suppor_point_c_6f251b_idx;",
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.RemoveIndex(
                    model_name="supportticket",
                    name="core_suppor_point_c_6f251b_idx",
                ),
            ],
        ),
        # Tell Django's state that the old single-field category index is gone
        # and the composite category+status+is_active index exists.
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="DROP INDEX IF EXISTS core_suppor_categor_db22f1_idx;",
                    reverse_sql=migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    sql=(
                        "CREATE INDEX IF NOT EXISTS core_suppor_categor_093f61_idx "
                        "ON core_supportticket (category_id, status, is_active);"
                    ),
                    reverse_sql="DROP INDEX IF EXISTS core_suppor_categor_093f61_idx;",
                ),
            ],
            state_operations=[
                migrations.RemoveIndex(
                    model_name="supportticket",
                    name="core_suppor_categor_db22f1_idx",
                ),
                migrations.AddIndex(
                    model_name="supportticket",
                    index=models.Index(
                        fields=["category", "status", "is_active"],
                        name="core_suppor_categor_093f61_idx",
                    ),
                ),
            ],
        ),
    ]
